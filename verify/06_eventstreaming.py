"""Reproduces the event streaming checks: the five kfk functions, the auto.offset.reset trap proved
three ways, and a replay of the whole topic compared to PostgreSQL column by column.

It also covers the two defects found on 2026-08-16, because both were invisible to every check that
existed at the time: the topic must hold one application generation, and the timestamps on it must be
whole milliseconds.

Needs SQL Server, PostgreSQL, Redpanda and the photoservice container running.

IT STOPS THE SHOP AND STARTS IT AGAIN. Freezing the source is the only way to compare a replay
against PostgreSQL without the two moving apart underneath - and starting it again truncates its
tables and empties the topic, so scenarios 4 and 6 need their usual two minutes afterwards.
"""

import argparse
import subprocess
import uuid
from datetime import datetime

import pandas as pd
from confluent_kafka import TopicPartition
from confluent_kafka.admin import AdminClient

from verify_common import add_repository_paths, complete_verify, fact, line, start_verify

root = add_repository_paths()

from connect_kfk_consumer import connect_kfk_consumer  # noqa: E402
from connect_kfk_producer import connect_kfk_producer  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
from connect_sql_instance import connect_sql_instance  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402
from read_kfk_topic import read_kfk_topic  # noqa: E402
from remove_kfk_topic import remove_kfk_topic  # noqa: E402
from write_kfk_topic import write_kfk_topic  # noqa: E402
from write_sql_table import write_sql_table  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("Event streaming", args.report_path)

INSTANCE = "127.0.0.1:19092"
TOPIC = "photoservice.events"


def compose(*command):
    subprocess.run(
        ["wsl", "--cd", str(root / "docker"), "--user", "root", "docker", "compose", *command],
        check=True, capture_output=True
    )


def as_datetime(value):
    """NULL arrives as None from one driver and NaT from the other, and the topic carries a string."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if pd.isna(value):
        return None
    return pd.Timestamp(value).to_pydatetime()


def as_text(value):
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return str(value).lower()


###############################################################################
# The five kfk functions, against a throwaway topic
###############################################################################

# uuid4 rather than random.randint: a group id has to be one nobody has used, and uuid4 says
# that directly instead of hoping. It also keeps ruff's S311 quiet without an ignore.
probe_topic = f"verify.probe.{uuid.uuid4().hex[:8]}"
producer = connect_kfk_producer(instance=INSTANCE, enable_exception=True)
fact("connect_kfk_producer returns a producer", producer is not None, type(producer).__name__)

sent = [
    {
        "Seq": i,
        "Text": f"line {i} with a tab\t a newline\n and a backslash \\ and Umlaute aeoeue",
        "When": "2026-08-16T12:34:56.789",
        "Amount": "9876.5432",
        "Nested": {"Inner": {"Deep": f"deep-{i}"}, "List": [1, 2, 3]},
    }
    for i in range(1, 51)
]
fact("the probe payload really carries tab, newline and backslash",
     "\t" in sent[0]["Text"] and "\n" in sent[0]["Text"] and "\\" in sent[0]["Text"],
     "present in the source")

write_kfk_topic(connection=producer, topic=probe_topic, data=sent, enable_exception=True)

group_a = f"verify-a-{uuid.uuid4().hex[:8]}"
consumer_a = connect_kfk_consumer(instance=INSTANCE, group_id=group_a, from_beginning=True,
                                  enable_exception=True)
read = read_kfk_topic(connection=consumer_a, topic=probe_topic, first=50, as_type="dict",
                      enable_exception=True)
fact("a new group with from_beginning reads all 50", len(read) == 50, f"read {len(read)}")

differ = sum(
    1 for i in range(len(read))
    if read[i]["Seq"] != sent[i]["Seq"]
    or read[i]["Text"] != sent[i]["Text"]
    or read[i]["When"] != sent[i]["When"]
    or read[i]["Amount"] != sent[i]["Amount"]
    or read[i]["Nested"]["Inner"]["Deep"] != sent[i]["Nested"]["Inner"]["Deep"]
    or read[i]["Nested"]["List"] != sent[i]["Nested"]["List"]
)
fact("the round trip is value-exact over all 50", differ == 0, f"{differ} of {len(read)} differ")

# from_beginning is auto.offset.reset, which only applies to a group with no committed offset
consumer_a.close()
consumer_again = connect_kfk_consumer(instance=INSTANCE, group_id=group_a, from_beginning=True,
                                      enable_exception=True)
reread = read_kfk_topic(connection=consumer_again, topic=probe_topic, timeout=8, as_type="dict",
                        enable_exception=True)
fact("the same group id reads 0 the second time", len(reread) == 0, f"read {len(reread)}")
consumer_again.close()

consumer_b = connect_kfk_consumer(instance=INSTANCE, group_id=f"verify-b-{uuid.uuid4().hex[:8]}",
                                  from_beginning=True, enable_exception=True)
read_again = read_kfk_topic(connection=consumer_b, topic=probe_topic, first=50, as_type="dict",
                            enable_exception=True)
fact("a different group id reads all 50 again", len(read_again) == 50, f"read {len(read_again)}")
consumer_b.close()

remove_kfk_topic(instance=INSTANCE, topic=probe_topic, enable_exception=True)
still_there = probe_topic in AdminClient({"bootstrap.servers": INSTANCE}).list_topics(timeout=10).topics
fact("remove_kfk_topic deleted the probe topic", not still_there, probe_topic)

###############################################################################
# The real topic, with the shop frozen
###############################################################################

sql_connection = connect_sql_instance(instance="127.0.0.1", database="PhotoService",
                                      username="PhotoService", password="Passw0rd!",
                                      enable_exception=True)
pg_connection = connect_pg_instance(instance="127.0.0.1", database="photoservice",
                                    username="photoservice", password="Passw0rd!",
                                    enable_exception=True)

line("      stopping the shop so that the topic and PostgreSQL stop moving apart")
compose("stop", "photoservice")

try:
    scan = connect_kfk_consumer(instance=INSTANCE, group_id=f"verify-scan-{uuid.uuid4().hex[:8]}",
                                from_beginning=True, enable_exception=True)
    low, high = scan.get_watermark_offsets(TopicPartition(TOPIC, 0), timeout=10)
    total = high - low
    line(f"      topic holds {total} messages (low {low}, high {high})")

    fact("the topic is not empty", total > 0, f"{total} messages")
    events = read_kfk_topic(connection=scan, topic=TOPIC, first=total, as_type="dict",
                            enable_exception=True)
    fact("the whole topic reads up to the high watermark", len(events) == total,
         f"read {len(events)} of {total}")

    # One application generation. The shop restarts its ids at 1, so a topic that outlived the
    # tables holds one "Added customer" with id 1 per start - and the replay below then dies on a
    # primary key violation. This is the check that did not exist on 2026-08-16.
    added_customer = [e for e in events if e["Message"] == "Added customer"]
    id_one = [e for e in added_customer if e["Details"]["id"] == 1]
    fact("the topic holds exactly one application generation", len(id_one) == 1,
         f"{len(id_one)} events with customer id = 1")
    ids = [e["Details"]["id"] for e in added_customer]
    duplicates = len(ids) - len(set(ids))
    fact("no customer id appears twice on the topic", duplicates == 0, f"{duplicates} duplicated ids")

    # Whole milliseconds. TIMESTAMP(3) rounds, so anything finer makes the replay land a different
    # value in SQL Server than scenario 4's direct transfer does. Checked by value and not by the
    # rendering: str(datetime) always prints six digits, so ".199000" is 199 ms and not a failure.
    headers = [e for e in events if e["Message"] == "Added order header"]
    if headers:
        sub_millisecond = [h for h in headers
                           if as_datetime(h["Details"]["created_at"]).microsecond % 1000 != 0]
        fact("every created_at on the topic is a whole number of milliseconds",
             len(sub_millisecond) == 0,
             f"{len(sub_millisecond)} of {len(headers)} carry sub-millisecond digits")
    else:
        fact("the topic has order headers to inspect", False, "none - has the shop been up a minute?")

    ###########################################################################
    # The replay, compared to PostgreSQL column by column
    ###########################################################################

    for table in ["dbo.Verify_customer", "dbo.Verify_order_header", "dbo.Verify_order_detail"]:
        invoke_sql_query(connection=sql_connection, query=f"DROP TABLE IF EXISTS {table}",
                         enable_exception=True)
    invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
        "CREATE TABLE dbo.Verify_customer (id INT, firstname VARCHAR(50), surname VARCHAR(50), "
        "city VARCHAR(50), email VARCHAR(200), CONSTRAINT Verify_customer_pk PRIMARY KEY (id))"))
    invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
        "CREATE TABLE dbo.Verify_order_header (id INT, customer_id INT, created_at DATETIME2, "
        "updated_at DATETIME2, payment_uuid UNIQUEIDENTIFIER, shipment_uuid UNIQUEIDENTIFIER, "
        "CONSTRAINT Verify_order_header_pk PRIMARY KEY (id))"))
    invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
        "CREATE TABLE dbo.Verify_order_detail (order_id INT, photo_id INT, quantity INT, "
        "price NUMERIC(7, 2), CONSTRAINT Verify_order_detail_pk PRIMARY KEY (order_id, photo_id))"))

    try:
        # The notebook's fold, unchanged apart from the table names
        customers = []
        order_headers = {}
        lines = []
        for event in events:
            details = event["Details"]
            message = event["Message"]
            if message == "Added customer":
                customers.append(details)
            elif message == "Added order header":
                order_headers[details["id"]] = details
            elif message == "Added order details":
                lines.extend(details)
            elif message == "Added payment":
                header = order_headers.get(details["order_id"])
                if header:
                    header["updated_at"] = details["updated_at"]
                    header["payment_uuid"] = details["payment_uuid"]
            elif message == "Added shipment":
                header = order_headers.get(details["order_id"])
                if header:
                    header["updated_at"] = details["updated_at"]
                    header["shipment_uuid"] = details["shipment_uuid"]

        replay_error = None
        try:
            if customers:
                write_sql_table(connection=sql_connection, table="dbo.Verify_customer",
                                data=pd.DataFrame(customers), enable_exception=True)
            if order_headers:
                write_sql_table(connection=sql_connection, table="dbo.Verify_order_header",
                                data=pd.DataFrame(list(order_headers.values())),
                                enable_exception=True)
            if lines:
                write_sql_table(connection=sql_connection, table="dbo.Verify_order_detail",
                                data=pd.DataFrame(lines), enable_exception=True)
        except Exception as e:
            replay_error = str(e)
        fact("the whole topic replays without a primary key violation", replay_error is None,
             replay_error or "no error")

        sql_customers = invoke_sql_query(
            connection=sql_connection, as_type="dict", enable_exception=True,
            query="SELECT id, firstname, surname, city, email FROM dbo.Verify_customer ORDER BY id")
        pg_customers = invoke_pg_query(
            connection=pg_connection, as_type="dict", enable_exception=True,
            query="SELECT id, firstname, surname, city, email FROM customer ORDER BY id")
        fact("customer row counts agree with PostgreSQL", len(sql_customers) == len(pg_customers),
             f"{len(sql_customers)} replayed, {len(pg_customers)} in PostgreSQL")
        # strict=False on purpose: a row count mismatch is its own fact above, and strict=True
        # would raise here instead, ending the run rather than describing it
        differ = sum(1 for a, b in zip(sql_customers, pg_customers, strict=False)
                     if a["id"] != b["id"] or a["firstname"] != b["firstname"]
                     or a["surname"] != b["surname"] or a["city"] != b["city"]
                     or a["email"] != b["email"])
        fact("customer: 0 differences on every column", differ == 0 and len(sql_customers) > 0,
             f"{differ} of {len(sql_customers)} differ")

        columns = ["id", "customer_id", "created_at", "updated_at", "payment_uuid", "shipment_uuid"]
        sql_headers = invoke_sql_query(
            connection=sql_connection, as_type="dict", enable_exception=True,
            query=f"SELECT {', '.join(columns)} FROM dbo.Verify_order_header ORDER BY id")
        pg_headers = invoke_pg_query(
            connection=pg_connection, as_type="dict", enable_exception=True,
            query=f"SELECT {', '.join(columns)} FROM order_header ORDER BY id")
        fact("order_header row counts agree with PostgreSQL", len(sql_headers) == len(pg_headers),
             f"{len(sql_headers)} replayed, {len(pg_headers)} in PostgreSQL")

        column_differ = dict.fromkeys(columns, 0)
        pay_compared = ship_compared = updated_compared = 0
        for a, b in zip(sql_headers, pg_headers, strict=False):
            if a["id"] != b["id"]:
                column_differ["id"] += 1
            if a["customer_id"] != b["customer_id"]:
                column_differ["customer_id"] += 1
            if as_datetime(a["created_at"]) != as_datetime(b["created_at"]):
                column_differ["created_at"] += 1
            if as_datetime(a["updated_at"]) != as_datetime(b["updated_at"]):
                column_differ["updated_at"] += 1
            if as_datetime(b["updated_at"]) is not None:
                updated_compared += 1
            if as_text(a["payment_uuid"]) != as_text(b["payment_uuid"]):
                column_differ["payment_uuid"] += 1
            if as_text(b["payment_uuid"]) is not None:
                pay_compared += 1
            if as_text(a["shipment_uuid"]) != as_text(b["shipment_uuid"]):
                column_differ["shipment_uuid"] += 1
            if as_text(b["shipment_uuid"]) is not None:
                ship_compared += 1

        for column in columns:
            fact(f"order_header {column}: 0 differences", column_differ[column] == 0,
                 f"{column_differ[column]} of {len(sql_headers)} differ")

        # Without these the uuid and timestamp comparisons above could all be NULL on both sides and
        # still read as green, which is how three checks passed for the wrong reason in one session.
        fact("payment uuids were actually compared, so the fold did work", pay_compared > 0,
             f"{pay_compared} compared")
        fact("shipment uuids were actually compared, so the fold did work", ship_compared > 0,
             f"{ship_compared} compared")
        fact("updated_at was actually compared and is not all NULL", updated_compared > 0,
             f"{updated_compared} compared")

        sql_lines = invoke_sql_query(
            connection=sql_connection, as_type="dict", enable_exception=True,
            query="SELECT order_id, photo_id, quantity, price FROM dbo.Verify_order_detail "
                  "ORDER BY order_id, photo_id")
        pg_lines = invoke_pg_query(
            connection=pg_connection, as_type="dict", enable_exception=True,
            query="SELECT order_id, photo_id, quantity, price FROM order_detail "
                  "ORDER BY order_id, photo_id")
        fact("order_detail row counts agree with PostgreSQL", len(sql_lines) == len(pg_lines),
             f"{len(sql_lines)} replayed, {len(pg_lines)} in PostgreSQL")
        differ = sum(1 for a, b in zip(sql_lines, pg_lines, strict=False)
                     if a["order_id"] != b["order_id"] or a["photo_id"] != b["photo_id"]
                     or a["quantity"] != b["quantity"] or float(a["price"]) != float(b["price"]))
        fact("order_detail: 0 differences on every column", differ == 0 and len(sql_lines) > 0,
             f"{differ} of {len(sql_lines)} differ")
    finally:
        for table in ["dbo.Verify_customer", "dbo.Verify_order_header", "dbo.Verify_order_detail"]:
            invoke_sql_query(connection=sql_connection, query=f"DROP TABLE IF EXISTS {table}",
                             enable_exception=True)

    scan.close()
finally:
    line("      starting the shop again - it truncates its tables and empties the topic")
    compose("start", "photoservice")
    sql_connection.close()
    pg_connection.close()

complete_verify()
