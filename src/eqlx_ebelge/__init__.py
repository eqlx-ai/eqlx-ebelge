"""eqlx-ebelge: read Turkish e-Fatura (UBL-TR) and e-Defter (XBRL GL) files.

Clean data, a trial balance, and consistency checks, all locally. An optional MCP server lets AI agents use
the same functions read-only.
"""

__version__ = "0.1.0"

from .errors import EbelgeError, Finding
from .ids import is_valid_tax_id, is_valid_tckn, is_valid_vkn
from .invoice import Invoice, check_invoice, find_duplicates, read_invoice, read_invoices
from .ledger import Ledger, TrialBalanceRow, check_ledger, read_ledger, trial_balance
from .report import Report, scan
from .sources import Document, Limits, iter_documents

__all__ = [
    "Document",
    "EbelgeError",
    "Finding",
    "Invoice",
    "Ledger",
    "Limits",
    "Report",
    "TrialBalanceRow",
    "__version__",
    "check_invoice",
    "check_ledger",
    "find_duplicates",
    "is_valid_tax_id",
    "is_valid_tckn",
    "is_valid_vkn",
    "iter_documents",
    "read_invoice",
    "read_invoices",
    "read_ledger",
    "scan",
    "trial_balance",
]
