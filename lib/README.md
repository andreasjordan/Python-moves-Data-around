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
`lib/` has 35 functions. This one has three. The rest of this file is as much a to-do list as an index.

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
- `query_timeout` is present but commented out — pyodbc has no built-in statement timeout.

### `write_sql_table(connection, table, data=None, batch_size=1000, truncate_table=False, enable_exception=False)`

Bulk-loads a pandas DataFrame into `table`, which may be `schema.table`. Reads the target's column list
with `SELECT TOP 0 *`, reindexes the DataFrame onto exactly those columns — extra columns are dropped,
missing ones become `NULL` — then inserts with `fast_executemany` in batches of `batch_size`, committing
after each batch and printing rows done, percentage and rows/sec. `truncate_table=True` empties the
table first.

Dropping extra columns and writing `NULL` for missing ones is not a shortcut — it is what the sibling's
`Write-SqlTable` does for its `-Data` parameter as well, because it fills the target's columns from
each source object and leaves the rest untouched.

Two things the sibling has and this function does not, both waiting for the scenarios that need them:
`-DataReader`, for streaming from one database into another without going through memory, and
`-Transaction`.

## Gaps in the grid

Nothing below exists yet. The names are fixed by the naming grid, so they are worth writing down before
anyone invents a different one:

| Family | SQL Server | Oracle | PostgreSQL | MongoDB | MinIO |
| --- | --- | --- | --- | --- | --- |
| Connect | ✔ `connect_sql_instance` | `connect_ora_instance` | `connect_pg_instance` | `connect_mdb_instance` | `connect_mio_instance` |
| Query, all at once | ✔ `invoke_sql_query` | `invoke_ora_query` | `invoke_pg_query` | — | — |
| Query, streamed | `read_sql_query` | `read_ora_query` | `read_pg_query` | `read_mdb_collection` | — |
| Cursor for streaming into a writer | `get_sql_data_reader` | `get_ora_data_reader` | `get_pg_data_reader` | — | — |
| Bulk write | ✔ `write_sql_table` | `write_ora_table` | `write_pg_table` | `write_mdb_collection` | — |
| File → table | `import_sql_table` | `import_ora_table` | `import_pg_table` | — | — |
| Table → file | `export_sql_table` | `export_ora_table` | `export_pg_table` | — | — |
| Column metadata | `get_sql_table_information` | `get_ora_table_information` | `get_pg_table_information` | — | — |
| Object storage | — | — | — | — | `get_mio_file`, `get_mio_file_list`, `set_mio_file`, `remove_mio_file` |

The grid is intentionally not square, for the same reasons as in the sibling repository: MongoDB has no
column metadata to return and already streams, and MinIO stores whole files, so `get_mio_file` and
`set_mio_file` cover it.

Two things the sibling needs and this repository does not: `Import-OraLibrary` and `Import-PgLibrary`,
which download the ADO.NET DLLs from nuget.org. In Python the drivers are `pip install`ed by
`03_python_setup.sh` (`oracledb`, `psycopg`, `pymongo` when their scenarios arrive), so those two cells
of the grid disappear.

When you add a function for one provider, check whether the same function belongs in its siblings, and
either add it there too or record the reason here.
