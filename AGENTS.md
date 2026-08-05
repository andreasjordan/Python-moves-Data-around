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

The repository is early. **Timesheets** is complete. **StackExchange** is being built step by step and
imports the files into SQL Server, PostgreSQL, Oracle and MongoDB and streams between the three
relational ones. MinIO is still missing.

| Area | State |
| --- | --- |
| `demo/01_timesheets.ipynb` | Works, end to end, against a running SQL Server container. |
| `demo/02_stackexchange.ipynb` | Reading the XML files, importing them into SQL Server, PostgreSQL and Oracle, streaming table to table, and a MongoDB bonus section at the end. Stepped through end to end, outputs committed. No MinIO yet. |
| `lib/` | Eighteen functions: `connect`, `invoke`, `write`, `import` and `get_*_data_reader` for `sql`, `ora` and `pg`, plus `connect`, `write` and `read` for `mdb`. MinIO is empty. |
| `docker/` | Complete — a straight copy from the sibling repository. All scenarios' databases are created. |
| The setup chain | Ported to Python and verified end to end against a clean WSL2. `01_setup.ps1` is the only remaining PowerShell file, because it is what Windows starts. |
| The charts in `Report.xlsx` | **Open, and parked on purpose.** The pie and bar chart that the last cells of `demo/01_timesheets.ipynb` create are correct but do not look good enough yet. Do not polish them as a side effect of another task — see below. |
| `docker/photoservice-app.ps1` | Still the sibling's, and it dot-sources `./lib/*-Pg*.ps1`, which does not exist here. The `photoservice` service is commented out in `docker-compose.yaml` until scenario 4 is ported, so nothing tries to start it. |
| `05_sample_data_setup.py` | Timesheets, plus the StackExchange **download**. The upload of those files to MinIO is not ported yet, and neither is the Geodata block. They come back with their scenarios. |
| `06_test_connections.py` | Timesheets on SQL Server, StackExchange on SQL Server, Oracle, PostgreSQL and MongoDB. It grows one block per ported scenario and per provider. |

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

## The StackExchange port — remaining steps

The scenario is being built in small steps, deliberately not in the order of the sibling's demo, so
that each step settles one design question. Done: the sample data, reading the XML, the SQL Server
import, the PostgreSQL import, streaming table to table, Oracle, and MongoDB. One step is left:

### MinIO

`connect_mio_instance` and the four file functions, plus the upload block in `05_sample_data_setup.py`.
**Left for last on purpose:** the sibling hand-rolls AWS SigV4 as script methods on a `PSCustomObject`,
while Python has `boto3` and `minio`. Reaching for an SDK would be the first time a library hides the
protocol being demonstrated — the same category of decision as "no SQLAlchemy" — so it needs an
explicit decision from the owner rather than a default.

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

The prefixes are `sql` (SQL Server), `ora` (Oracle), `pg` (PostgreSQL), `mdb` (MongoDB) and `mio`
(MinIO). Helper functions that are not part of the public surface are prefixed with `_` and live in the
same file as their caller.

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

Read-only inspection (`docker ps`, `docker compose logs`, `git`) is fine.

If a change really cannot be verified without a database, say so rather than claiming it works.

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
