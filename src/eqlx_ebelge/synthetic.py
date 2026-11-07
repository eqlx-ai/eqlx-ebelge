"""Synthetic e-Fatura and e-Defter files for tests, demos and trying the tools without real data.

Every name, number and amount here is made up. Tax ids are generated with valid check digits so that the
documents look real to the checks; amounts are computed the way an invoicing system would.
"""

from __future__ import annotations

import random
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

from .ids import tckn_check_digits, vkn_check_digit

CENT = Decimal("0.01")


def _r(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def make_vkn(rng: random.Random) -> str:
    first9 = f"{rng.randrange(10**8, 10**9)}"
    return first9 + str(vkn_check_digit(first9))


def make_tckn(rng: random.Random) -> str:
    first9 = f"{rng.randrange(10**8, 10**9)}"
    return first9 + tckn_check_digits(first9)


@dataclass(frozen=True)
class Item:
    name: str
    quantity: Decimal
    price: Decimal
    vat_percent: Decimal = Decimal(20)
    discount_percent: Decimal = Decimal(0)


@dataclass
class InvoiceSpec:
    number: str
    issue_date: date
    supplier_vkn: str
    supplier_name: str
    customer_id: str
    customer_name: str
    items: Sequence[Item]
    uuid: str = field(default_factory=lambda: str(_uuid.uuid4()).upper())
    profile: str = "TICARIFATURA"
    type_code: str = "SATIS"
    withholding_percent: Decimal | None = None  # tevkifat share of the VAT, e.g. 50
    payable_override: Decimal | None = None  # to build a tampered invoice in tests


def _amt(tag: str, value: Decimal) -> str:
    return f'<cbc:{tag} currencyID="TRY">{value}</cbc:{tag}>'


def _party(role: str, tax_id: str, name: str, city: str) -> str:
    scheme = "VKN" if len(tax_id) == 10 else "TCKN"
    if scheme == "VKN":
        who = f"<cac:PartyName><cbc:Name>{escape(name)}</cbc:Name></cac:PartyName>"
    else:
        first, _, last = name.partition(" ")
        who = (
            f"<cac:Person><cbc:FirstName>{escape(first)}</cbc:FirstName>"
            f"<cbc:FamilyName>{escape(last)}</cbc:FamilyName></cac:Person>"
        )
    return (
        f"<cac:{role}><cac:Party>"
        f'<cac:PartyIdentification><cbc:ID schemeID="{scheme}">{tax_id}</cbc:ID></cac:PartyIdentification>'
        f"{who if scheme == 'VKN' else ''}"
        f"<cac:PostalAddress><cbc:CityName>{escape(city)}</cbc:CityName>"
        f"<cac:Country><cbc:Name>Türkiye</cbc:Name></cac:Country></cac:PostalAddress>"
        f"<cac:PartyTaxScheme><cac:TaxScheme><cbc:Name>{escape(city)}</cbc:Name></cac:TaxScheme>"
        f"</cac:PartyTaxScheme>"
        f"{who if scheme == 'TCKN' else ''}"
        f"</cac:Party></cac:{role}>"
    )


def make_invoice(spec: InvoiceSpec) -> bytes:
    """A UBL-TR 1.2 invoice whose amounts add up (unless ``payable_override`` is set)."""
    lines_xml = []
    line_total = Decimal(0)
    discount_total = Decimal(0)
    vat_by_rate: dict[Decimal, list[Decimal]] = {}
    for i, it in enumerate(spec.items, start=1):
        gross = _r(it.quantity * it.price)
        discount = _r(gross * it.discount_percent / 100)
        net = gross - discount
        vat = _r(net * it.vat_percent / 100)
        line_total += net
        discount_total += discount
        acc = vat_by_rate.setdefault(it.vat_percent, [Decimal(0), Decimal(0)])
        acc[0] += net
        acc[1] += vat
        allowance = (
            "<cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator>"
            f"<cbc:MultiplierFactorNumeric>{it.discount_percent / 100}</cbc:MultiplierFactorNumeric>"
            f"{_amt('Amount', discount)}{_amt('BaseAmount', gross)}</cac:AllowanceCharge>"
            if discount
            else ""
        )
        lines_xml.append(
            "<cac:InvoiceLine>"
            f"<cbc:ID>{i}</cbc:ID>"
            f'<cbc:InvoicedQuantity unitCode="C62">{it.quantity}</cbc:InvoicedQuantity>'
            f"{_amt('LineExtensionAmount', net)}{allowance}"
            f"<cac:TaxTotal>{_amt('TaxAmount', vat)}<cac:TaxSubtotal>{_amt('TaxableAmount', net)}"
            f"{_amt('TaxAmount', vat)}<cbc:Percent>{it.vat_percent}</cbc:Percent>"
            "<cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name>"
            "<cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme></cac:TaxCategory>"
            "</cac:TaxSubtotal></cac:TaxTotal>"
            f"<cac:Item><cbc:Name>{escape(it.name)}</cbc:Name></cac:Item>"
            f"<cac:Price>{_amt('PriceAmount', it.price)}</cac:Price>"
            "</cac:InvoiceLine>"
        )
    vat_total = sum((v[1] for v in vat_by_rate.values()), Decimal(0))
    subtotals = "".join(
        f"<cac:TaxSubtotal>{_amt('TaxableAmount', base)}{_amt('TaxAmount', vat)}"
        f"<cbc:Percent>{rate}</cbc:Percent><cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name>"
        "<cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal>"
        for rate, (base, vat) in sorted(vat_by_rate.items())
    )
    withholding_xml = ""
    withheld = Decimal(0)
    if spec.withholding_percent is not None:
        withheld = _r(vat_total * spec.withholding_percent / 100)
        withholding_xml = (
            f"<cac:WithholdingTaxTotal>{_amt('TaxAmount', withheld)}<cac:TaxSubtotal>"
            f"{_amt('TaxableAmount', vat_total)}{_amt('TaxAmount', withheld)}"
            f"<cbc:Percent>{spec.withholding_percent}</cbc:Percent><cac:TaxCategory><cac:TaxScheme>"
            "<cbc:Name>KDV TEVKIFAT</cbc:Name><cbc:TaxTypeCode>9015</cbc:TaxTypeCode></cac:TaxScheme>"
            "</cac:TaxCategory></cac:TaxSubtotal></cac:WithholdingTaxTotal>"
        )
    inclusive = line_total + vat_total
    payable = spec.payable_override if spec.payable_override is not None else inclusive - withheld
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        "<cbc:UBLVersionID>2.1</cbc:UBLVersionID><cbc:CustomizationID>TR1.2</cbc:CustomizationID>"
        f"<cbc:ProfileID>{spec.profile}</cbc:ProfileID><cbc:ID>{spec.number}</cbc:ID>"
        f"<cbc:CopyIndicator>false</cbc:CopyIndicator><cbc:UUID>{spec.uuid}</cbc:UUID>"
        f"<cbc:IssueDate>{spec.issue_date.isoformat()}</cbc:IssueDate>"
        f"<cbc:InvoiceTypeCode>{spec.type_code}</cbc:InvoiceTypeCode>"
        "<cbc:Note>Synthetic invoice generated by eqlx-ebelge. Not a real document.</cbc:Note>"
        "<cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>"
        f"<cbc:LineCountNumeric>{len(spec.items)}</cbc:LineCountNumeric>"
        + _party("AccountingSupplierParty", spec.supplier_vkn, spec.supplier_name, "İstanbul")
        + _party("AccountingCustomerParty", spec.customer_id, spec.customer_name, "Ankara")
        + f"<cac:TaxTotal>{_amt('TaxAmount', vat_total)}{subtotals}</cac:TaxTotal>"
        + withholding_xml
        + "<cac:LegalMonetaryTotal>"
        + _amt("LineExtensionAmount", line_total)
        + _amt("TaxExclusiveAmount", line_total)
        + _amt("TaxInclusiveAmount", inclusive)
        + _amt("AllowanceTotalAmount", discount_total)
        + _amt("PayableAmount", payable)
        + "</cac:LegalMonetaryTotal>"
        + "".join(lines_xml)
        + "</Invoice>"
    )
    return xml.encode("utf-8")


def make_envelope(invoices: Sequence[bytes]) -> bytes:
    """A GİB-style envelope (``StandardBusinessDocument``) carrying several invoices."""
    bodies = b"".join(inv.split(b"?>", 1)[1] for inv in invoices)
    head = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<sh:StandardBusinessDocument xmlns:sh="http://www.unece.org/cefact/namespaces/'
        b'StandardBusinessDocumentHeader" xmlns:ef="http://www.efatura.gov.tr/package-namespace">'
        b"<sh:StandardBusinessDocumentHeader><sh:HeaderVersion>1.0</sh:HeaderVersion>"
        b"</sh:StandardBusinessDocumentHeader><ef:Package><Elements><ElementType>INVOICE</ElementType>"
        b"<ElementCount>" + str(len(invoices)).encode() + b"</ElementCount><ElementList>"
    )
    return head + bodies + b"</ElementList></Elements></ef:Package></sh:StandardBusinessDocument>"


# --- e-Defter --------------------------------------------------------------------------------------

#: A few Tekdüzen Hesap Planı main accounts, enough for realistic synthetic books.
ACCOUNTS = {
    "100": "KASA",
    "102": "BANKALAR",
    "120": "ALICILAR",
    "153": "TİCARİ MALLAR",
    "191": "İNDİRİLECEK KDV",
    "320": "SATICILAR",
    "360": "ÖDENECEK VERGİ VE FONLAR",
    "391": "HESAPLANAN KDV",
    "500": "SERMAYE",
    "600": "YURT İÇİ SATIŞLAR",
    "621": "SATILAN TİCARİ MALLAR MALİYETİ",
    "770": "GENEL YÖNETİM GİDERLERİ",
}

Posting = tuple[str, Decimal, str]  # (account, amount, "D" or "C"); account may be "120.001"


@dataclass(frozen=True)
class EntrySpec:
    day: date
    postings: Sequence[Posting]
    total_debit: Decimal | None = None  # override to build a tampered header
    total_credit: Decimal | None = None


def _ctx(tag: str, value: object) -> str:
    return f'<{tag} contextRef="journal_context">{value}</{tag}>'


def _money(tag: str, value: Decimal) -> str:
    return f'<{tag} contextRef="journal_context" unitRef="try" decimals="INF">{value}</{tag}>'


def make_ledger(
    *,
    tax_id: str,
    title: str,
    period_start: date,
    period_end: date,
    entries: Sequence[EntrySpec],
    first_counter: int = 1,
    entries_type: str = "journal",
) -> bytes:
    """An e-Defter XBRL GL journal (yevmiye) file. Postings in each :class:`EntrySpec` are written as given;
    balance them yourself unless you want an unbalanced entry for a test."""
    body = []
    for n, e in enumerate(entries):
        counter = first_counter + n
        debit = sum((a for _, a, s in e.postings if s == "D"), Decimal(0))
        credit = sum((a for _, a, s in e.postings if s == "C"), Decimal(0))
        details = []
        for k, (acc, amount, side) in enumerate(e.postings, start=1):
            main = acc.split(".")[0]
            sub = (
                f"<gl-cor:accountSub>{_ctx('gl-cor:accountSubID', acc)}</gl-cor:accountSub>"
                if "." in acc
                else ""
            )
            details.append(
                "<gl-cor:entryDetail>"
                f"{_ctx('gl-cor:lineNumber', k)}{_ctx('gl-cor:lineNumberCounter', k)}"
                "<gl-cor:account>"
                f"{_ctx('gl-cor:accountMainDescription', escape(ACCOUNTS.get(main, 'HESAP')))}"
                f"{_ctx('gl-cor:accountMainID', main)}{sub}</gl-cor:account>"
                f"{_money('gl-cor:amount', amount)}{_ctx('gl-cor:debitCreditCode', side)}"
                f"{_ctx('gl-cor:postingDate', e.day.isoformat())}"
                "</gl-cor:entryDetail>"
            )
        body.append(
            "<gl-cor:entryHeader>"
            f"{_ctx('gl-cor:enteredDate', e.day.isoformat())}{_ctx('gl-cor:entryNumber', counter)}"
            f"{_ctx('gl-cor:entryComment', 'Sentetik fiş')}"
            f"{_money('gl-bus:totalDebit', e.total_debit if e.total_debit is not None else debit)}"
            f"{_money('gl-bus:totalCredit', e.total_credit if e.total_credit is not None else credit)}"
            f"{_ctx('gl-cor:entryNumberCounter', counter)}" + "".join(details) + "</gl-cor:entryHeader>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<edefter:defter xmlns:edefter="http://www.edefter.gov.tr" '
        'xmlns:xbrli="http://www.xbrl.org/2003/instance" '
        'xmlns:gl-cor="http://www.xbrl.org/int/gl/cor/2006-10-25" '
        'xmlns:gl-bus="http://www.xbrl.org/int/gl/bus/2006-10-25" '
        'xmlns:iso4217="http://www.xbrl.org/2003/iso4217">'
        "<xbrli:xbrl>"
        '<xbrli:context id="journal_context"><xbrli:entity>'
        f'<xbrli:identifier scheme="http://www.gib.gov.tr">{tax_id}</xbrli:identifier></xbrli:entity>'
        f"<xbrli:period><xbrli:instant>{period_end.isoformat()}</xbrli:instant></xbrli:period>"
        "</xbrli:context>"
        '<xbrli:unit id="try"><xbrli:measure>iso4217:TRY</xbrli:measure></xbrli:unit>'
        "<gl-cor:accountingEntries><gl-cor:documentInfo>"
        f"{_ctx('gl-cor:entriesType', entries_type)}"
        f"{_ctx('gl-cor:periodCoveredStart', period_start.isoformat())}"
        f"{_ctx('gl-cor:periodCoveredEnd', period_end.isoformat())}"
        "</gl-cor:documentInfo><gl-cor:entityInformation><gl-bus:organizationIdentifiers>"
        f"{_ctx('gl-bus:organizationIdentifier', escape(title))}"
        "</gl-bus:organizationIdentifiers>"
        f"{_ctx('gl-bus:fiscalYearStart', date(period_start.year, 1, 1).isoformat())}"
        f"{_ctx('gl-bus:fiscalYearEnd', date(period_start.year, 12, 31).isoformat())}"
        "</gl-cor:entityInformation>" + "".join(body) + "</gl-cor:accountingEntries></xbrli:xbrl>"
        "</edefter:defter>"
    )
    return xml.encode("utf-8")


# --- a demo set ------------------------------------------------------------------------------------


def demo_files(seed: int = 7) -> dict[str, bytes]:
    """A small folder's worth of synthetic files: clean invoices, one duplicate, one with wrong totals, one
    with a bad tax id, and one month of a balanced journal. Keys are file names."""
    rng = random.Random(seed)
    supplier = make_vkn(rng)
    customers = [make_vkn(rng) for _ in range(3)]
    day0 = date(2026, 10, 1)
    files: dict[str, bytes] = {}
    specs = []
    for n in range(1, 7):
        items = [
            Item("Çelik profil 40x40", Decimal(rng.randint(5, 50)), Decimal("185.40")),
            Item(
                "Montaj hizmeti",
                Decimal(1),
                Decimal(rng.randint(500, 3000)),
                Decimal(20),
                Decimal(10),
            ),
        ]
        spec = InvoiceSpec(
            number=f"EQX2026{n:09d}",
            issue_date=day0 + timedelta(days=3 * n),
            supplier_vkn=supplier,
            supplier_name="Örnek Metal Sanayi A.Ş.",
            customer_id=customers[n % 3],
            customer_name="Deneme Yapı Ltd. Şti.",
            items=items,
            uuid=str(_uuid.UUID(int=rng.getrandbits(128), version=4)).upper(),
        )
        specs.append(spec)
        files[f"fatura_{n:02d}.xml"] = make_invoice(spec)
    # the same invoice sent twice under a new number: a classic factoring problem
    again = specs[1]
    files["fatura_07.xml"] = make_invoice(
        InvoiceSpec(**{**again.__dict__, "number": "EQX2026000000007", "uuid": str(_uuid.UUID(int=1))})
    )
    files["fatura_08_toplam_hatali.xml"] = make_invoice(
        InvoiceSpec(
            **{
                **specs[2].__dict__,
                "number": "EQX2026000000008",
                "uuid": str(_uuid.UUID(int=2)),
                "payable_override": Decimal("99999.99"),
            }
        )
    )
    bad_vkn = supplier[:-1] + str((int(supplier[-1]) + 1) % 10)
    files["fatura_09_vkn_hatali.xml"] = make_invoice(
        InvoiceSpec(
            **{
                **specs[3].__dict__,
                "number": "EQX2026000000009",
                "uuid": str(_uuid.UUID(int=3)),
                "supplier_vkn": bad_vkn,
            }
        )
    )
    d = Decimal
    entries = [
        EntrySpec(date(2026, 10, 1), [("102.01", d("500000.00"), "D"), ("500", d("500000.00"), "C")]),
        EntrySpec(
            date(2026, 10, 5),
            [
                ("153", d("120000.00"), "D"),
                ("191", d("24000.00"), "D"),
                ("320.017", d("144000.00"), "C"),
            ],
        ),
        EntrySpec(
            date(2026, 10, 12),
            [
                ("120.004", d("90000.00"), "D"),
                ("600", d("75000.00"), "C"),
                ("391", d("15000.00"), "C"),
            ],
        ),
        EntrySpec(date(2026, 10, 12), [("621", d("52000.00"), "D"), ("153", d("52000.00"), "C")]),
        EntrySpec(date(2026, 10, 20), [("102.01", d("60000.00"), "D"), ("120.004", d("60000.00"), "C")]),
        EntrySpec(date(2026, 10, 28), [("770", d("8500.00"), "D"), ("100", d("8500.00"), "C")]),
        EntrySpec(date(2026, 10, 31), [("100", d("10000.00"), "D"), ("102.01", d("10000.00"), "C")]),
    ]
    files["edefter_2026_10_yevmiye.xml"] = make_ledger(
        tax_id=supplier,
        title="ÖRNEK METAL SANAYİ ANONİM ŞİRKETİ",
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        entries=entries,
    )
    return files
