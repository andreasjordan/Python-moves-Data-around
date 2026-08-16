import logging
from urllib.parse import quote_plus

from pymongo import MongoClient

logger = logging.getLogger("lib." + __name__)


def connect_mdb_instance(
    instance,
    database="admin",
    username=None,
    password=None,
    enable_exception=False
):
    logger.debug(f"Creating connection to instance [{instance}]")

    # DIFFERENCE: the sibling returns a PSCustomObject holding the client, the database and a
    # collection, because the Mdbc module needs all three. In pymongo the database object is the
    # one thing everything else hangs off - connection["Users"] is the collection - so that is
    # what is returned, and the write and read functions take the collection by name. The
    # -Collection parameter of the sibling has no purpose here and is gone.

    if username and password:
        logger.debug("Using password authentication")
        # The demo users are created in their own database, so that is also where they
        # authenticate. quote_plus is the counterpart of [uri]::EscapeDataString.
        credentials = f"{quote_plus(username)}:{quote_plus(password)}@"
        auth_source = f"?authSource={database}"
    else:
        logger.debug("Connecting without authentication")
        credentials = ""
        auth_source = ""

    connection_string = f"mongodb://{credentials}{instance}/{database}{auth_source}"

    try:
        logger.debug("Opening connection")
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)

        # MongoClient does not talk to the server at all until the first operation, so without
        # this it would return a database object for a server that is not even running - and
        # 06_test_connections.py would report success. The other connect functions in lib/ fail
        # while connecting, and this one has to be made to do the same.
        logger.debug("Checking the connection")
        client[database].command("ping")

        logger.debug("Returning database object")
        return client[database]

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
