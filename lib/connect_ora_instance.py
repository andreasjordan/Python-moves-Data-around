import oracledb


def connect_ora_instance(
    instance,
    username=None,
    password=None,
    as_sysdba=False,
    pooled_connection=False,
    enable_exception=False
):
    print(f"[VERBOSE] Creating connection to instance [{instance}]")

    # DIFFERENCE: by default oracledb hands out a CLOB as a LOB object - a handle that has to be
    # read separately - where ADO.NET gives the sibling a string. A DataFrame full of those still
    # *prints* as text, because a LOB renders as its content, and pyodbc then refuses them with
    # "Unknown object type LOB during describe". So CLOB columns are asked for as strings, which
    # also measured 17 times faster than reading each LOB by hand: 0.27 s against 4.68 s.
    # This is a driver wide default and it is read when a connection is created, so it has to be
    # set here, before the connect below.
    oracledb.defaults.fetch_lobs = False

    # DIFFERENCE: there is no database parameter, and the sibling function has none either.
    # For Oracle the service name is part of the instance, so this is called with
    # 127.0.0.1/XEPDB1 rather than with a separate database name.
    connection_parameters = {
        "dsn": instance
    }

    if username and password:
        print("[VERBOSE] Using password authentication")
        connection_parameters["user"] = username
        connection_parameters["password"] = password
    else:
        print("[VERBOSE] Using the current operating system user")

    if as_sysdba:
        print("[VERBOSE] Adding SYSDBA to the connection")
        connection_parameters["mode"] = oracledb.AUTH_MODE_SYSDBA

    try:
        if pooled_connection:
            # DIFFERENCE: the third answer to the same question. Npgsql and Oracle's ADO.NET
            # provider both pool through the connection string, psycopg keeps pooling in a
            # separate package that this repository does not use - and oracledb brings a pool
            # of its own. A connection taken from a pool returns to it when it is closed.
            print("[VERBOSE] Using connection pooling")
            pool = oracledb.create_pool(min=1, max=4, increment=1, **connection_parameters)
            connection = pool.acquire()
        else:
            print("[VERBOSE] Opening connection")
            connection = oracledb.connect(**connection_parameters)

        print("[VERBOSE] Returning connection object")
        return connection

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
