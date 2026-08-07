import json
import time


def _print_progress(produced, total_rows, start_time):
    elapsed = time.time() - start_time
    rate = produced / elapsed if elapsed > 0 else 0

    print(
        f"[VERBOSE] {produced}/{total_rows} messages produced "
        f"({produced / total_rows * 100:.1f}%) "
        f"- {int(rate)} messages/sec"
    )


def write_kfk_topic(
    connection,
    topic,
    data=None,
    key=None,
    batch_size=1000,
    enable_exception=False
):
    try:
        if data is None:
            raise Exception("No data is used, so there is nothing to do")

        if not len(data):
            raise Exception("No messages to produce, data is empty")

        print(f"[VERBOSE] Producing to topic {topic}")

        # DIFFERENCE: like write_mdb_collection, there is no target schema to ask about - a topic
        # is a sequence of bytes with no idea what is in them. Unlike a collection, there is not
        # even a document model: whatever goes in has to be serialised by whoever sends it, and
        # JSON is what this repository sends.
        #
        # default=str is doing real work. The events carry datetime and UUID values, and
        # json.dumps refuses both. This is the same question the MongoDB path answered with
        # float() for a Decimal - the driver will not guess, so the caller decides.

        total_rows = len(data)
        print(f"[VERBOSE] Producing {total_rows} messages")

        start_time = time.time()

        for produced, document in enumerate(data, start=1):
            connection.produce(
                topic,
                key=str(document[key]) if key else None,
                value=json.dumps(document, default=str)
            )

            # produce() only queues. poll(0) lets the client hand off what it can without
            # waiting, which keeps the internal queue from filling up on a long run.
            connection.poll(0)

            if produced % batch_size == 0:
                _print_progress(produced, total_rows, start_time)

        # Nothing has necessarily reached the broker until this returns
        print("[VERBOSE] Flushing")
        remaining = connection.flush(30)

        if remaining:
            raise Exception(f"{remaining} messages were still queued after the flush timed out")

        _print_progress(total_rows, total_rows, start_time)
        print("[VERBOSE] Produce complete")

    except Exception as e:
        message = f"Producing to topic failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
