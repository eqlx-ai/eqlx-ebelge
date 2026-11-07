import io
import zipfile

import pytest

from eqlx_ebelge import EbelgeError, Limits, iter_documents, read_invoices, read_ledger, scan
from eqlx_ebelge.synthetic import demo_files

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&lol2;</Invoice>"""

XXE = b"""<?xml version="1.0"?>
<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&secret;</Invoice>"""


@pytest.mark.parametrize("payload", [BILLION_LAUGHS, XXE])
def test_dtd_and_entities_are_refused(payload):
    for reader in (read_invoices, read_ledger):
        with pytest.raises(EbelgeError) as e:
            reader(payload)
        assert e.value.code == "unsafe_xml"


def test_malformed_xml():
    with pytest.raises(EbelgeError) as e:
        read_invoices(b"<Invoice><unclosed></Invoice>")
    assert e.value.code == "bad_xml"


def test_unreadable_file_does_not_stop_the_scan(tmp_path):
    for name, data in demo_files().items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "evil.xml").write_bytes(XXE)
    (tmp_path / "truncated.xml").write_bytes(demo_files()["fatura_01.xml"][:600])
    (tmp_path / "other.xml").write_bytes(b"<note>hello</note>")
    rep = scan([tmp_path])
    assert len(rep.invoices) == 9 and len(rep.ledgers) == 1
    by_code = {f.code: set() for f in rep.findings}
    for f in rep.findings:
        by_code[f.code].add(f.source.rsplit("/", 1)[-1])
    assert by_code["unreadable"] == {"evil.xml", "truncated.xml"}
    assert by_code["unsupported"] == {"other.xml"}


def test_zip_bomb_ratio_is_refused(tmp_path):
    z = tmp_path / "bomb.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.xml", b"<a>" + b" " * 5_000_000 + b"</a>")
    docs = list(iter_documents([z]))
    assert docs[0].kind == "unreadable" and docs[0].root.startswith("zip_ratio")


def test_zip_with_documents_and_size_limit(tmp_path):
    files = demo_files()
    z = tmp_path / "set.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(f"inner/{name}", data)
        zf.writestr("readme.txt", "not xml, ignored")
    docs = list(iter_documents([z]))
    assert len(docs) == len(files) and all("!" in d.name for d in docs)
    tiny = list(iter_documents([z], Limits(max_total_mb=0)))
    assert all(d.kind == "unreadable" for d in tiny)


def test_not_a_zip(tmp_path):
    p = tmp_path / "fake.zip"
    p.write_bytes(b"nope")
    assert next(iter(iter_documents([p]))).root.startswith("bad_zip")


def test_missing_path():
    with pytest.raises(EbelgeError):
        list(iter_documents(["/definitely/not/here"]))


def test_bytesio_ledger_stream():
    lg = read_ledger(io.BytesIO(demo_files()["edefter_2026_10_yevmiye.xml"]))
    assert len(lg.entries) == 7
