import dataclasses
from decimal import Decimal

import pytest

from eqlx_ebelge import EbelgeError, check_invoice, find_duplicates, read_invoice, read_invoices
from eqlx_ebelge.ids import PLACEHOLDER_TCKN
from eqlx_ebelge.synthetic import make_envelope, make_invoice

D = Decimal


def codes(findings, severity=None):
    return {f.code for f in findings if severity is None or f.severity == severity}


def test_reads_fields_and_hand_computed_totals(spec):
    inv = read_invoice(make_invoice(spec), "a.xml")
    assert inv.number == "EQX2026000000001"
    assert inv.uuid == spec.uuid
    assert str(inv.issue_date) == "2026-10-04"
    assert (inv.profile, inv.type_code, inv.currency) == ("TICARIFATURA", "SATIS", "TRY")
    assert inv.supplier.tax_id == spec.supplier_vkn and inv.supplier.scheme == "VKN"
    assert inv.supplier.name == "Örnek Metal Sanayi A.Ş."
    assert inv.customer.city == "Ankara"
    assert len(inv.lines) == 2 and inv.line_count == 2
    l2 = inv.lines[1]
    assert (l2.quantity, l2.price, l2.allowance, l2.amount) == (D(1), D(1000), D("100.00"), D("900.00"))
    assert inv.totals.line_extension == D("2754.00")
    assert inv.tax_total == D("550.80")
    assert inv.totals.tax_inclusive == D("3304.80")
    assert inv.totals.payable == D("3304.80")
    assert inv.taxes[0].percent == D(20) and inv.taxes[0].type_code == "0015"
    d = inv.to_dict()
    assert d["totals"]["payable"] == "3304.80" and d["issue_date"] == "2026-10-04"


def test_clean_invoice_has_no_findings(spec):
    assert check_invoice(read_invoice(make_invoice(spec))) == []


def test_tampered_payable_is_an_error(spec):
    spec.payable_override = D("9999.99")
    f = check_invoice(read_invoice(make_invoice(spec)))
    assert codes(f, "error") == {"payable"}


def test_small_payable_gap_is_only_a_warning(spec):
    spec.payable_override = D("3304.30")
    assert codes(check_invoice(read_invoice(make_invoice(spec))), "warning") == {"payable"}


def test_tampered_line_amount(spec):
    xml = make_invoice(spec).replace(
        b'<cbc:LineExtensionAmount currencyID="TRY">900.00</cbc:LineExtensionAmount>',
        b'<cbc:LineExtensionAmount currencyID="TRY">990.00</cbc:LineExtensionAmount>',
    )
    f = check_invoice(read_invoice(xml))
    assert "lines_total" in codes(f, "error")
    assert "line_amount" in codes(f, "warning")


def test_tampered_tax_amounts(spec):
    xml = make_invoice(spec).replace(
        b'<cbc:TaxAmount currencyID="TRY">550.80</cbc:TaxAmount>',
        b'<cbc:TaxAmount currencyID="TRY">450.80</cbc:TaxAmount>',
    )
    f = check_invoice(read_invoice(xml))
    assert {"tax_rate", "tax_inclusive"} <= codes(f)


def test_bad_supplier_vkn(spec):
    spec.supplier_vkn = spec.supplier_vkn[:-1] + "9"
    assert codes(check_invoice(read_invoice(make_invoice(spec))), "error") == {"tax_id_check_digit"}


def test_individual_customer_and_placeholder(spec):
    spec.customer_id, spec.customer_name = "10000000146", "Ayşe Yılmaz"
    inv = read_invoice(make_invoice(spec))
    assert inv.customer.scheme == "TCKN" and inv.customer.name == "Ayşe Yılmaz"
    assert check_invoice(inv) == []
    spec.customer_id = PLACEHOLDER_TCKN
    assert codes(check_invoice(read_invoice(make_invoice(spec)))) == {"placeholder_tckn"}


def test_number_format_and_year(spec):
    spec.number = "EQX2025000000001"
    assert codes(check_invoice(read_invoice(make_invoice(spec)))) == {"number_year"}
    spec.number = "INV-1"
    assert codes(check_invoice(read_invoice(make_invoice(spec)))) == {"number_format"}


def test_withholding_reduces_payable(spec):
    spec.withholding_percent = D(50)
    inv = read_invoice(make_invoice(spec))
    assert inv.withholding_total == D("275.40")
    assert inv.totals.payable == D("3029.40")
    assert check_invoice(inv) == []


def test_envelope_with_several_invoices(spec):
    docs = []
    for n in range(3):
        s = dataclasses.replace(
            spec, number=f"EQX202600000001{n}", uuid=f"00000000-0000-4000-8000-00000000000{n}"
        )
        docs.append(make_invoice(s))
    invs = read_invoices(make_envelope(docs), "env.xml")
    assert [i.number for i in invs] == ["EQX2026000000010", "EQX2026000000011", "EQX2026000000012"]
    assert invs[0].source == "env.xml#1"
    with pytest.raises(EbelgeError):
        read_invoice(make_envelope(docs))


def test_duplicates(spec):
    a = read_invoice(make_invoice(spec), "a.xml")
    same_uuid = read_invoice(make_invoice(dataclasses.replace(spec, number="EQX2026000000002")), "b.xml")
    same_number = read_invoice(
        make_invoice(dataclasses.replace(spec, uuid="11111111-2222-4333-8444-555555555555")), "c.xml"
    )
    lookalike = read_invoice(
        make_invoice(
            dataclasses.replace(spec, number="EQX2026000000099", uuid="21111111-2222-4333-8444-555555555555")
        ),
        "d.xml",
    )
    assert codes(find_duplicates([a, same_uuid])) == {"duplicate_uuid"}
    assert codes(find_duplicates([a, same_number])) == {"duplicate_number"}
    assert codes(find_duplicates([a, lookalike])) == {"possible_duplicate"}
    other = dataclasses.replace(
        spec,
        number="EQX2026000000050",
        uuid="31111111-2222-4333-8444-555555555555",
        payable_override=D("1.00"),
    )
    assert find_duplicates([a, read_invoice(make_invoice(other))]) == []


def test_not_an_invoice():
    with pytest.raises(EbelgeError) as e:
        read_invoices(b"<root/>")
    assert e.value.code == "not_an_invoice"


def test_amount_with_thousands_separator_is_rejected(spec):
    xml = make_invoice(spec).replace(b">3304.80<", b">3,304.80<", 1)
    with pytest.raises(EbelgeError) as e:
        read_invoice(xml)
    assert e.value.code == "bad_amount"
