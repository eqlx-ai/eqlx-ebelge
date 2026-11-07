import csv
import io
import json

from eqlx_ebelge.cli import main


def run(capsys, *args):
    code = main(list(args))
    return code, capsys.readouterr().out


def test_sample_check_invoices_mizan(tmp_path, capsys):
    d = str(tmp_path / "demo")
    code, out = run(capsys, "sample", d)
    assert code == 0 and "10 synthetic files" in out

    code, out = run(capsys, "check", d)
    assert code == 1  # the demo set has errors on purpose
    for c in ("tax_id_check_digit", "payable", "possible_duplicate"):
        assert c in out

    code, out = run(capsys, "check", d, "--json")
    data = json.loads(out)
    assert data["summary"]["invoices"] == 9 and data["summary"]["findings"]["error"] == 2

    code, out = run(capsys, "invoices", d, "--csv")
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0][0] == "number" and len(rows) == 10

    code, out = run(capsys, "mizan", d, "--json")
    rows = json.loads(out)
    assert sum(float(r["debit"]) for r in rows) == sum(float(r["credit"]) for r in rows)
    code, out = run(capsys, "mizan", d)
    assert "TOTAL" in out and "KASA" in out


def test_clean_folder_exits_zero(tmp_path, capsys, spec):
    from eqlx_ebelge.synthetic import make_invoice

    (tmp_path / "a.xml").write_bytes(make_invoice(spec))
    code, out = run(capsys, "check", str(tmp_path))
    assert code == 0 and "0 errors" in out


def test_mizan_without_ledgers(tmp_path, capsys):
    assert main(["mizan", str(tmp_path)]) == 1
