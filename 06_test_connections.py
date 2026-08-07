import sys
from pathlib import Path

sys.path.append(str((Path(__file__).parent / "lib").resolve()))

from connect_kfk_producer import connect_kfk_producer  # noqa: E402
from connect_mdb_instance import connect_mdb_instance  # noqa: E402
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
    "pg_database": "stackexchange",
    "mdb_instance": "127.0.0.1",
    "mdb_user": "stackexchange",
    "mdb_password": "Passw0rd!",
    "mdb_database": "stackexchange"
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

stackexchange["mdb_connection"] = connect_mdb_instance(
    instance=stackexchange["mdb_instance"],
    database=stackexchange["mdb_database"],
    username=stackexchange["mdb_user"],
    password=stackexchange["mdb_password"],
    enable_exception=True
)

# connect_mdb_instance returns a database, not a connection, and a database has nothing to
# close - the client behind it does.
stackexchange["mdb_connection"].client.close()


# Geodata
print("Setting up variables and connections for Geodata")

geodata = {
    "sql_instance": "127.0.0.1",
    "sql_login": "Geodata",
    "sql_password": "Passw0rd!",
    "sql_database": "Geodata",
    "ora_instance": "127.0.0.1/XEPDB1",
    "ora_user": "geodata",
    "ora_password": "Passw0rd!",
    "pg_instance": "127.0.0.1",
    "pg_user": "geodata",
    "pg_password": "Passw0rd!",
    "pg_database": "geodata"
}

geodata["sql_connection"] = connect_sql_instance(
    instance=geodata["sql_instance"],
    database=geodata["sql_database"],
    username=geodata["sql_login"],
    password=geodata["sql_password"],
    enable_exception=True
)

geodata["sql_connection"].close()

geodata["ora_connection"] = connect_ora_instance(
    instance=geodata["ora_instance"],
    username=geodata["ora_user"],
    password=geodata["ora_password"],
    enable_exception=True
)

geodata["ora_connection"].close()

geodata["pg_connection"] = connect_pg_instance(
    instance=geodata["pg_instance"],
    database=geodata["pg_database"],
    username=geodata["pg_user"],
    password=geodata["pg_password"],
    enable_exception=True
)

geodata["pg_connection"].close()


# PhotoService
print("Setting up variables and connections for PhotoService")

photoservice = {
    "sql_instance": "127.0.0.1",
    "sql_login": "PhotoService",
    "sql_password": "Passw0rd!",
    "sql_database": "PhotoService",
    "pg_instance": "127.0.0.1",
    "pg_user": "photoservice",
    "pg_password": "Passw0rd!",
    "pg_database": "photoservice",
    "mdb_instance": "127.0.0.1",
    "mdb_user": "photoservice",
    "mdb_password": "Passw0rd!",
    "mdb_database": "photoservice"
}

photoservice["sql_connection"] = connect_sql_instance(
    instance=photoservice["sql_instance"],
    database=photoservice["sql_database"],
    username=photoservice["sql_login"],
    password=photoservice["sql_password"],
    enable_exception=True
)

photoservice["sql_connection"].close()

photoservice["pg_connection"] = connect_pg_instance(
    instance=photoservice["pg_instance"],
    database=photoservice["pg_database"],
    username=photoservice["pg_user"],
    password=photoservice["pg_password"],
    enable_exception=True
)

photoservice["pg_connection"].close()

photoservice["mdb_connection"] = connect_mdb_instance(
    instance=photoservice["mdb_instance"],
    database=photoservice["mdb_database"],
    username=photoservice["mdb_user"],
    password=photoservice["mdb_password"],
    enable_exception=True
)

photoservice["mdb_connection"].client.close()

# The broker the application produces its events to, and demo 6 reads them from. This is the
# address seen from outside the compose network - the application itself uses redpanda:9092.
photoservice["kfk_producer"] = connect_kfk_producer(
    instance="127.0.0.1:19092",
    enable_exception=True
)

# A Producer has nothing to close. It is flushed, and it has already been checked by connecting.


# ProjectStatus
print("Setting up variables and connections for ProjectStatus")

projectstatus = {
    "sql_instance": "127.0.0.1",
    "sql_login": "ProjectStatus",
    "sql_password": "Passw0rd!",
    "sql_database": "ProjectStatus"
}

projectstatus["sql_connection"] = connect_sql_instance(
    instance=projectstatus["sql_instance"],
    database=projectstatus["sql_database"],
    username=projectstatus["sql_login"],
    password=projectstatus["sql_password"],
    enable_exception=True
)

projectstatus["sql_connection"].close()

print("Finished")

print("pgAdmin: http://127.0.0.1:5050/browser/")
print("Redpanda Console: http://127.0.0.1:8080")
