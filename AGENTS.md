# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this repository is

A teaching and demo repository that accompanies talks and videos: infrastructure as code, sample data
and demo code showing how Python can move data around. It is deliberately **not production code**
(see `README.md`).

It is the sibling of [PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around),
and it is being built by porting that repository scenario by scenario. The two are presented side by
side in one session, so **a Python function is expected to read like a recognisable translation of its
PowerShell counterpart, not like idiomatic-at-any-cost Python.** Where Python genuinely wants something
different — a DataFrame instead of an array of objects, a context manager instead of `finally` — that
difference is itself part of the talk and worth making visible.

**Prime directive:** optimize every change for *readability while being shown on a projector*, not for
robustness, genericity or production hardening. If a change makes the code shorter and clearer, it is
probably right. If it adds abstraction, indirection or defensive layers, it is probably wrong.

## Current state — read this before assuming anything works

**Three scenarios are complete: Timesheets, StackExchange and Geodata.** StackExchange imports the
files into SQL Server, PostgreSQL, Oracle and MongoDB and streams between the three relational ones;
Geodata moves GPX and GeoJSON geometry into all three through WKT. MinIO was dropped on purpose and is
not coming — see `DIFFERENCES.md`.

**PhotoService is complete.** Binary JPEGs into PostgreSQL and on into SQL Server, incremental
transfers against the running application, transactions, and CDC. See "The PhotoService port" below.

**ProjectStatus is complete.** One Excel form into SQL Server, where four of the eight rows are
rejected and the scenario is about what you do next. It needed no new `lib/` function. See "The
ProjectStatus port" below.

**With that, every scenario of the sibling repository is ported.** What is left is a short list of
bonus sections that were each left out for a stated reason — see "What is left to port".

| Area | State |
| --- | --- |
| `demo/01_timesheets.ipynb` | Works, end to end, against a running SQL Server container. |
| `demo/02_stackexchange.ipynb` | Reading the XML files, importing them into SQL Server, PostgreSQL and Oracle, streaming table to table, and a MongoDB bonus section at the end. Stepped through end to end, outputs committed. Complete, apart from the sibling's Azure SQL bonus. |
| `demo/03_geodata.ipynb` | GPX and GeoJSON into SQL Server, PostgreSQL/PostGIS and Oracle Spatial, through WKT. Stepped through end to end, outputs committed. Complete apart from the Mauttabelle bonus, which was left out on purpose. **One caveat:** the `ORA-13199` counts near the end are not reproducible — re-running the notebook will print different numbers, so the narration deliberately names no single count. |
| `demo/04_photoservice.ipynb` | JPEGs into PostgreSQL `bytea` and on into SQL Server `VARBINARY(MAX)`, then incremental transfers against the running application, transactions, and CDC. Stepped through end to end, outputs committed. Complete, apart from the sibling's MinIO and Azure sections. **The order counts are not reproducible** — the application keeps writing, so every run prints different numbers, and no narration quotes one. |
| `lib/` | Eighteen functions: `connect`, `invoke`, `write`, `import` and `get_*_data_reader` for `sql`, `ora` and `pg`, plus `connect`, `write` and `read` for `mdb`. The `mio` column is empty by decision, not as a to-do. The six `invoke_*_query` and `write_*_table` functions grew `commit=True` for PhotoService. |
| `demo/05_projectstatus.ipynb` | One Excel form into SQL Server, where four of the eight rows are rejected for four different reasons. Stepped through end to end, outputs committed. Complete. **Reproducible**, unlike the other four — the sample data is fixed, so the narration quotes its counts. |
| `docker/` | Complete. `sqlserver-projectstatus.sql` had been missing and was added, so all five scenarios' databases are created. `photoservice-app.ps1` has been replaced by `photoservice-app.py`. |
| The setup chain | Ported to Python and verified end to end against a clean WSL2. `01_setup.ps1` is the only remaining PowerShell file, because it is what Windows starts. |
| The charts in `Report.xlsx` | **Open, and parked on purpose.** The pie and bar chart that the last cells of `demo/01_timesheets.ipynb` create are correct but do not look good enough yet. Do not polish them as a side effect of another task — see below. |
| `docker/photoservice-app.py` | The ported application, running as the `photoservice` service on a stock `python:3.13-slim` image. It mounts `lib/` and installs `pandas`, `psycopg[binary]` and `pymongo` when the container starts. It is the source of everything the second half of scenario 4 transfers, so **that half of the notebook is empty unless this container is running.** |
| `05_sample_data_setup.py` | Timesheets, the StackExchange download, the Geodata downloads and the ProjectStatus Excel. PhotoService needs no block — its photos are committed. The sibling's upload of those files to MinIO has no counterpart and will not get one. |
| `06_test_connections.py` | Timesheets on SQL Server, StackExchange on SQL Server, Oracle, PostgreSQL and MongoDB, Geodata on SQL Server, Oracle and PostgreSQL, PhotoService on SQL Server, PostgreSQL and MongoDB, ProjectStatus on SQL Server. One block per scenario and per provider. **Its MongoDB block will fail inside WSL2** unless `03_python_setup.sh` has been re-run since `pymongo` was added to it. |

Do not "discover" these as new findings and do not fix them as a side effect of an unrelated task.
They are known, and each one is a decision the repository owner has not made yet.

**When something is wrong in the sibling repository, append an entry to `SIBLING-FINDINGS.md`** rather
than fixing it there. That file is the work list for a session opened in the PowerShell repository, and
each entry records whether this repository — which inherited `docker/` verbatim — is already fixed, so
the two do not drift unnoticed.

**When a design decision is made, append an entry to `DIFFERENCES.md`** — what the sibling does, what
Python forced, the evidence, the decision, and what was rejected. That file is the record of *why* the
port looks the way it does, and it is the one place where the rejected alternatives are written down.
Keep the scope: behaviour of a function belongs in `lib/README.md`, rules belong here, narration
belongs in the notebooks.

### The chart formatting in the Timesheets report

The charts are the one part of the Timesheets scenario that is not finished. They render and the
numbers are right, but the appearance has not been settled. When that is picked up, these are the
known approximations, so nobody has to work them out again:

- The sizes are guesses. The sibling passes pixels to `Export-Excel` (300x300 for the pie, 1000x300
  for the bar); openpyxl wants centimetres, so `height`/`width` are set to 10x10 and 26x10.
- The bar chart has about 25 dates as categories, which is where the axis labels get crowded.
- Neither chart has data labels, and the pie chart has no percentages.
- The sibling styles both blocks as an Excel table (`TableStyle Light18`) and uses `AutoSize`. Here the
  column widths are four hard-coded numbers and there is no table style at all.

The data layout is deliberate and should survive any restyling: both results share one worksheet, the
first 19 rows are left free for the charts, and the second block starts at column E. Reading a block
back needs `nrows`, because the two blocks have a different number of rows.

The setup runs Python **inside WSL2**, from a pyenv installation that belongs to the default user
(uid 1000), not to root. Two things follow, and both have already bitten this repository once:

- A script started by `01_setup.ps1` is **not interactive**, and `~/.bashrc` returns immediately when
  it is not. The pyenv initialisation therefore lives in `~/.profile`, and steps 05 and 06 are started
  with `bash -lc` so that a login shell reads it. Never move that initialisation back into `~/.bashrc`
  alone.
- Steps that need Python must **not** run `--user root`. `/root` is `drwx------`, so root's home is
  invisible to the user that owns the pyenv installation.

`04_docker_compose.sh` does not return until SQL Server has created the demo databases. That wait is
load-bearing: `06_test_connections.py` used to fail with an `08001` handshake error because it ran
about four seconds after `docker compose up`. The sibling repository never noticed, because its `05`
spends minutes downloading sample data. Do not check the container log for the init script's
"complete" message instead — `docker logs` keeps the output of earlier runs, so it matches
immediately after a restart. All four databases have their own wait now. Oracle's is a shell
function rather than a one-liner, because `sqlplus` takes its query on stdin, and it gets 15 minutes
instead of 5, because Oracle takes far longer to start than the other two.

## What is left to port

**All five scenarios are ported:** Timesheets, StackExchange, Geodata, PhotoService, ProjectStatus.
MinIO was dropped on purpose. There is no next scenario.

What is left is three bonus sections, each left out for a reason that is written down. Do not treat
them as a backlog — two of them need resources this repository does not have, and the third was a
judgement call.

### Also unported, and undecided

The **Azure SQL bonus** at the end of the sibling's `demo/02_stackexchange.ps1`. It streams a file and a
table into an Azure SQL Database, and needs Azure resources, the `Az` module, a firewall rule and two
environment variables — so it is not local. Nobody has decided whether it belongs. The **MongoDB → Azure
SQL JSON bonus** at the end of `demo/04_photoservice.ps1` is in the same position, for the same reason.

## The ProjectStatus port — finished

One Excel form into one SQL Server table, and the only scenario where the **data is wrong**. The first
four move data that already fits the target; this one is about what you do when four of the eight rows
do not.

**It needed no new `lib/` function and no change to an existing one** — `invoke_sql_query` with
`parameter_values` and `write_sql_table` covered it, which is what the notes here had predicted.

The shape of the demo, which is the sibling's: `write_sql_table` refuses the whole frame and imports
nothing; the rows then go in one at a time; `enable_exception` turns a printed `[ERROR]` into something
the loop can catch, so the failures can be named; the failures are collected with the database's own
message and written back out to an Excel file; and finally the loop retries the one failure it can fix
without guessing, recognising it by the constraint name that comes back in the error.

Four rows fail, for four different reasons, and it is worth knowing which so a changed run is
recognisable: `Late july 2026` in a `DATETIME2`, a `Status` of 79 characters against a `VARCHAR(50)`,
`DarkRed` against the `Color` CHECK constraint, and `unknown` in an `INT`. The colour is the one that
gets retried, so five rows end up in the table and three are handed back.

Two things Python forced, both in `DIFFERENCES.md`: a missing cell is `NaN`, a **float**, so it has to
become `None` before it is bound; and the bulk load fails in a different place than the sibling's, with
a byte-count message that names neither the column nor the row. The second one is left visible on
purpose — it makes the scenario's point better than a tidy message would.

Unlike the other four scenarios, **this one is reproducible**: the sample data is fixed, so the same
run produces the same numbers every time. The narration may quote them.

## The PhotoService port — finished

Binary JPEGs into PostgreSQL and on into SQL Server, then the harder half: transferring only what is
new while an application keeps writing to the source.

**It is the first scenario that needed a change to an existing `lib/` signature.** The six
`invoke_*_query` and `write_*_table` functions now take `commit=True`; with `commit=False` they neither
commit nor roll back, so several calls make up one unit of work. That is the port of the sibling's
`-Transaction`, which could not be ported as a parameter at all, and it is in `DIFFERENCES.md`. Before
it, every function in `lib/` committed unconditionally, so a transaction spanning two calls was
impossible. The three `get_*_data_reader` functions deliberately got nothing.

**The application is a container, and it is not optional.** `docker/photoservice-app.py` replaces the
sibling's `photoservice-app.ps1`, which was still PowerShell here and could never have run. It is the
source of every customer and order the second half of the notebook transfers, so **if that container is
not running, those cells have nothing to find.** It also needs a few minutes of runtime before the
notebook is interesting: the first order is scheduled ten minutes after it starts, the first payment at
fifteen, the first shipment at twenty — the sibling's schedule, kept.

**Left out on purpose, and both follow from decisions already made:**

- The sibling's **"Transfer data from logging (or kafka)"** section and its **MinIO logging bonus**.
  Both read the application's logging archives out of MinIO, which is not ported. The application still
  produces those events — it prints them instead of archiving them — but the demo section that replayed
  them is gone. That is the largest thing the MinIO decision has cost, and it is recorded there.
- The **MongoDB → Azure SQL JSON bonus**, which needs Azure.

**The `04_photoservice_transfer_01.ps1` loop of the sibling has no counterpart** and did not need one:
it is the same transfer as the notebook, wrapped in a `while` loop to run unattended.

## The Geodata port — finished, minus one bonus

GPX and GeoJSON into all three relational systems, through WKT. It needed **no new `lib/` function** —
`invoke_*_query` with `parameter_values` and `write_*_table` already covered it — but it did find three
real defects in functions the earlier scenarios had been using happily. All three are in
`DIFFERENCES.md`: the `::` operator being read as a named parameter, a failed statement leaving a
PostgreSQL connection unusable, and a missing `CLOB` declaration for bind parameters over 4000
characters.

`demo/import_gpx_file.py` is the only new module, next to `import_xls_timesheet.py`.

**Left out on purpose:** the sibling's **Mauttabelle** bonus, which scrapes
`balm.bund.de` for the newest zip file, unpacks it and reads a 137530-row Excel. It is the most
realistic ETL in the sibling and also the most fragile — it breaks whenever that page changes — and
the decision was to skip it rather than carry a scraper. If it is ever wanted, the sibling code is at
the end of `demo/03_geodata.ps1`.

## The StackExchange port — finished

The scenario was built in small steps, deliberately not in the order of the sibling's demo, so that
each step settled one design question: the sample data, reading the XML, the SQL Server import, the
PostgreSQL import, streaming table to table, Oracle, and MongoDB. All of it is done.

**MinIO is not a remaining step — it is out of scope.** It was dropped because MinIO changed its
licence, and because uploading and downloading files is not the question this repository asks. The full
decision, including what it costs, is in `DIFFERENCES.md`. Do not treat the empty `mio` column of the
grid in `lib/README.md` as a gap, and do not offer to fill it.

The one part of the sibling's `demo/02_stackexchange.ps1` with no counterpart here is its **Azure SQL
Database bonus**, which streams a file and a table into an Azure SQL Database. That needs Azure
resources, the `Az` PowerShell module, a firewall rule and two environment variables, so it is not
local and not part of the demo as it is presented. It is unported, and nobody has decided whether it
should be.

## Adding a dependency

`pip install` is on the deny list in `.claude/settings.json`, so an agent cannot install anything. The
owner has to. What an agent **can** and must do, in the same turn as the code that needs it:

1. Add it to the `pip install` line in `03_python_setup.sh` — that is WSL2, where `06` runs.
2. Add it to the pip block in `README.md`, and to the `03_python_setup.sh` row of the setup table there.
3. Add it to the runtime dependency list in the `Loading model` section below.
4. Then tell the owner the exact command to run on Windows, where the notebooks live.

Do not wait to be asked for steps 1 to 3. The owner has had to prompt for it once
("You have not changed the 03_python_setup.sh - so I wait for that to change?") and it should not
happen again.

**Currently known gap:** `pymongo` is in `03_python_setup.sh` but was added after the last WSL2 setup
run. Unless `03_python_setup.sh` has been re-run since, `06_test_connections.py` will fail on its
MongoDB block inside WSL2. The Windows install was done, so the notebooks are fine.

## The sample data on disk

`data/` holds the inputs for the scenarios. Everything generated or downloaded is gitignored, so a
fresh clone has only the `README.md` files, `sample.json` and the PhotoService photos.

`05_sample_data_setup.py` creates or downloads the rest, and **it downloads everything on every run** —
see finding 5 in `SIBLING-FINDINGS.md`, which is open on both sides. The Geodata part pulls about 15 MB,
most of it `countries.geojson`.

Two practical notes for an agent that needs the data present:

- `05` extracts the Berlin GPX archive with `7za`, which exists in WSL2. On Windows the equivalent is
  `C:\Program Files\7-Zip\7z.exe`, which is installed but not on the PATH. A scratchpad script that
  fetches the data for local development has to use the full path.
- A large download run with `run_in_background` can be cut off, and a truncated
  `countries.geojson` fails as `JSONDecodeError` a long way downstream. It should be
  **14643643 bytes / 258 features**; check the size before trusting it.

## Demo notebooks are stepped through, never run

`demo/01_timesheets.ipynb` is opened in VS Code and executed **cell by cell**, telling a story as it
goes. The markdown cells between the code are the narration.

- Never run the notebook, and never run "Run All".
- Never merge cells to make them run in one go, and never restructure it into a `.py` script.
- **Never strip the outputs.** They are committed on purpose: the printed DataFrames and the
  `[VERBOSE]` lines are what the reader of the repository sees without a database of their own.
  A tool or hook that clears notebook output is wrong for this repository.
- Cells that only put a variable name on the last line, imports repeated in a later cell, and code
  commented out on purpose (`os.startfile`, the `DROP TABLE`) are **pedagogical, not dead code**.
  Do not flag or remove them.

When you do change a notebook, edit the JSON minimally with `NotebookEdit` and touch only the cells
the task is about. Do not reformat the file — a whole-file rewrite loses the diff and usually the
outputs with it.

### How to actually edit these notebooks, because the obvious way stops working

Two of the three notebooks are now past the point where the tooling copes, and this will cost you time
if you do not know it in advance:

- **`NotebookEdit` requires a successful `Read` first, and `Read` refuses these files.**
  `demo/03_geodata.ipynb` is about 26k tokens with its outputs, over the limit, and `offset`/`limit` do
  not help on an `.ipynb`. `demo/02_stackexchange.ipynb` is close behind.
- **The `Edit` tool refuses `.ipynb` outright**, and tells you to use `NotebookEdit`.

So for a notebook that already carries outputs, change one cell with a **raw exact-match replacement in
Python**: read the file as text, `assert raw.count(OLD) == 1`, replace, write back. Get `OLD` by
printing the raw JSON slice around the cell id first, so the escaping is exactly right. The assert is
the safety rail — without it a near-miss silently writes nothing or, worse, twice.

Do **not** load the JSON and re-dump it. Whatever indent or `ensure_ascii` you pick will differ from
what Jupyter wrote, and the entire file reformats — losing the diff, which is the thing this section
exists to protect.

Adding cells to the *end* of a notebook, or building a new notebook, is fine with `Write` or a small
generator script. Inserting into the middle of one that has outputs is where you need the raw
replacement. When inserting several cells with `NotebookEdit`, insert them in **reverse order** all
anchored to the same existing `cell_id`; you do not know the ids of cells you have not created yet.

Also: `Path.write_text` on Windows turns `\n` into `\r\n`, so a generated notebook lands with CRLF.
Git normalises it to LF on commit, so it does not matter — but do not go chasing the warning.

### The working rhythm for a notebook change

An agent cannot run a notebook, so a notebook change is finished in two steps and the second one is the
owner's:

1. Write or edit the cells. New cells have **no outputs** — never hand-write an output.
2. Say so, and stop. The owner steps through the notebook in VS Code and then asks for the commit.

State that the cells have no committed output in the `Current state` table while that is true, and
**remove that note in the same commit that lands the outputs** — not in a follow-up. Before committing
after the owner's run, check what they actually produced: count the outputs, look for code cells that
came back empty, and read the cells whose numbers the narration quotes. That last check has caught a
contradiction twice — a markdown cell asserting a count that the cell above it no longer printed.

Scripts that *are* meant to run: the numbered scripts in the repository root (subject to the table
above) and `start_containers.ps1`. `demo/import_xls_timesheet.py` only defines a function and is
imported.

## Repository map

| Path | What it is |
| --- | --- |
| `01_setup.ps1` … `06_test_connections.py` | One-time setup, started from Windows, shells into WSL2. `01_setup.ps1` orchestrates the rest and stays PowerShell because Windows starts it; `02` and `03` are shell scripts, `05` and `06` are Python. |
| `start_containers.ps1` | Restarts the Docker containers after a reboot. |
| `data/<scenario>/` | Sample data per scenario. Generated and downloaded artifacts are gitignored; only `README.md` and `sample.json` (plus the photos) are committed. |
| `demo/` | The notebooks, plus the helper modules a notebook imports. |
| `docker/` | `docker-compose.yaml`, the per-scenario database init SQL/sh/js, and the PhotoService application. |
| `lib/` | The data access layer. One function per file. |

## The lib/ naming grid

Every module is `<verb>_<prefix>_<noun>.py` and holds **exactly one public function of the same name**.
This mirrors the sibling's `<Verb>-<Prefix><Noun>` one-function-per-file layout, so the two can be shown
next to each other:

| PowerShell | Python |
| --- | --- |
| `lib/Connect-SqlInstance.ps1` → `Connect-SqlInstance` | `lib/connect_sql_instance.py` → `connect_sql_instance` |
| `lib/Write-PgTable.ps1` → `Write-PgTable` | `lib/write_pg_table.py` → `write_pg_table` |

The prefixes are `sql` (SQL Server), `ora` (Oracle), `pg` (PostgreSQL) and `mdb` (MongoDB). The
sibling also has `mio` (MinIO); nothing here uses it and nothing will. Helper functions that are not
part of the public surface are prefixed with `_` and live in the same file as their caller.

**There is exactly one exception, and it is deliberate:** each `get_*_data_reader` imports
`_prepare_query_and_params` from its own `invoke_*_query`, rather than carrying a fourth, fifth and
sixth copy of that regex. Do not "fix" it by copying the helper back, and do not generalise it into a
shared module either — the reasoning is in `DIFFERENCES.md`.

`lib/README.md` has the index of what exists today and which cells of the grid are still empty.

**Sibling rule:** once a second provider exists, the `sql`, `ora` and `pg` implementations of a verb
family are near-identical by design. Before changing `lib/xxx_sql_yyy.py`, read `xxx_ora_yyy.py` and
`xxx_pg_yyy.py`. Either apply the same change to all siblings, or say explicitly why that provider has
to differ. Unexplained divergence between siblings is a bug. **This rule also reaches across
repositories:** if the sibling PowerShell function has a parameter, a guard clause or a `finally` block
and the Python one does not, that is a finding unless the difference is inherent to the language.

## Function contract

```python
def connect_sql_instance(
    instance,
    database=None,
    username=None,
    password=None,
    pooled_connection=False,
    enable_exception=False
):
```

- Plain functions. **No type hints, no dataclasses, no classes.** The sibling's parameter block is a
  `param()` with attributes; here it is a plain signature with defaults, and that comparison is easier
  to make when nothing else is in the way.
- `snake_case` parameters, one per line, keyword arguments at the call site. Positional calls into
  `lib/` are not used anywhere and should not start.
- Parameter names are the sibling's, lower-cased: `-Instance` → `instance`, `-BatchSize` →
  `batch_size`, `-TruncateTable` → `truncate_table`.
- **Every function ends its parameter list with `enable_exception=False`**, the port of
  `[switch]$EnableException`. It is the only error-handling switch in the library:

  ```python
  except Exception as e:
      message = f"<Step> failed: {str(e)}"
      if enable_exception:
          raise Exception(message)
      else:
          print(f"[ERROR] {message}")
          return None
  ```

  The `return None` matters — without it execution continues into code that assumes the failed step
  worked. A function that raises unconditionally, or that has no `enable_exception` at all, does not
  meet the contract.
- Progress and diagnostics go through `print()` with a level tag, the stand-in for the sibling's
  `Write-PSFMessage`: `[VERBOSE]` inside `lib/`, `[ERROR]` on the failure path. Notebooks print
  whatever reads well. Do not introduce `logging` in `lib/` without being asked — there is a commented
  sketch at the bottom of `connect_sql_instance.py` and that decision is still open.
- **No emoji in `lib/`.** `demo/import_xls_timesheet.py` prints `📄` and `↳`; that is fine in Jupyter,
  which is UTF-8, but the same code raises `UnicodeEncodeError` in a `cp1252` Windows console.
- Cursors, readers and files are closed on every path — `try/finally`, or a `with` block where the
  driver supports it.
- Long-running bulk operations print progress per batch: rows done, percentage, rows/sec.
- Runnable scripts do not swallow errors; an exception should stop the script.

## Loading model

There is **no package, no `__init__.py`, no `setup.py`/`pyproject.toml` — that is deliberate**, so the
audience sees plain functions in plain files. `lib/` is put on `sys.path` and the functions are imported
by name, which is the closest thing Python has to the sibling's dot-sourcing:

```python
import sys
from pathlib import Path

sys.path.append(str(Path("../lib").resolve()))

from connect_sql_instance import connect_sql_instance
from invoke_sql_query import invoke_sql_query
from write_sql_table import write_sql_table
```

The relative `../lib` means a notebook only resolves it correctly when the working directory is `demo/`,
which is what VS Code and Jupyter do. Modules that live next to the notebook (`import_xls_timesheet`)
are imported directly, without the `sys.path` dance.

Runtime dependencies, all installed with plain `pip` into the system interpreter today:
`pyodbc`, `psycopg[binary]`, `oracledb`, `pymongo`, `pandas`, `openpyxl`, `notebook`. SQL Server additionally
needs the [Microsoft ODBC Driver 18](https://learn.microsoft.com/sql/connect/odbc/) — the driver name
is hard-coded in `connect_sql_instance.py`. Oracle and PostgreSQL need nothing of the kind:
`oracledb` runs in thin mode and speaks the Oracle protocol itself, so there is no Instant Client. There is no `requirements.txt` and no virtual environment
yet; `README.md` says so and calls it "quick and dirty". Do not add either one without being asked.

## Deliberate decisions — do not "fix" these

- The password `Passw0rd!` is hard-coded in `docker/.env`, the init SQL, the notebooks and the setup
  scripts. These are throwaway local containers and the password being visible is part of the teaching.
  It is not a security finding. Do not parameterize it, do not move it to a vault, do not add
  `python-dotenv`.
- `127.0.0.1` rather than `localhost`, to force IPv4.
- `TrustServerCertificate=yes` in the connection string — local containers with self-signed
  certificates.
- **SQLAlchemy and ORMs are deliberately not used.** Hand-written DB-API code *is* the demo, exactly as
  the sibling uses hand-written ADO.NET rather than dbatools. Never propose replacing it. `pandas` is
  fine — it is the data container, not the database layer — but `pandas.read_sql` /
  `DataFrame.to_sql` hide the very thing being demonstrated.
- No tests, no CI, no packaging, no type hints, no docstring standard.
- Committed notebook outputs, see above.

## Verifying a change

The containers are probably not running, and starting them costs a WSL2 boot and several minutes.

**Do not run** `wsl`, `docker compose up`/`down`, `01_setup.ps1`, `start_containers.ps1`, or any
notebook in `demo/`. Verify statically instead:

```bash
# Syntax check — works with nothing installed beyond Python
python -m compileall -q lib demo

# Style and rule check — needs `pip install ruff` first
python -m ruff check .

# Notebook still parses as a notebook, and the outputs are still there
python -c "import json,sys; nb=json.load(open(sys.argv[1],encoding='utf-8')); print(len(nb['cells']),'cells,',sum(len(c.get('outputs',[])) for c in nb['cells']),'outputs')" demo/01_timesheets.ipynb
```

Read-only inspection (`docker ps`, `docker compose logs`, `git`) is fine. Note that `docker` lives
inside WSL2 and is **not** on the Windows PATH, so reaching it would mean running `wsl` — ask the owner
about container state instead of starting anything.

`ruff` is **not installed** in the Windows interpreter, so `python -m ruff check` fails with
`No module named ruff`. Say so rather than reporting it as passing.

**Set `PYTHONIOENCODING=utf-8` on anything that prints notebook content.** The console is `cp1252` and
the committed outputs contain non-ASCII from the sample data — a StackExchange display name is
`ypercubeᵀᴹ`, `import_gpx_file` prints `📄`. Without it an inspection script dies with
`UnicodeEncodeError` partway through, which looks like a broken notebook and is not one. The `[VERBOSE]`
lines are also worth filtering out when reading a verification run; there are thousands of them.

### But static checks are not enough, and this is the lesson of the port so far

Every real defect found in `lib/` was found by **running Python against the live containers** — never by
reading the code. `compileall` was green every single time.

When the containers are up, write a throwaway script in the scratchpad directory that **drives the real
`lib/` functions the way a notebook would**, and run it. That is not on the forbidden list: it is
ordinary Python, it touches only demo tables, and it is the only thing that works. The pattern that has
paid off four times now:

- Import from `lib/` and `demo/` via `sys.path`, exactly as a notebook does. Do not reimplement the
  logic in the test — the point is to exercise the shipped function.
- **Pass the repository root in as an argument.** The scratchpad is not inside the repository, so the
  obvious `while not (root / "lib").is_dir(): root = root.parent` never terminates — `Path("C:/").parent`
  is `Path("C:/")`, and the script spins at 100% CPU looking like a hung database connection. That cost
  half an hour once.
- **Have the script write its own report file**, with `buffering=1`. PowerShell holds redirected output
  until the process exits, so `> file` shows nothing at all while a long run is in progress.
- Print `PASS`/`FAIL` per check and a summary at the end, so a partial failure is obvious.
- Create and drop your own tables, and clean up.
- Run it with `run_in_background: true`. A GeoJSON import or an Oracle round trip takes minutes.

**Compare values against the source, column by column. A row count is not a check.** This is how the
worst bug in the port was found and it is worth repeating: `import_ora_table` reported
`OK - 12220 rows in 0.27 s` while silently discarding the milliseconds of every timestamp. Checking
`CreationDate` alone would have confirmed the bug as correct, because every value in that column
happens to end in `.000`. Only comparing `LastAccessDate` per row against the file exposed it.

**And do not trust a passing check that could have got lucky.** `FETCH FIRST 3 ROWS ONLY` reported the
Oracle geometry read-back as working; over the whole table it fails for a fifth of the rows. Ask
whether the check could pass for the wrong reason.

**Watch for a confound in your own script.** One round of measurements "proved" that
`oracledb.defaults.fetch_lobs = False` had no effect. It had reused the SQL text of the previous query,
so oracledb's statement cache served the old fetch metadata. Vary the SQL, or pass `stmtcachesize=0`.

If a change really cannot be verified — containers down, driver missing — say so plainly rather than
claiming it works.

## Style

Four-space indentation, double quotes, f-strings, `snake_case`. Blank line between logical steps inside
a function, with a short comment naming the step — the comments are read aloud during the demo:

```python
# Build connection string
conn_parts = [
    "DRIVER={ODBC Driver 18 for SQL Server}",
    f"SERVER={instance}"
]
```

DataFrames are the canonical in-memory shape for data in flight, the counterpart to the sibling's
`[PSCustomObject]` arrays. Prefer a single chained `assign(...)[[columns]]` over building a frame
column by column — it fits on a slide.

**Do not reformat lines you are not otherwise changing.** There is pre-existing trailing whitespace and
there are missing final newlines in places; leave them alone unless the task is explicitly a formatting
pass.

## Adding or porting a demo scenario

A scenario touches all of these. Miss one and the repository is inconsistent.

1. `data/<name>/README.md` and, if the data is generated, `data/<name>/sample.json`
2. The generated or downloaded artifact pattern in `.gitignore`
3. The scenario block in `05_sample_data_setup.py`, and the connection block in
   `06_test_connections.py` — the sibling's `05_sample_data_setup.ps1` still has the download and
   upload code for the scenarios that are not ported yet
4. `docker/sqlserver-<name>.sql` (and the Oracle/Postgres equivalent if used), plus the mount in
   `docker/docker-compose.yaml` and the line in `docker/sqlserver-init.sh` — for the ported scenarios
   these all already exist, since `docker/` came over complete
5. `demo/NN_<name>.ipynb`, with markdown narration between the code cells
6. Any `lib/` function the scenario needs, following the naming grid and the function contract
7. The entry in `lib/README.md`
8. **The `### <Name>` section under "Demo scenarios" in `README.md`**
