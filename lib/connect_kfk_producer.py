from confluent_kafka import Producer


# DIFFERENCE: there is no cell of the grid this fits without splitting. Every other provider here
# has one connection that reads and writes; Kafka has a Producer and a Consumer, which are
# different clients with different configuration and no common object behind them. Pretending
# otherwise would mean inventing a connection Kafka does not have, so there are two connect
# functions instead of one.
def connect_kfk_producer(
    instance,
    enable_exception=False
):
    print(f"[VERBOSE] Creating producer for instance [{instance}]")

    # Kafka calls this the bootstrap server: the broker that is asked where the others are.
    # There is only one here, so it answers with itself.
    configuration = {
        "bootstrap.servers": instance
    }

    try:
        producer = Producer(configuration)

        # A Producer does not contact the broker until the first message, the same way a
        # MongoClient does not until the first operation. Asking for the topic list forces it,
        # so that a broker that is not running fails here rather than somewhere later.
        print("[VERBOSE] Checking the connection")
        producer.list_topics(timeout=10)

        print("[VERBOSE] Returning producer")
        return producer

    except Exception as e:
        message = f"Connection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
