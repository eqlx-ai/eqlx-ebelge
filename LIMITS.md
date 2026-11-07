# Limits

What eqlx-ebelge does **not** do in version 0.1. Read this before relying on it.

- **No signature check.** It does not verify the electronic signature or the GİB seal on an invoice or
  a ledger. A file that passes every check can still be forged.
- **No schema or Schematron validation.** GİB's XSD and Schematron packages are not bundled. The checks
  are arithmetic and structural; they are not GİB's own validation.
- **No GİB or portal access.** It cannot tell whether an invoice was really registered, cancelled or
  rejected. Duplicate detection only sees the files you give it.
- **Invoices in TRY.** Foreign-currency invoices are read, but the checks do not convert currencies.
  e-Defter amounts must be in TRY; another unit is refused.
- **e-Defter journal and ledger files only.** Berat (seal) files and the e-Defter report (defter raporu)
  are not read. The trial balance is built from the entries; opening and closing entries are included
  as they appear.
- **Checked against GİB's public samples, not against every issuer.** The totals checks accept the
  writing variants seen in GİB's sample invoices: exemptions (istisna) that show or charge the tax,
  stopaj deducted from the payable amount, withholding (tevkifat) with the tax total before or after the
  withheld part, HKS market charges, and line totals written before discounts. Other issuers may write
  totals in ways not yet seen; please report them.
- **e-Defter journal (yevmiye) and general ledger (kebir) only.** In a kebir, entries are read per
  account. Other e-Defter types (e.g. the 2026 assets book) are reported as unsupported.
- **Findings are signals, not decisions.** A warning is a reason to look, not proof of fraud. Legal,
  tax and credit decisions stay with qualified people.
- **Memory.** A journal file is read entry by entry, but the kept lines stay in memory (about 5 million
  lines by default, `max_lines`).
