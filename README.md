# eqlx-ebelge

[![PyPI](https://img.shields.io/pypi/v/eqlx-ebelge)](https://pypi.org/project/eqlx-ebelge/) [![CI](https://github.com/eqlx-ai/eqlx-ebelge/actions/workflows/ci.yml/badge.svg)](https://github.com/eqlx-ai/eqlx-ebelge/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Read Turkish **e-Fatura** (UBL-TR) and **e-Defter** (XBRL GL) files: clean data, a trial balance
(mizan), and consistency checks that catch wrong totals, invalid tax ids, duplicate invoices and
unbalanced journal entries. An optional **MCP server** lets AI agents such as Claude use the same
functions, read-only.

Built by [eqlx](https://eqlx.ai). Part of [eqlx.org](https://eqlx.org), open research and tools.

> Status: alpha (0.1.1). Tested on synthetic documents and checked against GİB's public sample
> packages (e-Fatura, e-Arşiv, e-Defter): on those samples it raises no false alarms, and the
> findings it does raise are real inconsistencies in the samples. Please report any real-world file it
> reads wrongly (without sending the file itself).

## Why

Lenders, factoring companies and finance teams receive invoices and ledgers as GİB XML and still read
them by hand or through paid tools. This library turns them into data you can check and analyse,
locally, with no network access.

## Install

```bash
pip install "eqlx-ebelge[mcp]"
```

Python 3.10+. The core needs only `defusedxml`; `[mcp]` adds the MCP server.

## Command line

```bash
ebelge sample demo          # write 10 synthetic files to try it on
ebelge check demo           # every check, on files, folders or ZIP archives
ebelge invoices demo --csv  # one row per invoice
ebelge mizan demo           # trial balance from e-Defter journals (add --level sub)
```

```text
$ ebelge check demo
10 documents: 9 invoices, 1 ledger files (7 entries). 2 errors, 1 warnings, 0 info.

severity  code                file                         message
error     payable             fatura_08_toplam_hatali.xml  TaxInclusiveAmount - withholding + rounding = 4682.88, PayableAmount is 99999.99 (gap 95317.11)
error     tax_id_check_digit  fatura_09_vkn_hatali.xml     supplier VKN 4477127821 fails its check digit
warning   possible_duplicate  fatura_02.xml                supplier 4477127820, same customer, 2026-10-07, payable 10140.12: EQX2026000000002 (fatura_02.xml), EQX2026000000007 (fatura_07.xml)

$ ebelge mizan demo
account  name             debit      credit     debit_bal  credit_bal
100      KASA             10000.00   8500.00    1500.00    0
102      BANKALAR         560000.00  10000.00   550000.00  0
120      ALICILAR         90000.00   60000.00   30000.00   0
...
```

`ebelge check` exits with code 1 when it finds an error, so it can gate a pipeline.

## Python

```python
from pathlib import Path
import eqlx_ebelge as eb

inv = eb.read_invoice(Path("fatura.xml").read_bytes(), "fatura.xml")
inv.supplier.tax_id, inv.totals.payable, [line.name for line in inv.lines]
eb.check_invoice(inv)  # list of Finding(code, severity, message, ...)

report = eb.scan(["inbox/", "archive.zip"])  # every document, every check, duplicates across all
report.summary()

ledgers = [eb.read_ledger(p.read_bytes(), p.name) for p in sorted(Path("edefter").glob("*.xml"))]
rows = eb.trial_balance(ledgers)  # e.g. twelve monthly journals -> one year's mizan
```

Amounts are `Decimal`, never floats.

## Checks

| Code | Severity | What it catches |
|---|---|---|
| `tax_id_check_digit`, `tax_id_length`, `tax_id_missing` | error | VKN or TCKN that fails its check digit, has the wrong length, or is missing |
| `lines_total` | error | invoice lines do not add up to `LineExtensionAmount` |
| `tax_total`, `tax_inclusive` | error | tax subtotals or the tax-inclusive total do not add up |
| `payable` | error above 1 TRY, else warning | payable amount differs from tax-inclusive total minus withholding (tevkifat) |
| `line_amount`, `tax_rate` | warning | quantity x price - discount, or base x rate, differs from what the line or tax says |
| `number_format`, `number_year`, `uuid_format` | warning | invoice number is not 3 characters + year + 9 digits, its year differs from the date, malformed ETTN |
| `duplicate_uuid`, `duplicate_number` | error | the same ETTN, or the same supplier and number, appears more than once |
| `possible_duplicate` | warning | same supplier, customer, date and amount under different numbers |
| `entry_unbalanced`, `entry_total`, `ledger_unbalanced` | error | a journal entry, its header totals, or the whole file do not balance |
| `counter_repeat` / `counter_gap` | error / warning | journal entry counters repeat or skip |
| `date_outside_period` | warning | an entry dated outside the period the file covers |
| `placeholder_tckn`, `same_party`, `account_code`, `unsupported` | info | context worth knowing |
| `unreadable` | error | a file that is malformed or unsafe to parse |

Tolerances: one kuruş per comparison, plus half a kuruş per line where per-line rounding adds up.

## MCP server (for Claude and other agents)

The server exposes four read-only tools: `list_documents`, `check`, `read_invoices` and
`trial_balance`. It reads only inside the folder you give it; `..`, absolute paths and symlinks that
point outside are refused.

Claude Code:

```bash
claude mcp add ebelge -- ebelge mcp --root /path/to/invoices
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ebelge": { "command": "ebelge", "args": ["mcp", "--root", "/path/to/invoices"] }
  }
}
```

Then ask, for example: *"Bu klasördeki faturaları kontrol et, sorunlu olanları ve mükerrerleri göster."*

## Safety and privacy

- Runs locally. No network access, no telemetry.
- XML with a DOCTYPE is refused, which blocks entity-expansion and external-entity (XXE) attacks.
- ZIP archives are read in memory with limits on size, file count and compression ratio.
- From e-Defter it keeps only what the checks and the trial balance need; entry comments, document
  numbers and people's names are not read.
- Tests use synthetic documents only. `ebelge sample` writes the same kind of made-up files.

See [LIMITS.md](LIMITS.md) for what it does not do.

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). GİB schemas are not included.
