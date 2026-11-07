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
- **Not every UBL-TR profile is exercised.** Tests cover TEMELFATURA/TICARIFATURA sales invoices,
  individuals, the e-Arşiv placeholder TCKN, withholding (tevkifat) and GİB envelopes. Export, public
  sector, energy and other special profiles are read with the same rules but not specifically tested.
- **Findings are signals, not decisions.** A warning is a reason to look, not proof of fraud. Legal,
  tax and credit decisions stay with qualified people.
- **Memory.** A journal file is read entry by entry, but the kept lines stay in memory (about 5 million
  lines by default, `max_lines`).
