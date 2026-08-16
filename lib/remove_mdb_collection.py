import logging

logger = logging.getLogger("lib." + __name__)


# The shortest function in lib/, and that is the point of it rather than an embarrassment. It sits
# next to remove_kfk_topic in docker/photoservice-app.py, where the two clear the previous run
# together - and the contrast between them is the interesting part: emptying a topic needs an
# admin client, a delete and a wait for the broker, while dropping a collection is one call.
def remove_mdb_collection(
    connection,
    collection,
    enable_exception=False
):
    logger.debug(f"Removing collection {collection}")

    # DIFFERENCE: the sibling's -Collection is optional, because Connect-MdbInstance returns a
    # PSCustomObject that already holds a collection to fall back on. connect_mdb_instance returns
    # a plain pymongo Database, which has no default collection, so the name is required here.
    try:
        # A collection that does not exist is not an error - MongoDB has nothing to drop and says
        # so quietly, which is the same thing the sibling's Remove-MdbcCollection does.
        connection.drop_collection(collection)

    except Exception as e:
        message = f"Removing collection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
