import time

import pandas as pd


# PostgreSQL folds unquoted identifiers to lower case, and the tables of this repository are
# created unquoted. So we lower case the name and quote it, which is what the catalog holds.
def _quote_identifier(name):
    return '"{}"'.format(name.lower().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


def write_pg_table(
    connection,
    table,
    data=None,
    batch_size=1000,
    truncate_table=False,
    enable_exception=False
):
    cursor = None

    try:
        if not isinstance(data, pd.DataFrame):
            raise Exception("No data provided, data has to be a pandas DataFrame")

        if data.empty:
            raise Exception("No rows to import, the DataFrame is empty")

        quoted_table = _quote_table_name(table)
        print(f"[VERBOSE] Importing data into {quoted_table}")

        print("[VERBOSE] Creating cursor")
        cursor = connection.cursor()

        # Get the column names of the target table
        cursor.execute(f"SELECT * FROM {quoted_table} WHERE 1=0")
        columns = [column.name for column in cursor.description]

        if truncate_table:
            print("[VERBOSE] Truncating table")
            cursor.execute(f"TRUNCATE TABLE {quoted_table}")

        # Match the DataFrame columns case insensitively. The columns of the table are lower
        # case, the data usually is not.
        position_of = {str(column).lower(): index for index, column in enumerate(data.columns)}
        positions = [position_of.get(column) for column in columns]

        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        copy_sql = f"COPY {quoted_table} ({quoted_columns}) FROM STDIN"

        total_rows = len(data)
        print(f"[VERBOSE] Inserting {total_rows} rows")

        start_time = time.time()
        inserted = 0

        # DIFFERENCE: the sibling fills a DataTable and lets an NpgsqlDataAdapter generate the
        # INSERT statements. COPY is what PostgreSQL itself offers for this, and it measured
        # about four times faster than the same rows through executemany.
        with cursor.copy(copy_sql) as copy:
            for row in data.itertuples(index=False, name=None):
                copy.write_row(tuple(
                    None if position is None or pd.isna(row[position]) else row[position]
                    for position in positions
                ))
                inserted += 1

                if inserted % batch_size == 0:
                    elapsed = time.time() - start_time
                    rate = inserted / elapsed if elapsed > 0 else 0

                    print(
                        f"[VERBOSE] {inserted}/{total_rows} rows inserted "
                        f"({inserted / total_rows * 100:.1f}%) "
                        f"- {int(rate)} rows/sec"
                    )

        connection.commit()

        print("[VERBOSE] Bulk insert complete")

    except Exception as e:
        connection.rollback()
        message = f"Writing table failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None

    finally:
        if cursor is not None:
            cursor.close()
