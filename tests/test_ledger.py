from datetime import date
from decimal import Decimal

import pytest

from eqlx_ebelge import EbelgeError, check_ledger, read_ledger, trial_balance
from eqlx_ebelge.synthetic import EntrySpec, demo_files, make_ledger

D = Decimal
OCT = (date(2026, 10, 1), date(2026, 10, 31))


def ledger(entries, **kw):
    args = {"tax_id": "4477127820", "title": "ÖRNEK A.Ş.", "period_start": OCT[0], "period_end": OCT[1]}
    args.update(kw)
    return make_ledger(entries=entries, **args)


BASIC = [
    EntrySpec(date(2026, 10, 1), [("102.01", D("1000.00"), "D"), ("500", D("1000.00"), "C")]),
    EntrySpec(
        date(2026, 10, 2),
        [("153", D("300.00"), "D"), ("191", D("60.00"), "D"), ("320.007", D("360.00"), "C")],
    ),
    EntrySpec(date(2026, 10, 3), [("320.007", D("360.00"), "D"), ("102.01", D("360.00"), "C")]),
]


def codes(findings, severity=None):
    return {f.code for f in findings if severity is None or f.severity == severity}


def test_reads_header_entries_and_lines():
    lg = read_ledger(ledger(BASIC), "y.xml")
    h = lg.header
    assert (h.tax_id, h.title, h.entries_type) == ("4477127820", "ÖRNEK A.Ş.", "journal")
    assert (h.period_start, h.period_end, h.fiscal_end) == (OCT[0], OCT[1], date(2026, 12, 31))
    assert [e.counter for e in lg.entries] == [1, 2, 3]
    ln = lg.entries[1].lines[2]
    assert (ln.account, ln.sub_account, ln.account_name, ln.amount, ln.side) == (
        "320",
        "320.007",
        "SATICILAR",
        D("360.00"),
        "C",
    )
    assert lg.entries[1].total_debit == D("360.00")
    assert check_ledger(lg) == []


def test_trial_balance_by_hand():
    rows = {r.account: r for r in trial_balance(read_ledger(ledger(BASIC)))}
    assert (rows["102"].debit, rows["102"].credit, rows["102"].debit_balance) == (D(1000), D(360), D(640))
    assert rows["320"].debit == rows["320"].credit == D(360) and rows["320"].credit_balance == 0
    assert rows["500"].credit_balance == D(1000)
    assert sum(r.debit for r in rows.values()) == sum(r.credit for r in rows.values()) == D(1720)
    sub = {r.account for r in trial_balance(read_ledger(ledger(BASIC)), level="sub")}
    assert sub == {"102.01", "153", "191", "320.007", "500"}


def test_trial_balance_over_several_months():
    oct_, nov = (
        read_ledger(ledger(BASIC)),
        read_ledger(
            ledger(
                [EntrySpec(date(2026, 11, 2), [("770", D("50.00"), "D"), ("102.01", D("50.00"), "C")])],
                period_start=date(2026, 11, 1),
                period_end=date(2026, 11, 30),
                first_counter=4,
            )
        ),
    )
    rows = {r.account: r for r in trial_balance([oct_, nov])}
    assert rows["102"].debit_balance == D(590) and rows["770"].debit == D(50)


def test_unbalanced_entry():
    bad = [*BASIC, EntrySpec(date(2026, 10, 9), [("770", D("10.00"), "D"), ("100", D("9.00"), "C")])]
    assert codes(check_ledger(read_ledger(ledger(bad))), "error") == {"entry_unbalanced", "ledger_unbalanced"}


def test_header_total_mismatch():
    bad = [
        *BASIC,
        EntrySpec(date(2026, 10, 9), [("770", D(10), "D"), ("100", D(10), "C")], total_debit=D(99)),
    ]
    assert codes(check_ledger(read_ledger(ledger(bad)))) == {"entry_total"}


def test_counter_gap_and_repeat():
    xml = ledger(BASIC)
    gap = xml.replace(
        b'entryNumberCounter contextRef="journal_context">3<',
        b'entryNumberCounter contextRef="journal_context">5<',
    )
    assert codes(check_ledger(read_ledger(gap))) == {"counter_gap"}
    rep = xml.replace(
        b'entryNumberCounter contextRef="journal_context">3<',
        b'entryNumberCounter contextRef="journal_context">2<',
    )
    assert codes(check_ledger(read_ledger(rep))) == {"counter_repeat"}


def test_date_outside_period_and_bad_tax_id():
    bad = [*BASIC, EntrySpec(date(2026, 11, 3), [("770", D(1), "D"), ("100", D(1), "C")])]
    assert codes(check_ledger(read_ledger(ledger(bad)))) == {"date_outside_period"}
    assert codes(check_ledger(read_ledger(ledger(BASIC, tax_id="4477127821")))) == {"tax_id_check_digit"}


def test_foreign_currency_unit_is_refused():
    xml = ledger(BASIC).replace(b"iso4217:TRY", b"iso4217:USD")
    with pytest.raises(EbelgeError) as e:
        read_ledger(xml)
    assert e.value.code == "foreign_currency"


def test_not_a_ledger(spec):
    from eqlx_ebelge.synthetic import make_invoice

    with pytest.raises(EbelgeError) as e:
        read_ledger(make_invoice(spec))
    assert e.value.code == "not_a_ledger"


def test_line_budget():
    with pytest.raises(EbelgeError) as e:
        read_ledger(ledger(BASIC), max_lines=5)
    assert e.value.code == "too_many_lines"


def test_demo_journal_is_clean_and_balanced():
    lg = read_ledger(demo_files()["edefter_2026_10_yevmiye.xml"])
    assert check_ledger(lg) == []
    rows = trial_balance(lg)
    assert sum(r.debit_balance for r in rows) == sum(r.credit_balance for r in rows)
