import time

from confluent_kafka.admin import AdminClient


def remove_kfk_topic(
    instance,
    topic,
    enable_exception=False
):
    print(f"[VERBOSE] Removing topic {topic} on instance [{instance}]")

    # docker/photoservice-app.py calls this next to its drop_collection("Orders"). The application
    # restarts its ids at 1 every time it starts, so a topic that outlives the tables ends up
    # holding several customers with id 1 - and demo 6 replays all of them into one primary key.
    #
    # What this does not throw away is the history demo 6 is about. That history is across
    # readers, not across application starts: a new group id still replays the whole topic, and
    # the offsets that make it work are per group.

    # DIFFERENCE: instance rather than connection, unlike every other function that takes one.
    # Deleting a topic is neither producing nor consuming, so neither of the two clients
    # connect_kfk_* returns is the right thing to hand over - see the note in
    # connect_kfk_producer about why there are two of them. The sibling's Remove-KfkTopic takes
    # -Instance for the same reason.
    try:
        admin_client = AdminClient({"bootstrap.servers": instance})

        # The whole topic list, not list_topics(topic=...) - asking about one topic by name is
        # enough to create it on a broker with auto-creation on, which is the state of this lab.
        if topic not in admin_client.list_topics(timeout=10).topics:
            print(f"[VERBOSE] Topic {topic} does not exist, so there is nothing to do")
            return None

        for _, future in admin_client.delete_topics([topic], operation_timeout=30).items():
            future.result()

        # The broker acknowledges the request before the topic is actually gone, and the caller's
        # next message would simply recreate it - so wait for it to disappear rather than race it.
        deadline = time.time() + 30
        while time.time() < deadline:
            if topic not in admin_client.list_topics(timeout=10).topics:
                print(f"[VERBOSE] Removed topic {topic}")
                return None
            time.sleep(0.5)

        raise Exception(f"topic {topic} was still there 30 seconds after it was deleted")

    except Exception as e:
        message = f"Removing topic failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
