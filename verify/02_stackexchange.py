"""Reproduces the StackExchange numbers from AGENTS.md: Users.xml has 12220 rows, 12179 of them carry
real milliseconds in LastAccessDate while all 12220 CreationDate values end in .000, and the import
lands 0 of 12220 differing on either timestamp column on SQL Server, PostgreSQL and Oracle, with no
tolerance.

The asymmetry between the two columns is the point. CreationDate alone proves nothing - every value
in it ends in .000, so a driver that silently discards milliseconds passes on that column and fails on
the other. That is exactly how the worst defect of the port hid, in import_ora_table.

Needs SQL Server, PostgreSQL and Oracle running. Uses the shipped Users and Badges tables rather than
copies, because the DATETIME2(3) and TIMESTAMP(3) column types are part of what is being checked, and
truncates them again at the end.

Takes several minutes, mostly Oracle. Pass --report-path to watch it while it runs.
"""

import argparse
import xml.etree.ElementTree as ElementTree
from datetime import datetime

from verify_common import add_repository_paths, complete_verify, fact, line, start_verify

root = add_repository_paths()

from connect_ora_instance import connect_ora_instance  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
from connect_sql_instance import connect_sql_instance  # noqa: E402
from import_ora_table import import_ora_table  # noqa: E402
from import_pg_table import import_pg_table  # noqa: E402
from import_sql_table import import_sql_table  # noqa: E402
from invoke_ora_query import invoke_ora_query  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("StackExchange", args.report_path)


def lower_keys(row):
    """PostgreSQL folds unquoted column names to lower case and Oracle to upper, so the same query
    text comes back with three different key spellings.

    PowerShell hides this, because its property access is case-insensitive - which is finding 6 of
    SIBLING-FINDINGS.md and the reason the import loop works there at all. A Python dict does not
    hide it, so the keys are folded here instead.
    """
    return {key.lower(): value for key, value in row.items()}


###############################################################################
# The source, before anything is compared against it
###############################################################################

users_path = root / "data" / "stackexchange" / "Users.xml"
fact("Users.xml is on disk", users_path.is_file(), str(users_path))

# Read independently of the import path - an XML parse rather than the line-by-line reader the
# import_*_table functions use, so the two cannot share a bug
source_rows = ElementTree.parse(users_path).getroot().findall("row")
fact("Users.xml holds 12220 rows", len(source_rows) == 12220, f"{len(source_rows)} rows")

source = {}
creation_with_milliseconds = 0
last_access_with_milliseconds = 0
for row in source_rows:
    creation = datetime.fromisoformat(row.get("CreationDate"))
    last_access = datetime.fromisoformat(row.get("LastAccessDate"))
    source[int(row.get("Id"))] = (creation, last_access)
    if creation.microsecond:
        creation_with_milliseconds += 1
    if last_access.microsecond:
        last_access_with_milliseconds += 1

fact("12179 LastAccessDate values carry real milliseconds",
     last_access_with_milliseconds == 12179, f"{last_access_with_milliseconds} of {len(source_rows)}")
fact("every CreationDate ends in .000, which is why that column alone proves nothing",
     creation_with_milliseconds == 0, f"{creation_with_milliseconds} carry milliseconds")

###############################################################################
# Import into all three, and compare every value back against the file
###############################################################################

sql_connection = connect_sql_instance(instance="127.0.0.1", database="StackExchange",
                                      username="StackExchange", password="Passw0rd!",
                                      enable_exception=True)
pg_connection = connect_pg_instance(instance="127.0.0.1", database="stackexchange",
                                    username="stackexchange", password="Passw0rd!",
                                    enable_exception=True)
ora_connection = connect_ora_instance(instance="127.0.0.1/XEPDB1", username="stackexchange",
                                      password="Passw0rd!", enable_exception=True)

providers = [
    ("SQL Server", import_sql_table, invoke_sql_query, sql_connection, "dbo.Users",
     "SELECT Id, CreationDate, LastAccessDate FROM dbo.Users"),
    ("PostgreSQL", import_pg_table, invoke_pg_query, pg_connection, "Users",
     "SELECT Id, CreationDate, LastAccessDate FROM Users"),
    ("Oracle", import_ora_table, invoke_ora_query, ora_connection, "Users",
     "SELECT Id, CreationDate, LastAccessDate FROM Users"),
]

for name, import_table, invoke_query, connection, table, query in providers:
    line(f"      importing 12220 rows into {name} ...")

    import_table(connection=connection, path=str(users_path), table=table,
                 batch_size=5000, truncate_table=True, enable_exception=True)

    loaded = [lower_keys(r) for r in invoke_query(connection=connection, query=query,
                                                  as_type="dict", enable_exception=True)]
    fact(f"{name}: 12220 rows land", len(loaded) == 12220, f"{len(loaded)} rows")

    creation_differ = last_access_differ = matched = milliseconds_seen = 0
    for row in loaded:
        expected = source.get(int(row["id"]))
        if expected is None:
            continue
        matched += 1
        if row["creationdate"] != expected[0]:
            creation_differ += 1
        if row["lastaccessdate"] != expected[1]:
            last_access_differ += 1
        if row["lastaccessdate"].microsecond:
            milliseconds_seen += 1

    fact(f"{name}: every row matched a row in the file", matched == 12220, f"{matched} of 12220")
    fact(f"{name}: 0 of 12220 differ on CreationDate, no tolerance", creation_differ == 0,
         f"{creation_differ} differ")
    fact(f"{name}: 0 of 12220 differ on LastAccessDate, no tolerance", last_access_differ == 0,
         f"{last_access_differ} differ")

    # The precondition that makes the line above mean anything. If the column had silently lost its
    # milliseconds on the way in, both sides would still agree on CreationDate - and this number
    # would be 0 instead of 12179. That is the shape of the import_ora_table defect.
    fact(f"{name}: the stored LastAccessDate still carries 12179 millisecond values",
         milliseconds_seen == 12179, f"{milliseconds_seen} of 12220")

###############################################################################
# Badges, which is here for column_map
###############################################################################

# Badges.xml is the one file whose timestamp attribute is called Date rather than CreationDate, while
# every table uses CreationDate - so the import has to be told about the rename. Without the map it
# fails on a NULL, which is what a forgotten mapping looks like: not a wrong value, a missing one.
badges_path = root / "data" / "stackexchange" / "Badges.xml"
badges_rows = ElementTree.parse(badges_path).getroot().findall("row")
line(f"      Badges.xml holds {len(badges_rows)} rows")

fact("Badges.xml really uses Date rather than CreationDate",
     badges_rows[0].get("Date") is not None and badges_rows[0].get("CreationDate") is None,
     f"first row has Date={badges_rows[0].get('Date')}")

import_sql_table(connection=sql_connection, path=str(badges_path), table="dbo.Badges",
                 batch_size=5000, truncate_table=True,
                 column_map={"CreationDate": "Date"}, enable_exception=True)

badges_loaded = [lower_keys(r) for r in invoke_sql_query(
    connection=sql_connection, as_type="dict", enable_exception=True,
    query="SELECT Id, CreationDate FROM dbo.Badges")]
fact(f"Badges: all {len(badges_rows)} rows of the file land in SQL Server",
     len(badges_loaded) == len(badges_rows), f"{len(badges_loaded)} rows")

# The mapped column carries the file's Date values, not NULL and not something else. A row count
# alone would pass with every CreationDate empty, which is the failure mode the map prevents.
badges_source = {int(r.get("Id")): datetime.fromisoformat(r.get("Date")) for r in badges_rows}
badges_null = sum(1 for r in badges_loaded if r["creationdate"] is None)
badges_differ = sum(1 for r in badges_loaded
                    if r["creationdate"] is not None
                    and r["creationdate"] != badges_source[int(r["id"])])
fact("Badges: no CreationDate landed NULL", badges_null == 0, f"{badges_null} NULL")
fact("Badges: column_map put the file Date into CreationDate, value for value", badges_differ == 0,
     f"{badges_differ} of {len(badges_loaded)} differ")

# Only SQL Server here. The three-provider comparison is what the Users block above is for; this
# block exists for the mapping, and that is provider-independent.
#
# No literal row count is asserted for Badges, because AGENTS.md records none and inventing one would
# be a number copied out of a run rather than out of the data.

###############################################################################

invoke_sql_query(connection=sql_connection, query="TRUNCATE TABLE dbo.Users", enable_exception=True)
invoke_sql_query(connection=sql_connection, query="TRUNCATE TABLE dbo.Badges", enable_exception=True)
invoke_pg_query(connection=pg_connection, query="TRUNCATE TABLE Users", enable_exception=True)
invoke_ora_query(connection=ora_connection, query="TRUNCATE TABLE Users", enable_exception=True)

sql_connection.close()
pg_connection.close()
ora_connection.close()

complete_verify()
