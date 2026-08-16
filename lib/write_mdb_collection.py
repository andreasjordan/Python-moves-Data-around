import logging
import time

logger = logging.getLogger("lib." + __name__)


def _log_progress(inserted, total_rows, start_time):
    elapsed = time.time() - start_time
    rate = inserted / elapsed if elapsed > 0 else 0

    logger.info(
        f"{inserted}/{total_rows} documents inserted "
        f"({inserted / total_rows * 100:.1f}%) "
        f"- {int(rate)} documents/sec"
    )


def write_mdb_collection(
    connection,
    collection,
    data=None,
    batch_size=1000,
    truncate_collection=False,
    enable_exception=False
):
    try:
        if data is None:
            raise Exception("No data is used, so there is nothing to do")

        if not len(data):
            raise Exception("No documents to import, data is empty")

        logger.debug(f"Importing data into {collection}")

        if truncate_collection:
            # MongoDB has no TRUNCATE. The collection is dropped and the first insert creates
            # it again, which is what the sibling does as well.
            logger.debug("Dropping collection")
            connection.drop_collection(collection)

        target = connection[collection]

        # DIFFERENCE: there is no target schema to read, and that is the whole point of this
        # one. Every other write function starts by asking the target for its columns and then
        # matching the source against them. A collection has no columns, so there is nothing to
        # ask and nothing to match - the documents go in as they were handed over, and whoever
        # built them decided what type each value has.

        total_rows = len(data)
        logger.debug(f"Inserting {total_rows} documents")

        start_time = time.time()

        for start in range(0, total_rows, batch_size):
            target.insert_many(data[start:start + batch_size])
            _log_progress(min(start + batch_size, total_rows), total_rows, start_time)

        logger.info("Bulk insert complete")

    except Exception as e:
        message = f"Importing data failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
