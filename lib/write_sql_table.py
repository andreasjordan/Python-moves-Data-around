import time

import pandas as pd


def _quote_identifier(name):
    return f"[{name.replace(']', ']]')}]"


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split('.'))


def write_sql_table(
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
        cursor.execute(f"SELECT TOP 0 * FROM {quoted_table}")
        columns = [column[0] for column in cursor.description]

        if truncate_table:
            print("[VERBOSE] Truncating table")
            cursor.execute(f"TRUNCATE TABLE {quoted_table}")
            connection.commit()

        # Build the insert statement from the target schema
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"

        # Align the DataFrame to the target: extra columns are dropped, missing ones become NULL
        data = data.reindex(columns=columns)
        values = [tuple(row) for row in data.itertuples(index=False, name=None)]

        # Enable fast bulk mode
        cursor.fast_executemany = True

        total_rows = len(values)
        print(f"[VERBOSE] Inserting {total_rows} rows")

        start_time = time.time()

        for start in range(0, total_rows, batch_size):
            cursor.executemany(insert_sql, values[start:start + batch_size])
            connection.commit()

            inserted = min(start + batch_size, total_rows)
            elapsed = time.time() - start_time
            rate = inserted / elapsed if elapsed > 0 else 0

            print(
                f"[VERBOSE] {inserted}/{total_rows} rows inserted "
                f"({inserted / total_rows * 100:.1f}%) "
                f"- {int(rate)} rows/sec"
            )

        print("[VERBOSE] Bulk insert complete")

    except Exception as e:
        message = f"Writing table failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None

    finally:
        if cursor is not None:
            cursor.close()
