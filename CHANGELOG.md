# Changelog

## 0.1.0 (unreleased)

- Read e-Fatura / e-Arşiv invoices (UBL-TR 1.2), single files and GİB envelopes.
- Read e-Defter journal and ledger files (XBRL GL), streaming, TRY only.
- Checks: tax ids, invoice number and ETTN format, line, tax and total arithmetic, withholding,
  duplicates across files; journal entry balance, header totals, counters, dates, file balance.
- Trial balance (mizan) by main or sub-account, across several files.
- Files, folders and ZIP archives with size, count and compression-ratio limits.
- Command line `ebelge` and a read-only MCP server.
- Synthetic document generator for tests and demos.
