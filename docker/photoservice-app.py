# The PhotoService application: a small shop that keeps inventing customers and orders, so that
# demo/04_photoservice.ipynb has a live system to transfer data away from.
#
# This is the port of photoservice-app.ps1 from the sibling repository. Two differences:
#
# * The sibling archives its logging events as JSON files on MinIO, and the notebook reads them
#   back. MinIO is not ported (see DIFFERENCES.md), so the events are printed instead - with the
#   same component names the sibling gives them - and "docker compose logs -f photoservice" is
#   where you watch the shop run.
# * The sibling sets $PSDefaultParameterValues to turn EnableException on for every -Pg and -Mdb
#   call at once. Python has no such thing, so every call passes enable_exception=True itself.

import json
import random
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# lib/ is mounted into the container, the same way the PowerShell app mounts the PowerShell
# modules from the WSL2 host. This is the container's version of the sys.path dance a notebook
# does, and the functions are the very ones the notebook calls.
sys.path.append("/PhotoService/lib")

from connect_mdb_instance import connect_mdb_instance  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from write_mdb_collection import write_mdb_collection  # noqa: E402
from write_pg_table import write_pg_table  # noqa: E402


# The port of Add-LoggingEvent. In the sibling the events are collected and shipped to MinIO;
# here they are the console trace, so the component name stays and the rest goes.
def log(message, component="Main"):
    print(f"[{component}] {message}")


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
    "mdb_database": "photoservice"
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

        break

    except Exception as e:
        print(f"[ERROR] Connection failed: {str(e)}")
        time.sleep(10)

pg_connection = db_config["pg_connection"]
mdb_connection = db_config["mdb_connection"]

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

print("Reading photo data")
photos = invoke_pg_query(
    connection=pg_connection,
    query="SELECT id, name, price FROM photo",
    as_type="dict",
    enable_exception=True
)

print("Setting up state objects")
new_customer = {
    "delay_sec": 60,
    "next_run": datetime.now(),
    "next_id": 1
}

new_order = {
    "delay_sec": 1,
    "next_run": datetime.now() + timedelta(minutes=10),
    "next_id": 1
}

new_payment = {
    "delay_sec": 1,
    "next_run": datetime.now() + timedelta(minutes=15)
}

new_shipment = {
    "delay_sec": 1,
    "next_run": datetime.now() + timedelta(minutes=20)
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
        log(f"Added customer {customer['id']}", component="Customer")

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
            "created_at": datetime.now(),
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
        log(f"Added order header {order_header['id']} with {len(order_details)} details", component="Order")

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
                "updated_at": datetime.now()
            }
            invoke_pg_query(
                connection=pg_connection,
                query="UPDATE order_header SET updated_at = :updated_at, payment_uuid = :payment_uuid WHERE id = :order_id",
                parameter_values=payment,
                enable_exception=True
            )
            invoke_pg_query(
                connection=pg_connection,
                query="INSERT INTO order_event (order_id, updated_at, payment_uuid) VALUES (:order_id, :updated_at, :payment_uuid)",
                parameter_values=payment,
                enable_exception=True
            )
            log(f"Added payment for order {order_id}", component="Payment")

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
                "updated_at": datetime.now()
            }
            invoke_pg_query(
                connection=pg_connection,
                query="UPDATE order_header SET updated_at = :updated_at, shipment_uuid = :shipment_uuid WHERE id = :order_id",
                parameter_values=shipment,
                enable_exception=True
            )
            invoke_pg_query(
                connection=pg_connection,
                query="INSERT INTO order_event (order_id, updated_at, shipment_uuid) VALUES (:order_id, :updated_at, :shipment_uuid)",
                parameter_values=shipment,
                enable_exception=True
            )
            log(f"Added shipment for order {order_id}", component="Shipment")

        new_shipment["next_run"] = datetime.now() + timedelta(seconds=new_shipment["delay_sec"])
        log(f"Scheduled next shipment for {new_shipment['next_run']}", component="Shipment")

    time.sleep(0.1)
