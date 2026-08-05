import datetime
import decimal
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# This is the counterpart of the typed DataTable in the sibling function. There, the columns
# of the DataTable are typed from GetSchemaTable() and ADO.NET converts the strings on its own.
# pyodbc has no such thing: with fast_executemany it binds a value by its Python type, so a
# string never reaches an INT column. We therefore convert here, driven by the type that
# cursor.description reports for each column.
_CONVERTERS = {
    int: int,
    float: float,
    str: str,
    bool: lambda value: value in ("1", "true", "True"),
    decimal.Decimal: decimal.Decimal,
    datetime.date: datetime.date.fromisoformat,
    datetime.datetime: datetime.datetime.fromisoformat,
    datetime.time: datetime.time.fromisoformat
}


def _quote_identifier(name):
    return f"[{name.replace(']', ']]')}]"


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split('.'))


def _parse_row(line, data_type):
    # Returns the values of one line as a dict, or None for a line without data
    if data_type == "xml" and line.lstrip().startswith("<row"):
        return ET.fromstring(line).attrib
    if data_type == "json":
        return json.loads(line)
    return None


def import_sql_table(
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

        # Get the columns of the target table and one converter per column
        cursor.execute(f"SELECT TOP 0 * FROM {quoted_table}")

        columns = []
        converters = []
        for column in cursor.description:
            name, type_code = column[0], column[1]
            if type_code not in _CONVERTERS:
                raise Exception(f"No converter for column {name} of type {type_code.__name__}")
            columns.append(name)
            converters.append(_CONVERTERS[type_code])

        if truncate_table:
            print("[VERBOSE] Truncating table")
            cursor.execute(f"TRUNCATE TABLE {quoted_table}")
            connection.commit()

        # Build the insert statement from the target schema
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"

        # Enable fast bulk mode
        cursor.fast_executemany = True

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
                    _convert_value(row, column, column_map, convert)
                    for column, convert in zip(columns, converters, strict=True)
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


def _convert_value(row, column, column_map, convert):
    # The column map names the source value for a target column, like CreationDate -> Date
    source = column_map.get(column, column) if column_map else column
    value = row.get(source)
    return None if value is None else convert(value)
