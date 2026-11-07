"""MCP server: lets an AI agent read and check e-Fatura and e-Defter files.

Read-only by construction: the tools only read files, and only inside the ``--root`` folder given at start-up
(paths are resolved, so ``..`` and symlinks cannot leave it). Nothing is written and nothing is sent anywhere;
results go back to the agent that asked.

Start it with ``ebelge mcp --root /path/to/folder`` (needs ``pip install 'eqlx-ebelge[mcp]'``).
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import __version__
from .ledger import trial_balance as _trial_balance
from .report import scan

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
MAX_INVOICES = 200


class OutsideRootError(ValueError):
    pass


def _resolve(root: Path, path: str) -> Path:
    p = (root / path).resolve()
    if p != root and root not in p.parents:
        raise OutsideRootError(f"{path!r} is outside the allowed folder")
    if not p.exists():
        raise FileNotFoundError(path)
    return p


def _files(root: Path, path: str) -> list[Path]:
    """Files under ``path`` that resolve inside ``root`` (symlinks pointing out are skipped)."""
    p = _resolve(root, path)
    if p.is_file():
        return [p]
    out = []
    for f in sorted(p.rglob("*")):
        if f.suffix.lower() not in (".xml", ".zip") or not f.is_file():
            continue
        real = f.resolve()
        if root in real.parents:
            out.append(real)
    return out


def _rel(root: Path, name: str) -> str:
    path, sep, member = name.partition("!")
    with contextlib.suppress(ValueError):
        path = str(Path(path).relative_to(root))
    return path + sep + member


def build_server(root: Path) -> MCPServer:
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    server = MCPServer(
        "eqlx-ebelge",
        version=__version__,
        instructions=(
            "Reads Turkish e-Fatura (UBL-TR) and e-Defter (XBRL GL) files in one local folder. "
            "Paths are relative to that folder. Use `check` first; it reports errors such as totals that "
            "do not add up, invalid VKN/TCKN, duplicate invoices and unbalanced journal entries."
        ),
    )

    @server.tool(annotations=READ_ONLY)
    def list_documents(path: str = ".") -> list[dict[str, str]]:
        """List the e-Fatura, e-Defter and other XML documents under a path (folders and ZIPs included)."""
        rep = scan(_files(root, path))
        return [{**d, "name": _rel(root, d["name"])} for d in rep.documents]

    @server.tool(annotations=READ_ONLY)
    def check(path: str = ".", include_info: bool = False) -> dict[str, Any]:
        """Run every check on the documents under a path: invoice arithmetic and identifiers, duplicate
        invoices across all files, and journal entry balance, counters and dates."""
        rep = scan(_files(root, path))
        findings = [
            {**f.to_dict(), "source": _rel(root, f.source)}
            for f in rep.findings
            if include_info or f.severity != "info"
        ]
        return {"summary": rep.summary(), "findings": findings}

    @server.tool(annotations=READ_ONLY)
    def read_invoices(path: str) -> dict[str, Any]:
        """Return the invoices under a path as structured data (parties, lines, taxes, totals)."""
        rep = scan(_files(root, path))
        items = rep.invoices[:MAX_INVOICES]
        return {
            "invoices": [{**inv.to_dict(), "source": _rel(root, inv.source)} for inv in items],
            "truncated": len(rep.invoices) > MAX_INVOICES,
        }

    @server.tool(annotations=READ_ONLY)
    def trial_balance(path: str = ".", level: Literal["main", "sub"] = "main") -> dict[str, Any]:
        """Trial balance (mizan) from the e-Defter journal files under a path, by main or sub-account."""
        rep = scan(_files(root, path))
        rows = _trial_balance(rep.ledgers, level=level)
        return {
            "files": [_rel(root, lg.source) for lg in rep.ledgers],
            "rows": [r.to_dict() for r in rows],
        }

    return server


def serve(root: Path) -> None:
    build_server(root).run("stdio")
