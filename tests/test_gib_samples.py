"""Optional: run against GİB's public sample packages when they are available locally.

GİB's samples are not redistributed here. To run, point EBELGE_GIB_SAMPLES at a folder holding them, e.g.
the extracted e-Fatura and e-Defter packages from ebelge.gib.gov.tr.
"""

import os
from pathlib import Path

import pytest

from eqlx_ebelge import scan

ROOT = os.environ.get("EBELGE_GIB_SAMPLES")
pytestmark = pytest.mark.skipif(not ROOT, reason="EBELGE_GIB_SAMPLES not set")


def test_official_samples_read_without_false_alarms():
    rep = scan([Path(ROOT or ".")])
    assert rep.invoices or rep.ledgers, "no invoices or ledgers found"
    # every file is either read, reported as unsupported, or genuinely malformed XML
    unreadable = [f for f in rep.findings if f.code == "unreadable"]
    assert all(f.message.startswith("bad_xml") for f in unreadable)
    # journals in the official e-Defter package balance; ledgers (kebir) are read by account
    assert not [f for f in rep.findings if f.code in ("entry_unbalanced", "ledger_unbalanced", "entry_total")]
