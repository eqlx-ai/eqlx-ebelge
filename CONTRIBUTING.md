# Contributing to eqlx-ebelge

Thanks for helping. Bug reports, new checks, support for more UBL-TR profiles and documentation fixes
are all welcome.

## Ground rules

1. **Never share real documents.** No real invoices, ledgers, tax ids or company names in issues,
   tests or examples. Describe the structure, or reproduce it with `eqlx_ebelge.synthetic`.
2. **Public formats only.** Work from GİB's published guides and the UBL 2.1 / XBRL GL standards. Do not
   bundle GİB schema packages or third-party code.
3. **Safe by default.** No network access, no writing files outside what the user asked for, no new
   parser that accepts DTDs or external entities.
4. **Every check is tested** on a synthetic document that triggers it and one that does not.
5. **Dependencies:** `defusedxml` for the core, `mcp` for the server. Propose anything else in an
   issue first.

## Workflow

1. Open an issue first for anything larger than a small fix.
2. Fork, create a branch (`fix/...`, `feat/...`), and run the checks locally:

   ```bash
   uv sync --all-extras
   uv run pytest
   uv run ruff check . && uv run ruff format --check . && uv run mypy src
   ```

3. Open a pull request against `main` and fill in the template. CI must pass before review; for
   outside contributors a maintainer approves the CI run.

By contributing you agree that your contribution is licensed under the Apache License 2.0.

Questions: open an issue or write to research@eqlx.ai.
