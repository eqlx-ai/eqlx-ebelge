"""e-Fatura / e-Arşiv invoices in GİB's UBL-TR 1.2 format.

:func:`read_invoices` accepts a single invoice or a GİB envelope (``StandardBusinessDocument``) with
several, and returns plain dataclasses. :func:`check_invoice` checks one invoice against itself;
:func:`find_duplicates` compares many. Amounts are :class:`~decimal.Decimal`, never floats.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from xml.etree.ElementTree import Element

from ._xml import local, parse, parse_date, parse_decimal, text
from .errors import EbelgeError, Finding, Severity
from .ids import PLACEHOLDER_TCKN, is_valid_tckn, is_valid_vkn

INV = "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}"
CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"
CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"

CENT = Decimal("0.01")
_NUMBER = re.compile(r"^[A-Z0-9]{3}(\d{4})\d{9}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class Party:
    tax_id: str | None
    scheme: str | None  # "VKN" or "TCKN"
    name: str | None
    tax_office: str | None
    city: str | None


@dataclass(frozen=True)
class Tax:
    type_code: str | None  # "0015" is KDV (VAT)
    name: str | None
    percent: Decimal | None
    taxable: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True)
class InvoiceLine:
    id: str | None
    name: str | None
    quantity: Decimal | None
    unit: str | None
    price: Decimal | None
    allowance: Decimal
    charge: Decimal
    amount: Decimal | None
    taxes: tuple[Tax, ...]


@dataclass(frozen=True)
class Totals:
    line_extension: Decimal | None
    tax_exclusive: Decimal | None
    tax_inclusive: Decimal | None
    allowance_total: Decimal | None
    charge_total: Decimal | None
    payable_rounding: Decimal | None
    payable: Decimal | None


@dataclass(frozen=True)
class Invoice:
    source: str
    number: str | None
    uuid: str | None
    issue_date: date | None
    profile: str | None
    type_code: str | None
    currency: str | None
    line_count: int | None
    supplier: Party
    customer: Party
    lines: tuple[InvoiceLine, ...]
    taxes: tuple[Tax, ...]
    tax_total: Decimal | None
    withholding: tuple[Tax, ...]
    withholding_total: Decimal | None
    totals: Totals
    notes: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = _jsonable(self)
        return out


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, tuple | list):
        return [_jsonable(x) for x in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _jsonable(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return obj


class _Reader:
    def __init__(self, source: str) -> None:
        self.source = source

    def amount(self, parent: Element | None, path: str) -> Decimal | None:
        el = parent.find(path) if parent is not None else None
        return parse_decimal(text(el), self.source, path.rsplit("}", 1)[-1])

    def party(self, el: Element | None) -> Party:
        party = el.find(f"{CAC}Party") if el is not None else None
        if party is None:
            return Party(None, None, None, None, None)
        tax_id = scheme = None
        for pid in party.findall(f"{CAC}PartyIdentification/{CBC}ID"):
            s = (pid.get("schemeID") or "").upper()
            if s in ("VKN", "TCKN"):
                tax_id, scheme = text(pid), s
                break
        name = text(party.find(f"{CAC}PartyName/{CBC}Name"))
        if name is None:
            person = party.find(f"{CAC}Person")
            if person is not None:
                parts = [
                    text(person.find(f"{CBC}FirstName")),
                    text(person.find(f"{CBC}FamilyName")),
                ]
                name = " ".join(p for p in parts if p) or None
        return Party(
            tax_id=tax_id,
            scheme=scheme,
            name=name,
            tax_office=text(party.find(f"{CAC}PartyTaxScheme/{CAC}TaxScheme/{CBC}Name")),
            city=text(party.find(f"{CAC}PostalAddress/{CBC}CityName")),
        )

    def taxes(self, total: Element | None) -> tuple[Tax, ...]:
        if total is None:
            return ()
        out = []
        for sub in total.findall(f"{CAC}TaxSubtotal"):
            scheme = sub.find(f"{CAC}TaxCategory/{CAC}TaxScheme")
            out.append(
                Tax(
                    type_code=text(scheme.find(f"{CBC}TaxTypeCode")) if scheme is not None else None,
                    name=text(scheme.find(f"{CBC}Name")) if scheme is not None else None,
                    percent=parse_decimal(text(sub.find(f"{CBC}Percent")), self.source, "Percent"),
                    taxable=self.amount(sub, f"{CBC}TaxableAmount"),
                    amount=self.amount(sub, f"{CBC}TaxAmount"),
                )
            )
        return tuple(out)

    def line(self, el: Element) -> InvoiceLine:
        qty_el = el.find(f"{CBC}InvoicedQuantity")
        allowance = charge = Decimal(0)
        for ac in el.findall(f"{CAC}AllowanceCharge"):
            amt = self.amount(ac, f"{CBC}Amount") or Decimal(0)
            if (text(ac.find(f"{CBC}ChargeIndicator")) or "false").lower() == "true":
                charge += amt
            else:
                allowance += amt
        return InvoiceLine(
            id=text(el.find(f"{CBC}ID")),
            name=text(el.find(f"{CAC}Item/{CBC}Name")),
            quantity=parse_decimal(text(qty_el), self.source, "InvoicedQuantity"),
            unit=qty_el.get("unitCode") if qty_el is not None else None,
            price=self.amount(el, f"{CAC}Price/{CBC}PriceAmount"),
            allowance=allowance,
            charge=charge,
            amount=self.amount(el, f"{CBC}LineExtensionAmount"),
            taxes=self.taxes(el.find(f"{CAC}TaxTotal")),
        )

    def invoice(self, root: Element) -> Invoice:
        if root.tag != f"{INV}Invoice":
            raise EbelgeError("not_an_invoice", self.source, local(root.tag))
        tax_total_el = root.find(f"{CAC}TaxTotal")
        wh_els = root.findall(f"{CAC}WithholdingTaxTotal")
        withholding = tuple(t for w in wh_els for t in self.taxes(w))
        wh_amounts = [self.amount(w, f"{CBC}TaxAmount") for w in wh_els]
        lmt = root.find(f"{CAC}LegalMonetaryTotal")
        count = text(root.find(f"{CBC}LineCountNumeric"))
        return Invoice(
            source=self.source,
            number=text(root.find(f"{CBC}ID")),
            uuid=text(root.find(f"{CBC}UUID")),
            issue_date=parse_date(text(root.find(f"{CBC}IssueDate")), self.source, "IssueDate"),
            profile=text(root.find(f"{CBC}ProfileID")),
            type_code=text(root.find(f"{CBC}InvoiceTypeCode")),
            currency=text(root.find(f"{CBC}DocumentCurrencyCode")),
            line_count=int(count) if count and count.isdigit() else None,
            supplier=self.party(root.find(f"{CAC}AccountingSupplierParty")),
            customer=self.party(root.find(f"{CAC}AccountingCustomerParty")),
            lines=tuple(self.line(el) for el in root.findall(f"{CAC}InvoiceLine")),
            taxes=self.taxes(tax_total_el),
            tax_total=self.amount(tax_total_el, f"{CBC}TaxAmount"),
            withholding=withholding,
            withholding_total=(sum((a for a in wh_amounts if a is not None), Decimal(0)) if wh_els else None),
            totals=Totals(
                line_extension=self.amount(lmt, f"{CBC}LineExtensionAmount"),
                tax_exclusive=self.amount(lmt, f"{CBC}TaxExclusiveAmount"),
                tax_inclusive=self.amount(lmt, f"{CBC}TaxInclusiveAmount"),
                allowance_total=self.amount(lmt, f"{CBC}AllowanceTotalAmount"),
                charge_total=self.amount(lmt, f"{CBC}ChargeTotalAmount"),
                payable_rounding=self.amount(lmt, f"{CBC}PayableRoundingAmount"),
                payable=self.amount(lmt, f"{CBC}PayableAmount"),
            ),
            notes=tuple(n for n in (text(e) for e in root.findall(f"{CBC}Note")) if n),
        )


def read_invoices(data: bytes, source: str = "<bytes>") -> list[Invoice]:
    """Invoices in one XML document: a single ``Invoice``, or every ``Invoice`` inside a GİB envelope."""
    root = parse(data, source)
    if root.tag == f"{INV}Invoice":
        return [_Reader(source).invoice(root)]
    found = list(root.iter(f"{INV}Invoice"))
    if not found:
        raise EbelgeError("not_an_invoice", source, local(root.tag))
    return [_Reader(f"{source}#{i + 1}").invoice(el) for i, el in enumerate(found)]


def read_invoice(data: bytes, source: str = "<bytes>") -> Invoice:
    """The single invoice in ``data``; raises if the document holds none or several."""
    invoices = read_invoices(data, source)
    if len(invoices) != 1:
        raise EbelgeError("not_single_invoice", source, f"{len(invoices)} invoices")
    return invoices[0]


# --- checks -------------------------------------------------------------------------------------


def _round(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _check_party(inv: Invoice, role: str, p: Party, out: list[Finding]) -> None:
    where = f"{role}.tax_id"
    if p.tax_id is None:
        out.append(Finding("tax_id_missing", "error", f"{role} has no VKN or TCKN", inv.source, where))
        return
    if p.scheme == "TCKN" and p.tax_id == PLACEHOLDER_TCKN:
        msg = f"{role} uses the placeholder TCKN for an unidentified consumer"
        out.append(Finding("placeholder_tckn", "info", msg, inv.source, where))
        return
    expected = 10 if p.scheme == "VKN" else 11
    if len(p.tax_id) != expected:
        msg = f"{role} {p.scheme} {p.tax_id} must have {expected} digits"
        out.append(Finding("tax_id_length", "error", msg, inv.source, where))
        return
    ok = is_valid_vkn(p.tax_id) if p.scheme == "VKN" else is_valid_tckn(p.tax_id)
    if not ok:
        msg = f"{role} {p.scheme} {p.tax_id} fails its check digit"
        out.append(Finding("tax_id_check_digit", "error", msg, inv.source, where))


def _gap(a: Decimal | None, b: Decimal | None, tolerance: Decimal) -> Decimal | None:
    if a is None or b is None:
        return None
    d = abs(a - b)
    return d if d > tolerance else None


def check_invoice(inv: Invoice) -> list[Finding]:
    """Check one invoice against itself: identifiers, number format, and that the amounts add up.

    Tolerance is one kuruş (0.01) per comparison, plus half a kuruş per line where per-line rounding
    can accumulate.
    """
    out: list[Finding] = []
    src = inv.source
    _check_party(inv, "supplier", inv.supplier, out)
    _check_party(inv, "customer", inv.customer, out)
    if (
        inv.supplier.tax_id
        and inv.supplier.tax_id == inv.customer.tax_id
        and inv.supplier.tax_id != PLACEHOLDER_TCKN
    ):
        msg = "supplier and customer have the same tax id"
        out.append(Finding("same_party", "info", msg, src, "customer.tax_id"))

    if inv.number is None:
        out.append(Finding("number_missing", "error", "invoice has no number (cbc:ID)", src, "number"))
    else:
        m = _NUMBER.match(inv.number)
        if m is None:
            msg = f"invoice number {inv.number} is not 3 characters + 4-digit year + 9 digits"
            out.append(Finding("number_format", "warning", msg, src, "number"))
        elif inv.issue_date is not None and int(m.group(1)) != inv.issue_date.year:
            msg = f"invoice number year {m.group(1)} differs from issue date {inv.issue_date}"
            out.append(Finding("number_year", "warning", msg, src, "number"))
    if inv.uuid is None or not _UUID.match(inv.uuid):
        msg = f"ETTN (UUID) {inv.uuid!r} is missing or malformed"
        out.append(Finding("uuid_format", "warning", msg, src, "uuid"))
    if inv.issue_date is None:
        out.append(Finding("date_missing", "error", "invoice has no issue date", src, "issue_date"))

    if inv.line_count is not None and inv.line_count != len(inv.lines):
        msg = f"LineCountNumeric says {inv.line_count}, the invoice has {len(inv.lines)} lines"
        out.append(Finding("line_count", "warning", msg, src, "line_count"))

    for line in inv.lines:
        if line.quantity is None or line.price is None or line.amount is None:
            continue
        expected = _round(line.quantity * line.price - line.allowance + line.charge)
        if (g := _gap(expected, line.amount, CENT)) is not None:
            msg = (
                f"line {line.id}: quantity x price - discount + charge = {expected}, "
                f"line amount is {line.amount} (gap {g})"
            )
            out.append(Finding("line_amount", "warning", msg, src, f"lines[{line.id}]"))

    t = inv.totals
    if t.payable is None and t.line_extension is None:
        msg = "invoice has no LegalMonetaryTotal"
        out.append(Finding("totals_missing", "error", msg, src, "totals"))
        return out

    line_sum = sum((ln.amount for ln in inv.lines if ln.amount is not None), Decimal(0))
    if inv.lines and (g := _gap(line_sum, t.line_extension, CENT)) is not None:
        msg = f"lines add up to {line_sum}, LineExtensionAmount is {t.line_extension} (gap {g})"
        out.append(Finding("lines_total", "error", msg, src, "totals.line_extension"))

    per_line = CENT + Decimal("0.005") * max(len(inv.lines), 1)
    for tax in inv.taxes:
        if tax.taxable is None or tax.percent is None or tax.amount is None:
            continue
        expected = _round(tax.taxable * tax.percent / 100)
        if (g := _gap(expected, tax.amount, per_line)) is not None:
            label = tax.name or tax.type_code
            msg = f"{label} {tax.percent}% of {tax.taxable} is {expected}, invoice says {tax.amount}"
            out.append(Finding("tax_rate", "warning", msg, src, "taxes"))
    if inv.taxes and inv.tax_total is not None:
        sub_sum = sum((x.amount for x in inv.taxes if x.amount is not None), Decimal(0))
        if (g := _gap(sub_sum, inv.tax_total, CENT)) is not None:
            msg = f"tax subtotals add up to {sub_sum}, TaxTotal is {inv.tax_total} (gap {g})"
            out.append(Finding("tax_total", "error", msg, src, "tax_total"))

    if t.tax_exclusive is not None and t.tax_inclusive is not None:
        expected = t.tax_exclusive + (inv.tax_total or Decimal(0))
        if (g := _gap(expected, t.tax_inclusive, CENT)) is not None:
            msg = (
                f"TaxExclusiveAmount + taxes = {expected}, TaxInclusiveAmount is {t.tax_inclusive} (gap {g})"
            )
            out.append(Finding("tax_inclusive", "error", msg, src, "totals.tax_inclusive"))
    if t.tax_inclusive is not None and t.payable is not None:
        expected = (
            t.tax_inclusive - (inv.withholding_total or Decimal(0)) + (t.payable_rounding or Decimal(0))
        )
        if (g := _gap(expected, t.payable, CENT)) is not None:
            msg = (
                f"TaxInclusiveAmount - withholding + rounding = {expected}, "
                f"PayableAmount is {t.payable} (gap {g})"
            )
            sev: Severity = "error" if g > Decimal(1) else "warning"
            out.append(Finding("payable", sev, msg, src, "totals.payable"))
    return out


def _name(source: str) -> str:
    """File name without folders, keeping a ZIP member or envelope position."""
    return source.replace("\\", "/").rsplit("/", 1)[-1]


def find_duplicates(invoices: Iterable[Invoice]) -> list[Finding]:
    """Invoices that appear more than once.

    * the same ETTN (UUID) in two places: error;
    * the same supplier and invoice number: error;
    * the same supplier, customer, date and payable amount under different numbers: warning.
    """
    by_uuid: dict[str, list[Invoice]] = defaultdict(list)
    by_number: dict[tuple[str, str], list[Invoice]] = defaultdict(list)
    by_shape: dict[tuple[Any, ...], list[Invoice]] = defaultdict(list)
    for inv in invoices:
        if inv.uuid:
            by_uuid[inv.uuid.upper()].append(inv)
        if inv.supplier.tax_id and inv.number:
            by_number[(inv.supplier.tax_id, inv.number)].append(inv)
        if inv.supplier.tax_id and inv.issue_date and inv.totals.payable is not None:
            key = (
                inv.supplier.tax_id,
                inv.customer.tax_id,
                inv.issue_date,
                inv.totals.payable,
            )
            by_shape[key].append(inv)

    out: list[Finding] = []
    flagged: set[frozenset[str]] = set()
    for uuid, group in by_uuid.items():
        if len(group) > 1:
            names = ", ".join(_name(i.source) for i in group)
            flagged.add(frozenset(i.source for i in group))
            msg = f"ETTN {uuid} appears {len(group)} times: {names}"
            out.append(Finding("duplicate_uuid", "error", msg, group[0].source, "uuid"))
    for (vkn, number), group in by_number.items():
        sources = frozenset(i.source for i in group)
        if len(group) > 1 and sources not in flagged:
            flagged.add(sources)
            names = ", ".join(_name(i.source) for i in group)
            msg = f"supplier {vkn} invoice {number} appears {len(group)} times: {names}"
            out.append(Finding("duplicate_number", "error", msg, group[0].source, "number"))
    for (vkn, _cust, day, payable), group in by_shape.items():
        sources = frozenset(i.source for i in group)
        if len({i.number for i in group}) > 1 and sources not in flagged:
            names = ", ".join(f"{i.number} ({_name(i.source)})" for i in group)
            msg = f"supplier {vkn}, same customer, {day}, payable {payable}: {names}"
            out.append(Finding("possible_duplicate", "warning", msg, group[0].source, "number"))
    return out
