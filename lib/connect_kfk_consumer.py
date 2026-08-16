import logging
from confluent_kafka import Consumer

logger = logging.getLogger("lib." + __name__)


# The counterpart of connect_kfk_producer - see the note there about why there are two.
def connect_kfk_consumer(
    instance,
    group_id,
    from_beginning=False,
    enable_exception=False
):
    logger.debug(f"Creating consumer for instance [{instance}] in group [{group_id}]")

    # group_id is what Kafka remembers a reader by. Two consumers in the same group share the
    # work and share one set of offsets; a consumer in a new group has never read anything.
    #
    # from_beginning sets auto.offset.reset, and the name of that setting is worth reading
    # carefully: it only applies when the group has no committed offset yet. An existing group
    # continues where it left off no matter what is passed here.
    configuration = {
        "bootstrap.servers": instance,
        "group.id": group_id,
        "auto.offset.reset": "earliest" if from_beginning else "latest"
    }

    try:
        consumer = Consumer(configuration)

        logger.debug("Checking the connection")
        consumer.list_topics(timeout=10)

        logger.debug("Returning consumer")
        return consumer

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
