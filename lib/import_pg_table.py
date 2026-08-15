import contextlib
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path


# PostgreSQL folds unquoted identifiers to lower case, and the tables of this repository are
# created unquoted. So we lower case the name and quote it, which is what the catalog holds.
def _quote_identifier(name):
    return '"{}"'.format(name.lower().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


def _parse_row(line, data_type):
    # Returns the values of one line as a dict with lower cased keys, or None for a line
    # without data. The keys are lower cased because the columns of the table are, and because
    # PowerShell finds a property no matter how it is written.
    if data_type == "xml" and line.lstrip().startswith("<row"):
        return {key.lower(): value for key, value in ET.fromstring(line).attrib.items()}
    if data_type == "json":
        return {key.lower(): value for key, value in json.loads(line).items()}
    return None


def import_pg_table(
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

        # Get the columns of the target table. Unlike the SQL Server version we do not need a
        # converter per column: COPY hands the text to PostgreSQL, which parses it into the
        # column type itself.
        cursor.execute(f"SELECT * FROM {quoted_table} WHERE 1=0")
        columns = [column.name for column in cursor.description]

        if truncate_table:
            print("[VERBOSE] Truncating table")
            cursor.execute(f"TRUNCATE TABLE {quoted_table}")

        # The column map names the source value for a target column, like CreationDate -> Date
        lowered_map = {key.lower(): value.lower() for key, value in column_map.items()} if column_map else {}
        source_names = [lowered_map.get(column, column) for column in columns]

        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        copy_sql = f"COPY {quoted_table} ({quoted_columns}) FROM STDIN"

        file_size = Path(path).stat().st_size

        print("[VERBOSE] Inserting rows")

        start_time = time.time()
        data_type = None
        row_count = 0

        # "utf-8-sig" and not "utf-8", because these files start with a byte order mark and the
        # format detection below would not see the "<?xml" behind it.
        with open(path, encoding=encoding) as file, cursor.copy(copy_sql) as copy:
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

                # One value per column of the target table, as text. A value that is not in the
                # row becomes NULL.
                copy.write_row(tuple(row.get(name) for name in source_names))
                row_count += 1

                if row_count % batch_size == 0:
                    elapsed = time.time() - start_time
                    rate = row_count / elapsed if elapsed > 0 else 0

                    print(
                        f"[VERBOSE] {row_count} rows inserted "
                        f"({file.tell() / file_size * 100:.1f}%) "
                        f"- {int(rate)} rows/sec"
                    )

        connection.commit()

        print(f"[VERBOSE] Imported {row_count} rows in {time.time() - start_time:.1f} seconds")

    except Exception as e:
        # Guarded, because the rollback can fail too and would then replace the real error with
        # its own - see the same guard in write_pg_table.
        with contextlib.suppress(Exception):
            connection.rollback()
        message = f"Importing table failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None

    finally:
        if cursor is not None:
            cursor.close()
