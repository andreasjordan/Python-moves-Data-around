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
`lib/` has 35 functions. This one has eighteen. The rest of this file is as much a to-do list as an index.

Every module is `<verb>_<prefix>_<noun>.py` and holds one public function of the same name, so
`Connect-SqlInstance` ↔ `connect_sql_instance`. Prefixes: **sql** = SQL Server · **ora** = Oracle ·
**pg** = PostgreSQL · **mdb** = MongoDB · **mio** = MinIO.

Every function takes `enable_exception=False`. With it, a failure raises; without it, the function
prints `[ERROR] …` and returns `None`. Callers turn it on per call — there is no equivalent of
PowerShell's `$PSDefaultParameterValues`, which is why it has to be passed explicitly.

## What exists today

### `connect_sql_instance(instance, database=None, username=None, password=None, pooled_connection=False, enable_exception=False)`

Returns an open `pyodbc.Connection`, or `None` on failure. Builds the connection string from
`ODBC Driver 18 for SQL Server` — that driver has to be installed separately, see `README.md`.
`username` **and** `password` together select SQL authentication; either one missing falls back to
`Trusted_Connection=yes`, so integrated security is the default. `TrustServerCertificate=yes` is always
appended, because the container's certificate is self-signed.

### `invoke_sql_query(connection, query, as_type="DataFrame", parameter_values=None, enable_exception=False)`

Runs a query and returns the whole result in memory.

- `as_type` selects the shape: `"DataFrame"` (default), `"dict"` (a list of column→value dicts, the
  closest thing to the sibling's `PSObject`), `"list"` (the raw `pyodbc.Row` objects), or
  `"single_value"` (the first column of the first row, or `None`).
- `parameter_values` accepts a list or tuple, which is passed straight through to pyodbc's positional
  `?` placeholders, or a dict, in which case `:name` and `@name` in the query are rewritten to `?` in
  order of appearance first. pyodbc has no named parameters of its own; that rewrite is a small regex
  in `_prepare_query_and_params` and it does not know about string literals, so a `:` inside a quoted
  string in the query will be mangled.
- A statement that returns no columns (DDL, `INSERT`, `TRUNCATE`) is committed unless the connection is
  in autocommit mode, and the function returns `None`.
- **A `SELECT` is committed too.** DB-API opens a transaction for a read as well, and a connection left
  idle in one keeps its locks. `invoke_pg_query` has the same line, and there it is the difference
  between a working demo and a `TRUNCATE` that hangs forever.
- `query_timeout` is present but commented out — pyodbc has no built-in statement timeout.

### `write_sql_table(connection, table, data=None, data_reader=None, data_reader_row_count=None, batch_size=1000, truncate_table=False, enable_exception=False)`

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

`-Transaction` is still missing, and waits for the scenario that needs it.

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

### `invoke_pg_query(connection, query, as_type="DataFrame", parameter_values=None, enable_exception=False)`

The same shape and the same `as_type` values as `invoke_sql_query`. The difference is in the
parameters: psycopg has real named parameters, written `%(name)s`, so the rewrite only renames
`:name` and `@name` and hands the dictionary over unchanged. `invoke_sql_query` has to count positions
and reorder the values, because pyodbc has no named parameters at all.

### `write_pg_table(connection, table, data=None, data_reader=None, data_reader_row_count=None, batch_size=1000, truncate_table=False, enable_exception=False)`

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

### `invoke_ora_query(connection, query, as_type="DataFrame", parameter_values=None, enable_exception=False)`

The same shape and the same `as_type` values as its two siblings, and the least work of the three
where the parameters are concerned: Oracle's own bind variable syntax **is** `:name`, so a query that
already uses it passes through untouched and only `@name` has to be renamed. The regex is identical
in all three files; only the replacement differs.

### `write_ora_table(connection, table, data=None, data_reader=None, data_reader_row_count=None, batch_size=1000, truncate_table=False, enable_exception=False)`

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

### `get_sql_data_reader(connection, table=None, query=None, enable_exception=False)`, `get_ora_data_reader(...)` and `get_pg_data_reader(...)`

Run `SELECT * FROM table`, or `query`, and return the open cursor. That cursor **is** the data reader:
`Get-SqlDataReader` returns a `DbDataReader` and disposes the command behind it, but in Python the
cursor is both at once, so it is simply returned.

The writer that receives it reads it with `fetchmany(batch_size)` and **closes it when it is done** —
the same ownership as in the sibling, where `Write-SqlTable` disposes the reader it was handed.

Two parameters of the sibling are missing: `-ParameterValues` / `-ParameterTypes`, because supporting
them would mean copying the whole named-parameter rewrite of `invoke_*_query` into two more files, and
no demo passes parameters to a reader; and `-QueryTimeout`, for the same reason it is missing from
`invoke_sql_query`.

**A caveat that is not visible from the call site:** psycopg's normal cursor fetches the whole result
before the first `fetchmany` returns, so `get_pg_data_reader` streams from the writer's point of view
but not from the server's. A server-side cursor — `connection.cursor(name=...)` — would change that,
and is the thing to reach for if a table ever stops fitting in memory.

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

`-Last` is missing. pymongo has no equivalent, it would mean reversing the sort and limiting, and no
demo uses it.

## Gaps in the grid

The names are fixed by the naming grid, so the empty cells are worth writing down before anyone invents
a different name for them. A tick marks what exists:

| Family | SQL Server | Oracle | PostgreSQL | MongoDB | MinIO |
| --- | --- | --- | --- | --- | --- |
| Connect | ✔ `connect_sql_instance` | ✔ `connect_ora_instance` | ✔ `connect_pg_instance` | ✔ `connect_mdb_instance` | `connect_mio_instance` |
| Query, all at once | ✔ `invoke_sql_query` | ✔ `invoke_ora_query` | ✔ `invoke_pg_query` | — | — |
| Query, streamed | `read_sql_query` | `read_ora_query` | `read_pg_query` | ✔ `read_mdb_collection` | — |
| Cursor for streaming into a writer | ✔ `get_sql_data_reader` | ✔ `get_ora_data_reader` | ✔ `get_pg_data_reader` | — | — |
| Bulk write | ✔ `write_sql_table` | ✔ `write_ora_table` | ✔ `write_pg_table` | ✔ `write_mdb_collection` | — |
| File → table | ✔ `import_sql_table` | ✔ `import_ora_table` | ✔ `import_pg_table` | — | — |
| Table → file | `export_sql_table` | `export_ora_table` | `export_pg_table` | — | — |
| Column metadata | `get_sql_table_information` | `get_ora_table_information` | `get_pg_table_information` | — | — |
| Object storage | — | — | — | — | `get_mio_file`, `get_mio_file_list`, `set_mio_file`, `remove_mio_file` |

The grid is intentionally not square, for the same reasons as in the sibling repository: MongoDB has no
column metadata to return and already streams, and MinIO stores whole files, so `get_mio_file` and
`set_mio_file` cover it.

Two things the sibling needs and this repository does not: `Import-OraLibrary` and `Import-PgLibrary`,
which download the ADO.NET DLLs from nuget.org. In Python the drivers are `pip install`ed by
`03_python_setup.sh` (`oracledb`, `psycopg`, `pymongo`), so those two cells of the grid disappear. For
Oracle that saved more than the download: `oracledb` in thin mode needs no Oracle Instant Client at
all.

One sibling function has no cell in this grid at all: `Remove-MdbCollection`. Dropping a collection is
what `truncate_collection` does inside `write_mdb_collection`, so nothing has needed it yet — but the
omission is a decision nobody has made, rather than one that has been made.

When you add a function for one provider, check whether the same function belongs in its siblings, and
either add it there too or record the reason here.
