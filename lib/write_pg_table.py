import contextlib
import time

import pandas as pd


# PostgreSQL folds unquoted identifiers to lower case, and the tables of this repository are
# created unquoted. So we lower case the name and quote it, which is what the catalog holds.
def _quote_identifier(name):
    return '"{}"'.format(name.lower().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


def _print_progress(inserted, total_rows, start_time):
    elapsed = time.time() - start_time
    rate = inserted / elapsed if elapsed > 0 else 0

    if total_rows:
        print(
            f"[VERBOSE] {inserted}/{total_rows} rows inserted "
            f"({inserted / total_rows * 100:.1f}%) "
            f"- {int(rate)} rows/sec"
        )
    else:
        print(f"[VERBOSE] {inserted} rows inserted - {int(rate)} rows/sec")


# DIFFERENCE: the sibling takes a -Transaction and hands it to the command. In Python the
# transaction belongs to the connection, so there is nothing to hand over - the only question is
# who ends it. With commit=False this function neither commits nor rolls back, so several calls
# make up one unit of work and the caller commits the connection.
def write_pg_table(
    connection,
    table,
    data=None,
    data_reader=None,
    data_reader_row_count=None,
    batch_size=1000,
    truncate_table=False,
    commit=True,
    enable_exception=False
):
    cursor = None

    try:
        if data is None and data_reader is None:
            raise Exception("Neither data nor data_reader is used, so there is nothing to do")

        if data is not None and data_reader is not None:
            raise Exception("Use either data or data_reader, not both")

        if data is not None:
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

        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        copy_sql = f"COPY {quoted_table} ({quoted_columns}) FROM STDIN"

        start_time = time.time()
        inserted = 0

        # COPY is what PostgreSQL itself offers for this, and it measured about four times faster
        # than the same rows through executemany. The sibling's Write-PgTable used to fill a
        # DataTable and let an NpgsqlDataAdapter generate the INSERT statements; it writes to
        # Npgsql's BeginTextImport now, so the two are the same shape again.
        if data is not None:
            # Match the DataFrame columns case insensitively: extra columns are dropped,
            # columns the frame does not have become NULL
            position_of = {str(column).lower(): index for index, column in enumerate(data.columns)}
            positions = [position_of.get(column.lower()) for column in columns]

            total_rows = len(data)
            print(f"[VERBOSE] Inserting {total_rows} rows")

            with cursor.copy(copy_sql) as copy:
                for row in data.itertuples(index=False, name=None):
                    copy.write_row(tuple(
                        None if position is None or pd.isna(row[position]) else row[position]
                        for position in positions
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        _print_progress(inserted, total_rows, start_time)

        else:
            # Streaming from another table, possibly in another database system. The rows are
            # read in batches and never all held in memory at once.
            source_columns = [column[0] for column in data_reader.description]
            target_names = {column.lower() for column in columns}

            missing = [name for name in source_columns if name.lower() not in target_names]
            if missing:
                raise Exception(f"No target column for source column {', '.join(missing)}")

            position_of = {name.lower(): index for index, name in enumerate(source_columns)}
            positions = [position_of.get(column.lower()) for column in columns]

            total_rows = data_reader_row_count
            print("[VERBOSE] Inserting rows from the data reader")

            with cursor.copy(copy_sql) as copy:
                while True:
                    rows = data_reader.fetchmany(batch_size)
                    if not rows:
                        break

                    for row in rows:
                        copy.write_row(tuple(
                            None if position is None else row[position]
                            for position in positions
                        ))

                    inserted += len(rows)
                    _print_progress(inserted, total_rows, start_time)

        if commit:
            connection.commit()

        print("[VERBOSE] Bulk insert complete")

    except Exception as e:
        # With commit=False the transaction is not ours to end, so the caller rolls it back.
        # The rollback is guarded because it can fail too, and then it replaces the real error
        # with its own: when the server closes the connection, "terminating connection due to
        # administrator command" is what went wrong and "the connection is lost" is all you see.
        if commit:
            with contextlib.suppress(Exception):
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

        # The sibling disposes the data reader it was handed, so this does too
        if data_reader is not None:
            data_reader.close()
