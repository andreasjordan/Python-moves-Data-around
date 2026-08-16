"""Reproduces the PhotoService numbers from AGENTS.md: 24 images, 43.5 MB, byte-identical by MD5 and
length, and a transfer whose first pass carries the backlog while later passes do not.

Needs SQL Server, PostgreSQL and the photoservice container running. The second half has nothing to
find until the shop has been up for about two minutes, and says so rather than failing.

Loads the images into the PostgreSQL photo table, which is what scenario 4's first section does and
what leaves that table in its post-notebook state. Everything else is Verify_* and dropped again.
"""

import argparse
import hashlib
import time

from verify_common import add_repository_paths, complete_verify, fact, line, start_verify

root = add_repository_paths()

from connect_pg_instance import connect_pg_instance  # noqa: E402
from connect_sql_instance import connect_sql_instance  # noqa: E402
from get_pg_data_reader import get_pg_data_reader  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402
from write_sql_table import write_sql_table  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("PhotoService", args.report_path)

sql_connection = connect_sql_instance(instance="127.0.0.1", database="PhotoService",
                                      username="PhotoService", password="Passw0rd!",
                                      enable_exception=True)
pg_connection = connect_pg_instance(instance="127.0.0.1", database="photoservice",
                                    username="photoservice", password="Passw0rd!",
                                    enable_exception=True)

###############################################################################
# The photos
###############################################################################

files = sorted((root / "data" / "photoservice").glob("*.jpg"))
total_bytes = sum(f.stat().st_size for f in files)
fact("24 jpg files on disk", len(files) == 24, f"{len(files)} files")
fact("about 43.5 MB on disk", abs(total_bytes / 1024 / 1024 - 43.5) < 0.5,
     f"{total_bytes / 1024 / 1024:.1f} MB / {total_bytes} bytes")

# The notebook's first section, driven the way it drives it
for file in files:
    invoke_pg_query(
        connection=pg_connection,
        query="UPDATE photo SET image = :image WHERE name = :name",
        parameter_values={"name": file.name, "image": file.read_bytes()},
        enable_exception=True
    )

# The photo rows exist with a NULL image until the loop above runs, so a comparison that skipped this
# would be comparing nothing against nothing - which is how an MD5 check passed for the wrong reason.
not_null = invoke_pg_query(connection=pg_connection, as_type="single_value", enable_exception=True,
                           query="SELECT COUNT(*) FROM photo WHERE image IS NOT NULL")
fact("24 non-NULL images in PostgreSQL", not_null == 24, f"{not_null} non-NULL")

invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_photo",
                 enable_exception=True)
invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
    "CREATE TABLE dbo.Verify_photo (id INT, name VARCHAR(50), price NUMERIC(5, 2), "
    "image VARBINARY(MAX), CONSTRAINT Verify_photo_pk PRIMARY KEY (id))"))

try:
    data_reader = get_pg_data_reader(connection=pg_connection, table="photo", enable_exception=True)
    write_sql_table(connection=sql_connection, table="dbo.Verify_photo", data_reader=data_reader,
                    enable_exception=True)

    pg_rows = {r["name"]: r["image"] for r in invoke_pg_query(
        connection=pg_connection, as_type="dict", enable_exception=True,
        query="SELECT name, image FROM photo")}
    sql_rows = {r["name"]: r["image"] for r in invoke_sql_query(
        connection=sql_connection, as_type="dict", enable_exception=True,
        query="SELECT name, image FROM dbo.Verify_photo")}

    length_differ = hash_differ = null_seen = compared = 0
    for file in files:
        file_bytes = file.read_bytes()
        pg_image = pg_rows.get(file.name)
        sql_image = sql_rows.get(file.name)
        if pg_image is None or sql_image is None:
            null_seen += 1
            continue
        compared += 1
        if len(file_bytes) != len(pg_image) or len(file_bytes) != len(sql_image):
            length_differ += 1
        # usedforsecurity=False says what this is: a content fingerprint for comparing three copies
        # of the same JPEG, not a security decision. It is also what keeps ruff's S324 quiet without
        # a blanket ignore.
        digest = hashlib.md5(file_bytes, usedforsecurity=False).hexdigest()
        if digest != hashlib.md5(bytes(pg_image), usedforsecurity=False).hexdigest() or \
           digest != hashlib.md5(bytes(sql_image), usedforsecurity=False).hexdigest():
            hash_differ += 1

    fact("no NULL image reached the comparison", null_seen == 0, f"{null_seen} NULL")
    fact("all 24 were actually compared", compared == 24, f"{compared} compared")
    fact("length identical: file, PostgreSQL, SQL Server", length_differ == 0, f"{length_differ} differ")
    fact("MD5 identical: file, PostgreSQL, SQL Server", hash_differ == 0, f"{hash_differ} differ")
finally:
    invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_photo",
                     enable_exception=True)

###############################################################################
# The incremental transfer
###############################################################################

source_orders = invoke_pg_query(connection=pg_connection, as_type="single_value",
                                enable_exception=True,
                                query="SELECT COUNT(*) FROM order_header")

if source_orders < 1:
    fact("the shop has produced orders to transfer", False,
         "none yet - the first order is 60 s after the container starts")
else:
    fact("the shop has produced orders to transfer", True,
         f"{source_orders} order headers in PostgreSQL")

    for table in ["dbo.Verify_customer", "dbo.Verify_order_header", "dbo.Verify_order_detail"]:
        invoke_sql_query(connection=sql_connection, query=f"DROP TABLE IF EXISTS {table}",
                         enable_exception=True)
    invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
        "CREATE TABLE dbo.Verify_customer (id INT, firstname VARCHAR(50), surname VARCHAR(50), "
        "city VARCHAR(50), email VARCHAR(200), transfered_at DATETIME2, "
        "CONSTRAINT Verify_customer_pk PRIMARY KEY (id))"))
    invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
        "CREATE TABLE dbo.Verify_order_header (id INT, customer_id INT, created_at DATETIME2, "
        "updated_at DATETIME2, payment_uuid UNIQUEIDENTIFIER, shipment_uuid UNIQUEIDENTIFIER, "
        "CONSTRAINT Verify_order_header_pk PRIMARY KEY (id))"))
    invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
        "CREATE TABLE dbo.Verify_order_detail (order_id INT, photo_id INT, quantity INT, "
        "price NUMERIC(7, 2), CONSTRAINT Verify_order_detail_pk PRIMARY KEY (order_id, photo_id))"))

    def transfer_pass():
        """The notebook's incremental transfer, against Verify_ tables.

        commit=False is what makes the several calls one unit of work - the port of the sibling's
        -Transaction, and the reason the six invoke_*/write_* functions grew that parameter.
        """
        started = time.time()

        customer_target = invoke_sql_query(
            connection=sql_connection, as_type="single_value", enable_exception=True,
            query="SELECT ISNULL(MAX(id), 0) FROM dbo.Verify_customer")
        order_target = invoke_sql_query(
            connection=sql_connection, as_type="single_value", enable_exception=True,
            query="SELECT ISNULL(MAX(id), 0) FROM dbo.Verify_order_header")

        data_reader = get_pg_data_reader(
            connection=pg_connection, enable_exception=True,
            query="SELECT id, firstname, surname, city, email, NOW() AS transfered_at "
                  "FROM customer WHERE id > :id",
            parameter_values={"id": customer_target})
        write_sql_table(connection=sql_connection, table="dbo.Verify_customer",
                        data_reader=data_reader, commit=False, enable_exception=True)

        data_reader = get_pg_data_reader(
            connection=pg_connection, enable_exception=True,
            query="SELECT * FROM order_header WHERE id > :target_id",
            parameter_values={"target_id": order_target})
        write_sql_table(connection=sql_connection, table="dbo.Verify_order_header",
                        data_reader=data_reader, commit=False, enable_exception=True)

        data_reader = get_pg_data_reader(
            connection=pg_connection, enable_exception=True,
            query="SELECT * FROM order_detail WHERE order_id > :target_id",
            parameter_values={"target_id": order_target})
        write_sql_table(connection=sql_connection, table="dbo.Verify_order_detail",
                        data_reader=data_reader, commit=False, enable_exception=True)

        sql_connection.commit()
        return int((time.time() - started) * 1000)

    try:
        first = transfer_pass()
        second = transfer_pass()
        third = transfer_pass()
        line(f"      transfer passes: first {first} ms, second {second} ms, third {third} ms")

        # The shape, not the milliseconds. Both depend on how long the shop has been running, so an
        # absolute assertion would fail for a reason that is not a defect.
        fact("the first pass carries the backlog and later passes are cheaper",
             second < first and third < first, f"first {first} ms vs {second} / {third} ms")

        transferred = invoke_sql_query(connection=sql_connection, as_type="single_value",
                                       enable_exception=True,
                                       query="SELECT COUNT(*) FROM dbo.Verify_order_header")
        fact("the first pass moved the backlog it found", transferred >= source_orders,
             f"{transferred} in SQL Server, {source_orders} were in PostgreSQL when it started")

        # Values, not counts, bounded to what the target holds because the shop keeps writing
        max_id = invoke_sql_query(connection=sql_connection, as_type="single_value",
                                  enable_exception=True,
                                  query="SELECT MAX(id) FROM dbo.Verify_order_header")
        target = invoke_sql_query(
            connection=sql_connection, as_type="dict", enable_exception=True,
            query=f"SELECT id, customer_id, created_at FROM dbo.Verify_order_header "
                  f"WHERE id <= {max_id} ORDER BY id")
        source = invoke_pg_query(
            connection=pg_connection, as_type="dict", enable_exception=True,
            query=f"SELECT id, customer_id, created_at FROM order_header "
                  f"WHERE id <= {max_id} ORDER BY id")
        # strict=False on purpose: a row count mismatch is reported as its own fact above, and
        # strict=True would raise here instead, ending the run rather than describing it
        differ = sum(1 for a, b in zip(target, source, strict=False)
                     if a["id"] != b["id"] or a["customer_id"] != b["customer_id"]
                     or a["created_at"] != b["created_at"])
        fact("order_header: 0 differences on id, customer_id and created_at",
             differ == 0 and len(target) > 0, f"{differ} of {len(target)} differ")
    finally:
        for table in ["dbo.Verify_customer", "dbo.Verify_order_header", "dbo.Verify_order_detail"]:
            invoke_sql_query(connection=sql_connection, query=f"DROP TABLE IF EXISTS {table}",
                             enable_exception=True)

sql_connection.close()
pg_connection.close()

complete_verify()
