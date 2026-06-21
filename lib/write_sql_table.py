import pyodbc
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
    truncate_table=False
):
    """
    Python equivalent of Write-SqlTable using pyodbc bulk insert.

    The `data` parameter must be a pandas DataFrame.
    """

    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")
    if data.empty:
        raise ValueError("No data provided")

    cursor = connection.cursor()

    quoted_table = _quote_table_name(table)
    print(f"Importing data into {quoted_table}")

    # Get table schema (column names)
    cursor.execute(f"SELECT TOP 0 * FROM {quoted_table}")
    columns = [column[0] for column in cursor.description]

    # Optional truncate
    if truncate_table:
        print("Truncating table...")
        cursor.execute(f"TRUNCATE TABLE {quoted_table}")
        connection.commit()

    # Prepare insert statement
    column_list = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))

    quoted_columns = ", ".join(_quote_identifier(col) for col in columns)
    insert_sql = f"""
        INSERT INTO {quoted_table} ({quoted_columns})
        VALUES ({placeholders})
    """

    # Align DataFrame to schema order and drop extra columns
    data = data.reindex(columns=columns)

    # Convert DataFrame rows to tuples aligned to schema
    values = [tuple(row) for row in data.itertuples(index=False, name=None)]

    # Enable fast bulk mode
    cursor.fast_executemany = True

    total_rows = len(values)
    print(f"Inserting {total_rows} rows...")

    start_time = time.time()

    # Batch insert
    for i in range(0, total_rows, batch_size):
        batch = values[i:i + batch_size]
        cursor.executemany(insert_sql, batch)
        connection.commit()

        inserted = min(i + batch_size, total_rows)
        elapsed = time.time() - start_time

        rate = inserted / elapsed if elapsed > 0 else 0

        print(
            f"{inserted}/{total_rows} rows inserted "
            f"({inserted / total_rows * 100:.1f}%) "
            f"- {int(rate)} rows/sec"
        )

    cursor.close()

    print("Bulk insert complete.")