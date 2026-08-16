"""The ten lib/ functions no scenario reaches.

`read_*_query`, `export_*_table` and `get_*_table_information` have no caller in `demo/` — and neither
do their counterparts in the sibling. They exist so the two libraries can be shown side by side without
a hole in one of them, which means **nothing else in this folder would ever notice if they broke.**
`remove_mdb_collection` is here for the other half of the same reason: its one caller is the
photoservice container, so a run of scenario 4 or 6 exercises it only by accident.

This script is deliberately **not numbered**. Every other file here pairs with a `demo/NN_*.ipynb`, and
a `07_` would promise a seventh scenario that does not exist. `invoke_verify.py` names it explicitly.

It builds its own fixture rather than leaning on scenario data, because the properties being checked -
milliseconds, NULLs, non-ASCII text, a NUMERIC - have to be present on purpose. Five rows is enough and
it costs no time.

Two traps this script exists to keep caught, both of which cost a round of false failures when the
functions were written:

- **The fixture insert needs setinputsizes on Oracle.** oracledb binds a Python datetime as
  DB_TYPE_DATE, and an Oracle DATE holds whole seconds, so an unguarded insert drops the milliseconds
  *before the function under test ever sees them* and the failure looks like a bug in read_ora_query.
- **str(datetime) writes six fractional digits, not three.** A check that counts digits fails on
  correct output. The property that matters is that the value parses back equal.

Needs SQL Server, PostgreSQL, Oracle and MongoDB running. Seconds, not minutes.
"""

import argparse
import datetime
import decimal
import json
import tempfile
import types
from pathlib import Path

from verify_common import add_repository_paths, complete_verify, fact, line, start_verify

root = add_repository_paths()

import oracledb  # noqa: E402
from connect_mdb_instance import connect_mdb_instance  # noqa: E402
from connect_ora_instance import connect_ora_instance  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
from connect_sql_instance import connect_sql_instance  # noqa: E402
from export_ora_table import export_ora_table  # noqa: E402
from export_pg_table import export_pg_table  # noqa: E402
from export_sql_table import export_sql_table  # noqa: E402
from get_ora_table_information import get_ora_table_information  # noqa: E402
from get_pg_table_information import get_pg_table_information  # noqa: E402
from get_sql_table_information import get_sql_table_information  # noqa: E402
from import_ora_table import import_ora_table  # noqa: E402
from import_pg_table import import_pg_table  # noqa: E402
from import_sql_table import import_sql_table  # noqa: E402
from invoke_ora_query import invoke_ora_query  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402
from read_ora_query import read_ora_query  # noqa: E402
from read_pg_query import read_pg_query  # noqa: E402
from read_sql_query import read_sql_query  # noqa: E402
from remove_mdb_collection import remove_mdb_collection  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("The lib/ grid cells no scenario reaches", args.report_path)

TABLE = "Verify_LibGrid"
BACK = "Verify_LibGrid_Back"
BINARY = "Verify_LibGrid_Binary"
COLLECTION = "Verify_LibGrid"

# The fixture. Five rows, and every column is carrying something a careless implementation loses:
# non-ASCII text, four different non-zero millisecond values, a NUMERIC with a negative and a zero,
# an embedded single and double quote, and one row that is NULL in three columns.
ROWS = [
    (1, "ypercubeᵀᴹ", datetime.datetime(2026, 8, 16, 9, 46, 49, 52000), decimal.Decimal("12.34")),
    (2, "Grüße", datetime.datetime(2026, 8, 16, 9, 46, 49, 907000), decimal.Decimal("-0.05")),
    (3, "plain", datetime.datetime(2026, 1, 2, 3, 4, 5, 1000), decimal.Decimal("0.00")),
    (4, "quote'and\"double", datetime.datetime(2026, 12, 31, 23, 59, 59, 999000), decimal.Decimal("99999.99")),
    (5, None, None, None),
]


def lower_keys(rows):
    """PostgreSQL folds unquoted names to lower case and Oracle to upper, so one query text comes back
    with three key spellings. The same helper 02_stackexchange.py has, for the same reason."""
    return [{key.lower(): value for key, value in row.items()} for row in rows]


def compare_to_fixture(label, rows):
    """Compare rows against ROWS column by column, having first checked there is anything to compare."""
    if len(rows) != len(ROWS):
        fact(f"{label}: five rows came back", False, f"got {len(rows)}")
        return

    folded = lower_keys(rows)

    # The preconditions. Without these the comparison below could pass on two columns of None, which
    # is the exact way this repository has been fooled before.
    named = sum(1 for row in folded if row["name"] is not None)
    fact(f"{label}: precondition - four of the five names are not NULL", named == 4, f"{named} of 5")

    microseconds = [row["ts"].microsecond for row in folded if row["ts"] is not None]
    fact(f"{label}: precondition - all four timestamps carry milliseconds",
         len(microseconds) == 4 and all(m != 0 for m in microseconds), f"{microseconds}")

    wrong = []
    for got, want in zip(folded, ROWS, strict=True):
        if int(got["id"]) != want[0]:
            wrong.append(f"id {got['id']} != {want[0]}")
        if got["name"] != want[1]:
            wrong.append(f"name {got['name']!r} != {want[1]!r}")
        if got["ts"] != want[2]:
            wrong.append(f"ts {got['ts']!r} != {want[2]!r}")
        # Normalised first, because the three drivers hand back a NUMERIC as Decimal, float and int
        # respectively - and because Decimal(str(None)) is not a thing, so the None has to survive.
        amount = None if got["amount"] is None else decimal.Decimal(str(got["amount"]))
        if amount != want[3]:
            wrong.append(f"amount {got['amount']!r} != {want[3]!r}")

    fact(f"{label}: every value equals the source", not wrong, "; ".join(wrong[:4]) or "20 values")


def run_provider(provider, folder):
    label = provider["label"]
    connection = provider["connect"]()
    invoke, read = provider["invoke"], provider["read"]

    line("")
    line(f"--- {label} ---")

    try:
        for statement in provider["drop"]:
            invoke(connection=connection, query=statement)

        invoke(connection=connection, query=provider["create"].format(table=TABLE), enable_exception=True)
        invoke(connection=connection, query=provider["create"].format(table=BACK), enable_exception=True)

        cursor = connection.cursor()
        # TRAP: without this Oracle stores whole seconds and every millisecond check below fails
        # against correct code. See the module docstring.
        if provider["input_sizes"]:
            cursor.setinputsizes(*provider["input_sizes"])
        cursor.executemany(provider["insert"].format(table=TABLE), ROWS)
        connection.commit()
        cursor.close()

        # --- read_*_query -------------------------------------------------------------------------
        generator = read(connection=connection, query=f"SELECT * FROM {TABLE} ORDER BY id")
        fact(f"{label} read: returns a generator, so nothing has run yet",
             isinstance(generator, types.GeneratorType), type(generator).__name__)

        streamed = list(generator)
        compare_to_fixture(f"{label} read", streamed)

        collected = invoke(connection=connection, query=f"SELECT * FROM {TABLE} ORDER BY id",
                           as_type="dict", enable_exception=True)
        fact(f"{label} read: agrees with invoke_*_query row for row",
             lower_keys(streamed) == lower_keys(collected), f"{len(streamed)} rows compared")

        # A bad query has to surface on the first next(), not on the call
        broken = read(connection=connection, query="SELECT * FROM Verify_LibGrid_Missing",
                      enable_exception=True)
        raised = ""
        try:
            next(broken)
        except Exception as e:
            raised = str(e)
        fact(f"{label} read: a bad query raises on the first next() with enable_exception=True",
             "Query failed" in raised, raised.splitlines()[0][:70] if raised else "nothing raised")

        # ... and the connection has to still work. On PostgreSQL that is the rollback earning its keep.
        after = invoke(connection=connection, query=f"SELECT COUNT(*) FROM {TABLE}",
                       as_type="single_value", enable_exception=True)
        fact(f"{label} read: the connection survives a failed stream", int(after) == 5, f"count {after}")

        # The next thing on the console is a "Query failed:" line from lib/, and it is supposed to be
        # there: with enable_exception=False the contract says log and stop. logging has no handler
        # configured here, so its lastResort handler puts anything at WARNING or above on stderr -
        # which is why this is the one verify script whose output is not purely PASS/FAIL lines.
        line("      .. the next line is the expected error from the enable_exception=False path")
        quiet = list(read(connection=connection, query="SELECT * FROM Verify_LibGrid_Missing"))
        fact(f"{label} read: a bad query yields nothing with enable_exception=False", quiet == [],
             f"yielded {len(quiet)}")

        after = invoke(connection=connection, query=f"SELECT COUNT(*) FROM {TABLE}",
                       as_type="single_value", enable_exception=True)
        fact(f"{label} read: the connection survives a quietly failed stream", int(after) == 5,
             f"count {after}")

        filtered = list(read(connection=connection,
                             query=f"SELECT * FROM {TABLE} WHERE id = :wanted ORDER BY id",
                             parameter_values={"wanted": 4}, enable_exception=True))
        fact(f"{label} read: parameter_values filters to one row",
             len(filtered) == 1 and lower_keys(filtered)[0]["name"] == 'quote\'and"double',
             f"{len(filtered)} rows")

        # --- export_*_table -----------------------------------------------------------------------
        path = folder / f"{label.lower()}.jsonl"
        provider["export"](connection=connection, table=TABLE, path=str(path), batch_size=2,
                           enable_exception=True)

        lines = path.read_text(encoding="utf-8").splitlines()
        fact(f"{label} export: one JSON line per row", len(lines) == 5, f"{len(lines)} lines")

        parsed = lower_keys([json.loads(one) for one in lines])
        fact(f"{label} export: every line is an object of four columns",
             all(len(row) == 4 for row in parsed), f"{[len(row) for row in parsed]}")

        # TRAP: not "does the string have three digits" - str(datetime) writes six. What matters is
        # that it parses back to what went in.
        reparsed = [datetime.datetime.fromisoformat(row["ts"]) if row["ts"] else None for row in parsed]
        fact(f"{label} export: the milliseconds parse back exactly",
             reparsed == [row[2] for row in ROWS], f"{[row['ts'] for row in parsed][:2]}")

        fact(f"{label} export: the non-ASCII name survived",
             any(row["name"] == "ypercubeᵀᴹ" for row in parsed),
             f"{[row['name'] for row in parsed][:2]}")

        fact(f"{label} export: the NULL row is JSON null, not the string 'None'",
             parsed[4]["name"] is None and parsed[4]["ts"] is None and parsed[4]["amount"] is None,
             f"{parsed[4]}")

        # The round trip, which is the check a row count could not have made
        provider["import"](connection=connection, path=str(path), table=BACK, enable_exception=True)
        back = invoke(connection=connection, query=f"SELECT * FROM {BACK} ORDER BY id",
                      as_type="dict", enable_exception=True)
        compare_to_fixture(f"{label} export/import round trip", back)

        # A binary column must fail loudly rather than writing "b'\\x89PNG'"
        invoke(connection=connection, query=provider["create_binary"].format(table=BINARY),
               enable_exception=True)
        invoke(connection=connection, query=provider["insert_binary"].format(table=BINARY),
               enable_exception=True)
        refused = ""
        try:
            provider["export"](connection=connection, table=BINARY, path=str(folder / "binary.jsonl"),
                               enable_exception=True)
        except Exception as e:
            refused = str(e)
        fact(f"{label} export: a binary column is refused rather than written as b'...'",
             "No JSON representation" in refused, refused.splitlines()[0][:70] if refused else "no error")

        # --- get_*_table_information --------------------------------------------------------------
        one = provider["information"](connection=connection, table=TABLE, enable_exception=True)
        fact(f"{label} information: a bare string is taken as a one-element list",
             one is not None and len(one) == 1, f"{0 if one is None else len(one)} rows")
        fact(f"{label} information: the row count is 5", one is not None and int(one["Rows"].iloc[0]) == 5,
             f"{None if one is None else one['Rows'].iloc[0]}")

        size_column = provider["size_column"]
        fact(f"{label} information: {size_column} is a non-negative integer",
             one is not None and int(one[size_column].iloc[0]) >= 0,
             f"{size_column} = {None if one is None else one[size_column].iloc[0]}")
        line(f"      .. {label}: {None if one is None else one.to_dict('records')}")

        # Listing every table: an empty frame is the failure mode to catch, because a broken catalog
        # query returns nothing at all and every per-table check above would still pass.
        listed = provider["information"](connection=connection, enable_exception=True)
        fact(f"{label} information: listing the schema returns tables",
             listed is not None and len(listed) > 0, f"{0 if listed is None else len(listed)} tables")
        fact(f"{label} information: the listing contains {TABLE}",
             listed is not None and any(t.lower() == TABLE.lower() for t in listed["Table"]),
             f"{0 if listed is None else len(listed)} tables listed")

    finally:
        for statement in provider["drop"]:
            invoke(connection=connection, query=statement)
        connection.close()


PROVIDERS = [
    {
        "label": "SqlServer",
        "connect": lambda: connect_sql_instance(
            instance="127.0.0.1", database="StackExchange", username="StackExchange",
            password="Passw0rd!", enable_exception=True),
        "invoke": invoke_sql_query,
        "read": read_sql_query,
        "export": export_sql_table,
        "import": import_sql_table,
        "information": get_sql_table_information,
        "size_column": "Pages",
        "create": "CREATE TABLE {table} (id INT NOT NULL, name NVARCHAR(100) NULL, "
                  "ts DATETIME2(3) NULL, amount DECIMAL(10,2) NULL)",
        "insert": "INSERT INTO {table} (id, name, ts, amount) VALUES (?, ?, ?, ?)",
        "create_binary": "CREATE TABLE {table} (id INT NOT NULL, blob_column VARBINARY(MAX) NULL)",
        "insert_binary": "INSERT INTO {table} (id, blob_column) VALUES (1, 0x89504E47)",
        "drop": [f"DROP TABLE IF EXISTS {TABLE}", f"DROP TABLE IF EXISTS {BACK}",
                 f"DROP TABLE IF EXISTS {BINARY}"],
        "input_sizes": None,
    },
    {
        "label": "PostgreSQL",
        "connect": lambda: connect_pg_instance(
            instance="127.0.0.1", database="stackexchange", username="stackexchange",
            password="Passw0rd!", enable_exception=True),
        "invoke": invoke_pg_query,
        "read": read_pg_query,
        "export": export_pg_table,
        "import": import_pg_table,
        "information": get_pg_table_information,
        "size_column": "Bytes",
        "create": "CREATE TABLE {table} (id INT NOT NULL, name VARCHAR(100) NULL, "
                  "ts TIMESTAMP(3) NULL, amount NUMERIC(10,2) NULL)",
        "insert": "INSERT INTO {table} (id, name, ts, amount) VALUES (%s, %s, %s, %s)",
        "create_binary": "CREATE TABLE {table} (id INT NOT NULL, blob_column BYTEA NULL)",
        "insert_binary": "INSERT INTO {table} (id, blob_column) VALUES (1, '\\x89504E47'::bytea)",
        "drop": [f"DROP TABLE IF EXISTS {TABLE}", f"DROP TABLE IF EXISTS {BACK}",
                 f"DROP TABLE IF EXISTS {BINARY}"],
        "input_sizes": None,
    },
    {
        "label": "Oracle",
        "connect": lambda: connect_ora_instance(
            instance="127.0.0.1/XEPDB1", username="stackexchange", password="Passw0rd!",
            enable_exception=True),
        "invoke": invoke_ora_query,
        "read": read_ora_query,
        "export": export_ora_table,
        "import": import_ora_table,
        "information": get_ora_table_information,
        "size_column": "Blocks",
        "create": "CREATE TABLE {table} (id NUMBER(10) NOT NULL, name VARCHAR2(100) NULL, "
                  "ts TIMESTAMP(3) NULL, amount NUMBER(10,2) NULL)",
        "insert": "INSERT INTO {table} (id, name, ts, amount) VALUES (:1, :2, :3, :4)",
        "create_binary": "CREATE TABLE {table} (id NUMBER(10) NOT NULL, blob_column BLOB NULL)",
        "insert_binary": "INSERT INTO {table} (id, blob_column) VALUES (1, HEXTORAW('89504E47'))",
        # Oracle has no DROP TABLE IF EXISTS, so the exception is swallowed in PL/SQL
        "drop": [f"BEGIN EXECUTE IMMEDIATE 'DROP TABLE {t}'; EXCEPTION WHEN OTHERS THEN NULL; END;"
                 for t in (TABLE, BACK, BINARY)],
        # TRAP: see the module docstring. Without this the fixture loses its own milliseconds.
        "input_sizes": (None, None, oracledb.DB_TYPE_TIMESTAMP, None),
    },
]

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    for provider in PROVIDERS:
        run_provider(provider, folder)

# --- remove_mdb_collection --------------------------------------------------------------------
line("")
line("--- MongoDB ---")

mdb = connect_mdb_instance(instance="127.0.0.1", database="stackexchange", username="stackexchange",
                           password="Passw0rd!", enable_exception=True)
try:
    mdb.drop_collection(COLLECTION)
    mdb[COLLECTION].insert_many([{"_id": i, "n": f"document {i}"} for i in range(1, 8)])

    # The precondition matters more here than anywhere else in this file: "the collection is gone"
    # is trivially true of a collection that was never created.
    documents = mdb[COLLECTION].count_documents({})
    fact("MongoDB: precondition - the collection holds seven documents",
         COLLECTION in mdb.list_collection_names() and documents == 7, f"{documents} documents")

    remove_mdb_collection(connection=mdb, collection=COLLECTION, enable_exception=True)
    fact("MongoDB: remove_mdb_collection dropped it",
         COLLECTION not in mdb.list_collection_names(), f"{mdb.list_collection_names()}")

    quiet = True
    try:
        remove_mdb_collection(connection=mdb, collection="Verify_LibGrid_NeverExisted",
                              enable_exception=True)
    except Exception as e:
        quiet = False
        detail = str(e)
    fact("MongoDB: dropping a collection that is not there is quiet", quiet,
         "" if quiet else detail[:70])
finally:
    mdb.drop_collection(COLLECTION)
    mdb.client.close()

complete_verify()
