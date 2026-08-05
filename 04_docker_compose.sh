#!/bin/bash

set -e

cd ./docker

docker compose up -d

# The steps that follow connect to the databases right away, but a container needs a while for
# its first start and the demo databases are created only after that. Without these waits,
# 06_test_connections.py fails with a handshake error.
#
# Each check asks for the database of a demo instead of just asking whether the server answers,
# because the databases are created after the server accepts connections. Reading the container
# log is not an alternative: "docker logs" keeps the output of earlier runs, so the message of a
# previous start would be found immediately.

wait_for() {
    local name="$1"
    local attempts="$2"
    shift 2

    echo "Waiting for $name to create the demo databases..."

    for _ in $(seq 1 "$attempts"); do
        if "$@" 2>/dev/null | grep -q '^1$'; then
            echo "$name is ready"
            return 0
        fi
        sleep 2
    done

    echo "$name did not become ready in time" >&2
    return 1
}

wait_for "SQL Server" 150 \
    docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Passw0rd!' -C -h -1 -W \
    -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = 'TimeSheets'"

wait_for "PostgreSQL" 150 \
    docker compose exec -T postgres psql -U postgres -tAc \
    "SELECT COUNT(*) FROM pg_database WHERE datname = 'stackexchange'"

wait_for "MongoDB" 150 \
    docker compose exec -T mongo mongosh --quiet -u stackexchange -p 'Passw0rd!' \
    --authenticationDatabase stackexchange stackexchange \
    --eval 'db.runCommand({ ping: 1 }).ok'

# Oracle needs a command of its own, because sqlplus takes its query on stdin and not as an
# argument. Connecting as the demo user is the check: while the startup scripts have not run,
# that user does not exist yet and sqlplus simply fails.
oracle_ready() {
    printf 'SET PAGESIZE 0 FEEDBACK OFF HEADING OFF\nSELECT COUNT(*) FROM user_tables WHERE table_name = '"'"'USERS'"'"';\nEXIT\n' \
        | docker compose exec -T oracle sqlplus -S 'stackexchange/Passw0rd!@localhost/XEPDB1' \
        | tr -d '[:space:]'
}

# Oracle takes far longer to start than the other two, so it gets 15 minutes rather than 5
wait_for "Oracle" 450 oracle_ready
