# Changelog

## 0.1.1

Run against GİB's public sample packages; fixed false alarms they revealed.

- Totals checks accept the UBL-TR variants found in GİB's samples: exempt taxes shown but not charged
  (and those charged then refunded), stopaj (0003, 0011) deducted from payable, tevkifat with a net tax
  total, HKS market charges, LineExtensionAmount written before discounts.
- Kebir (general ledger) files are checked per account; header totals may be net balances.
- Envelopes without invoices (system and application responses) and other e-Defter types are reported
  as `unsupported` (info) instead of `unreadable`.
- Optional test against local GİB samples (`EBELGE_GIB_SAMPLES`).

## 0.1.0

- Read e-Fatura / e-Arşiv invoices (UBL-TR 1.2), single files and GİB envelopes.
- Read e-Defter journal and ledger files (XBRL GL), streaming, TRY only.
- Checks: tax ids, invoice number and ETTN format, line, tax and total arithmetic, withholding,
  duplicates across files; journal entry balance, header totals, counters, dates, file balance.
- Trial balance (mizan) by main or sub-account, across several files.
- Files, folders and ZIP archives with size, count and compression-ratio limits.
- Command line `ebelge` and a read-only MCP server.
- Synthetic document generator for tests and demos.
