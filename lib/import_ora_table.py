import datetime
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import oracledb

# DIFFERENCE: the third answer to the same question, and it sits between the other two.
# import_sql_table has to convert every value, because pyodbc binds a value by its Python type.
# import_pg_table converts nothing, because COPY hands the text to PostgreSQL. Oracle converts
# the numbers out of their strings without being asked, but not the timestamps: the ISO dates of
# these files do not match NLS_TIMESTAMP_FORMAT, so the insert fails with
# "ORA-01843: not a valid month". Exactly two column types therefore need a converter, and a
# column that is not in this table keeps the string it came from.
_CONVERTERS = {
    oracledb.DB_TYPE_TIMESTAMP: datetime.datetime.fromisoformat,
    oracledb.DB_TYPE_DATE: datetime.datetime.fromisoformat
}

# And converting alone is not enough. oracledb binds a Python datetime as DB_TYPE_DATE, and an
# Oracle DATE holds whole seconds, so the fractional seconds are dropped on the way in - without
# an error, and with the right number of rows reported. The TIMESTAMP columns have to be
# declared with setinputsizes to keep them. Only those: declaring the CLOB column as well was
# measured 30 times slower.
_BIND_TYPES = {
    oracledb.DB_TYPE_TIMESTAMP: oracledb.DB_TYPE_TIMESTAMP,
    oracledb.DB_TYPE_DATE: oracledb.DB_TYPE_TIMESTAMP
}


# Oracle folds unquoted identifiers to UPPER CASE, the inverse of PostgreSQL, and the tables of
# this repository are created unquoted. So we upper case the name and quote it, which is what
# the data dictionary holds.
def _quote_identifier(name):
    return '"{}"'.format(name.upper().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


def _parse_row(line, data_type):
    # Returns the values of one line as a dict with lower cased keys, or None for a line
    # without data. The keys are lower cased because the columns of the table arrive in upper
    # case, and because PowerShell finds a property no matter how it is written.
    if data_type == "xml" and line.lstrip().startswith("<row"):
        return {key.lower(): value for key, value in ET.fromstring(line).attrib.items()}
    if data_type == "json":
        return {key.lower(): value for key, value in json.loads(line).items()}
    return None


def import_ora_table(
    connection,
    path,
    table,
    batch_size=1000,
    encoding="utf-8-sig",
    column_map=None,
    truncate_table=False,
    enable_exception=False
):
    cursor = None

    try:
        quoted_table = _quote_table_name(table)
        print(f"[VERBOSE] Importing data from {path} into {quoted_table}")

        print("[VERBOSE] Creating cursor")
        cursor = connection.cursor()

        # Get the columns of the target table, a converter for the ones that need one, and the
        # bind type for the ones that have to be declared
        cursor.execute(f"SELECT * FROM {quoted_table} WHERE 1=0")

        columns = []
        converters = []
        bind_types = []
        for column in cursor.description:
            columns.append(column.name)
            converters.append(_CONVERTERS.get(column.type_code))
            bind_types.append(_BIND_TYPES.get(column.type_code))

        if truncate_table:
            print("[VERBOSE] Truncating table")
            cursor.execute(f"TRUNCATE TABLE {quoted_table}")
            connection.commit()

        # The column map names the source value for a target column, like CreationDate -> Date
        lowered_map = {key.lower(): value.lower() for key, value in column_map.items()} if column_map else {}
        source_names = [lowered_map.get(column.lower(), column.lower()) for column in columns]

        # Build the insert statement from the target schema. Oracle binds by name, and its own
        # placeholder syntax is :name, so the columns are numbered :1 .. :n.
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(f":{position}" for position in range(1, len(columns) + 1))
        insert_sql = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"

        # Declare the TIMESTAMP columns, so that the milliseconds survive. Everything else stays
        # None and is bound by its Python type: a 5440 character AboutMe reaches the CLOB
        # without being declared, and declaring it would cost more than the whole import does.
        cursor.setinputsizes(*bind_types)

        file_size = Path(path).stat().st_size

        print("[VERBOSE] Inserting rows")

        start_time = time.time()
        data_type = None
        row_count = 0
        batch = []

        # The file is read line by line, so its size does not matter.
        # "utf-8-sig" and not "utf-8", because these files start with a byte order mark and
        # the format detection below would not see the "<?xml" behind it.
        with open(path, encoding=encoding) as file:
            while True:
                line = file.readline()
                if not line:
                    break

                # The first line tells us what kind of file we are reading
                if data_type is None:
                    if line.startswith("<?xml"):
                        data_type = "xml"
                    elif line.startswith("{"):
                        data_type = "json"

                row = _parse_row(line, data_type)
                if row is None:
                    continue

                # One value per column of the target table. A value that is not in the row
                # becomes NULL - the rows of these files do not all have the same attributes.
                batch.append(tuple(
                    _convert_value(row.get(name), convert)
                    for name, convert in zip(source_names, converters, strict=True)
                ))
                row_count += 1

                if len(batch) == batch_size:
                    cursor.executemany(insert_sql, batch)
                    connection.commit()
                    batch.clear()

                    elapsed = time.time() - start_time
                    rate = row_count / elapsed if elapsed > 0 else 0

                    print(
                        f"[VERBOSE] {row_count} rows inserted "
                        f"({file.tell() / file_size * 100:.1f}%) "
                        f"- {int(rate)} rows/sec"
                    )

            if batch:
                cursor.executemany(insert_sql, batch)
                connection.commit()

        print(f"[VERBOSE] Imported {row_count} rows in {time.time() - start_time:.1f} seconds")

    except Exception as e:
        message = f"Importing table failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None

    finally:
        if cursor is not None:
            cursor.close()


def _convert_value(value, convert):
    if value is None or convert is None:
        return value
    return convert(value)
