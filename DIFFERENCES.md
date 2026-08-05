# DIFFERENCES.md

Where the Python port had to diverge from
[PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around), and why.

This is the record of the design decisions, including the alternatives that were tried and rejected.
The demo notebooks show what works; they deliberately do not show what failed. This file does.

Scope, so that it does not become a fourth dumping ground:

- **How a function behaves** belongs in `lib/README.md`.
- **Rules for working in this repository** belong in `AGENTS.md`.
- **The story told to an audience** belongs in the notebooks.
- **A decision and its evidence** belongs here. One entry per decision, appended when it is made.

Measurements were taken on the repository's own containers, against SQL Server 2025 in Docker on
WSL2, with the `dba.meta` StackExchange data. They are indicative, not benchmarks.

---

## Reading files

### The byte order mark

**The sibling:** `Get-Content` removes a BOM without mentioning it, so `$line -like '<?xml*'` matches
the first line of the StackExchange files and the format detection works.

**Python:** `open(path, encoding="utf-8")` keeps it. The first line arrives as
`'﻿<?xml version="1.0"...'`, so `line.startswith("<?xml")` is `False`.

**Evidence:** the files start with `b'\xef\xbb\xbf'`. With `utf-8` the test is `False`, with
`utf-8-sig` it is `True`.

**Decision:** `import_sql_table` takes `encoding="utf-8-sig"` as its default. `utf-8-sig` also reads
files without a BOM correctly, so it is safe as a default rather than a special case.

**Why it matters:** the failure is silent. The format is simply never detected, the loop parses nothing,
and the import reports zero rows without an error.

### A value that is not there

**The sibling:** `$row.AboutMe` on an `XmlElement` without that attribute returns `$null`. The import
loop is built on this — it walks the *target* columns and writes whatever `$rowObject.$sourceColumnName`
gives it, leaving the `DataRow` at its default when that is `$null`.

**Python:** `row["AboutMe"]` raises `KeyError`. The dictionary from `ElementTree.attrib` only contains
the attributes that are actually in the line.

**Evidence:** in `Users.xml`, of 12220 rows — `Location` on 6813, `AboutMe` on 5824, `WebsiteUrl` on
3927. Two further columns of `dbo.Users`, `Age` and `EmailHash`, never appear in the file at all.

**Decision:** iterate the target columns and ask with `.get()`, so a missing value becomes `NULL`. Same
shape as the sibling, different mechanism.

**Note:** pandas is a third behaviour again — `DataFrame` collects every key it sees and fills the gaps
with `NaN`, and `NaN` is not `None`. That mattered below.

---

## Writing to a database

### Converting strings to column types

The largest single difference in the port so far.

**The sibling:** builds a `DataTable` whose columns are typed from `GetSchemaTable()`, adds the strings
from the XML, and lets ADO.NET convert on the way into `SqlBulkCopy`. Nothing in the script mentions a
type.

**Python:** pyodbc has no equivalent. With `fast_executemany` it binds a value by its Python type, so a
string never arrives in an `INT` or `DATETIME` column.

**Evidence** — `Users.xml`, 12220 rows, into `dbo.Users`:

| Approach | Result |
| --- | --- |
| strings, `fast_executemany` | fails, `22018 Invalid character value for cast specification` |
| strings, no `fast_executemany` | works, **51.4 s** |
| convert from `cursor.description` | works, **0.97 s** |
| DataFrame of strings → `write_sql_table` | fails, `22003 Numeric value out of range` |
| same, with `NaN` turned into `None` | fails, `22003` again |
| convert first, then DataFrame → `write_sql_table` | works, **1.17 s** |

**Decision:** convert in Python, choosing a converter per column from the type in `cursor.description`.
That call is the counterpart of `GetSchemaTable()` — it reports a Python type (`int`, `str`,
`datetime.datetime`) for every column. The converter table in `import_sql_table` has no counterpart in
the sibling at all.

**Rejected:** letting the driver convert, which is the approach that mirrors ADO.NET most closely. It
either fails outright or costs 53×. Also rejected: building the DataFrame first — the types have to be
correct *before* the frame exists, and turning `NaN` into `None` does not rescue it.

### Matching a column name to a value

**The sibling:** never has to think about it. PowerShell property access is case insensitive, so
`$rowObject.aboutme` finds the `AboutMe` attribute and the same import loop works against SQL Server
and PostgreSQL unchanged.

**Python:** dictionary lookup is case sensitive, and the two databases do not agree on case.
SQL Server stores the identifiers as written, `CreationDate`. PostgreSQL folds unquoted identifiers to
lower case, and the tables of this repository are created unquoted, so the catalog holds
`creationdate`.

**Evidence:** for the PostgreSQL `Users` table, of fourteen columns, **zero** match an attribute of
`Users.xml` by exact name. Twelve match case insensitively.

**Decision:** both `import_sql_table` and `import_pg_table` lower case the keys of a row, the column
names and the entries of `column_map` before matching. `write_pg_table` matches its DataFrame columns
the same way. The quoting helper for PostgreSQL lower cases the identifier as well, so that
`Users` reaches the catalog as `"users"`.

**Why it matters:** exact matching does not fail loudly here. It fills every column with `NULL`,
reports the correct number of rows, and returns success.

### Bulk loading

**The sibling:** `SqlBulkCopy` with `TableLock` and `UseInternalTransaction`, and `NotifyAfter` driving
a `Write-Progress` handler.

**Python:** `cursor.executemany` with `cursor.fast_executemany = True`. Batching, committing and
progress reporting are all written out by hand.

**Evidence:** roughly 10 000 rows/sec for `Users.xml` and 19 000 rows/sec for `Badges.xml` at
`batch_size=5000`.

**Consequence:** the loop is visible. That is more code than the sibling needs, but on a projector the
batching is on screen rather than hidden behind a .NET class.

### Loading into PostgreSQL: COPY

**The sibling:** `Write-PgTable` fills a `DataTable` and lets an `NpgsqlDataAdapter` with an
`NpgsqlCommandBuilder` generate the `INSERT` statements. It does **not** use a binary import or
`COPY`. Making that faster is an open item in the sibling repository.

**Python:** psycopg exposes `COPY` directly through `cursor.copy()`, and the text format takes the
values as text and lets PostgreSQL parse them into the column types.

**Evidence** — `Users.xml`, 12220 rows, into the PostgreSQL `Users` table:

| Approach | Result |
| --- | --- |
| `executemany`, converted values | 1.27 s |
| `executemany`, raw strings | 0.95 s |
| `COPY`, converted values | 0.30 s |
| `COPY`, raw strings | **0.14 s** |

All four produce identical data. Escaping was checked separately on the `Text` column of
`Comments.xml`: of 4512 rows, 24 contain a tab, a newline or a backslash, and all of them round-trip
byte-exact through `copy.write_row`.

**Decision:** `write_pg_table` and `import_pg_table` use `COPY`. `import_pg_table` passes the raw
strings, so it needs no converter table at all — the whole `_CONVERTERS` mechanism that SQL Server
forced on `import_sql_table` is absent here.

**Note:** this is a deliberate divergence from the sibling's shape rather than a translation of it,
agreed because the PowerShell side wants the same improvement. The intention is to port `COPY` back
to `Write-PgTable`.

**Why it matters:** the same problem produced opposite answers on the two databases. On SQL Server,
passing raw strings fails outright and the fastest path needs the most code. On PostgreSQL, passing
raw strings is both the fastest path and the least code.

### Loading into Oracle: two converters out of fourteen

**The sibling:** `Import-OraTable` fills a `DataTable` typed from `GetSchemaTable()` and hands it to
`OracleBulkCopy`. It is the same shape as its SQL Server counterpart, and again nothing in the script
mentions a type.

**Python:** Oracle has no `COPY`, so this looks like the SQL Server version — `executemany` with
batches — and the question is again which values have to be converted first. The answer is neither of
the two earlier answers.

**Evidence** — `Users.xml`, 12220 rows, into `Import_Users`:

| Approach | Result |
| --- | --- |
| raw strings | fails, `ORA-01843: not a valid month` |
| raw strings, CLOB declared with `setinputsizes` | fails, `ORA-01843` again |
| only the numbers converted | fails, `ORA-01843` again |
| only the timestamps converted | works, **0.27 s** |
| every value converted | works, 0.45 s |
| every value converted, CLOB declared with `setinputsizes` | works, **13.84 s** |

**Decision:** convert the `TIMESTAMP` and `DATE` columns and nothing else. Oracle converts the
numbers out of their strings on its own; it will not take an ISO timestamp, because that is not what
`NLS_TIMESTAMP_FORMAT` describes. So `_CONVERTERS` in `import_ora_table` has two entries where the
SQL Server version needs eight, and a column type that is *not* in the table keeps its string — the
inverse of `import_sql_table`, where a missing entry has to be an error.

**Rejected:** declaring the CLOB column with `setinputsizes`. It is the thing that looks careful, and
it costs 30×. Undeclared, a 5440 character `AboutMe` reaches the CLOB perfectly well.

**Also rejected:** `ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS.FF'`, which
makes raw strings work for every column and is exactly as fast (0.37 s), and would have removed the
converter table entirely — the PostgreSQL answer. It was rejected because `write_ora_table` cannot
use it: its input is a DataFrame or a data reader, which hold `datetime` objects rather than text, so
only the declaration below helps there. Choosing it for the import would have left the two Oracle
functions solving one problem two different ways.

**Why it matters:** the same question has now produced three different answers on three databases —
convert everything, convert nothing, convert two columns — and in each case the shortest code and the
fastest code were the same thing.

### The timestamp that arrived without its milliseconds

The most dangerous thing found in the port so far, because every check short of comparing the values
said it had worked.

**The sibling:** never encounters it. The `DataTable` column is typed `DateTime` from
`GetSchemaTable()`, and `OracleBulkCopy` puts it into a `TIMESTAMP(3)` with its fraction intact.

**Python:** converting the string to a `datetime` is **not enough**. oracledb binds a Python
`datetime` as `DB_TYPE_DATE`, and an Oracle `DATE` holds whole seconds. The fractional part is
dropped on the way in — with no error, no warning, and the correct number of rows reported.

**Evidence** — `Users.xml`, the `LastAccessDate` column:

| | |
| --- | --- |
| the file says | `2011-01-03T17:13:19.040` |
| `datetime.fromisoformat` gives | `datetime(2011, 1, 3, 17, 13, 19, 40000)` — correct |
| Oracle stored | `2011-01-03 17:13:19.000` — the fraction is gone |

**12179 of 12220 rows** were affected. The other 41 have a `.000` fraction in the file. `CreationDate`
matched on all 12220 rows and hid the problem completely, because those values all end in `.000`.

**Decision:** `cursor.setinputsizes(...)` declaring the `TIMESTAMP` columns as `DB_TYPE_TIMESTAMP`,
in `import_ora_table` **and** in `write_ora_table`. With it, all 12220 rows are exact, and it is
slightly *faster* than not declaring them (0.32 s against 0.34 s). Verified afterwards on every path
that carries a timestamp into Oracle: from the file, from Oracle, from PostgreSQL, and from a pandas
DataFrame whose column is `datetime64[us]`.

**Why it matters:** this is the failure mode this repository keeps meeting, in its worst form yet. The
first measurement of this path reported `OK - 12220 rows in 0.27 s` and was believed. It was only
caught by joining the result against the source file and comparing values, and the comparison had to
be per column — checking `CreationDate` alone would have confirmed the bug as correct.

### A CLOB is a handle, and it prints like a string

**The sibling:** an `AboutMe` read through `OracleDataReader` is a `string`. Nothing in the sibling
mentions LOBs.

**Python:** by default `oracledb` returns a `CLOB` as a `LOB` object — a lazy handle that has to be
read separately. `oracledb.defaults.fetch_lobs = False` asks for strings instead, and that default is
read **when a connection is created**, not when a row is fetched.

**Evidence:**

| | |
| --- | --- |
| `type()` of the value | `oracledb.lob.LOB` |
| the same value in a printed DataFrame | `<p>Hi, I'm not really a person.</p>…` |
| streaming it into SQL Server | fails, `Unknown object type LOB during describe` |
| full table fetch, LOB handles never read | 0.20 s |
| full table fetch, `fetch_lobs = False` | 0.27 s |
| full table fetch, then `.read()` on each LOB | **4.68 s** |

**Decision:** `connect_ora_instance` sets `oracledb.defaults.fetch_lobs = False`. A `lib/` function
writing to a driver-wide default is not pretty, but the default is consulted at connect time, so
that is the only place it can go — and the alternative, an output type handler on every cursor that
might see a CLOB, would have to be repeated in `invoke_ora_query` and `get_ora_data_reader` and
silently breaks whichever one it is forgotten in.

**Rejected:** the per-cursor output type handler. It works and it is marginally faster (0.25 s), but
it has to be remembered in two places, and its failure mode is the one below.

**Why it matters:** a DataFrame full of LOB handles *looks* right on a projector, because a LOB
renders as its own content. The trap is that it displays perfectly and then fails the moment the
data leaves Python for another database — which is the entire point of this demo.

### A read opens a transaction nobody asked for

**The sibling:** an ADO.NET or Npgsql command without an explicit transaction commits itself. There is
no state left behind after a `SELECT`, and nothing in the sibling ever mentions this.

**Python:** DB-API connections start in manual-commit mode. psycopg opens a transaction for a `SELECT`
too, and it stays open until it is ended. A connection sitting **idle in transaction** keeps the
`AccessShareLock` on everything it read.

**Evidence:** after stepping through `demo/02_stackexchange.ipynb` in Jupyter and leaving the kernel
open, its connection sat idle in transaction holding a lock on `badges`. The next `TRUNCATE TABLE` —
from a second run of the same notebook — blocked, and so did the run behind it. `pg_blocking_pids`
showed the chain: the idle kernel blocked run one, which blocked run two. Nothing timed out; they
would have waited forever.

**Decision:** `invoke_pg_query` and `invoke_sql_query` end the transaction after a read, not only after
a non-query. SQL Server releases read locks at the end of the statement, so it hurts far less there,
but the open transaction is the same and the two functions stay siblings.

**Rejected:** making the connections autocommit, which is what ADO.NET effectively does. It would fix
this class of problem outright, but `import_pg_table` truncates and copies in one transaction so that a
failed load does not leave the table empty, and autocommit would give that up.

**Still true:** a data reader keeps its transaction open until it is closed, because it has to. Whoever
opens a source connection for streaming should close it.

**Why it matters:** the failure is a hang, not an error, and it happens in exactly the situation this
repository is built for — a notebook left open after stepping through it.

### Named parameters

**The sibling:** ADO.NET has real named parameters, and `Invoke-SqlQuery` also exposes
`-ParameterTypes` to pin a `SqlDbType` per parameter.

**Python:** the two drivers disagree. pyodbc supports positional `?` only. psycopg has real named
parameters, written `%(name)s`.

**Decision:** both functions accept the same dict and the same `:name` / `@name` syntax in the query,
so the call sites stay identical across providers. What they do with it differs — `invoke_sql_query`
rewrites to `?` and has to collect the values in order of appearance, `invoke_pg_query` only renames
to `%(name)s` and passes the dict through untouched.

**Limitation, accepted:** the rewrite is a regular expression that does not know about string literals,
so a `:` inside a quoted string in the query would be mangled. There is no equivalent of
`-ParameterTypes` in either.

---

### Streaming from one table into another

**The sibling:** `Get-SqlDataReader` returns a `DbDataReader` — an open result set that yields one row
at a time — and `Write-SqlTable` hands it straight to `SqlBulkCopy.WriteToServer($reader)`, a single
call that does the whole transfer.

**Python:** a cursor after `execute()` already is that reader, so `get_sql_data_reader` returns the
cursor as it is. There is no `WriteToServer` equivalent, so the writer loops: `fetchmany(batch_size)`,
build the tuples, `executemany` or `COPY`, repeat.

**Consequence, and arguably an improvement:** the loop is on screen. The .NET version hides the
transfer inside one method call; here the audience sees the batch being fetched, mapped and written.

**Decision:** the writer closes the reader it was handed, mirroring the sibling, where `Write-SqlTable`
disposes the reader in its `finally`. The alternative — the caller closes it — was rejected only
because it would diverge from the sibling for no gain.

**Evidence**, 12220 rows. The first four were measured together, the Oracle five in a later run once
`write_ora_table` existed, so compare within a block rather than across them:

| From | To | Result |
| --- | --- | --- |
| SQL Server | SQL Server | 1.00 s |
| PostgreSQL | SQL Server | 0.88 s |
| SQL Server | PostgreSQL | 0.31 s |
| PostgreSQL | PostgreSQL | 0.16 s |
| Oracle | Oracle | 0.89 s |
| SQL Server | Oracle | 0.61 s |
| PostgreSQL | Oracle | 0.48 s |
| Oracle | SQL Server | 1.03 s |
| Oracle | PostgreSQL | 0.50 s |

Nothing had to be converted between the systems: psycopg hands out Python objects, pyodbc takes Python
objects, and the dates, integers and `NULL`s survive unchanged. The two targets that are PostgreSQL are
the fast ones, for the same reason the file import was — `COPY`.

**With one exception, and it is Oracle on both sides of it.** Writing *into* Oracle needs the
`TIMESTAMP` columns declared or the milliseconds are lost, and reading *out of* Oracle needs
`fetch_lobs = False` or pyodbc is handed a LOB object it cannot describe. Both have their own entries
above. Once those two lines are in place, all nine directions carry the data through unchanged, and
the millisecond fractions were verified against the file on every path whose target is `TIMESTAMP(3)`.
SQL Server is excluded from that check on purpose: `DATETIME` has 1/300 second resolution, so it
rounds the fractions by design rather than by accident.

**Known limitation:** psycopg's normal cursor fetches the whole result before the first `fetchmany`
returns, so `get_pg_data_reader` streams from the writer's point of view but not from the server's. A
server-side cursor would change that. `Get-PgDataReader` does stream, so this is a real difference and
not just an implementation detail.

## Excel

### Writing a report

**The sibling:** one `Export-Excel` call takes the data, the layout, the table style and the chart
through `-ExcelChartDefinition`.

**Python:** `DataFrame.to_excel` writes the data, and the charts are built as openpyxl objects —
`PieChart`, `BarChart`, `Reference` — inside the same `ExcelWriter` block. Sizes are centimetres rather
than pixels.

**Decision:** keep it in the notebook rather than in a `lib/` function, exactly as the sibling does.

### A directory is not a file pattern

**The sibling:** the demo calls `Import-XlsTimesheet -Path ..\data\timesheets\Department*.xlsx`. The
parameter is a *file pattern*.

**Python:** the port turned that into a directory and globbed `*.xlsx` inside it. That reads better
until you notice that the last section of the same notebook writes `Report.xlsx` into exactly that
directory.

**Evidence:** `demo/01_timesheets.ipynb` failed on every second run with `KeyError: 'date'` — the
importer was trying to read the report it had produced itself.

**Decision:** `import_xls_timesheet` takes a pattern again, like the sibling.

**Why it matters:** this is a divergence that was not a decision. Nobody chose to change the meaning of
the parameter; it happened while translating, and it produced a bug the sibling cannot have. When a
parameter changes shape in the port, that is worth a second look.

### Reading a block back

**Python only.** Two result blocks of different length share one worksheet. Reading a column range
without `nrows` also reads the empty rows beside the longer block.

**Evidence:** 22 phantom `NaN` rows, and `ProjectMinutesWorked` silently changed from `int64` to
`float64` because of them.

**Decision:** pass `nrows`. The failure is quiet and produces a plausible-looking frame, which is the
dangerous kind.

---

## Drivers and environment

### Getting a driver

**The sibling:** `Import-OraLibrary` and `Import-PgLibrary` download the ADO.NET DLLs from nuget.org
into `lib/` on first use. The DLLs are gitignored and must never be committed.

**Python:** `pip install` in `03_python_setup.sh`. Two cells of the function grid disappear entirely.

**Measured, and the expectation held.** `oracledb` runs in **thin mode** by default —
`oracledb.is_thin_mode()` is `True` before and after connecting — and it speaks the Oracle network
protocol itself. It connected to `127.0.0.1/XEPDB1` and reported
`Oracle Database 21c Express Edition Release 21.0.0.0.0` with **no Oracle Instant Client installed
anywhere**, on Windows or in WSL2.

**Decision:** `pip install oracledb` in `03_python_setup.sh`, and nothing else. This is the larger
simplification of the two: `Import-PgLibrary` replaces a DLL download with a pip install, but
`Import-OraLibrary` also implies a client installation that disappears completely.

### Where the runtime lives

**The sibling:** `Install-Module -Scope AllUsers` puts the modules in
`/usr/local/share/powershell/Modules`, readable by every account — which is also why the PhotoService
container can mount that path.

**Python:** the interpreter is per-user by default. pyenv installs into `$HOME/.pyenv`.

**Evidence:** three things had to be discovered on a clean Ubuntu 24.04 WSL2 —

- `/root` is `drwx------`, so an interpreter installed as root is invisible to the demo user. The setup
  steps that need Python must not run `--user root`.
- `~/.bashrc` starts with `[ -z "$PS1" ] && return`, so a script started non-interactively never sees
  anything appended to it. The pyenv initialisation lives in `~/.profile`, and the steps are started
  with `bash -lc`.
- Ubuntu 24.04 marks the system interpreter `EXTERNALLY-MANAGED`, so a plain `pip install` into it is
  refused. pyenv sidesteps this; it is not only about the version.

**Consequence:** the PowerShell setup is machine-wide almost by accident, and the Python setup is
per-user almost by accident. Neither is a decision either project made deliberately.

---

## Infrastructure

### The port got faster, and that broke it

**Symptom:** `06_test_connections.py` failed with
`08001 ... error was encountered during handshakes before login`, about four seconds after
`docker compose up`.

**Cause:** not a defect in anything ported. The sibling's `05_sample_data_setup.ps1` spends minutes
downloading StackExchange archives and Geodata, which always gave SQL Server enough time to finish
starting. The Python `05` writes three Excel files and finishes in about two seconds, so `06` now
arrives while SQL Server is still coming up. The sibling never needed a readiness wait because it
accidentally always had one.

**Decision:** `04_docker_compose.sh` does not return until the demo databases exist.

**Rejected:** waiting for the init script's `SQL Server configuration complete.` message in the
container log. `docker logs` keeps the output of previous runs, so on a restarted container the message
matches **immediately** — the check passed in one second while the server was still starting. It would
have looked like a fix and silently reintroduced the race. The wait queries `sys.databases` instead.

---

## The demos themselves

### Stepping through

**The sibling:** every demo script starts with a bare `break`, and is executed section by section with
F8 in VS Code.

**Python:** a notebook, executed cell by cell.

**Consequence:** the notebook outputs are committed on purpose, so the repository shows printed frames
and `[VERBOSE]` lines to a reader who has no database. The cost is that they go stale — adding the
`[VERBOSE]` prefix to `write_sql_table` invalidated the output of one cell, which then had to be
re-run rather than edited. Output must never be written by hand.

### Progress and logging

**The sibling:** `Write-PSFMessage` from PSFramework, with `Write-Progress -Id 1` for long operations.
Because PSFramework keeps a message log, demo 02 can run `Get-PSFMessage | Where-Object Message -like
Finished*Milliseconds` afterwards to compare the timings of three imports.

**Python:** `print()` with a level tag — `[VERBOSE]` inside `lib/`, `[ERROR]` on the failure path.

**Consequence:** there is no message log to query afterwards, so a function that wants its duration
shown has to print it itself. `import_sql_table` ends with its own `Imported N rows in X seconds` for
exactly that reason.

**Open:** whether to move `lib/` to `logging`. A commented sketch sits at the bottom of
`connect_sql_instance.py` and the decision has not been made.

### Non-ASCII output

**Python only.** `demo/import_xls_timesheet.py` prints `📄` and `↳`. That is fine in Jupyter, which is
UTF-8.

**Evidence:** the same code raised `UnicodeEncodeError: 'charmap' codec can't encode characters` when
run from a `cp1252` Windows console during development.

**Decision:** no emoji in `lib/`. The notebooks may use them, because they only ever run in Jupyter.
