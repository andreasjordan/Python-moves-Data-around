---
description: Repo-specific Python review for lib/, demo/ and the notebooks
---

Review $ARGUMENTS. If no argument is given, review the working diff against `main`; if that is empty,
review `lib/`.

Read `AGENTS.md` first. This is a teaching repository, not production code, and a generic Python review
of it produces mostly false positives.

## Do not report

These are deliberate. Reporting them is noise:

- The hard-coded password `Passw0rd!`, the hard-coded `127.0.0.1`, and `TrustServerCertificate=yes`
- Missing tests, missing CI, missing packaging, missing type hints, missing docstrings
- "Use SQLAlchemy", "use `pandas.read_sql`", "use `DataFrame.to_sql`" — hand-written DB-API code is
  the demo
- `except Exception` and `raise Exception(...)` — that is the `enable_exception` contract
- Committed notebook outputs, and cells whose last line is a bare variable name
- Imports repeated in a later notebook cell, code commented out on purpose (`os.startfile`,
  `DROP TABLE`), and variables that are only inspected interactively
- The `.ps1` files that are still the sibling repository's, and the `powershell-moves-data-around`
  compose project name — these are listed as known state in `AGENTS.md`

## Do report, in this order

1. **Contract divergence inside `lib/`.** Every function takes `enable_exception=False` and, on
   failure, either raises or prints `[ERROR]` and returns `None`. A function that raises
   unconditionally, omits the parameter, or returns after a failure without `return None` is a
   finding. Say which of the three other `lib/` functions it should have matched.
2. **Divergence from the PowerShell sibling.** The counterpart lives in
   `../PowerShell-moves-Data-around/lib/`. A parameter, default value, guard clause or cleanup block
   present there and missing here is a finding unless the difference is inherent to Python.
3. **Resources not released on every path** — a cursor, connection or file handle that is only closed
   on the success path, or not at all.
4. **SQL built by string interpolation from anything other than schema-derived, quoted identifiers.**
   Values must go through `?` placeholders. This is the one security rule that does apply.
5. **Silent data corruption in the pandas paths** — `reindex` dropping or inventing columns, an
   `assign` that depends on a column the source may not have, `NaT`/`NaN` reaching the database as
   something other than `NULL`, dtype changes across `concat`.
6. **Encoding and platform traps** — non-ASCII printed from code that may run in a `cp1252` console,
   `r"..\path"` backslash paths in code that is also meant to run under WSL2, `os.startfile` outside a
   comment.
7. **Notebook damage** — cleared or mismatched outputs, a cell that can no longer run standalone in
   order, `sys.path` set up after the import that needs it.
8. **Drift between the docs and the code** — `README.md`, `AGENTS.md`, `lib/README.md` and
   `data/*/README.md` versus what the code actually does.
9. **Ruff findings** under `./ruff.toml`. Run `python -m ruff check .` and cite the rule code. If ruff
   is not installed, say so instead of guessing what it would report.

## Rules

- Verify each finding by reading the code before reporting it. Say what concrete input or state
  produces the wrong behaviour.
- Do not run any container, WSL command, or notebook.
- Report findings only. Do not edit files unless explicitly asked to afterwards.
