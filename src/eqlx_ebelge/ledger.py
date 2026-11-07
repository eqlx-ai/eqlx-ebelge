"""e-Defter files in GİB's XBRL GL format: journal (yevmiye) and general ledger (kebir).

The file is read entry by entry (``gl-cor:entryHeader``) and each processed entry is cleared, so memory grows
with the number of journal lines kept, not with the XML size. Only what bookkeeping checks and a trial balance
need is kept: account codes and the main account name, amount, debit or credit, dates, and the voucher number.
Entry comments, document numbers and people's names are not read.
"""

from __future__ import annotations

import io
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import IO, Any, Literal

from ._xml import iterparse, parse_date, parse_decimal, text
from .errors import EbelgeError, Finding
from .ids import is_valid_tax_id
from .invoice import _jsonable

EDEFTER = "{http://www.edefter.gov.tr}"
XBRLI = "{http://www.xbrl.org/2003/instance}"
COR = "{http://www.xbrl.org/int/gl/cor/2006-10-25}"
BUS = "{http://www.xbrl.org/int/gl/bus/2006-10-25}"

Side = Literal["D", "C"]
_SIDES: dict[str, Side] = {"D": "D", "debit": "D", "C": "C", "credit": "C"}


@dataclass(frozen=True)
class LedgerLine:
    account: str  # accountMainID, e.g. "100"
    sub_account: str | None  # accountSubID, e.g. "100.01"
    account_name: str | None  # accountMainDescription, e.g. "KASA"
    amount: Decimal
    side: Side
    posting_date: date | None


@dataclass(frozen=True)
class Entry:
    counter: int | None  # entryNumberCounter: 1, 2, 3 ... through the fiscal year
    number: str | None  # entryNumber, the voucher number as the books print it
    entered: date | None
    total_debit: Decimal | None
    total_credit: Decimal | None
    lines: tuple[LedgerLine, ...]

    @property
    def debit(self) -> Decimal:
        return sum((ln.amount for ln in self.lines if ln.side == "D"), Decimal(0))

    @property
    def credit(self) -> Decimal:
        return sum((ln.amount for ln in self.lines if ln.side == "C"), Decimal(0))


@dataclass(frozen=True)
class LedgerHeader:
    tax_id: str | None
    title: str | None
    entries_type: str | None  # "journal" (yevmiye) or "ledger" (kebir)
    fiscal_start: date | None
    fiscal_end: date | None
    period_start: date | None
    period_end: date | None


@dataclass(frozen=True)
class Ledger:
    source: str
    header: LedgerHeader
    entries: tuple[Entry, ...]

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = _jsonable(self)
        return out


class _LedgerReader:
    def __init__(self, source: str, max_lines: int) -> None:
        self.source = source
        self.max_lines = max_lines
        self.units: dict[str, bool] = {}
        self.head: dict[str, Any] = {}
        self.lines_read = 0

    def amount(self, el: Any, where: str) -> Decimal:
        if el is None:
            raise EbelgeError("bad_amount", self.source, f"{where} missing")
        unit = el.get("unitRef")
        if unit not in self.units:
            raise EbelgeError("unit_unknown", self.source, f"{where} unitRef {unit!r}")
        if not self.units[unit]:
            raise EbelgeError("foreign_currency", self.source, f"{where} is not in TRY")
        value = parse_decimal(text(el), self.source, where)
        if value is None:
            raise EbelgeError("bad_amount", self.source, f"{where} empty")
        return value

    def line(self, d: Any) -> LedgerLine:
        account = d.find(f"{COR}account")
        main = text(account.find(f"{COR}accountMainID")) if account is not None else None
        if account is None or main is None:
            raise EbelgeError("bad_account", self.source, "entryDetail without accountMainID")
        side = _SIDES.get(text(d.find(f"{COR}debitCreditCode")) or "")
        if side is None:
            raise EbelgeError("bad_side", self.source, "debitCreditCode must be D or C")
        return LedgerLine(
            account=main,
            sub_account=text(account.find(f"{COR}accountSub/{COR}accountSubID")),
            account_name=text(account.find(f"{COR}accountMainDescription")),
            amount=self.amount(d.find(f"{COR}amount"), "amount"),
            side=side,
            posting_date=parse_date(text(d.find(f"{COR}postingDate")), self.source, "postingDate"),
        )

    def entry(self, h: Any) -> Entry:
        lines = tuple(self.line(d) for d in h.iterfind(f"{COR}entryDetail"))
        self.lines_read += len(lines)
        if self.lines_read > self.max_lines:
            raise EbelgeError("too_many_lines", self.source, f"more than {self.max_lines} lines")
        counter = text(h.find(f"{COR}entryNumberCounter"))
        if counter is not None and not counter.isdigit():
            raise EbelgeError("bad_counter", self.source, counter)
        td, tc = h.find(f"{BUS}totalDebit"), h.find(f"{BUS}totalCredit")
        return Entry(
            counter=int(counter) if counter is not None else None,
            number=text(h.find(f"{COR}entryNumber")),
            entered=parse_date(text(h.find(f"{COR}enteredDate")), self.source, "enteredDate"),
            total_debit=self.amount(td, "totalDebit") if td is not None else None,
            total_credit=self.amount(tc, "totalCredit") if tc is not None else None,
            lines=lines,
        )

    def header_field(self, el: Any) -> None:
        tag = el.tag
        if tag == f"{XBRLI}identifier":
            self.head.setdefault("tax_id", text(el))
        elif tag == f"{XBRLI}unit" and el.get("id"):
            measures = [text(m) or "" for m in el.findall(f"{XBRLI}measure")]
            self.units[el.get("id")] = len(measures) == 1 and measures[0].rsplit(":", 1)[-1] == "TRY"
        elif tag == f"{BUS}organizationIdentifier":
            self.head.setdefault("title", text(el))
        elif tag == f"{COR}entriesType":
            self.head.setdefault("entries_type", text(el))
        else:
            key = {
                f"{BUS}fiscalYearStart": "fiscal_start",
                f"{BUS}fiscalYearEnd": "fiscal_end",
                f"{COR}periodCoveredStart": "period_start",
                f"{COR}periodCoveredEnd": "period_end",
            }.get(tag)
            if key:
                self.head.setdefault(key, parse_date(text(el), self.source, key))

    def read(self, stream: IO[bytes]) -> Ledger:
        entries: list[Entry] = []
        depth = 0
        in_entry = 0
        for event, el in iterparse(stream, self.source):
            if event == "start":
                if depth == 0 and el.tag != f"{EDEFTER}defter":
                    raise EbelgeError("not_a_ledger", self.source, el.tag.rsplit("}", 1)[-1])
                depth += 1
                if el.tag == f"{COR}entryHeader":
                    in_entry += 1
                continue
            depth -= 1
            if el.tag == f"{COR}entryHeader":
                in_entry -= 1
                kind = self.head.get("entries_type")
                if kind not in (None, "journal", "ledger"):
                    raise EbelgeError("unsupported_ledger_type", self.source, f"entriesType {kind!r}")
                entries.append(self.entry(el))
                el.clear()
            elif not in_entry:
                self.header_field(el)
        header = LedgerHeader(
            tax_id=self.head.get("tax_id"),
            title=self.head.get("title"),
            entries_type=self.head.get("entries_type"),
            fiscal_start=self.head.get("fiscal_start"),
            fiscal_end=self.head.get("fiscal_end"),
            period_start=self.head.get("period_start"),
            period_end=self.head.get("period_end"),
        )
        return Ledger(source=self.source, header=header, entries=tuple(entries))


def read_ledger(data: bytes | IO[bytes], source: str = "<bytes>", *, max_lines: int = 5_000_000) -> Ledger:
    """Read one e-Defter journal or ledger file (XML, not the ZIP around it)."""
    stream = io.BytesIO(data) if isinstance(data, bytes) else data
    return _LedgerReader(source, max_lines).read(stream)


def check_ledger(ledger: Ledger) -> list[Finding]:
    """Bookkeeping checks on one file: every entry balances, header totals match the lines, entry counters
    run without gaps or repeats, dates sit inside the covered period, and the file balances overall."""
    out: list[Finding] = []
    src = ledger.source
    h = ledger.header
    if h.tax_id and not is_valid_tax_id(h.tax_id):
        msg = f"taxpayer id {h.tax_id} fails its check digit"
        out.append(Finding("tax_id_check_digit", "warning", msg, src, "header.tax_id"))

    # In a general ledger (kebir) each entryHeader groups one account's postings: it does not balance on
    # its own, and its header totals may be the account's net balance rather than gross sums.
    is_kebir = h.entries_type == "ledger"
    seen: dict[int, int] = {}
    for e in ledger.entries:
        where = f"entry {e.counter if e.counter is not None else e.number}"
        if not e.lines:
            out.append(Finding("empty_entry", "warning", f"{where} has no lines", src, where))
            continue
        if not is_kebir and e.debit != e.credit:
            msg = f"{where}: debit {e.debit} != credit {e.credit}"
            out.append(Finding("entry_unbalanced", "error", msg, src, where))
        if e.total_debit is not None or e.total_credit is not None:
            gross = (e.debit, e.credit)
            net = (max(e.debit - e.credit, Decimal(0)), max(e.credit - e.debit, Decimal(0)))
            header = (e.total_debit or Decimal(0), e.total_credit or Decimal(0))
            if header != gross and not (is_kebir and header == net):
                msg = f"{where}: header totals {header[0]} / {header[1]}, lines {e.debit} / {e.credit}"
                out.append(Finding("entry_total", "error", msg, src, where))
        if e.counter is not None:
            seen[e.counter] = seen.get(e.counter, 0) + 1
        if (
            e.entered
            and h.period_start
            and h.period_end
            and not (h.period_start <= e.entered <= h.period_end)
        ):
            msg = f"{where}: dated {e.entered}, outside {h.period_start}..{h.period_end}"
            out.append(Finding("date_outside_period", "warning", msg, src, where))
        for ln in e.lines:
            if not (len(ln.account) == 3 and ln.account.isdigit()):
                msg = f"{where}: account {ln.account!r} is not a 3-digit main account"
                out.append(Finding("account_code", "info", msg, src, where))

    repeats = sorted(c for c, n in seen.items() if n > 1)
    if repeats:
        msg = f"entry counters used more than once: {_short(repeats)}"
        out.append(Finding("counter_repeat", "error", msg, src, "entries"))
    if seen:
        lo, hi = min(seen), max(seen)
        missing = sorted(set(range(lo, hi + 1)) - set(seen))
        if missing:
            msg = f"entry counters {lo}..{hi} skip {_short(missing)}"
            out.append(Finding("counter_gap", "warning", msg, src, "entries"))

    debit = sum((e.debit for e in ledger.entries), Decimal(0))
    credit = sum((e.credit for e in ledger.entries), Decimal(0))
    if debit != credit:
        msg = f"file total debit {debit} != credit {credit}"
        out.append(Finding("ledger_unbalanced", "error", msg, src, "entries"))
    return out


def _short(values: list[int], limit: int = 10) -> str:
    shown = ", ".join(map(str, values[:limit]))
    return shown + (f" and {len(values) - limit} more" if len(values) > limit else "")


@dataclass(frozen=True)
class TrialBalanceRow:
    account: str
    name: str | None
    debit: Decimal
    credit: Decimal

    @property
    def debit_balance(self) -> Decimal:
        return max(self.debit - self.credit, Decimal(0))

    @property
    def credit_balance(self) -> Decimal:
        return max(self.credit - self.debit, Decimal(0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "name": self.name,
            "debit": str(self.debit),
            "credit": str(self.credit),
            "debit_balance": str(self.debit_balance),
            "credit_balance": str(self.credit_balance),
        }


def trial_balance(
    ledgers: Ledger | Iterable[Ledger], level: Literal["main", "sub"] = "main"
) -> list[TrialBalanceRow]:
    """Trial balance (mizan) over one or more files, e.g. the twelve monthly journals of a year.

    ``level="main"`` groups by the 3-digit main account; ``"sub"`` by sub-account, falling back to the main
    account for lines without one. Rows are sorted by account code.
    """
    items = [ledgers] if isinstance(ledgers, Ledger) else list(ledgers)
    debit: dict[str, Decimal] = defaultdict(Decimal)
    credit: dict[str, Decimal] = defaultdict(Decimal)
    names: dict[str, str] = {}
    for ledger in items:
        for e in ledger.entries:
            for ln in e.lines:
                key = (ln.sub_account or ln.account) if level == "sub" else ln.account
                if ln.side == "D":
                    debit[key] += ln.amount
                else:
                    credit[key] += ln.amount
                if ln.account_name and ln.account not in names:
                    names[ln.account] = ln.account_name
    keys = sorted(set(debit) | set(credit))
    return [
        TrialBalanceRow(k, names.get(k.split(".")[0]), debit.get(k, Decimal(0)), credit.get(k, Decimal(0)))
        for k in keys
    ]
