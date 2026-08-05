import sys
from pathlib import Path

sys.path.append(str((Path(__file__).parent / "lib").resolve()))

from connect_ora_instance import connect_ora_instance  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
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


# StackExchange
print("Setting up variables and connections for StackExchange")

stackexchange = {
    "sql_instance": "127.0.0.1",
    "sql_login": "StackExchange",
    "sql_password": "Passw0rd!",
    "sql_database": "StackExchange",
    # Oracle has no separate database: the service name is part of the instance
    "ora_instance": "127.0.0.1/XEPDB1",
    "ora_user": "stackexchange",
    "ora_password": "Passw0rd!",
    "pg_instance": "127.0.0.1",
    "pg_user": "stackexchange",
    "pg_password": "Passw0rd!",
    "pg_database": "stackexchange"
}

stackexchange["sql_connection"] = connect_sql_instance(
    instance=stackexchange["sql_instance"],
    database=stackexchange["sql_database"],
    username=stackexchange["sql_login"],
    password=stackexchange["sql_password"],
    enable_exception=True
)

stackexchange["sql_connection"].close()

stackexchange["ora_connection"] = connect_ora_instance(
    instance=stackexchange["ora_instance"],
    username=stackexchange["ora_user"],
    password=stackexchange["ora_password"],
    enable_exception=True
)

stackexchange["ora_connection"].close()

stackexchange["pg_connection"] = connect_pg_instance(
    instance=stackexchange["pg_instance"],
    database=stackexchange["pg_database"],
    username=stackexchange["pg_user"],
    password=stackexchange["pg_password"],
    enable_exception=True
)

stackexchange["pg_connection"].close()

print("Finished")

print("MinIO: http://127.0.0.1:9001/login")
print("pgAdmin: http://127.0.0.1:5050/browser/")
