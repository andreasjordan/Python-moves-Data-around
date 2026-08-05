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
    shift

    echo "Waiting for $name to create the demo databases..."

    for _ in $(seq 1 150); do
        if "$@" 2>/dev/null | grep -q '^1$'; then
            echo "$name is ready"
            return 0
        fi
        sleep 2
    done

    echo "$name did not become ready in time" >&2
    return 1
}

wait_for "SQL Server" \
    docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Passw0rd!' -C -h -1 -W \
    -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = 'TimeSheets'"

wait_for "PostgreSQL" \
    docker compose exec -T postgres psql -U postgres -tAc \
    "SELECT COUNT(*) FROM pg_database WHERE datname = 'stackexchange'"
