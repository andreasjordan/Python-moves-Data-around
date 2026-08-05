#!/bin/bash

set -e

cd ./docker

docker compose up -d

# The steps that follow connect to the databases right away, but SQL Server needs a while
# for its first start, and sqlserver-init.sh creates the demo databases only after that.
# Without this wait, 06_test_connections.py fails with a handshake error.
#
# The check asks for the database of the first demo instead of just asking whether the
# server answers, because the databases are created after SQL Server accepts connections.
# Reading the container log is not an alternative: "docker logs" keeps the output of
# earlier runs, so the message of a previous start would be found immediately.
echo "Waiting for SQL Server to create the demo databases..."

for _ in $(seq 1 150); do
    if docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Passw0rd!' -C -h -1 -W \
        -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = 'TimeSheets'" 2>/dev/null | grep -q '^1$'; then
        echo "SQL Server is ready"
        exit 0
    fi
    sleep 2
done

echo "SQL Server did not become ready in time" >&2
exit 1
