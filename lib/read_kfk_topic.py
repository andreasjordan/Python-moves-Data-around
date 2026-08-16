import json
import logging

import pandas as pd

logger = logging.getLogger("lib." + __name__)


def read_kfk_topic(
    connection,
    topic,
    first=None,
    timeout=5.0,
    as_type="DataFrame",  # DataFrame, dict
    enable_exception=False
):
    try:
        logger.debug(f"Subscribing to topic {topic}")
        connection.subscribe([topic])

        messages = []

        # DIFFERENCE: every other read function in lib/ asks a question and gets an answer. A
        # topic has no end, so this one needs a stopping rule instead: `first` messages, or
        # `timeout` seconds with nothing new. That is not a limitation of the port - it is what
        # reading a log is.
        logger.debug(f"Reading, stopping after {first} messages" if first else
              f"Reading, stopping after {timeout} seconds without a message")

        while True:
            message = connection.poll(timeout)

            if message is None:
                break

            if message.error():
                raise Exception(str(message.error()))

            messages.append(json.loads(message.value()))

            if first and len(messages) >= first:
                break

        logger.debug(f"Retrieved {len(messages)} messages")

        if as_type == "dict":
            return messages

        elif as_type == "DataFrame":
            return pd.DataFrame(messages)

        else:
            # There is no "list" and no "single_value": a message is already a dict, the same
            # argument read_mdb_collection makes about a document
            raise Exception(f"Unknown as_type '{as_type}', use DataFrame or dict")

    except Exception as e:
        message = f"Reading topic failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
