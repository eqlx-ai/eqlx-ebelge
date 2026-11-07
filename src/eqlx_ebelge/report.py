"""One call that reads a set of files and runs every check: what the command line and the MCP server use."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import EbelgeError, Finding
from .invoice import Invoice, check_invoice, find_duplicates, read_invoices
from .ledger import Ledger, check_ledger, read_ledger
from .sources import Limits, iter_documents


@dataclass
class Report:
    documents: list[dict[str, str]] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    ledgers: list[Ledger] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        c = {"error": 0, "warning": 0, "info": 0}
        for f in self.findings:
            c[f.severity] += 1
        return c

    def summary(self) -> dict[str, Any]:
        return {
            "documents": len(self.documents),
            "invoices": len(self.invoices),
            "ledgers": len(self.ledgers),
            "ledger_entries": sum(len(lg.entries) for lg in self.ledgers),
            "findings": self.counts,
        }


def scan(paths: Iterable[str | Path], limits: Limits | None = None) -> Report:
    """Read every document under ``paths``, run the per-document checks, then the duplicate check across
    all invoices. Documents that cannot be read become ``unreadable`` error findings."""
    rep = Report()
    for doc in iter_documents(paths, limits):
        rep.documents.append({"name": doc.name, "kind": doc.kind, "root": doc.root})
        try:
            if doc.kind == "invoice":
                for inv in read_invoices(doc.data, doc.name):
                    rep.invoices.append(inv)
                    rep.findings.extend(check_invoice(inv))
            elif doc.kind == "ledger":
                lg = read_ledger(doc.data, doc.name)
                rep.ledgers.append(lg)
                rep.findings.extend(check_ledger(lg))
            elif doc.kind == "unreadable":
                rep.findings.append(Finding("unreadable", "error", doc.root, doc.name))
            else:
                msg = f"not an e-Fatura or e-Defter document (root element {doc.root})"
                rep.findings.append(Finding("unsupported", "info", msg, doc.name))
        except EbelgeError as exc:
            reason = exc.code + (f": {exc.detail}" if exc.detail else "")
            rep.findings.append(Finding("unreadable", "error", reason, doc.name))
    rep.findings.extend(find_duplicates(rep.invoices))
    return rep
