"""Command line: ``ebelge check | invoices | mizan | sample | mcp``."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import __version__
from .ledger import trial_balance
from .report import scan
from .synthetic import demo_files

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _print_json(obj: Any) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _table(rows: list[list[str]], header: list[str]) -> None:
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    for r in [header, ["-" * w for w in widths], *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)).rstrip())


def _cmd_check(args: argparse.Namespace) -> int:
    rep = scan(args.paths)
    findings = sorted(rep.findings, key=lambda f: (_SEVERITY_ORDER[f.severity], f.source, f.code))
    if not args.all:
        findings = [f for f in findings if f.severity != "info"]
    if args.json:
        _print_json({"summary": rep.summary(), "findings": [f.to_dict() for f in findings]})
    else:
        s = rep.summary()
        c = s["findings"]
        print(
            f"{s['documents']} documents: {s['invoices']} invoices, {s['ledgers']} ledger files "
            f"({s['ledger_entries']} entries). {c['error']} errors, {c['warning']} warnings, "
            f"{c['info']} info."
        )
        if findings:
            print()
            _table(
                [
                    [f.severity, f.code, f.source.replace("\\", "/").rsplit("/", 1)[-1], f.message]
                    for f in findings
                ],
                ["severity", "code", "file", "message"],
            )
    return 1 if rep.counts["error"] else 0


def _cmd_invoices(args: argparse.Namespace) -> int:
    rep = scan(args.paths)
    if args.json:
        _print_json([inv.to_dict() for inv in rep.invoices])
        return 0
    rows = [
        [
            inv.number or "",
            str(inv.issue_date or ""),
            inv.type_code or "",
            inv.supplier.tax_id or "",
            inv.customer.tax_id or "",
            str(inv.totals.line_extension or ""),
            str(inv.tax_total or ""),
            str(inv.totals.payable or ""),
            inv.currency or "",
        ]
        for inv in sorted(rep.invoices, key=lambda i: (i.issue_date or "", i.number or ""))
    ]
    header = ["number", "date", "type", "supplier", "customer", "net", "tax", "payable", "cur"]
    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(header)
        w.writerows(rows)
    else:
        _table(rows, header)
    return 0


def _cmd_mizan(args: argparse.Namespace) -> int:
    rep = scan(args.paths)
    unreadable = [f for f in rep.findings if f.code == "unreadable"]
    for f in unreadable:
        print(f"skipped {f.source}: {f.message}", file=sys.stderr)
    if not rep.ledgers:
        print("no e-Defter files found", file=sys.stderr)
        return 1
    rows = trial_balance(rep.ledgers, level=args.level)
    if args.json:
        _print_json([r.to_dict() for r in rows])
        return 0
    out = [
        [
            r.account,
            r.name or "",
            str(r.debit),
            str(r.credit),
            str(r.debit_balance),
            str(r.credit_balance),
        ]
        for r in rows
    ]
    total = [
        sum((getattr(r, k) for r in rows), Decimal(0))
        for k in ("debit", "credit", "debit_balance", "credit_balance")
    ]
    header = ["account", "name", "debit", "credit", "debit_bal", "credit_bal"]
    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(header)
        w.writerows(out)
    else:
        _table([*out, ["TOTAL", "", *map(str, total)]], header)
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in demo_files().items():
        (target / name).write_bytes(data)
    print(f"wrote {len(demo_files())} synthetic files to {target}")
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    try:
        from .mcp_server import serve
    except ImportError:
        print("the MCP server needs the extra: pip install 'eqlx-ebelge[mcp]'", file=sys.stderr)
        return 2
    serve(Path(args.root))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ebelge",
        description="Read Turkish e-Fatura and e-Defter files. Everything runs locally.",
    )
    p.add_argument("--version", action="version", version=f"eqlx-ebelge {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="run every check on files, folders or ZIP archives")
    c.add_argument("paths", nargs="+")
    c.add_argument("--json", action="store_true")
    c.add_argument("--all", action="store_true", help="include info findings")
    c.set_defaults(func=_cmd_check)

    i = sub.add_parser("invoices", help="list the invoices found")
    i.add_argument("paths", nargs="+")
    g = i.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true")
    g.add_argument("--csv", action="store_true")
    i.set_defaults(func=_cmd_invoices)

    m = sub.add_parser("mizan", help="trial balance from e-Defter journal files")
    m.add_argument("paths", nargs="+")
    m.add_argument("--level", choices=["main", "sub"], default="main")
    g = m.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true")
    g.add_argument("--csv", action="store_true")
    m.set_defaults(func=_cmd_mizan)

    s = sub.add_parser("sample", help="write synthetic demo files to a folder")
    s.add_argument("dir")
    s.set_defaults(func=_cmd_sample)

    v = sub.add_parser("mcp", help="start the MCP server (stdio), read-only inside --root")
    v.add_argument("--root", required=True, help="the only folder the server may read")
    v.set_defaults(func=_cmd_mcp)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
