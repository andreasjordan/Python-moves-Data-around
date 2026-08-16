"""Reproduces the Timesheets numbers from AGENTS.md: 94 rows from the three Department*.xlsx,
3 departments, 4 people.

Needs SQL Server running. Creates dbo.Verify_Timesheet and drops it again.
"""

import argparse

from verify_common import add_repository_paths, complete_verify, fact, start_verify

root = add_repository_paths()

from connect_sql_instance import connect_sql_instance  # noqa: E402
from import_xls_timesheet import import_xls_timesheet  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402
from write_sql_table import write_sql_table  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("Timesheets", args.report_path)

# Preconditions on the source, before anything is compared against it
files = sorted((root / "data" / "timesheets").glob("Department*.xlsx"))
fact("three Department*.xlsx on disk", len(files) == 3,
     f"{len(files)} files: {', '.join(f.name for f in files)}")

# The shipped function, not a reimplementation of it
data = import_xls_timesheet(str(root / "data" / "timesheets" / "Department*.xlsx"))

departments = sorted(data["Department"].unique())
people = sorted(data["Person"].unique())
fact("94 rows read from the three files", len(data) == 94, f"{len(data)} rows")
fact("3 departments", len(departments) == 3, ", ".join(departments))
fact("4 people", len(people) == 4, ", ".join(people))

# A frame of 94 nulls would satisfy every count above.
#
# The dtype check is not redundant here, although the sibling's equivalent nearly is: two object
# columns holding strings would still compare with > and give a lexical answer, so "End after Start"
# can pass over data that never became a timestamp at all.
fact("Start and End are datetime columns, not strings",
     str(data["Start"].dtype).startswith("datetime") and str(data["End"].dtype).startswith("datetime"),
     f"Start={data['Start'].dtype}, End={data['End'].dtype}")

ordered = int((data["End"] > data["Start"]).sum())
fact("every row has End after Start", ordered == 94, f"{ordered} of 94")

sql_connection = connect_sql_instance(
    instance="127.0.0.1",
    database="TimeSheets",
    username="TimeSheets",
    password="Passw0rd!",
    enable_exception=True
)

# Our own table rather than the notebook's dbo.Timesheet, so that a verify run cannot collide with a
# notebook somebody is stepping through
invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_Timesheet",
                 enable_exception=True)
invoke_sql_query(
    connection=sql_connection,
    query="""
        CREATE TABLE dbo.Verify_Timesheet (
          Department VARCHAR(100),
          Person     VARCHAR(100),
          Start      DATETIME2,
          [End]      DATETIME2,
          Project    VARCHAR(100),
          Task       VARCHAR(1000),
          CONSTRAINT Verify_Timesheet_PK PRIMARY KEY (Department, Person, Start)
        )
    """,
    enable_exception=True
)

try:
    write_sql_table(connection=sql_connection, table="dbo.Verify_Timesheet", data=data,
                    truncate_table=True, enable_exception=True)

    loaded = invoke_sql_query(
        connection=sql_connection,
        query='SELECT Department, Person, Start, [End], Project, Task FROM dbo.Verify_Timesheet '
              'ORDER BY Department, Person, Start',
        enable_exception=True
    )
    fact("94 rows land in SQL Server", len(loaded) == 94, f"{len(loaded)} rows")

    # Column by column against what was read from Excel, not a row count
    source = data.sort_values(["Department", "Person", "Start"]).reset_index(drop=True)
    target = loaded.sort_values(["Department", "Person", "Start"]).reset_index(drop=True)
    differ = 0
    for i in range(min(len(source), len(target))):
        a, b = source.iloc[i], target.iloc[i]
        if (a["Department"] != b["Department"] or a["Person"] != b["Person"]
                or a["Start"] != b["Start"] or a["End"] != b["End"]
                or a["Project"] != b["Project"] or a["Task"] != b["Task"]):
            differ += 1
    fact("0 of 94 differ on any column", differ == 0, f"{differ} differ")

    # The minutes the notebook's report is built from, so a silent type change in Start/End shows up
    minutes = invoke_sql_query(
        connection=sql_connection,
        query='SELECT SUM(DATEDIFF(minute, Start, [End])) FROM dbo.Verify_Timesheet',
        as_type="single_value",
        enable_exception=True
    )
    expected = int(((data["End"] - data["Start"]).dt.total_seconds() / 60).sum())
    fact("total minutes agree with the Excel data", minutes == expected,
         f"{minutes} in SQL Server, {expected} from Excel")
finally:
    invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_Timesheet",
                     enable_exception=True)
    sql_connection.close()

complete_verify()
