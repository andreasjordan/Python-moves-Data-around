import logging
import pyodbc

logger = logging.getLogger("lib." + __name__)


def connect_sql_instance(
    instance,
    database=None,
    username=None,
    password=None,
    pooled_connection=False,
    enable_exception=False
):
    logger.debug(f"Creating connection to instance [{instance}]")

    # Build connection string
    conn_parts = [
        "DRIVER={ODBC Driver 18 for SQL Server}",
        f"SERVER={instance}"
    ]

    if database:
        conn_parts.append(f"DATABASE={database}")

    if username and password:
        logger.debug("Using SQL authentication")
        conn_parts.append(f"UID={username}")
        conn_parts.append(f"PWD={password}")
    else:
        logger.debug("Using Integrated Security")
        conn_parts.append("Trusted_Connection=yes")

    if pooled_connection:
        logger.debug("Using connection pooling")
        conn_parts.append("Pooling=yes")
    else:
        logger.debug("Disabling connection pooling")
        conn_parts.append("Pooling=no")

    # Required for SQL Server 18 driver (avoids SSL issues)
    conn_parts.append("TrustServerCertificate=yes")

    connection_string = ";".join(conn_parts)

    try:
        logger.debug("Opening connection")
        connection = pyodbc.connect(connection_string)

        logger.debug("Returning connection object")
        return connection

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
