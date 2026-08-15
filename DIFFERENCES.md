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

**The sibling:** `Write-PgTable` **also uses `COPY`**, through Npgsql's `BeginTextImport`, since
2026-08-15. Until then it filled a `DataTable` and let an `NpgsqlDataAdapter` with an
`NpgsqlCommandBuilder` generate the `INSERT` statements, and this section recorded that as the
largest remaining divergence. It was entry 3 of `SIBLING-FINDINGS.md`, and it is closed.

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

**Note:** this started as a deliberate divergence from the sibling's shape rather than a translation
of it, agreed because the PowerShell side wanted the same improvement. **That has happened, so this
is no longer a difference between the two repositories** — both load PostgreSQL through the text
form of `COPY`, and the entry stays because it is the record of why.

Two things the PowerShell side found that this one never had to:

- **A `bytea` value has to be written as `\\x…`, not `\x…`.** `\x` is an escape of the copy format
  itself, so a single backslash makes PostgreSQL decode the hex into raw bytes rather than pass the
  text to the `bytea` parser — and a `0x00` in there then fails as `invalid byte sequence for
  encoding "UTF8"`. psycopg's `copy.write_row` never exposes this, because it does its own
  adaptation instead of being handed a string.
- **A `DateTime` needs an explicit format.** PowerShell renders numbers culture invariantly but a
  `DateTime` without its milliseconds, so `Write-PgTable` formats those with `ToString('o')`. In
  Python the value is passed as an object and never becomes text on this side.

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

**And it came back, in the PhotoService scenario.** `write_sql_table` closes the cursor it was handed —
that is the documented ownership — but closing a cursor is not ending a transaction, so every transfer
leaves the *source* connection `INTRANS`. Three cells of `demo/04_photoservice.ipynb` streamed happily
that way before the fourth failed with
`can't change 'isolation_level' now: connection in transaction status INTRANS`: PostgreSQL will not
change the isolation level while a transaction is running. The notebook now ends the source transaction
explicitly, and says so in the narration, because the failure is a good illustration of the entry above.
Nothing in `lib/` changed for it — `write_*_table` must not commit a connection it does not own, which
is the whole point of `commit=False`.

**Why it matters:** the failure is a hang, not an error, and it happens in exactly the situation this
repository is built for — a notebook left open after stepping through it.

### A failed statement poisons the whole connection

The other half of the same problem, found while porting the Geodata scenario.

**The sibling:** an Npgsql command without an explicit transaction commits or fails on its own. A failed
statement is over when it has failed, and the next one runs normally.

**Python:** PostgreSQL aborts the **entire transaction** when any statement in it fails. The connection
then answers every further statement with
`current transaction is aborted, commands ignored until end of transaction block` — until somebody
rolls back. `invoke_pg_query` printed `[ERROR]`, returned `None`, and left the connection in exactly
that state.

**Evidence:** a `DROP TABLE` for a table that did not exist yet — the ordinary way to make a script
re-runnable. It failed as expected, and then the `CREATE TABLE` after it failed too, and so did
everything else on that connection. The reported error named the aborted transaction, not the `DROP`
that caused it.

**Decision:** roll back in the failure path of `invoke_pg_query`, and in `invoke_sql_query` and
`invoke_ora_query` as well. Only PostgreSQL needs it — SQL Server and Oracle let the next statement
run — but a failed statement should not leave anything behind on any of them, and the three functions
stay siblings.

**Already correct elsewhere:** `import_pg_table` and `write_pg_table` have rolled back on failure from
the start. `invoke_pg_query` was the one that did not, which is what made it hard to spot: two of the
three PostgreSQL functions were right.

**Why it matters:** in a notebook this is worse than a plain error. One mistyped query, and every cell
after it fails with a message that does not mention the mistake — on a projector, in front of an
audience, with the real cause already scrolled off the screen.

### A transaction has no object to pass around

Found while porting the PhotoService scenario, which is the first demo that needs two writes to
succeed or fail together.

**The sibling:** `$connection.BeginTransaction()` returns a transaction object, and every command it is
handed to belongs to that transaction. Nine functions take `-Transaction` for exactly that reason:
`Invoke-SqlQuery`, `Invoke-OraQuery`, `Invoke-PgQuery`, `Write-SqlTable`, `Write-OraTable`,
`Write-PgTable`, and the three `Get-*DataReader` functions.

**Python:** DB-API has no transaction object. The transaction belongs to the **connection** — it is
opened by the first statement and it ends when the connection is committed or rolled back. There is
nothing to hand to a function, so `-Transaction` cannot be ported as a parameter at all.

**Evidence:** worse than missing, the parameter was impossible. Every function in `lib/` committed
unconditionally: `write_sql_table` after each batch, `invoke_sql_query` even after a `SELECT` (see *A
read opens a transaction nobody asked for*, which is why those commits are there). Two calls could
therefore never make up one unit of work — the first one ended the transaction the second was supposed
to join. `lib/README.md` had recorded `-Transaction` as "still missing, waits for the scenario that
needs it"; the scenario arrived and the parameter turned out to be the wrong shape.

**Decision:** the six `invoke_*_query` and `write_*_table` functions take `commit=True`. With
`commit=False` a function neither commits nor rolls back, so several calls make up one unit of work and
the caller ends it. The notebook then shows the idiom each driver actually has: psycopg's
`with connection.transaction():` on the PostgreSQL side, a plain `connection.commit()` on the pyodbc
side.

The three `get_*_data_reader` functions get **nothing**, and that is not an omission. A Python cursor is
created on a connection and is already inside whatever transaction that connection has open, so the
sibling's `-Transaction` has nothing left to do.

**Rejected:** a `transaction=` parameter that takes a psycopg `Transaction` or a marker object, to keep
the sibling's name. It would have invented an object Python does not have, and hidden the one thing
worth showing — that the transaction is a property of the connection, not of the statement.

**Also rejected:** leaving the transaction sections out of the demo, which would have been the smallest
change to `lib/` and would have dropped a key takeaway the sibling names explicitly.

**Why it matters:** it is the clearest example in the whole port of a parameter that cannot be
translated, only replaced. Side by side, `-Transaction $transaction` and `commit=False` do the same job
and say something different about where a transaction lives.

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

**And a limitation that was not accepted, because the Geodata scenario walked straight into it.**
Both SQL Server and PostgreSQL use a doubled colon as an operator — `geometry::STGeomFromText(...)` for
a type method, `value::numeric` for a cast — and the rewrite read the second colon as the start of a
parameter name:

| Query | Before |
| --- | --- |
| `geometry::STGeomFromText(@wkt, 4326)` | `KeyError: "Named parameter 'STGeomFromText' not provided"` |
| `SELECT laenge::numeric … WHERE x = :abschnitt` | `KeyError: "Named parameter 'numeric' not provided"` |

The very first statement of `demo/03_geodata.ipynb` is the first one in that table, so nothing in that
scenario could have worked. **Fix:** a `(?<!:)` in front of the colon, in all three functions. Checked
against `:a::text`, where a parameter and a cast sit next to each other, and against every query the
three notebooks use.

**Worth noting for its own sake:** this only became visible in the third scenario. The two before it
never wrote a doubled colon, and the ADO.NET side cannot have the bug at all, because it never rewrites
anything.

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

## Geodata

### The namespace nobody mentions

**The sibling:** `Import-GpxFile` reads `([xml]$content).gpx`, then `$gpx.trk`, `$track.trkseg`,
`$segment.trkpt`. PowerShell's XML adapter resolves those names without caring which namespace the
document declares, so the function never mentions one.

**Python:** `ElementTree` puts the namespace into every tag. A `<trk>` in a document that declares
`xmlns="http://www.topografix.com/GPX/1/1"` arrives as `{http://www.topografix.com/GPX/1/1}trk`, and
`root.findall("trk")` finds nothing.

**Evidence, and this is the part that matters:** the twenty sample files do not agree on the namespace.
Fourteen declare GPX **1/1**, six declare GPX **1/0** — both berlin.de downloads, from the same
archive. So a port that pins the namespace to the version it happened to test against would silently
return **zero rows for six of the twenty files**, with no error and a plausible-looking result for the
other fourteen.

**Decision:** match with the `{*}` wildcard — `root.findall("{*}trk")` — which accepts any namespace and
is the closest thing Python has to `$gpx.trk`.

**Rejected:** registering the namespace, or stripping it from the document before parsing. Both work
for one version and quietly fail for the other, which is the failure this repository keeps meeting.

**A place where Python is shorter, for once:** a GPX name is often a CDATA section, and the sibling has
to check `$name.'#cdata-section'` and fall back. `ElementTree` hands over the text of a CDATA section
like any other text, so `_name_of` is two lines with no special case.

### A bind parameter over 4000 characters

**The sibling:** `Invoke-OraQuery` carries a guard that looks like an afterthought and is not:

```powershell
} elseif ($ParameterValues[$parameterName].Length -gt 4000) {
    $parameter.OracleDbType = 'CLOB'
}
```

**Python:** `invoke_ora_query` was written without it, because nothing in the StackExchange scenario
passes a long parameter. The GeoJSON import does: a country geometry serialised as JSON runs from 125
characters to 1573724, and 190 of the 258 features are over 4000.

**Evidence** — `countries.geojson` into `SDO_UTIL.FROM_GEOJSON(:geometry)`:

| | Result |
| --- | --- |
| without the guard | **187 of 258 rows**, 71 failures with `ORA-01461: can bind a LONG value only for insert into a LONG column` |
| with the guard | **258 of 258 rows**, including Canada at 1.5 MB |

**Decision:** the same guard, the same limit — declare any string parameter longer than 4000
characters as `oracledb.DB_TYPE_CLOB` via `setinputsizes`.

**The part worth pausing on:** this is the exact opposite of the decision two entries up. In the bulk
path, declaring a CLOB column costs 30× and is therefore avoided; here, declaring it is the only way
the value arrives at all. The difference is where the value is going — `executemany` into a `CLOB`
*column* works undeclared, while a single `execute` binding into a *function argument* does not,
because oracledb sends it as a LONG and Oracle only accepts a LONG bind for a LONG column. Same driver,
same data type, opposite answers.

**Why it matters:** the failure is loud, but it is also partial — 187 rows landed and looked fine. A
row count is not a check.

### Selecting a geometry column, three answers

**The sibling:** notes in the demo that `SELECT * FROM dbo.berlin_tours` does not work and records the
error — `DataReader.GetFieldType(2) returned null` — then selects `geometry.STAsText()` instead.

**Python:** the same statement fails, with a different message, and the three providers disagree about
what a geometry column even is over the wire:

| | `SELECT *` on the geometry column |
| --- | --- |
| SQL Server | fails: `ODBC SQL type -151 is not yet supported. column-index=2 type=-151` |
| PostgreSQL | succeeds, and returns a `str` — the hex EWKB, `0102000020E6100000…` |
| Oracle | an `SDO_GEOMETRY` object, which is why the demo asks for WKT instead |

**Consequence:** the lesson survives the port intact, and gets slightly better. The sibling shows that
you have to convert on the way out; here you can also see that "cannot represent it" and "hands you
something unusable" are different failures, and only one of them tells you so.

**Decision:** the demo reads geometry back as WKT everywhere — `geometry.STAsText()`,
`SDO_UTIL.TO_WKTGEOMETRY(...)` — exactly as the sibling does. WKT is the common currency between all
three, in both directions.

### Except on Oracle, where the round trip is not symmetrical

**The sibling:** puts one line in `03_geodata.ps1` with a comment — `SDO_UTIL.TO_WKTGEOMETRY` fails
with `ORA-13199: wk buffer merge failure` — and a link to a Stack Overflow question about it.

**Python:** the same, and looking closer makes it worse rather than better. It is not that the call
fails; it is that it fails for *some* rows, and one failing row takes the whole statement with it.

**Evidence:**

| | |
| --- | --- |
| `SELECT … TO_WKTGEOMETRY(geometry) FROM countries` | fails, `ORA-13199` |
| the same, row by row | most convert, a fifth to a quarter fail |
| `FETCH FIRST 3 ROWS ONLY` | *succeeds*, because those three happen to be convertible |
| the GPX table, rectified on the way in | **35 of 49 convert, 14 fail** |

**Four explanations checked, none of them right:**

- **Not size.** Canada is the largest geometry in the file, 1.5 MB of JSON, and it converts.
- **Not validity.** `SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT` returns the same
  `13367 [Element <1>] [Ring <1>]` for rows that convert and rows that do not.
- **Not a missing `RECTIFY_GEOMETRY`.** Rectifying on the way out rescued 10 of 57 in one run. And the
  GPX geometries *are* rectified on the way in, and 14 of 49 still failed.
- **Not deterministic, and this is the finding.** Four runs over identical data gave **59, 57, 49 and
  49** failures — and the membership moves as well: Oman and Uzbekistan converted in one run and failed
  in another. So it is not a property of particular geometries that could be cleaned up in advance.
  It is the same stored geometry getting a different answer from one call to the next.

**Consequence for the notebook:** no number can be written into the narration as a fact, because the
cell above it will disagree on the next run. The markdown says "around a fifth" and lists the four
counts observed, rather than claiming one.

**Decision:** leave it in the notebook as a dead end, with the investigation written out. The
`BERLIN_TOURS` cell reads a `COUNT(*)` rather than WKT, because a `FETCH FIRST 3 ROWS ONLY` there is a
coin flip and a demo cell should not be one.

**The real consequence, and it is worth saying out loud:** on SQL Server and PostgreSQL, WKT goes in
and comes back out. On Oracle it goes in reliably and does not always come back. That asymmetry is a
property of Oracle Spatial, not of the port — but it is the port that found out how big it is.

## PhotoService

### The application that generates the data

**The sibling:** `docker/photoservice-app.ps1` runs in a PowerShell container and is the shop itself —
it invents a customer a minute and an order a second, pays and ships them, and writes into PostgreSQL,
MongoDB and MinIO. It dot-sources `./lib/*-Pg*.ps1`, `*-Mdb*.ps1` and `*-Mio*.ps1` out of the
repository, mounted into the container, and mounts the PowerShell modules from the WSL2 host.

**Python:** the file came over verbatim with `docker/` and could never have run here — this repository
has no PowerShell `lib/` to dot-source. The `photoservice` service was commented out in
`docker-compose.yaml` until somebody decided what to do about it.

**Decision: ported to `docker/photoservice-app.py`.** It is not decoration. Without it, `customer`,
`order_header` and `order_detail` are empty, and the entire second half of the demo — transferring only
what is new while the source keeps writing — has nothing to transfer. It runs on a stock
`python:3.13-slim` image, mounts the same `lib/` the notebook imports, and installs its three drivers
when the container starts, which keeps the repository free of a Dockerfile.

Five things changed on the way over, and each one is the same kind of difference the rest of this file
records:

- **The logging archive is gone.** The sibling collects logging events and writes them to MinIO as
  JSON, where the notebook picks them up again. MinIO is not ported, so the events are printed with
  their component names instead and `docker compose logs -f photoservice` is where you watch the shop
  run. See the MinIO section for what that costs the demo.
- **`Remove-MdbCollection` was not needed.** The sibling calls it to clear the `Orders` collection at
  startup. pymongo drops a collection in one line, so that is the line — rather than a
  `remove_mdb_collection` in `lib/` with one caller.
- **`$PSDefaultParameterValues` has no counterpart.** The sibling turns `-EnableException` on for every
  `-Pg` and `-Mdb` call at once. Every call in the Python app passes `enable_exception=True` itself,
  which is the same point `lib/README.md` already makes about that switch.
- **`commit=False` where the sibling uses `-Transaction`.** The order header and its details are one
  unit of work in both versions; see *A transaction has no object to pass around*.
- **The prices had to be converted.** See below.

**Rejected:** leaving it as PowerShell and copying the sibling's `lib/*-Pg*.ps1` and `*-Mdb*.ps1` into
this repository, which would have been quickest to get running and would have put PowerShell back into
a repository that deliberately has none. **Also rejected:** dropping the application and seeding a fixed
set of customers and orders in `05_sample_data_setup.py`, which is cheaper still but turns "transfer
what changed while you were reading" into a story the audience has to take on trust.

### Binary data needed no code at all

The one data shape the port had not touched, and the expectation was that it would be the expensive
one. It was not.

**The sibling:** `Get-Content -AsByteStream -Raw` produces a `[byte[]]`, and Npgsql binds it to a
`bytea`.

**Python:** `Path.read_bytes()` produces `bytes`, and psycopg binds it to a `bytea`. Reading it back
gives `bytes` again — not a `memoryview`, which was the thing worth checking, because a `memoryview`
would have needed converting before it could be compared or written to a file.

**Measured against the running containers**, driving the real `lib/` functions:

- All 24 photos into the `bytea` column through `invoke_pg_query` with a parameter value: **2.9 s**,
  largest file 4,045,546 bytes. Every one of them **byte for byte identical** to the file on disk.
- Streamed from PostgreSQL into SQL Server `VARBINARY(MAX)` with `get_pg_data_reader` and
  `write_sql_table`: **2.3 s**, and every column of every row matched the source — not just the row
  count, and not just the length of the image.
- `uuid.UUID` reaches a `UNIQUEIDENTIFIER` through pyodbc unchanged, and a `TIMESTAMP(3)` reaches a
  `DATETIME2` unchanged. Both were checked because the order tables carry them.

**Decision:** nothing was added to `lib/`. No converter, no `setinputsizes`, no branch — which is worth
saying out loud, because the Oracle `TIMESTAMP` and `CLOB` entries above are exactly the cases where a
type *did* need declaring, and the contrast is the lesson. The only thing the notebook changes is
`batch_size`, down from 1000 to 5: `fast_executemany` sizes its bind buffer from the longest value in
the batch, so a thousand four-megabyte rows would multiply out into gigabytes of buffer for twenty-four
rows' worth of data.

**A check that failed for the wrong reason, which is worth recording next to the one that passed for the
wrong reason:** the first run reported the milliseconds as lost — source `…14.006533`, target
`…14.007000`. The comparison was against the original Python `datetime`, truncated to milliseconds. But
PostgreSQL **rounds** a `TIMESTAMP(3)`, it does not truncate: `.001500` becomes `.002`, `.001499`
becomes `.001`, and `.999999` becomes the next second. Comparing the two *databases* instead of the
database against Python showed the value arriving unchanged. The Oracle entry above is a real defect
found by comparing values; this is the same technique producing a false alarm by comparing against the
wrong reference.

### The first `_` helper that is used outside its own file

**The sibling:** `Get-SqlDataReader`, `Get-OraDataReader` and `Get-PgDataReader` all take
`-ParameterValues`, and each one builds its parameters with the same few lines the `Invoke-*Query`
functions use.

**Python:** the three reader functions were written without it, and `lib/README.md` recorded the reason:
supporting it would mean copying the whole named-parameter rewrite into three more files, and no demo
passed parameters to a reader. **The PhotoService scenario passes them in six cells** — "everything after
the id the target already has" is the entire incremental-transfer technique, and the id is a parameter —
so the reason expired.

**Decision:** each reader imports `_prepare_query_and_params` from its own `invoke_*_query` module.
`lib/` already carries three copies of that regex, one per provider; three more would have made six.

This bends the rule in `AGENTS.md` that a `_` helper lives in the same file as its caller, and it is the
only place that happens. It is defensible on the terms the rule exists for: the modules are flat files on
`sys.path`, so the import is one readable line, and on a slide
`from invoke_pg_query import _prepare_query_and_params` says something true and useful — the reader and
the query function understand `:name` the same way because it is literally the same code.

**Rejected:** copying the helper three times, which is what the original note assumed would be necessary;
and promoting it to a `lib/_parameters.py` shared module, which would have been the tidy answer in a
package and is exactly the kind of indirection this repository does not want.

**Caught by:** stepping through the notebook. `get_pg_data_reader() got an unexpected keyword argument
'parameter_values'` — static checks were green, because a wrong keyword argument is only an error when
the call runs.

### A NUMERIC does not fit in a BSON document

**The sibling:** Npgsql hands back a `[decimal]`, and Mdbc converts it while building the document.
Nothing in `photoservice-app.ps1` mentions types.

**Python:** psycopg maps `NUMERIC` to `decimal.Decimal`, and **BSON cannot encode one**. pymongo raises
`InvalidDocument` rather than guessing, because the lossless BSON type is `Decimal128` and the lossy one
is a double, and it will not choose for you.

**Decision:** the application converts a photo price to `float` when it builds the order document, and
leaves it a `Decimal` everywhere it goes into a `NUMERIC` column. A shop price with two decimal places
is exactly what a double represents badly in theory and perfectly well in practice at this scale, and
`Decimal128` would have put a BSON type into a document the notebook then has to read back.

**Why it matters:** it is the same lesson as the timestamps that lost their milliseconds, in a friendlier
form — the driver that refuses to guess costs you one line, and the driver that guesses costs you a
day of looking for the missing digits.

## ProjectStatus

### A missing cell is a float

**The sibling:** `Import-Excel` hands back `$null` for an empty cell, and `$null` is what ADO.NET
wants for a `NULL`. Nothing in `demo/05_projectstatus.ps1` mentions it.

**Python:** pandas has no null. A missing value in a frame is `NaN`, which is a **float**, and binding
a float into a `VARCHAR` column is not what anybody meant. The `HR System Upgrade` row has no
`Milestone` and no `MilestoneDate`, so this is not hypothetical — it is one of the eight rows.

**Decision:** the notebook's `import_projectstatus_row` converts as it builds the parameters:
`None if pd.isna(value) else value`. One line, in the open, where the audience can see why it is
there.

**Already handled in `lib/`:** all five `write_*_table` functions have done this since the Timesheets
scenario — `None if position is None or pd.isna(row[position]) else row[position]`. This entry exists
because the row-by-row path is written in the notebook rather than in `lib/`, so the same question
comes back in a place where nobody had answered it yet.

**Why it matters:** it is the smallest possible example of the difference this whole file is about.
`$null` and `NaN` look like the same idea until one of them reaches a driver.

### The bulk load fails, but not in the same place

**The sibling:** `Write-SqlTable` never reaches the database. It fills a `DataTable` whose columns are
typed from the target schema, and the fill throws:
*"The string 'Late july 2026' was not recognized as a valid DateTime."* A client-side type conversion,
naming the value that caused it.

**Python:** `write_sql_table` binds with `fast_executemany`, which sizes its buffer from the target
column and hands the values to the driver. It fails with
`('String data, right truncation: length 158 buffer 100', 'HY000')` — the 79-character `Status`
against a `VARCHAR(50)`, both counted in UTF-16 bytes, and naming neither the column nor the row.

**Decision:** nothing changed. Both versions do the thing the demo is about — refuse the whole batch,
import nothing, and report one problem out of four — and they pick a *different* one of the four to
complain about, which is worth showing rather than smoothing over. The notebook says so.

**Why it matters:** it makes the argument better than a tidy message would. The lesson of the
scenario is that a bulk load gives you one answer for the whole batch; that the Python answer is also
the more opaque of the two only sharpens it.

### `-DataOnly` is a switch, `dropna` is a decision

**The sibling:** `Import-Excel -DataOnly` drops the blank rows on the way in.

**Python:** `pd.read_excel` returns them, three rows of `NaN`, because the managers left a gap between
the sections of the form. `dropna(how="all")` is the counterpart, and it is a line in the notebook
rather than a parameter.

**Consequence, and it is the useful half:** the sibling needs two guards in its import loop, one for
`Title -eq ""` and one for `NEW PROJECTS:`. After `dropna(how="all")` the blank rows are gone
entirely, so only the second guard is left. Slightly less code, and the reason for it is visible.

## Kafka

### The one thing here that was not a port, until the sibling caught up

Everything else in this file explains why a translation came out the way it did. This entry was the
exception: Kafka started here, as an addition rather than a difference, and it is written down because
there was nowhere else recording why the two repositories had stopped being the same shape.

**The sibling caught up on 2026-08-15.** It has `demo/06_eventstreaming.ps1`, five `lib/*-Kfk*.ps1`
functions and the same two Redpanda services, copied from this compose file including the two
advertised listeners. So this is a difference in *origin* now, not in content — see "What the .NET
client forced" at the end of this entry for the handful of places the two really do differ.

**How it happened:** MinIO was dropped for two good reasons, and the cost recorded at the time was
that the PhotoService demo lost its *"Transfer data from logging (or kafka)"* section — the one that
replays the application's own events into a target instead of comparing two databases. That section is
the only place either repository talks about event streaming, and losing it was collateral damage from
a decision made about *object storage*. The sibling's own section title says what the real answer
always was.

**Decision:** a `kfk` column in `lib/`, a Redpanda container, and `demo/06_eventstreaming.ipynb`.
Redpanda rather than Apache Kafka because it speaks the Kafka protocol — so every client call, every
word on the slide and everything the audience learns is Kafka — while being one container with no JVM,
which matters next to the five that were already there and an Oracle image that wants 3 GB.

**What stayed a port:** the events keep the shape of the sibling's `Add-LoggingEvent`, and the replay
loop in the notebook is a translation of the loop in `demo/04_photoservice.ps1`. Only the transport
underneath changed, from files in a bucket to messages on a topic. So the section is *recovered*, not
invented — which is the difference between this and simply adding a feature.

**Rejected:** keeping MinIO, which would have restored the two lost sections most cheaply but answers
the storage question rather than the streaming one, and leaves the licence reason untouched. **Also
rejected:** stopping at the `order_event` outbox table, which needs no new infrastructure and is now
the *opening* of the demo rather than the whole of it — it makes the case for a log by running into
the three problems a log solves.

**What it cost while it lasted:** the two repositories could not be shown side by side for this one
section, because one side was empty. That is over.

### What the .NET client forced

Both sides wrap **librdkafka** — `confluent-kafka` here, `Confluent.Kafka` there — so the two demos
are near-identical in shape. Four things still came out differently, and all four are the wrapper
rather than the language:

- **Loading the driver is real work over there.** `pip install confluent-kafka` brings a wheel with
  the native library inside it. `Import-KfkLibrary` has to fetch *two* nuget packages and put the
  native one beside the managed assembly, pick a different build per platform, and cope with `lib/`
  being shared by Windows, WSL2 and the container at once. Nothing here has an equivalent problem.
- **The plain Linux `librdkafka.so` is unusable on Ubuntu.** It links `libsasl2.so.3` where Ubuntu
  ships `libsasl2.so.2`; the sibling takes the `centos8` build, which has everything linked in. The
  manylinux wheel here hides all of that.
- **There is no `producer.list_topics()`.** Metadata belongs to the admin client in .NET, so both
  sibling connect functions build a dependent admin client purely to prove the broker answers, where
  `connect_kfk_producer` just calls `list_topics`.
- **`read_kfk_topic` has an `as_type` and `Read-KfkTopic` does not.** Here the choice is DataFrame or
  dict; there `ConvertFrom-Json` already produces the `[PSCustomObject]` that is the canonical shape,
  so there is nothing to choose. Language, this one, not the wrapper.

**And two things the sender does differently, which shows up in the messages themselves.**
`json.dumps(..., default=str)` renders a `datetime` and a `UUID` as plain strings; PowerShell's
`ConvertTo-Json` renders a `[datetime]` as an ISO string but expands a `[guid]` into an *object* with
`value` and `Guid` properties, which is why the sibling's replay reads `.PaymentUuid.Guid`. Coming
back, `json.loads` leaves a timestamp a string while `ConvertFrom-Json` turns it into a `[datetime]`
by itself. Same lesson on both sides — JSON has no date, no decimal and no GUID, so the sender
decides — reached by opposite routes.

### A topic has no end

**Every other read function in `lib/`** asks a question and gets an answer. `invoke_sql_query` returns
when the rows run out; even `read_mdb_collection`, which streams, streams something finite.

**`read_kfk_topic` cannot.** A topic is a log that the producer is still writing to, so "read it" has
no natural end and the function needs a stopping rule instead: `first` messages, or `timeout` seconds
with nothing new.

**Decision:** both, as explicit parameters, and the notebook says why rather than treating it as an
awkwardness. It is the clearest illustration in the repository of the difference between querying a
state and reading a history.

**And the related trap, which is worse:** `from_beginning` sets `auto.offset.reset`, which applies
**only to a consumer group with no committed offset**. Passing it to a group that has read before does
nothing whatsoever. There is deliberately no "start again" parameter, because Kafka has no such thing —
starting again means a new `group_id`. `lib/README.md` and the notebook both say so, because it is
what everybody gets wrong first, and in a stepped-through notebook — where cells are re-run constantly —
it shows up as "the cell returned nothing the second time" rather than as an error.

## MongoDB

### A connection that is not a connection

**The sibling:** `Connect-MdbInstance` returns a `PSCustomObject` with three fields — `Client`,
`Database` and `Collection` — because the Mdbc module needs all three, and it takes a `-Collection`
parameter to fill the third.

**Python:** pymongo has the same three objects, and `Database` is the one everything else hangs off:
`connection["Users"]` is the collection.

**Decision:** return the `Database`. The write and read functions take the collection by name, which
keeps their call sites looking like the other four providers', and `-Collection` on the connect
function disappears because it has nothing left to do.

**Rejected:** a dict of the three handles, mirroring the sibling exactly. It would have made every
function start by unpacking it, for no gain. Also rejected: returning the `MongoClient`, which is the
closest thing to what the other four return, but then every call would need the database name as well
as the collection name — and no sibling call site does.

**The cost, and it is real:** a `Database` has no `close()`. The client behind it does, so the notebook
and `06_test_connections.py` both end with `connection.client.close()`. That is the one place where
this decision leaks, and it is commented at both call sites.

### The connection that was never made

**The sibling:** `Connect-Mdbc` contacts the server, so a wrong password or a stopped container fails
inside `Connect-MdbInstance`, like every other connect function in the library.

**Python:** `MongoClient(...)` does not talk to the server at all. It resolves the topology lazily, on
the first operation. So the obvious translation returns a perfectly good-looking database object for a
server that is not running, and the failure appears later, somewhere else entirely.

**Evidence:** with no ping, `connect_mdb_instance` against port 27099 — where nothing listens — returned
a `Database` and printed `Returning database object`. `06_test_connections.py`, whose whole purpose is
to prove the databases are reachable, would have passed.

**Decision:** `connect_mdb_instance` runs `client[database].command("ping")` before returning.
Verified both ways: a dead port and a wrong password now both fail during the connect, with
`[ERROR] Connection failed: …`, exactly as the other four do.

**Why it matters:** this is the only connect function in `lib/` where "it returned an object" does not
mean "it worked". The test script that exists to catch unreachable databases was the thing most likely
to be fooled by it.

### Nothing to ask about the types

**The sibling:** builds the documents by hand — `_id = [int]$row.Id`, `CreationDate =
[datetime]$row.CreationDate` — because there is no schema to convert against.

**Python:** the same, and for once the port is *shorter* rather than different. The XML rows are
already dicts, which is what pymongo wants, so the `[PSCustomObject]@{ … }` block becomes a dict
literal and nothing else has to change.

**The interesting part is what is absent.** Every other write function in `lib/` starts by asking the
target for its columns: `SELECT TOP 0 *`, `SELECT * FROM t WHERE 1=0`. That is where the converters
come from for SQL Server, where the two `TIMESTAMP` declarations come from for Oracle, and what
`COPY` makes unnecessary for PostgreSQL. A collection has no columns, so `write_mdb_collection` has
nothing to ask, nothing to match, and no converter table — it inserts what it is handed.

**Decision:** the conversion lives in the notebook, in the open, where the sibling also keeps it. The
alternative — accepting a DataFrame like the other four write functions and inserting
`to_dict("records")` — was rejected because it would move the typing into pandas dtypes and then need
`NaN` turned back into `None` and `Id` renamed to `_id` inside the function, which is more machinery
to hide a thing worth showing.

**Verified:** all 12220 documents round-trip with their types. `_id` and the counters come back as
`int`, the dates as `datetime` — and BSON stores a date to millisecond precision, which is exactly
what these files carry, so every one of the 12220 `LastAccessDate` values matches the file. Checked
rather than assumed, because the Oracle entry above is what happens otherwise.

## MinIO

### Not ported, and not pending either

**The sibling:** has `Connect-MioInstance` and four file functions, `Get-MioFile`,
`Get-MioFileList`, `Set-MioFile` and `Remove-MioFile`. They hand-roll AWS request signing as script
methods on a `PSCustomObject`, with no SDK involved. `05_sample_data_setup.ps1` uploads the
StackExchange files to a bucket, and `demo/02_stackexchange.ps1` ends by listing the bucket and
reading `Users.xml` back out of it.

**It is Signature Version 2, not SigV4** — HMAC-SHA1 over `verb \n content-md5 \n content-type \n date
\n /bucket/key`, base64, into an `Authorization: AWS <key>:<signature>` header. This file said SigV4
in two places until 2026-08-15 and so did the sibling's `AGENTS.md`; the code was always correct SigV2,
only the description was wrong. It matters for the paragraph below: SigV2 is four lines, while SigV4
would be a canonical request plus four chained HMAC-SHA256 rounds and a rather different talk.

**Decision: this is out of scope, not on the to-do list.** Two independent reasons, and either would
have been enough:

- **MinIO changed its licence.** Building a teaching repository on it is no longer something to
  recommend to an audience.
- **It is not what this repository is about.** Every other provider here answers the same question —
  how do rows get into and out of a database, and what has to happen to their types on the way. MinIO
  answers a different one: how does a *file* get uploaded and downloaded. The demo would show a file
  going up and coming back down unchanged, which is a storage story rather than a data-movement story.

**What that costs, and it is worth being honest about it:** the sibling's hand-rolled signing is the
most interesting code in either repository, precisely because nothing hides it. Porting it would have
meant either doing the same in Python — signing requests by hand — or reaching for `boto3` or `minio`,
which would have been the first time a library hid the protocol being demonstrated, the same category
of decision as "no SQLAlchemy". That comparison would have been a good five minutes of a talk. It is
not enough to keep a deprecated dependency for.

**The sibling is not deleting the code, though** (decided 2026-08-15). Its five `lib/*-Mio*.ps1` files
stay and its `lib/README.md` gained a *"MinIO is on its way out of the lab"* section with a worked
example of all five functions; only the container and the call sites go. So the code stays readable
over there, and this side still has no counterpart — which is the difference this entry records.

**Consequences elsewhere:**

- The `mio` column of the function grid in `lib/README.md` stays empty **by decision**. Nobody should
  read it as a gap and fill it in.
- **The container is gone too, and that decision has now been made.** For a long time the `minio`
  service stayed in `docker/docker-compose.yaml` with `minio-init.sh` and the two policy files, on the
  grounds that removing inherited infrastructure was a separate question from not porting it. Once the
  sibling was scheduled to lose MinIO as well, that reason expired: the service, its init script, its
  two policy files and its `.env` block have been deleted, and `06_test_connections.py` no longer
  prints the console URL. Nothing in the user-facing documentation mentions MinIO any more; the
  reasoning lives here, in `AGENTS.md`, and in `SIBLING-FINDINGS.md` entry 9.
- `05_sample_data_setup.py` downloads the StackExchange files and stops there. The upload block of the
  sibling has no counterpart and will not get one.
- **Two sections of the PhotoService demo went with it**, and that consequence was only noticed when
  that scenario was ported. The sibling's *Transfer data from logging (or kafka)* replays the
  application's logging events out of MinIO into SQL Server, and its *Bonus: Import Logging from files
  on MinIO* loads the same archives into a `logging` table. Both read the bucket, so both were gone —
  and with them the one part of the demo that showed event data as an alternative to comparing two
  tables.

  **The first of those has since come back, with Kafka underneath it instead of a bucket** — see the
  Kafka section. That was the right conclusion in the end: the event streaming story had been lost to
  a decision about object storage, which is a different subject, and the sibling's own section title
  said so all along. The second one, loading log archives into a `logging` table, is still gone and
  is not coming back; it is a file-import demo and demo 2 already is one.

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

### A wait that cannot say why it failed

**Symptom:** none observed — this is the failure mode the wait above would have had the first time it
went wrong in front of an audience.

**Cause:** the probes send stderr to `/dev/null`, and they have to. For most of the wait, "the user
does not exist yet" and "the database is not there yet" *are* the normal answers, so printing them
would fill the screen with errors that mean nothing. But that leaves the give-up path with one line
and no diagnosis, and it keeps probing for the full 5 or 15 minutes even when the container has
already exited — a container killed by its `mem_limit` is indistinguishable from a slow one.

**Decision:** `wait_for` checks `docker compose ps --status running` on each round and stops early if
the container is gone, and the failure path prints `docker compose logs --tail 50` for that service.
The first argument became the **compose service name** rather than a display name, so the message names
exactly what you would type next.

**And the daemon itself is waited for.** `02_wsl2_setup.sh` starts docker, but `01_setup.ps1` runs
`wsl --shutdown` immediately afterwards, and `start_demo.ps1` runs after a reboot. In both cases
the daemon comes back only because systemd starts it, which is a race against `docker compose up`
running seconds after WSL2 boots. `04` now runs `service docker start` and polls `docker info` before
it does anything else.

**Rejected:** a `healthcheck` per service in the compose file with `depends_on: condition:
service_healthy`. It is the idiomatic answer and it would move the waits out of the shell script — but
the thing being waited for is not "the server answers", it is "the init script has finished creating
the last demo database", which is what actually bit. Expressing that as a healthcheck means the same
query in a less visible place, and the setup step would stop being able to explain itself.

### The one password, in fifteen files

**The sibling:** the same, verbatim — `docker/` came over unchanged.

**What was there:** `README.md` said the password "is configured in `docker/.env`". It appears 22 times
across 15 files in `docker/`, and `.env` fed four container environment variables. `sqlserver-init.sh`
had it as a literal six times, in a container that already has `MSSQL_SA_PASSWORD` in its environment,
and `04_docker_compose.sh` had it three more times. Changing `.env` would have broken the setup in
places that look unrelated to it.

**Decision:** `sqlserver-init.sh` uses `$MSSQL_SA_PASSWORD`, and `04_docker_compose.sh` sources
`docker/.env` — which is valid shell as well as a Compose env file — and uses `$MSSQL_SA_PASSWORD` and
`$PASSWORD` in its probes.

**Not changed, deliberately:** the `CREATE USER` statements in `sqlserver-*.sql`, `oracle-*.sql`,
`postgres-*.sql` and `mongo-init.js`. Making those interpolate means an entrypoint that rewrites SQL
before running it, and the visible password is part of the teaching — a `CREATE USER ... WITH PASSWORD
'Passw0rd!'` on a slide says what it does. `README.md` now states which files still hold the literal
instead of implying there is one place.

### The half of the setup nothing checked

**The sibling:** the same gap, and worse — its `06_test_connections.ps1` also runs only inside WSL2,
while its demos run from Windows PowerShell.

**What was there:** `01_setup.ps1` shelled into WSL2 for every step, including
`06_test_connections.py`. The notebooks run on the **Windows** interpreter, whose packages came from a
prose list in `README.md` that had to be kept in sync by hand — and had drifted twice, for `pymongo`
and for `confluent-kafka`. So the setup could finish completely green while the machine that runs the
demo had no driver at all.

**Decision:** `01_setup.ps1` ends with a `pip install` on Windows and a second run of
`06_test_connections.py` there. The same script, both sides — the check is worth nothing on the side
that never opens a notebook, and it needed no new code to move it to the side that does.

**Consequence, and it was not free:** adding a dependency meant editing **two** `pip install` lines, in
two different files and two different languages, plus two prose lists. That is worse than one list, and
it had already failed twice before this change existed. It is what finally produced a
`requirements.txt`:

- `requirements.txt` is the shared list, installed by `03_python_setup.sh` inside WSL2 and by
  `01_setup.ps1` on Windows.
- `requirements-windows.txt` is `-r requirements.txt` plus `notebook`. Two files rather than one,
  because nothing inside WSL2 ever opens a notebook and installing a Jupyter server there to save a
  file would contradict the reason the two sides differ at all. The `-r` include means the shared list
  physically cannot drift — which was the whole complaint.

**Rejected:** one file installed on both sides. It is shorter, and it puts a notebook server inside
WSL2 that nothing runs. Also rejected: pinned versions and a virtual environment, which `README.md`
deliberately does without and which nobody has asked for.

**What it caught on its very first run, which is the point:** a connection failure to Oracle from
Windows, seconds after the WSL2 run of the same script had connected to the same database. See below.

### Two loopbacks, and only one of them is the demo's

**Symptom:** `DPY-6005` / `WinError 10061` connecting to Oracle from Windows, while `06` had just
passed inside WSL2 and `wait_for oracle` had confirmed the demo user exists.

**Cause:** `127.0.0.1:1521` does not mean the same thing on the two sides of WSL2. Inside WSL2 it is
docker's published port. On Windows it is a `wslrelay` listener that Windows creates a moment after
docker binds the port inside the VM — and those moments are not the same for every port. Four of the
five forwards were up; 1521 was not yet. Verified afterwards with the containers still running: every
port had a relay listener, every one accepted a connection, and the Windows `06` passed with exit 0.

**Why this is not a Python difference at all,** and is recorded here anyway: it is the one place where
the *shape* of this repository — WSL2 for the infrastructure, Windows for the demos — produces a
failure the sibling would produce identically. It is written down because the error names Oracle and
means the network.

**Decision:** `01_setup.ps1` waits until all five database ports accept a connection *from Windows*
before it runs `06` there. Same idea as the waits in `04`, one boundary further out. Silent, and 0.1 s
when the forwards are already up.

**Rejected:** retrying `06` a few times instead. It would have worked, but each attempt prints a full
traceback, so a genuinely broken driver would bury its own diagnosis under three copies of a stack. The
wait is silent until it gives up, and then it names the port rather than the database.

**Not established:** *why* one port lags the others. Do not invent a mechanism for it.

---

## The demos themselves

### Stepping through

**The sibling:** every demo script starts with a bare `break`, and is executed section by section with
F8 in VS Code.

**Python:** a notebook, executed cell by cell.

**Consequence, and it was decided twice.** A notebook *can* carry its outputs, and a `.ps1` cannot, so
for most of the port they were committed: the repository showed printed frames and `[VERBOSE]` lines to
a reader with no database. That had a cost — they go stale. Adding the `[VERBOSE]` prefix to
`write_sql_table` invalidated one cell's output, which then had to be re-run rather than edited.

**On 2026-08-15 the decision was reversed and the outputs are cleared.** Three reasons, in the owner's
order: the two repositories are shown side by side and the sibling has never had output to read, so
committing it here made the halves unequal; the files are much smaller, 560 KB down to 169 KB for the
six; and every session then starts from the same empty state. The cost is the one the old decision was
buying — a GitHub reader now sees code and narration but no results, and has to run it.

Output must still never be written by hand.

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
