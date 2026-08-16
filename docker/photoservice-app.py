# The PhotoService application: a small shop that keeps inventing customers and orders, so that
# demo/04_photoservice.ipynb has a live system to transfer data away from.
#
# This is the port of photoservice-app.ps1 from the sibling repository. Two differences:
#
# * Its logging events go to a Kafka topic, where demo/06_eventstreaming.ipynb reads them. They keep
#   the shape and the component names that the sibling's Add-LoggingEvent gives them, so the replay
#   on the other side is still a port of its loop. Every event is printed as well, so that
#   "docker compose logs -f photoservice" shows the shop running whether or not anybody is
#   consuming. The PowerShell version produces to the same topic since 2026-08-15, which closed
#   entry 10 of SIBLING-FINDINGS.md - so this is no longer a difference between the two.
# * The sibling sets $PSDefaultParameterValues to turn EnableException on for every -Pg and -Mdb
#   call at once. Python has no such thing, so every call passes enable_exception=True itself.

import json
import random
import socket
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# lib/ is mounted into the container, the same way the PowerShell app mounts the PowerShell
# modules from the WSL2 host. This is the container's version of the sys.path dance a notebook
# does, and the functions are the very ones the notebook calls.
sys.path.append("/PhotoService/lib")

from connect_kfk_producer import connect_kfk_producer  # noqa: E402
from connect_mdb_instance import connect_mdb_instance  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from remove_kfk_topic import remove_kfk_topic  # noqa: E402
from write_kfk_topic import write_kfk_topic  # noqa: E402
from write_mdb_collection import write_mdb_collection  # noqa: E402
from write_pg_table import write_pg_table  # noqa: E402

TOPIC = "photoservice.events"


# The port of Add-LoggingEvent, and it keeps that function's shape: an event has a timestamp, a
# host, an application, a component, a level, a message and - when something actually happened -
# the details of what happened.
#
# An event with details goes to the topic as well as to the console. The ones without are
# scheduling chatter, and the sibling only writes those to its archive because its archive is a
# log file. A topic somebody is going to replay is better off without them.
def log(message, component="Main", details=None):
    print(f"[{component}] {message}")

    if details is None:
        return

    event = {
        "Timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "Hostname": socket.gethostname(),
        "Appname": "PhotoService",
        "Component": component,
        "Level": "INFO",
        "Message": message,
        "Details": details
    }

    write_kfk_topic(
        connection=kfk_producer,
        topic=TOPIC,
        data=[event],
        enable_exception=True
    )


print("Reading sample data from files")
# Three lists of names and cities, and they have different lengths - so this stays a dict of
# lists rather than becoming a DataFrame
customer_source = json.loads(Path("/PhotoService/CustomerSource.json").read_text(encoding="utf-8"))

print("Setting up variables and connections")
db_config = {
    "pg_instance": "postgres",
    "pg_user": "photoservice",
    "pg_password": "Passw0rd!",
    "pg_database": "photoservice",
    "mdb_instance": "mongo",
    "mdb_user": "photoservice",
    "mdb_password": "Passw0rd!",
    "mdb_database": "photoservice",
    # On the compose network, not 127.0.0.1:19092 - that is the address the notebook uses from
    # Windows. The broker advertises both, see docker-compose.yaml.
    "kfk_instance": "redpanda:9092"
}

# The application starts together with the databases, so the first attempts are expected to fail
while True:
    try:
        print("Connecting to PostgreSQL")
        db_config["pg_connection"] = connect_pg_instance(
            instance=db_config["pg_instance"],
            database=db_config["pg_database"],
            username=db_config["pg_user"],
            password=db_config["pg_password"],
            enable_exception=True
        )

        print("Connecting to MongoDB")
        db_config["mdb_connection"] = connect_mdb_instance(
            instance=db_config["mdb_instance"],
            database=db_config["mdb_database"],
            username=db_config["mdb_user"],
            password=db_config["mdb_password"],
            enable_exception=True
        )

        print("Connecting to Redpanda")
        db_config["kfk_producer"] = connect_kfk_producer(
            instance=db_config["kfk_instance"],
            enable_exception=True
        )

        break

    except Exception as e:
        print(f"[ERROR] Connection failed: {str(e)}")
        time.sleep(10)

pg_connection = db_config["pg_connection"]
mdb_connection = db_config["mdb_connection"]
kfk_producer = db_config["kfk_producer"]

print("Removing data from previous run")
for table in ["order_event", "order_detail", "order_header", "customer"]:
    invoke_pg_query(
        connection=pg_connection,
        query=f"TRUNCATE TABLE {table}",
        enable_exception=True
    )

# The sibling calls Remove-MdbCollection here. There is no remove_mdb_collection in lib/ - see
# lib/README.md - and pymongo drops a collection in one line, so this is that line.
mdb_connection.drop_collection("Orders")

# The topic goes with the tables. It used to be kept - a topic keeps its history on purpose, the
# argument went - but not across restarts of the thing that writes it: the ids start again at 1
# here, so a topic that survives holds several customers with id 1 and demo 6's replay dies on a
# primary key violation. Emptying it makes the reset complete rather than half done.
#
# The history demo 6 teaches is across *readers*, not across application starts, and that is
# untouched: a new group id still replays the whole topic, and the offsets are per group.
#
# Unlike drop_collection above this is not a one-liner - it needs an admin client, a delete and a
# wait for the broker to catch up - so it is a lib/ function, and the sibling has the same one.
remove_kfk_topic(
    instance=db_config["kfk_instance"],
    topic=TOPIC,
    enable_exception=True
)

print("Reading photo data")
photos = invoke_pg_query(
    connection=pg_connection,
    query="SELECT id, name, price FROM photo",
    as_type="dict",
    enable_exception=True
)

# The counterpart of the sibling's Get-LocalTimestamp, and every timestamp that is stored goes
# through it. It needs none of that function's SpecifyKind - psycopg writes a naive datetime into
# a TIMESTAMP column unchanged, where Npgsql turns a Local one into UTC - but it does need the
# same truncation.
#
# datetime.now() carries microseconds, TIMESTAMP(3) keeps three digits and rounds. So the topic
# said 12:05:20.955381 while PostgreSQL held 12:05:20.955, and a replay through demo 6 landed a
# different value in SQL Server than the direct transfer in demo 4 did - sub-millisecond, on
# every row. Handing over what the column can actually store removes the question.
#
# Local time is a deliberate choice for a demo - the clock on the wall is the clock on the slide.
# The Timestamp of the logging event stays UTC, and the sibling's does too.
def get_local_timestamp():
    now = datetime.now()
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


# The schedule, ten times faster than it used to be
#
# What demos 4 and 6 teach is the order - a customer, then an order, then a payment, then a shipment -
# and nothing in that story needed the gaps to be ten, fifteen and twenty minutes. They were, and it
# made both demos empty for twenty minutes after every container start and after every switch between
# the two repositories. Demo 6 felt it worse, because it reads the events rather than the tables.
#
# The customer interval is scaled with the offsets and not left alone, because the proportion is
# what matters: at 6 seconds each, ten customers exist by the time the first order is placed, which
# is exactly what 60 seconds gave against a ten-minute offset. The one-second intervals stay as they
# are - they cannot be scaled down meaningfully, and they were already the fast end of this.
#
# Keep this schedule in step with docker/photoservice-app.ps1 in the sibling repository.
print("Setting up state objects")
new_customer = {
    "delay_sec": 6,
    "next_run": datetime.now(),
    "next_id": 1
}

new_order = {
    "delay_sec": 1,
    "next_run": datetime.now() + timedelta(seconds=60),
    "next_id": 1
}

new_payment = {
    "delay_sec": 1,
    "next_run": datetime.now() + timedelta(seconds=90)
}

new_shipment = {
    "delay_sec": 1,
    "next_run": datetime.now() + timedelta(seconds=120)
}

print("Starting Loop")
while True:

    if datetime.now() > new_customer["next_run"]:
        log("Starting NewCustomer", component="Customer")

        # Build a customer out of the three lists in CustomerSource.json
        firstname = random.choice(customer_source["Firstnames"])
        surname = random.choice(customer_source["Surnames"])
        city = random.choice(customer_source["Cities"])
        domain = city.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace(" ", "").lower()
        customer = {
            "id": new_customer["next_id"],
            "firstname": firstname,
            "surname": surname,
            "city": city,
            "email": f"{firstname}.{surname}@{domain}.de"
        }

        write_pg_table(
            connection=pg_connection,
            table="customer",
            data=pd.DataFrame([customer]),
            enable_exception=True
        )
        log("Added customer", component="Customer", details=customer)

        new_customer["next_id"] += 1
        new_customer["next_run"] = datetime.now() + timedelta(seconds=new_customer["delay_sec"])
        log(
            f"Scheduled next customer with id {new_customer['next_id']} for {new_customer['next_run']}",
            component="Customer"
        )

    if datetime.now() > new_order["next_run"]:
        log("Starting NewOrder", component="Order")

        order_header = {
            "id": new_order["next_id"],
            "customer_id": random.randint(1, max(new_customer["next_id"] - 1, 1)),
            "created_at": get_local_timestamp(),
            "updated_at": None,
            "payment_uuid": None,
            "shipment_uuid": None
        }

        # Draw photos with repetition, so that a photo ordered twice becomes a quantity of two
        number_of_photos = random.randint(1, 49)
        log(f"Order will contain {number_of_photos} photos", component="Order")
        quantity_of = Counter(random.randint(1, len(photos)) for _ in range(number_of_photos))
        order_details = [
            {
                "order_id": order_header["id"],
                "photo_id": photo["id"],
                "quantity": quantity_of[photo["id"]],
                "price": quantity_of[photo["id"]] * photo["price"]
            }
            for photo in photos
            if photo["id"] in quantity_of
        ]

        # The header and its details are one unit of work, so both writes go into one
        # transaction. commit=False is the port of the sibling's -Transaction: in Python the
        # transaction belongs to the connection, so there is nothing to hand over and the only
        # question is who ends it.
        write_pg_table(
            connection=pg_connection,
            table="order_header",
            data=pd.DataFrame([order_header]),
            commit=False,
            enable_exception=True
        )
        write_pg_table(
            connection=pg_connection,
            table="order_detail",
            data=pd.DataFrame(order_details),
            commit=False,
            enable_exception=True
        )
        pg_connection.commit()

        # Announced after the commit, not before it. An event that says a thing happened, sent
        # while the transaction that did it could still roll back, is the oldest mistake in this
        # subject - and demo 6 is about believing these events.
        log("Added order header", component="Order", details=order_header)
        log("Added order details", component="Order", details=order_details)

        # The same order as one document, the way a document database would hold it: the customer
        # and every photo denormalised into the order instead of joined to it
        customer = invoke_pg_query(
            connection=pg_connection,
            query="SELECT * FROM customer WHERE id = :id",
            parameter_values={"id": order_header["customer_id"]},
            as_type="dict",
            enable_exception=True
        )[0]
        photo_of = {photo["id"]: photo for photo in photos}
        order_document = {
            "OrderId": order_header["id"],
            "CreatedAt": order_header["created_at"],
            "Customer": {
                "CustomerId": customer["id"],
                "FirstName": customer["firstname"],
                "SurName": customer["surname"],
                "City": customer["city"],
                "EMail": customer["email"]
            },
            "Photos": [
                {
                    "Quantity": detail["quantity"],
                    "Photo": {
                        "PhotoId": detail["photo_id"],
                        "Name": photo_of[detail["photo_id"]]["name"],
                        # A NUMERIC arrives as a decimal.Decimal, and BSON cannot encode one.
                        # Npgsql hands the sibling a [decimal] and Mdbc converts it on the way in;
                        # pymongo raises InvalidDocument instead, so the conversion is ours.
                        "Price": float(photo_of[detail["photo_id"]]["price"])
                    }
                }
                for detail in order_details
            ],
            "Price": float(sum(detail["price"] for detail in order_details))
        }

        write_mdb_collection(
            connection=mdb_connection,
            collection="Orders",
            data=[order_document],
            enable_exception=True
        )
        log(f"Added order {order_header['id']} to the MongoDB collection", component="Order")

        new_order["next_id"] += 1
        new_order["next_run"] = datetime.now() + timedelta(seconds=new_order["delay_sec"])
        log(f"Scheduled next order with id {new_order['next_id']} for {new_order['next_run']}", component="Order")

    if datetime.now() > new_payment["next_run"]:
        log("Starting NewPayment", component="Payment")

        order_id = invoke_pg_query(
            connection=pg_connection,
            query="SELECT id FROM order_header WHERE payment_uuid IS NULL ORDER BY RANDOM() LIMIT 1",
            as_type="single_value",
            enable_exception=True
        )

        # Every order may already be paid for, and then there is nothing to do. The sibling has
        # no such check and writes an order_event with a NULL order_id - see SIBLING-FINDINGS.md.
        if order_id is not None:
            payment = {
                "order_id": order_id,
                "payment_uuid": uuid.uuid4(),
                "updated_at": get_local_timestamp()
            }
            # The change and the outbox row are one unit of work, and that is the whole point of an
            # outbox: if the order was not paid for, there is no row claiming it was. These used to
            # be two separate committed statements, so a crash between them left a paid order with
            # nothing to say so - and demo 6 had to explain the gap instead of the pattern.
            invoke_pg_query(
                connection=pg_connection,
                query="UPDATE order_header SET updated_at = :updated_at, payment_uuid = :payment_uuid WHERE id = :order_id",
                parameter_values=payment,
                commit=False,
                enable_exception=True
            )
            invoke_pg_query(
                connection=pg_connection,
                query="INSERT INTO order_event (order_id, updated_at, payment_uuid) VALUES (:order_id, :updated_at, :payment_uuid)",
                parameter_values=payment,
                commit=False,
                enable_exception=True
            )
            pg_connection.commit()

            # After the commit, for the reason the order block above gives
            log("Added payment", component="Payment", details=payment)

        new_payment["next_run"] = datetime.now() + timedelta(seconds=new_payment["delay_sec"])
        log(f"Scheduled next payment for {new_payment['next_run']}", component="Payment")

    if datetime.now() > new_shipment["next_run"]:
        log("Starting NewShipment", component="Shipment")

        order_id = invoke_pg_query(
            connection=pg_connection,
            query="SELECT id FROM order_header WHERE payment_uuid IS NOT NULL AND shipment_uuid IS NULL ORDER BY RANDOM() LIMIT 1",
            as_type="single_value",
            enable_exception=True
        )

        if order_id is not None:
            shipment = {
                "order_id": order_id,
                "shipment_uuid": uuid.uuid4(),
                "updated_at": get_local_timestamp()
            }
            # One unit of work, the same as the payment block above
            invoke_pg_query(
                connection=pg_connection,
                query="UPDATE order_header SET updated_at = :updated_at, shipment_uuid = :shipment_uuid WHERE id = :order_id",
                parameter_values=shipment,
                commit=False,
                enable_exception=True
            )
            invoke_pg_query(
                connection=pg_connection,
                query="INSERT INTO order_event (order_id, updated_at, shipment_uuid) VALUES (:order_id, :updated_at, :shipment_uuid)",
                parameter_values=shipment,
                commit=False,
                enable_exception=True
            )
            pg_connection.commit()

            log("Added shipment", component="Shipment", details=shipment)

        new_shipment["next_run"] = datetime.now() + timedelta(seconds=new_shipment["delay_sec"])
        log(f"Scheduled next shipment for {new_shipment['next_run']}", component="Shipment")

    time.sleep(0.1)
