"""UBL-TR writing variants found in GİB's public sample invoices. Each is rebuilt here as a minimal synthetic
document: one where the variant adds up (no finding) and, where useful, one where it does not."""

from decimal import Decimal

from eqlx_ebelge import check_invoice, read_invoice, scan
from eqlx_ebelge.ledger import check_ledger, read_ledger

NS = (
    'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
    'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"'
)
PARTY = (
    '<cac:{r}><cac:Party><cac:PartyIdentification><cbc:ID schemeID="VKN">{v}</cbc:ID>'
    "</cac:PartyIdentification></cac:Party></cac:{r}>"
)


def a(tag, v):
    return f'<cbc:{tag} currencyID="TRY">{v}</cbc:{tag}>'


def sub(taxable, amount, pct, code="0015", exemption=None):
    ex = f"<cbc:TaxExemptionReasonCode>{exemption}</cbc:TaxExemptionReasonCode>" if exemption else ""
    return (
        f"<cac:TaxSubtotal>{a('TaxableAmount', taxable)}{a('TaxAmount', amount)}<cbc:Percent>{pct}</cbc:Percent>"
        f"<cac:TaxCategory>{ex}<cac:TaxScheme><cbc:TaxTypeCode>{code}</cbc:TaxTypeCode></cac:TaxScheme>"
        "</cac:TaxCategory></cac:TaxSubtotal>"
    )


def invoice(*, lmt, tax_total, subs, lines, withholding="", profile="TICARIFATURA", extra=""):
    lines_xml = "".join(
        f"<cac:InvoiceLine><cbc:ID>{i}</cbc:ID>"
        f'<cbc:InvoicedQuantity unitCode="C62">{q}</cbc:InvoicedQuantity>{a("LineExtensionAmount", amt)}'
        + (
            f"<cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator>{a('Amount', disc)}"
            "</cac:AllowanceCharge>"
            if disc
            else ""
        )
        + f"<cac:Price>{a('PriceAmount', price)}</cac:Price></cac:InvoiceLine>"
        for i, (q, price, amt, disc) in enumerate(lines, 1)
    )
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><Invoice {NS}><cbc:ProfileID>{profile}</cbc:ProfileID>'
        "<cbc:ID>ABC2026000000001</cbc:ID><cbc:UUID>3F2504E0-4F89-41D3-9A0C-0305E82C3301</cbc:UUID>"
        "<cbc:IssueDate>2026-10-04</cbc:IssueDate><cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>"
        + PARTY.format(r="AccountingSupplierParty", v="4477127820")
        + PARTY.format(r="AccountingCustomerParty", v="1234567808")
        + extra
        + f"<cac:TaxTotal>{a('TaxAmount', tax_total)}{''.join(subs)}</cac:TaxTotal>"
        + withholding
        + "<cac:LegalMonetaryTotal>"
        + "".join(a(k, v) for k, v in lmt.items())
        + "</cac:LegalMonetaryTotal>"
        + lines_xml
        + "</Invoice>"
    )
    return read_invoice(xml.encode())


def codes(inv):
    return {f.code for f in check_invoice(inv)}


def lmt(line, excl, incl, payable, **kw):
    d = {"LineExtensionAmount": line, "TaxExclusiveAmount": excl, "TaxInclusiveAmount": incl}
    d.update(kw)
    d["PayableAmount"] = payable
    return d


def test_exemption_shows_tax_that_is_not_charged():
    inv = invoice(
        lmt=lmt("1500.00", "1500.00", "1500.00", "1500.00"),
        tax_total="0",
        subs=[sub("1500.00", "300.00", 20, exemption="308")],
        lines=[(15, 100, "1500.00", None)],
    )
    assert inv.taxes[0].exemption_code == "308"
    assert codes(inv) == set()


def test_exemption_that_is_charged_and_refunded():
    inv = invoice(
        lmt=lmt("100", "100", "118", "118"),
        tax_total="18",
        subs=[sub("100", "18", 18, exemption="501")],
        lines=[(1, 100, "100", None)],
        profile="YOLCUBERABERFATURA",
    )
    assert codes(inv) == set()


def test_stopaj_is_deducted_from_payable():
    inv = invoice(
        lmt=lmt("500.00", "450.00", "590.00", "540.00"),
        tax_total="90.00",
        subs=[sub("500.00", "50.00", 10, code="0003"), sub("500.00", "90.00", 18)],
        lines=[(1, 500, "500.00", None)],
    )
    assert codes(inv) == set()
    wrong = invoice(
        lmt=lmt("500.00", "450.00", "590.00", "590.00"),
        tax_total="90.00",
        subs=[sub("500.00", "50.00", 10, code="0003"), sub("500.00", "90.00", 18)],
        lines=[(1, 500, "500.00", None)],
    )
    assert "payable" in codes(wrong)


def test_tevkifat_with_tax_total_net_of_withholding():
    wh = (
        f"<cac:WithholdingTaxTotal>{a('TaxAmount', '20.25')}"
        f"{sub('22.50', '20.25', 90, code='613')}</cac:WithholdingTaxTotal>"
    )
    inv = invoice(
        lmt=lmt("225.00", "225.00", "247.50", "227.25"),
        tax_total="2.25",
        subs=[sub("225.00", "22.50", 10)],
        lines=[(15, 15, "225.00", None)],
        withholding=wh,
        profile="YATIRIMTESVIK",
    )
    assert codes(inv) == set()


def test_hks_market_charges_reduce_payable():
    fields = lmt("1500.00", "1500.00", "1500.00", "1260.00", ChargeTotalAmount="240.00")
    inv = invoice(
        lmt=fields,
        tax_total="0.00",
        subs=[sub("1500.00", "0.00", 0)],
        lines=[(10, 150, "1500.00", None)],
        profile="HKS",
    )
    assert codes(inv) == set()
    other = invoice(
        lmt=fields,
        tax_total="0.00",
        subs=[sub("1500.00", "0.00", 0)],
        lines=[(10, 150, "1500.00", None)],
    )
    assert "payable" in codes(other)  # only HKS invoices may deduct charges this way


def test_line_extension_written_before_discounts():
    inv = invoice(
        lmt=lmt("10.00", "7.20", "8.50", "8.50", AllowanceTotalAmount="2.80"),
        tax_total="1.30",
        subs=[sub("7.20", "1.30", 18)],
        lines=[(1, 10, "7.20", "2.80")],
    )
    assert codes(inv) == set()


def test_genuine_errors_still_caught():
    doubled = invoice(
        lmt=lmt("1875", "1875", "2250", "2250"),
        tax_total="375",
        subs=[sub("1875", "375", 20)],
        lines=[(15, 125, "1875", None), (15, 125, "1875", None)],
    )
    assert "lines_total" in codes(doubled)
    bad_tax = invoice(
        lmt=lmt("100", "100", "118", "118"),
        tax_total="25",
        subs=[sub("100", "18", 18)],
        lines=[(1, 100, "100", None)],
    )
    assert {"tax_total", "tax_inclusive"} & codes(bad_tax)


def test_envelope_without_invoice_is_unsupported_not_unreadable(tmp_path):
    (tmp_path / "yanit.xml").write_bytes(
        b'<sh:StandardBusinessDocument xmlns:sh="http://www.unece.org/cefact/namespaces/'
        b'StandardBusinessDocumentHeader"><x/></sh:StandardBusinessDocument>'
    )
    rep = scan([tmp_path])
    assert [(f.code, f.severity) for f in rep.findings] == [("unsupported", "info")]


KEBIR = b"""<edefter:defter xmlns:edefter="http://www.edefter.gov.tr" xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:gl-cor="http://www.xbrl.org/int/gl/cor/2006-10-25" xmlns:gl-bus="http://www.xbrl.org/int/gl/bus/2006-10-25">
<xbrli:xbrl><xbrli:unit id="try"><xbrli:measure>iso4217:TRY</xbrli:measure></xbrli:unit>
<gl-cor:accountingEntries><gl-cor:documentInfo><gl-cor:entriesType>{kind}</gl-cor:entriesType></gl-cor:documentInfo>
<gl-cor:entryHeader><gl-bus:totalDebit unitRef="try">{td}</gl-bus:totalDebit><gl-bus:totalCredit unitRef="try">0</gl-bus:totalCredit>
 <gl-cor:entryDetail><gl-cor:account><gl-cor:accountMainID>100</gl-cor:accountMainID></gl-cor:account>
  <gl-cor:amount unitRef="try">300</gl-cor:amount><gl-cor:debitCreditCode>D</gl-cor:debitCreditCode></gl-cor:entryDetail>
 <gl-cor:entryDetail><gl-cor:account><gl-cor:accountMainID>100</gl-cor:accountMainID></gl-cor:account>
  <gl-cor:amount unitRef="try">100</gl-cor:amount><gl-cor:debitCreditCode>C</gl-cor:debitCreditCode></gl-cor:entryDetail>
</gl-cor:entryHeader>
<gl-cor:entryHeader><gl-bus:totalDebit unitRef="try">0</gl-bus:totalDebit><gl-bus:totalCredit unitRef="try">200</gl-bus:totalCredit>
 <gl-cor:entryDetail><gl-cor:account><gl-cor:accountMainID>500</gl-cor:accountMainID></gl-cor:account>
  <gl-cor:amount unitRef="try">200</gl-cor:amount><gl-cor:debitCreditCode>C</gl-cor:debitCreditCode></gl-cor:entryDetail>
</gl-cor:entryHeader></gl-cor:accountingEntries></xbrli:xbrl></edefter:defter>"""


def kebir(kind="ledger", td="200"):
    return KEBIR.replace(b"{kind}", kind.encode()).replace(b"{td}", td.encode())


def test_kebir_entries_are_accounts_with_net_header_totals():
    lg = read_ledger(kebir())
    assert lg.header.entries_type == "ledger"
    assert check_ledger(lg) == []
    assert {f.code for f in check_ledger(read_ledger(kebir(td="250")))} == {"entry_total"}


def test_unknown_ledger_type_is_unsupported(tmp_path):
    (tmp_path / "e.xml").write_bytes(kebir(kind="assets"))
    rep = scan([tmp_path])
    assert [(f.code, f.severity) for f in rep.findings] == [("unsupported", "info")]
    assert rep.ledgers == []


def test_decimal_amounts_with_many_places():
    inv = invoice(
        lmt=lmt("250.00", "250.00", "295.00", "295.00"),
        tax_total="45.00000",
        subs=[sub("250", "45.00000", "18.00")],
        lines=[(1, 250, "250.0000000000", None)],
    )
    assert inv.tax_total == Decimal("45.00000")
    assert codes(inv) == set()
