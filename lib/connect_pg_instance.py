import psycopg


def connect_pg_instance(
    instance,
    database=None,
    username=None,
    password=None,
    pooled_connection=False,
    enable_exception=False
):
    print(f"[VERBOSE] Creating connection to instance [{instance}]")

    # The instance may carry a port, the same way the sibling function accepts it: 127.0.0.1:5432
    if ":" in instance:
        host, port = instance.split(":", 1)
    else:
        host, port = instance, 5432

    connection_parameters = {
        "host": host,
        "port": port
    }

    if database:
        connection_parameters["dbname"] = database

    if username and password:
        print("[VERBOSE] Using password authentication")
        connection_parameters["user"] = username
        connection_parameters["password"] = password
    else:
        print("[VERBOSE] Using the current operating system user")

    if pooled_connection:
        # Npgsql pools inside the connection string. psycopg keeps pooling in a separate
        # package, psycopg_pool, which this repository does not use.
        print("[VERBOSE] Connection pooling is not implemented, opening a single connection")

    try:
        print("[VERBOSE] Opening connection")
        connection = psycopg.connect(**connection_parameters)

        print("[VERBOSE] Returning connection object")
        return connection

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
