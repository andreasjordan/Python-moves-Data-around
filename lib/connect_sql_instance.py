import pyodbc


def connect_sql_instance(
    instance,
    database=None,
    username=None,
    password=None,
    pooled_connection=False,
    enable_exception=False
):
    print(f"[VERBOSE] Creating connection to instance [{instance}]")

    # Build connection string
    conn_parts = [
        "DRIVER={ODBC Driver 18 for SQL Server}",
        f"SERVER={instance}"
    ]

    if database:
        conn_parts.append(f"DATABASE={database}")

    if username and password:
        print("[VERBOSE] Using SQL authentication")
        conn_parts.append(f"UID={username}")
        conn_parts.append(f"PWD={password}")
    else:
        print("[VERBOSE] Using Integrated Security")
        conn_parts.append("Trusted_Connection=yes")

    if pooled_connection:
        print("[VERBOSE] Using connection pooling")
        conn_parts.append("Pooling=yes")
    else:
        print("[VERBOSE] Disabling connection pooling")
        conn_parts.append("Pooling=no")

    # Required for SQL Server 18 driver (avoids SSL issues)
    conn_parts.append("TrustServerCertificate=yes")

    connection_string = ";".join(conn_parts)

    try:
        print("[VERBOSE] Opening connection")
        connection = pyodbc.connect(connection_string)

        print("[VERBOSE] Returning connection object")
        return connection

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None



#import logging

#logging.basicConfig(level=logging.INFO)

#logging.info("Creating connection")
