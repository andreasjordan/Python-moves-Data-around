# lib/ — the data access layer

These functions are the plumbing the demos build on. They are plain functions in plain files — no
package, no `__init__.py` — so that a notebook can show exactly which code is being called. `lib/` is
put on `sys.path` and each function is imported by name:

```python
import sys
from pathlib import Path

sys.path.append(str(Path("../lib").resolve()))

from connect_sql_instance import connect_sql_instance
from invoke_sql_query import invoke_sql_query
from write_sql_table import write_sql_table
```

This is the counterpart to dot-sourcing in the sibling repository
[PowerShell moves Data around](https://github.com/andreasjordan/PowerShell-moves-Data-around), whose
`lib/` has 41 functions. This one has thirty-three.

Every module is `<verb>_<prefix>_<noun>.py` and holds one public function of the same name, so
`Connect-SqlInstance` ↔ `connect_sql_instance`. Prefixes: **sql** = SQL Server · **ora** = Oracle ·
**pg** = PostgreSQL · **mdb** = MongoDB · **kfk** = Kafka.

Every function takes `enable_exception=False`. With it, a failure raises; without it, the function
logs the message at `ERROR` and returns `None`. Callers turn it on per call — there is no equivalent
of PowerShell's `$PSDefaultParameterValues`, which is why it has to be passed explicitly.

**Nothing here prints.** Messages go to `logging.getLogger("lib." + __name__)`: `debug` for the
running commentary, `info` for bulk-load progress, `error` for the failure path above. That is the
counterpart of the sibling's PSFramework, and it means a caller that has configured nothing sees
nothing — which is why `06_test_connections.py` and `verify/` are quiet. `demo/configure_logging.py`
is what a notebook calls to put the progress on screen, everything in `demo.log`, and every message
into a `MessageLog` that becomes a DataFrame — the counterpart of `Get-PSFMessage`.

## What exists today

### `connect_sql_instance(instance, database=None, username=None, password=None, pooled_connection=False, enable_exception=False)`

Returns an open `pyodbc.Connection`, or `None` on failure. Builds the connection string from
`ODBC Driver 18 for SQL Server` — that driver has to be installed separately, see `README.md`.
`username` **and** `password` together select SQL authentication; either one missing falls back to
`Trusted_Connection=yes`, so integrated security is the default. `TrustServerCertificate=yes` is always
appended, because the container's certificate is self-signed.

### `invoke_sql_query(connection, query, as_type="DataFrame", parameter_values=None, commit=True, enable_exception=False)`

Runs a query and returns the whole result in memory.

- `as_type` selects the shape: `"DataFrame"` (default), `"dict"` (a list of column→value dicts, the
  closest thing to the sibling's `PSObject`), `"list"` (the raw `pyodbc.Row` objects), or
  `"single_value"` (the first column of the first row, or `None`).
- `parameter_values` accepts a list or tuple, which is passed straight through to pyodbc's positional
  `?` placeholders, or a dict, in which case `:name` and `@name` in the query are rewritten to `?` in
  order of appearance first. pyodbc has no named parameters of its own; that rewrite is a small regex
  in `_prepare_query_and_params`. It does not know about string literals, so a `:` inside a quoted
  string in the query will be mangled. It **does** know about a doubled colon, so
  `geometry::STGeomFromText(@wkt, 4326)` and `value::numeric` survive, which the Geodata scenario needs
  in its very first statement.
- **A failed statement rolls back.** PostgreSQL aborts the whole transaction when anything in it
  fails, so `invoke_pg_query` has to; the other two do it to stay siblings. Without it, one bad query
  makes every later query on the same connection fail with a message that does not mention the
  original mistake.
- A statement that returns no columns (DDL, `INSERT`, `TRUNCATE`) is committed unless the connection is
  in autocommit mode, and the function returns `None`.
- **A `SELECT` is committed too.** DB-API opens a transaction for a read as well, and a connection left
  idle in one keeps its locks. `invoke_pg_query` has the same line, and there it is the difference
  between a working demo and a `TRUNCATE` that hangs forever.
- **`commit=False` hands the transaction to the caller.** With it the function neither commits nor
  rolls back, so several calls make up one unit of work. This is the port of the sibling's
  `-Transaction`, which cannot be ported as a parameter: ADO.NET hands a transaction object to a
  command, and in Python the transaction belongs to the connection, so there is nothing to hand over.
  See `DIFFERENCES.md`. Note that with `commit=False` a failed statement is **not** rolled back either
  — on PostgreSQL the caller has to, because nothing else on that connection works until it does.
- `query_timeout` is present but commented out — pyodbc has no built-in statement timeout.

### `write_sql_table(connection, table, data=None, data_reader=None, data_reader_row_count=None, batch_size=1000, truncate_table=False, commit=True, enable_exception=False)`

Bulk-loads a pandas DataFrame, or the rows of a `data_reader`, into `table`, which may be
`schema.table`. Reads the target's column list with `SELECT TOP 0 *` and matches the source columns
against it **case insensitively** — extra columns are dropped, missing ones become `NULL` — then inserts
with `fast_executemany` in batches of `batch_size`, committing after each batch and printing rows done,
percentage and rows/sec. `truncate_table=True` empties the table first.

Dropping extra columns and writing `NULL` for missing ones is not a shortcut — it is what the sibling's
`Write-SqlTable` does for its `-Data` parameter as well, because it fills the target's columns from
each source object and leaves the rest untouched.

Either `data` or `data_reader`, never both. With `data_reader` the rows come from another table -
possibly in another database system - and are read in batches, so the source is never fully in memory.
`data_reader_row_count` only feeds the percentage in the progress output, because a reader does not
know how many rows are still coming. A source column with no matching target column is an error, as it
is in the sibling.

`commit=False` suppresses the commit after each batch, so that this call and the ones around it make up
one unit of work — the port of the sibling's `-Transaction`, and the reason it is not a `transaction`
parameter is in `DIFFERENCES.md`. It is what the PhotoService demo uses to write an order header and its
details together.

### `import_sql_table(connection, path, table, batch_size=1000, encoding="utf-8-sig", column_map=None, truncate_table=False, enable_exception=False)`

Reads a file line by line and loads it into `table`, so the size of the file does not matter. The first
line decides the format: `<?xml` means one `<row .../>` element per line, `{` means one JSON object per
line. For every line it builds one value per column of the *target* table, converts it, and sends the
rows in batches of `batch_size`, printing rows done, percentage of the file and rows/sec.

`column_map` names the source value for a target column, so `{"CreationDate": "Date"}` fills the
`CreationDate` column from the `Date` attribute — the same direction as the sibling's `-ColumnMap`.

Two things differ from `Import-SqlTable` and both are worth knowing:

- **The converters.** The sibling fills a `DataTable` whose columns are typed from `GetSchemaTable()`
  and lets ADO.NET convert the strings. pyodbc has no equivalent: with `fast_executemany` it binds a
  value by its Python type, so a string never arrives in an `INT` column — it fails with
  `22018 Invalid character value for cast specification`. Turning `fast_executemany` off makes strings
  work, but it was measured at 51s against 1s for the same file. So this function converts the values
  itself, choosing a converter per column from the type in `cursor.description`. A column whose type is
  not in `_CONVERTERS` is an error rather than a silent passthrough.
- **The default encoding is `utf-8-sig`, not `utf-8`.** These files start with a byte order mark.
  `Get-Content` drops it silently, `open` does not, and with plain `utf-8` the first line does not start
  with `<?xml`, so the format detection would never trigger.

A value that is missing from a row becomes `NULL`. That is not optional: in `Users.xml` three of the
twelve attributes are absent from thousands of rows, and two columns of the table are not in the file at
all.

### `connect_pg_instance(instance, database=None, username=None, password=None, pooled_connection=False, enable_exception=False)`

Returns an open `psycopg.Connection`, or `None` on failure. `instance` may carry a port as
`127.0.0.1:5432`, the same way the sibling's `-Instance` does. `pooled_connection` is accepted so that
the signature matches `connect_sql_instance`, but it only prints a note: Npgsql pools through the
connection string, while psycopg keeps pooling in a separate `psycopg_pool` package that this
repository does not use.

### `invoke_pg_query(connection, query, as_type="DataFrame", parameter_values=None, commit=True, enable_exception=False)`

The same shape and the same `as_type` values as `invoke_sql_query`. The difference is in the
parameters: psycopg has real named parameters, written `%(name)s`, so the rewrite only renames
`:name` and `@name` and hands the dictionary over unchanged. `invoke_sql_query` has to count positions
and reorder the values, because pyodbc has no named parameters at all.

### `write_pg_table(connection, table, data=None, data_reader=None, data_reader_row_count=None, batch_size=1000, truncate_table=False, commit=True, enable_exception=False)`

Loads a pandas DataFrame, or the rows of a `data_reader`, into `table` through `COPY`. Columns are
matched against the table columns **case insensitively**, so a frame with `CreationDate` fills a column called
`creationdate`. `NaN` and `NaT` become `NULL`. `batch_size` no longer splits the work into batches —
`COPY` is one stream — it only says how often progress is printed.

### `import_pg_table(connection, path, table, batch_size=1000, encoding="utf-8-sig", column_map=None, truncate_table=False, enable_exception=False)`

The counterpart of `import_sql_table`, and the call sites are identical. Two things inside are not:

- **No converters.** `COPY` hands the text to PostgreSQL, which parses it into the column type itself.
  The whole `_CONVERTERS` table of the SQL Server version is unnecessary here. It is also faster —
  measured on `Users.xml`, 12220 rows: `COPY` with raw strings 0.14 s, `COPY` with converted values
  0.30 s, `executemany` with raw strings 0.95 s, `executemany` with converted values 1.27 s.
- **Identifiers are lower cased.** PostgreSQL folds unquoted identifiers, and the tables of this
  repository are created unquoted, so the catalog holds `users` and `creationdate`. Both the table
  name and the keys of every row are lower cased before they are matched. Without that, not one of the
  fourteen columns of `Users` would match an attribute of the file, and the import would write 12220
  rows of `NULL` without an error.

`import_sql_table` lower cases as well, so that the two functions stay siblings. It is harmless there,
because `cursor.description` reports the names as SQL Server stores them.

### `connect_ora_instance(instance, username=None, password=None, as_sysdba=False, pooled_connection=False, enable_exception=False)`

Returns an open `oracledb.Connection`, or `None` on failure. **There is no `database` parameter**,
because `Connect-OraInstance` has none either — for Oracle the service name is part of the instance,
so this is called with `127.0.0.1/XEPDB1`. `as_sysdba` is the port of `-AsSysdba`; no demo uses it.

`oracledb` runs in **thin mode**, which speaks the Oracle network protocol itself, so no Oracle
Instant Client is installed anywhere in this repository. That is a bigger simplification than the
`Import-OraLibrary` DLL download it replaces.

Two things this function does that its siblings do not:

- `pooled_connection=True` really pools, through `oracledb.create_pool`. This is the third answer
  to the same question: Npgsql and Oracle's ADO.NET provider pool through the connection string,
  psycopg keeps pooling in a separate package, and `oracledb` brings its own. A connection taken
  from a pool returns to it when it is closed, rather than being closed.
- It sets **`oracledb.defaults.fetch_lobs = False`**, so a CLOB arrives as a `str`. That default is
  read when a connection is created, which is why it has to be set here and not where the rows are
  read. See the entry in `DIFFERENCES.md` — without it a `CLOB` is a lazy handle that *prints* as
  its own text, and streaming one into pyodbc fails.

### `invoke_ora_query(connection, query, as_type="DataFrame", parameter_values=None, commit=True, enable_exception=False)`

The same shape and the same `as_type` values as its two siblings, and the least work of the three
where the parameters are concerned: Oracle's own bind variable syntax **is** `:name`, so a query that
already uses it passes through untouched and only `@name` has to be renamed. The regex is identical
in all three files; only the replacement differs.

One thing it does that the other two do not: **a string parameter longer than 4000 characters is
declared a `CLOB`**, because Oracle otherwise answers `ORA-01461: can bind a LONG value only for
insert into a LONG column`. `Invoke-OraQuery` has the same guard with the same limit. Note that this
is the reverse of what `write_ora_table` wants — declaring a `CLOB` there costs 30× — because a value
bound into a `CLOB` column and a value bound into a function argument are not the same question. See
`DIFFERENCES.md`.

### `write_ora_table(connection, table, data=None, data_reader=None, data_reader_row_count=None, batch_size=1000, truncate_table=False, commit=True, enable_exception=False)`

Loads a pandas DataFrame, or the rows of a `data_reader`, into `table` with `executemany` in batches
— the same shape as `write_sql_table`, because Oracle has no `COPY`. Columns are matched **case
insensitively**, so a frame with `CreationDate` fills the `CREATIONDATE` column.

The one line that is not in either sibling is `cursor.setinputsizes(...)`, declaring the `TIMESTAMP`
columns. Without it the milliseconds are silently dropped — see below.

### `import_ora_table(connection, path, table, batch_size=1000, encoding="utf-8-sig", column_map=None, truncate_table=False, enable_exception=False)`

The third counterpart of `import_sql_table`, and the call sites are identical. What is inside sits
between the other two, which is the most interesting thing about it:

- **Two converters, not fourteen and not none.** Oracle converts the numbers out of their strings
  without being asked, so `_CONVERTERS` holds only `TIMESTAMP` and `DATE`. A column type that is not
  in the table keeps the string it came from — the inverse of `import_sql_table`, where a missing
  entry is an error, because there a missing converter means a value would be bound wrongly.
- **`setinputsizes` for the TIMESTAMP columns, and only those.** oracledb binds a Python `datetime`
  as `DB_TYPE_DATE`, and an Oracle `DATE` holds whole seconds. Converting is therefore not enough:
  the columns have to be declared as `DB_TYPE_TIMESTAMP` or the fractional seconds disappear without
  an error. Declaring the CLOB column as well was measured **30 times slower**, so it is left alone
  and a 5440 character `AboutMe` reaches the CLOB bound by its Python type.
- **Identifiers are upper cased.** Oracle folds unquoted identifiers to `UPPER CASE`, the exact
  inverse of PostgreSQL, and the tables of this repository are created unquoted. The lower casing
  that the import does *for matching* is case agnostic and needed no change; only
  `_quote_identifier` differs.

### `get_sql_data_reader(connection, table=None, query=None, parameter_values=None, enable_exception=False)`, `get_ora_data_reader(...)` and `get_pg_data_reader(...)`

Run `SELECT * FROM table`, or `query`, and return the open cursor. That cursor **is** the data reader:
`Get-SqlDataReader` returns a `DbDataReader` and disposes the command behind it, but in Python the
cursor is both at once, so it is simply returned.

The writer that receives it reads it with `fetchmany(batch_size)` and **closes it when it is done** —
the same ownership as in the sibling, where `Write-SqlTable` disposes the reader it was handed.

`get_ora_data_reader` carries the >4000-character CLOB guard, the same one `invoke_ora_query` and
`read_ora_query` have and the same one `Get-OraDataReader` has. Without it a long parameter fails with
`ORA-01460` — measured from about 250000 characters, not from 4001, which is why the entry in
`DIFFERENCES.md` warns against narrowing the limit to what a quick probe suggests.

`parameter_values` works exactly as it does in `invoke_*_query`, and it is **the same function doing the
work**: each reader imports `_prepare_query_and_params` from its own `invoke_*_query` module rather than
carrying a fourth, fifth and sixth copy of that regex. That is the one place in `lib/` where a `_` helper
is used outside the file it lives in, and it is deliberate — see `DIFFERENCES.md`. The PhotoService
scenario is what needs it: "transfer everything after the id the target already has" is the whole
incremental technique, and the id is a parameter.

Two parameters of the sibling are missing here, as they are from `invoke_*_query`: `-ParameterTypes`
and `-QueryTimeout`. Both are **decisions rather than omissions** — see the two entries in
`DIFFERENCES.md`, which say what each of the three drivers would have needed.

**`-Transaction` needs no counterpart here, and that is not an omission.** A Python cursor is created on
a connection and is already inside whatever transaction that connection has open, so there is nothing
for the parameter to do. The PhotoService demo reads two tables inside one `with pg_connection.transaction():`
block without passing anything to these functions.

**A caveat that is not visible from the call site:** psycopg's normal cursor fetches the whole result
before the first `fetchmany` returns, so `get_pg_data_reader` streams from the writer's point of view
but not from the server's. A server-side cursor — `connection.cursor(name=...)` — would change that,
and is the thing to reach for if a table ever stops fitting in memory.

### `read_sql_query(connection, query, parameter_values=None, enable_exception=False)`, `read_ora_query(...)` and `read_pg_query(...)`

The same query as `invoke_*_query`, streamed instead of collected. **These three are generators**, which
is the Python counterpart of the sibling writing one `[PSCustomObject]` per row to the pipeline: they
yield one dict per row and never hold more than one in memory.

Three things follow from being a generator, and all three are visible at the call site:

- **Nothing happens until the caller starts iterating.** `read_sql_query(...)` on its own opens no
  cursor and sends no SQL. `list(read_sql_query(...))` is what runs the query.
- **A failure therefore surfaces on the first `next()`, not on the call.** With
  `enable_exception=True` the exception is raised there; without it the message is logged and the
  generator simply ends, which is what the contract's `return None` means for a function that yields.
- **The transaction the read opens is only ended once the last row has been handed over.** A caller
  that abandons the generator half way leaves it open. On PostgreSQL that is the one worth knowing
  about, because an idle-in-transaction connection keeps its locks and the next `TRUNCATE` anywhere
  waits for it — see the entry in `DIFFERENCES.md`.

There is no `as_type`, because the sibling's `Read-*Query` has no `-As` either: it emits objects and
nothing else. `parameter_values` works exactly as it does in `invoke_*_query` and is the same
`_prepare_query_and_params` doing the work. `read_ora_query` carries the >4000-character CLOB guard as
well, for the reason `invoke_ora_query` gives — all three Oracle functions that bind a parameter have it.

The psycopg caveat above applies to `read_pg_query` too: it streams from the caller's point of view but
not from the server's.

### `export_sql_table(connection, table, path, batch_size=1000, encoding="utf-8", enable_exception=False)`, `export_ora_table(...)` and `export_pg_table(...)`

The inverse of `import_*_table`: `SELECT * FROM table` written to `path` as **one JSON object per
line**, which is one of the two formats `import_*_table` reads. So a table exported here can be loaded
straight back, into the same database or into another system — and that round trip is how these three
were checked, value by value rather than by row count.

`batch_size` only says how often progress is logged. A `SELECT COUNT(*)` runs first, for no other
reason than to put a percentage in that progress.

Two things are worth knowing about the JSON:

- **`json.dumps` refuses a `datetime`, a `Decimal` and a `UUID`**, and these tables hold all three.
  `_json_default` converts them with `str()` — the same decision `write_kfk_topic` makes — and that is
  the conversion that reads back, because `str(datetime)` is exactly what `datetime.fromisoformat`
  accepts. Milliseconds survive the round trip on all three providers.
- **A binary column is an error, not a silent passthrough.** `str(b"\x89PNG")` would write
  `"b'\\x89PNG'"`, which looks like a value and is not one, so `_json_default` raises instead — the
  same choice `import_sql_table` makes for a column type it has no converter for. Nothing needs to
  export a `VARBINARY`, `bytea` or `BLOB` today; when something does, this fails loudly first.

The default encoding is `utf-8` and not the `utf-8-sig` that `import_*_table` uses. The sibling writes
a byte order mark, because .NET's `Encoding.UTF8` emits one; this does not, and it does not matter —
the `utf-8-sig` decoder reads a file without a BOM perfectly well, so the round trip works either way.

**DIFFERENCE:** the sibling opens its `StreamWriter` first and closes it in a `finally`. Here the file
is opened in a `with` block around the loop, which is the same guarantee with less around it — so a
bad path is reported after the count query rather than before it.

### `get_sql_table_information(connection, table=None, enable_exception=False)`, `get_ora_table_information(...)` and `get_pg_table_information(...)`

Row count and size per table, as a **DataFrame**. With no `table` it lists every table in the current
schema; `table` takes one name or a list of them — a bare string is wrapped, so both call sites read the
same as the sibling's `[string[]]$Table`.

**The size column has a different name and a different unit per provider, and that is the point of
these three rather than an inconsistency:** `Pages` on SQL Server, `Blocks` on Oracle, `Bytes` on
PostgreSQL, because `sys.allocation_units`, `user_segments` and `pg_relation_size` answer in those
units. The sibling names them the same way. Normalising them to one unit would have invented arithmetic
nobody asked for and hidden the interesting part.

Three notes:

- **These are the only functions in `lib/` that call another public `lib/` function.** Each one is three
  `invoke_*_query` calls, exactly as the sibling is, and dot-sourcing makes that free over there while
  here it needs an import. See `DIFFERENCES.md` — this is a different thing from the
  `_prepare_query_and_params` import, which is a private helper.
- **`as_type="single_value"` is not the sibling's `As = 'SingleValue'`**, and this is the first caller to
  notice. PowerShell expands the whole first column into an array; this returns the first value of the
  first row and nothing else. So the list of table names is read with `as_type="list"`, and only the two
  scalars use `single_value`.
- **Identifiers are folded per provider**, `.lower()` for PostgreSQL and `.upper()` for Oracle. Without
  it, `get_ora_table_information(table="users")` finds no segment and reports `Blocks = 0` — a wrong
  answer that reads like a real one.

### `connect_mdb_instance(instance, database="admin", username=None, password=None, enable_exception=False)`

Returns a pymongo **`Database`**, or `None` on failure — not a client and not a connection. pymongo
hands out a client, a database and a collection as three separate objects, and the database is the one
everything else hangs off, so `connection["Users"]` is the collection and the write and read functions
take the collection by name. The sibling returns all three in a `PSCustomObject` because the Mdbc
module needs all three; the `-Collection` parameter it has for that reason is gone here.

Two consequences worth knowing at the call site:

- **A `Database` has no `close()`.** The client behind it does, as `connection.client.close()`. Every
  other connect function in `lib/` returns something you close directly.
- **It pings.** `MongoClient` does not contact the server until the first operation, so without that
  ping the function would return a database object for a server that is not running and
  `06_test_connections.py` would report success. The ping makes it fail where the other four fail.

There is no `pooled_connection`, because `Connect-MdbInstance` has none — and it would have nothing to
switch: a `MongoClient` is a connection pool whether you ask for one or not.

### `write_mdb_collection(connection, collection, data=None, batch_size=1000, truncate_collection=False, enable_exception=False)`

Inserts a list of dicts into `collection` with `insert_many`, in batches of `batch_size`, printing
documents done, percentage and documents/sec.

**The shortest of the five write functions, and for one reason:** there is no target schema. The other
four begin by asking the target for its columns and matching the source against them case
insensitively. A collection has no columns, so there is nothing to ask and nothing to match — the
documents go in as they were handed over, and whoever built them decided what type each value has.
That is why `demo/02_stackexchange.ipynb` builds the dicts in the open, exactly as the sibling does.

`truncate_collection=True` drops the collection, and the first insert creates it again — MongoDB has
no `TRUNCATE`, and this is what the sibling does too.

`data` is a list of dicts rather than a DataFrame, which is the one place the five write functions
disagree. `Write-MdbCollection` takes an array of `PSCustomObject`, and a document is a dict, so this
keeps both sides recognisable. There is no `data_reader` branch: nothing streams into MongoDB yet.

Three parameters of the sibling are missing. `-Convert`, `-Id` and `-Property` are options of
`Add-MdbcData` that shape the documents on the way in; here the caller shapes the dicts instead, which
is fewer moving parts and puts the shaping on screen.

### `read_mdb_collection(connection, collection, filter=None, first=None, skip=None, project=None, sort=None, as_type="DataFrame", enable_exception=False)`

Runs `find` and returns the documents, as a `DataFrame` (default) or as `dict` — the list of documents
as pymongo produced them. There is no `list`, because a document already *is* a dict, and no
`single_value`.

`filter`, `project` and `sort` are passed straight through, so a call site reads almost like the
sibling's: `-Filter @{ Location = 'Canada' }` becomes `filter={"Location": "Canada"}`. `filter`
shadows the builtin, which is deliberate — the naming rule says parameters keep the sibling's names.

`-Last` is missing, and that is a decision rather than an oversight: pymongo has no equivalent, it would
mean reversing the sort and limiting, and no demo uses it. The entry in `DIFFERENCES.md` says what was
rejected.

### `remove_mdb_collection(connection, collection, enable_exception=False)`

Drops `collection`. **The shortest function in `lib/`**, and that is what it is for rather than something
to apologise for: it sits next to `remove_kfk_topic` in `docker/photoservice-app.py`, where the two clear
the previous run together, and the contrast between them is the lesson. Dropping a collection is one
pymongo call; emptying a topic needs an admin client, a delete and a wait for the broker.

A collection that is not there is not an error — MongoDB has nothing to drop and says so quietly, which
is what the sibling's `Remove-MdbcCollection` does too.

**DIFFERENCE:** the sibling's `-Collection` is optional, because `Connect-MdbInstance` returns a
`PSCustomObject` that already holds a collection to fall back on. `connect_mdb_instance` returns a plain
pymongo `Database`, which has no default collection, so the name is required here.

Dropping is also what `truncate_collection=True` does inside `write_mdb_collection`, so the two overlap
on purpose: one is "empty it before writing", the other is "empty it and write nothing".

### `connect_kfk_producer(instance, enable_exception=False)` and `connect_kfk_consumer(instance, group_id, from_beginning=False, enable_exception=False)`

**Two connect functions, and that is the interesting thing about this provider.** Every other one
here has a single connection that reads and writes. Kafka does not: a `Producer` and a `Consumer` are
different clients with different configuration and nothing in common behind them. Returning one object
that is secretly either would have invented a connection Kafka does not have.

Both check the broker before returning, with `list_topics(timeout=10)`. Neither client contacts a
broker until its first real operation — the same trap `connect_mdb_instance` has, and the same answer.

`group_id` is what Kafka remembers a reader by: two consumers in one group share the work and one set
of offsets, and a consumer in a brand new group has never read anything. `from_beginning` sets
`auto.offset.reset`, **and that setting only applies to a group with no committed offset**. Passing it
to a group that has read before does nothing at all. There is no parameter that means "start again" —
that is what a new `group_id` is for, and `demo/06_eventstreaming.ipynb` says so out loud because it
is the thing everybody gets wrong first.

There is no `pooled_connection`: librdkafka maintains its own connections to the brokers whether you
ask or not, the same argument `connect_mdb_instance` makes.

### `write_kfk_topic(connection, topic, data=None, key=None, batch_size=1000, enable_exception=False)`

Produces a list of dicts as JSON, one message each, and **flushes before returning** — `produce()`
only queues, so without the flush a script that exits promptly loses messages that never left.

Like `write_mdb_collection` there is no target schema to match against, and one step further: a topic
has no document model either, so the caller decides the encoding. `json.dumps(..., default=str)` is
that decision. It is doing real work — the events carry `datetime` and `UUID` values and `json.dumps`
refuses both, which is the same question the MongoDB path answered with `float()` for a `Decimal`.

`key` names a field of each document to use as the message key. Kafka guarantees order per partition,
and a key is what pins related messages to the same one.

### `read_kfk_topic(connection, topic, first=None, timeout=5.0, as_type="DataFrame", enable_exception=False)`

Subscribes and reads, as a `DataFrame` (default) or `dict`. There is no `list` and no `single_value`,
for the reason `read_mdb_collection` gives: a message is already a dict.

**It needs a stopping rule, and no other read function in `lib/` does.** A query ends; a topic does
not. So it stops after `first` messages, or after `timeout` seconds with nothing new. That is not an
awkwardness of the port — it is what reading a log is, and the notebook makes the point rather than
hiding it.

**Calling it without `first` on a topic somebody is still writing to does not return.** The timeout
only fires after a gap with no messages at all, and a producer sending a few events a second never
leaves one. This is not theoretical — it hung a kernel during development, and interrupting a kernel
that is inside librdkafka is unreliable, so it had to be killed. When the topic is live, bound the
read: `first=n`, or ask the broker where the end is with
`get_watermark_offsets(TopicPartition(topic, 0))` and read exactly that many, which is what
`demo/06_eventstreaming.ipynb` does for its replay.

Offsets are committed automatically as it reads, which is why calling it twice returns different
messages rather than the same ones.

### `remove_kfk_topic(instance, topic, enable_exception=False)`

Deletes the topic and waits until the broker has really dropped it.

**It takes `instance` rather than `connection`, and it is the only function here that does.**
Deleting a topic is neither producing nor consuming, so neither of the two clients
`connect_kfk_*` returns is the right thing to hand over; it builds its own `AdminClient`, which is
where confluent-kafka keeps operations of this kind. The sibling's `Remove-KfkTopic` takes
`-Instance` for the same reason.

`docker/photoservice-app.py` calls it next to `remove_mdb_collection` when it clears the previous run. The application restarts its ids at 1 every time it starts, so a topic that outlived
the tables would hold several customers with id 1, and `demo/06_eventstreaming.ipynb` would replay
all of them into one primary key.

**It waits rather than returning on the broker's acknowledgement.** Deletion is asynchronous, and
the caller's next message would simply recreate the topic — with auto-creation on, which is how
this lab runs, that race is silent. For the same reason it asks for the whole topic list rather
than `list_topics(topic=...)`, which would create the very topic it is checking for.

## Gaps in the grid

The names are fixed by the naming grid, so the empty cells are worth writing down before anyone invents
a different name for them. **✔** marks what exists, a bare name is a cell that could still be filled,
and **—** is a cell that makes no sense for that provider:

| Family | SQL Server | Oracle | PostgreSQL | MongoDB | Kafka |
| --- | --- | --- | --- | --- | --- |
| Connect | ✔ `connect_sql_instance` | ✔ `connect_ora_instance` | ✔ `connect_pg_instance` | ✔ `connect_mdb_instance` | ✔ `connect_kfk_producer` + `connect_kfk_consumer` |
| Query, all at once | ✔ `invoke_sql_query` | ✔ `invoke_ora_query` | ✔ `invoke_pg_query` | — | — |
| Query, streamed | ✔ `read_sql_query` | ✔ `read_ora_query` | ✔ `read_pg_query` | ✔ `read_mdb_collection` | ✔ `read_kfk_topic` |
| Cursor for streaming into a writer | ✔ `get_sql_data_reader` | ✔ `get_ora_data_reader` | ✔ `get_pg_data_reader` | — | — |
| Bulk write | ✔ `write_sql_table` | ✔ `write_ora_table` | ✔ `write_pg_table` | ✔ `write_mdb_collection` | ✔ `write_kfk_topic` |
| File → table | ✔ `import_sql_table` | ✔ `import_ora_table` | ✔ `import_pg_table` | — | — |
| Table → file | ✔ `export_sql_table` | ✔ `export_ora_table` | ✔ `export_pg_table` | — | — |
| Column metadata | ✔ `get_sql_table_information` | ✔ `get_ora_table_information` | ✔ `get_pg_table_information` | — | — |
| Drop | — | — | — | ✔ `remove_mdb_collection` | ✔ `remove_kfk_topic` |

**Every cell the sibling fills is filled**, which was not true until the ten functions above were
written. The remaining `—` are cells that make no sense for that provider, not work left over: MongoDB
has no column metadata to return and already streams, and a table is not a thing Kafka has. The grid is
intentionally not square, for the same reasons as in the sibling repository.

**Nothing in `demo/` calls the nine `read_*_query`, `export_*_table` and `get_*_table_information`
functions, and nothing does in the sibling either** — they exist there too without a caller. They are
here so that the two libraries can be shown side by side without a hole in one of them, and they were
checked against the live containers rather than only read: the export/import round trip compares every
value against its source, which is the check a row count could not have made.

**Kafka is the first column with two functions in one cell.** Every other provider has one connection
that both reads and writes; Kafka has a producer and a consumer, which are separate clients. The
sibling makes the same split for the same reason, and `DIFFERENCES.md` records what the .NET client
forced there that `confluent-kafka` did not force here.

Three things the sibling needs and this repository does not: `Import-OraLibrary`, `Import-PgLibrary`
and `Import-KfkLibrary`, which download the drivers from nuget.org. In Python the drivers are
`pip install`ed by `03_python_setup.sh` (`oracledb`, `psycopg`, `pymongo`, `confluent-kafka`), so those
cells of the grid disappear — and the Kafka one is the widest gap of the three, because the wheel here
carries the native librdkafka while over there it is a second package that has to be put in the right
directory, per platform. For Oracle it saved more than the download: `oracledb` in thin mode needs no
Oracle Instant Client at all.

**The Drop row is where the two providers disagree about how much work a drop is**, and both cells are
now functions. `remove_mdb_collection` is a single pymongo call; `remove_kfk_topic` is an admin client, a
delete and a wait for the broker. The two sit next to each other in `docker/photoservice-app.py`, and the
difference between them is length rather than principle — which is easier to see now that both come from
`lib/` and only one of them is short.

**Three parameters of the sibling are deliberately not here**, and each has an entry in `DIFFERENCES.md`
saying what the driver would have needed and what was rejected:

| Sibling parameter | Where | Why not |
| --- | --- | --- |
| `-ParameterTypes` | `invoke_*_query`, `read_*_query`, `get_*_data_reader` | Three drivers, three mechanisms, and psycopg has none at all — it infers from the Python type. No demo passes it. |
| `-QueryTimeout` | the same three families | Implementable on all three and differently on each: `Connection.timeout` in pyodbc, `SET statement_timeout` in PostgreSQL, `Connection.call_timeout` in oracledb. All three live on the *connection* rather than the statement, so a per-call parameter would have to save and restore one. |
| `-Last` | `read_mdb_collection` | pymongo has no equivalent; it would mean reversing the sort and limiting, and it only means anything alongside a sort. |

When you add a function for one provider, check whether the same function belongs in its siblings, and
either add it there too or record the reason here.
