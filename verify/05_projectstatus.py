"""Reproduces the ProjectStatus numbers from AGENTS.md: 9 rows after dropna, 8 after the
"NEW PROJECTS:" heading is skipped, 4 rejected for 4 distinct reasons, 5 land after the colour retry,
3 handed back.

This is the only scenario whose numbers are fully deterministic - the sample data is fixed and
nothing is generated - so it is the one place where an exact count is a fair assertion.

Needs SQL Server running. Creates dbo.Verify_ProjectStatus and drops it again.
"""

import argparse

import pandas as pd

from verify_common import add_repository_paths, complete_verify, fact, line, start_verify

root = add_repository_paths()

from connect_sql_instance import connect_sql_instance  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("ProjectStatus", args.report_path)

data = pd.read_excel(
    root / "data" / "projectstatus" / "ProjectStatus.xlsx",
    sheet_name="ProjectStatus",
    skiprows=2
)
data = data.dropna(how="all")
fact("9 rows after dropna", len(data) == 9, f"{len(data)} rows")

to_import = data[~data["Title"].astype(str).str.endswith(":")]
fact('8 rows after the "NEW PROJECTS:" heading is skipped', len(to_import) == 8, f"{len(to_import)} rows")

sql_connection = connect_sql_instance(
    instance="127.0.0.1",
    database="ProjectStatus",
    username="ProjectStatus",
    password="Passw0rd!",
    enable_exception=True
)

invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_ProjectStatus",
                 enable_exception=True)
invoke_sql_query(
    connection=sql_connection,
    query="""
        CREATE TABLE dbo.Verify_ProjectStatus (
          Title            VARCHAR(50),
          Priority         VARCHAR(10),
          Manager          VARCHAR(50),
          Status           VARCHAR(50),
          Color            VARCHAR(10),
          ProgressPercent  INT,
          Milestone        VARCHAR(100),
          MilestoneDate    DATETIME2,
          CONSTRAINT Verify_ProjectStatus_PK PRIMARY KEY (Title),
          CONSTRAINT Verify_ProjectStatus_Priority CHECK (Priority IN ('Low', 'Medium', 'High')),
          CONSTRAINT Verify_ProjectStatus_Color CHECK (Color IN ('Green', 'Yellow', 'Red')),
          CONSTRAINT Verify_ProjectStatus_ProgressPercent CHECK (ProgressPercent >= 0 AND ProgressPercent <= 100)
        )
    """,
    enable_exception=True
)


def import_row(row):
    """The notebook's own import helper. It is narration rather than a lib/ function, so it is
    re-expressed here; what it drives - invoke_sql_query with parameter_values - is the shipped one.

    A missing cell is NaN, which is a float, so it has to become None before it is bound. That is a
    difference Python forced and it is recorded in DIFFERENCES.md.
    """
    values = {
        column: (None if pd.isna(row[column]) else row[column])
        for column in ["Title", "Priority", "Manager", "Status", "Color",
                       "ProgressPercent", "Milestone", "MilestoneDate"]
    }
    invoke_sql_query(
        connection=sql_connection,
        query="INSERT INTO dbo.Verify_ProjectStatus (Title, Priority, Manager, Status, Color, "
              "ProgressPercent, Milestone, MilestoneDate) VALUES (:Title, :Priority, :Manager, "
              ":Status, :Color, :ProgressPercent, :Milestone, :MilestoneDate)",
        parameter_values=values,
        enable_exception=True
    )


try:
    # First pass, no fixing
    failures = {}
    for _, row in to_import.iterrows():
        try:
            import_row(row)
        except Exception as e:
            failures[row["Title"]] = str(e)

    landed = invoke_sql_query(connection=sql_connection,
                              query="SELECT COUNT(*) FROM dbo.Verify_ProjectStatus",
                              as_type="single_value", enable_exception=True)
    fact("4 of the 8 rows are rejected", len(failures) == 4,
         f"{len(failures)} rejected: {', '.join(failures)}")
    fact("4 rows land on the first pass", landed == 4, f"{landed} rows")

    # Naming the four reasons rather than counting them. AGENTS.md warns about exactly this:
    # comparing failure counts while the membership moves underneath is a check that passes for the
    # wrong reason, and it did once. The patterns have to be precise enough to match one message
    # each - "convert|int" matches "converting", "Conversion" and the int inside "constraint".
    reasons = {
        "a date that is not a date": "converting date and/or time",
        "a Status longer than VARCHAR(50)": "would be truncated",
        "a colour the CHECK rejects": "Verify_ProjectStatus_Color",
        "a word in an INT column": "to data type int",
    }
    for reason, pattern in reasons.items():
        matched = [m for m in failures.values() if pattern in m]
        fact(f"exactly one failure is {reason}", len(matched) == 1, f"{len(matched)} message(s) match")

    classified = {reason for message in failures.values()
                  for reason, pattern in reasons.items() if pattern in message}
    fact("the 4 failures are 4 distinct reasons", len(classified) == 4, " | ".join(sorted(classified)))

    for title, message in failures.items():
        line(f"      rejected [{title}]: {' '.join(message.split())}")

    # Second pass, with the colour retry the notebook ends on
    invoke_sql_query(connection=sql_connection, query="TRUNCATE TABLE dbo.Verify_ProjectStatus",
                     enable_exception=True)

    handed_back = 0
    retried = 0
    for _, row in to_import.iterrows():
        try:
            import_row(row)
        except Exception as e:
            if "Verify_ProjectStatus_Color" in str(e):
                retried += 1
                row = row.copy()
                row["Color"] = "Red"
                try:
                    import_row(row)
                    continue
                except Exception as retry_error:
                    # A retry that fails again falls through to the hand-back below, which is what
                    # the notebook does too - but say so rather than swallowing it silently
                    line(f"      the colour retry also failed for [{row['Title']}]: "
                         f"{' '.join(str(retry_error).split())}")
            handed_back += 1

    landed = invoke_sql_query(connection=sql_connection,
                              query="SELECT COUNT(*) FROM dbo.Verify_ProjectStatus",
                              as_type="single_value", enable_exception=True)
    fact("exactly one row is retried, for its colour", retried == 1, f"{retried} retried")
    fact("5 rows land after the colour retry", landed == 5, f"{landed} rows")
    fact("3 rows are handed back", handed_back == 3, f"{handed_back} rows")

    # The retried row really is in the table, and really is Red. Without this the count above could
    # be reached by any five rows.
    red = invoke_sql_query(connection=sql_connection,
                           query="SELECT COUNT(*) FROM dbo.Verify_ProjectStatus WHERE Color = 'Red'",
                           as_type="single_value", enable_exception=True)
    fact("the retried row is in the table as Red", red >= 1, f"{red} row(s) are Red")
finally:
    invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_ProjectStatus",
                     enable_exception=True)
    sql_connection.close()

complete_verify()
