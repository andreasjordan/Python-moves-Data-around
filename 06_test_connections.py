import sys
from pathlib import Path

sys.path.append(str((Path(__file__).parent / "lib").resolve()))

from connect_sql_instance import connect_sql_instance  # noqa: E402

# Timesheets
print("Setting up variables and connections for Timesheets")

timesheets = {
    "sql_instance": "127.0.0.1",
    "sql_login": "TimeSheets",
    "sql_password": "Passw0rd!",
    "sql_database": "TimeSheets"
}

timesheets["sql_connection"] = connect_sql_instance(
    instance=timesheets["sql_instance"],
    database=timesheets["sql_database"],
    username=timesheets["sql_login"],
    password=timesheets["sql_password"],
    enable_exception=True
)

timesheets["sql_connection"].close()

print("Finished")

print("MinIO: http://127.0.0.1:9001/login")
print("pgAdmin: http://127.0.0.1:5050/browser/")
