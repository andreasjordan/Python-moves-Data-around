import logging
import time

import oracledb
import pandas as pd

logger = logging.getLogger("lib." + __name__)

# oracledb binds a Python datetime as DB_TYPE_DATE, and an Oracle DATE holds whole seconds, so
# the fractional seconds are dropped without an error. The TIMESTAMP columns have to be declared
# with setinputsizes to keep them - see the same table in import_ora_table.
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


def _log_progress(inserted, total_rows, start_time):
    elapsed = time.time() - start_time
    rate = inserted / elapsed if elapsed > 0 else 0

    if total_rows:
        logger.info(
            f"{inserted}/{total_rows} rows inserted "
            f"({inserted / total_rows * 100:.1f}%) "
            f"- {int(rate)} rows/sec"
        )
    else:
        logger.info(f"{inserted} rows inserted - {int(rate)} rows/sec")


# DIFFERENCE: the sibling takes a -Transaction and hands it to the command. In Python the
# transaction belongs to the connection, so there is nothing to hand over - the only question is
# who ends it. With commit=False this function neither commits nor rolls back, so several calls
# make up one unit of work and the caller commits the connection.
def write_ora_table(
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
        logger.debug(f"Importing data into {quoted_table}")

        logger.debug("Creating cursor")
        cursor = connection.cursor()

        # Get the column names of the target table, and the bind type for the ones that need one
        cursor.execute(f"SELECT * FROM {quoted_table} WHERE 1=0")
        columns = [column.name for column in cursor.description]
        bind_types = [_BIND_TYPES.get(column.type_code) for column in cursor.description]

        if truncate_table:
            logger.debug("Truncating table")
            cursor.execute(f"TRUNCATE TABLE {quoted_table}")
            if commit:
                connection.commit()

        # Build the insert statement from the target schema. Oracle's own placeholder syntax is
        # :name, so the columns are numbered :1 .. :n.
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(f":{position}" for position in range(1, len(columns) + 1))
        insert_sql = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"

        # Declare the TIMESTAMP columns, so that the milliseconds survive
        cursor.setinputsizes(*bind_types)

        start_time = time.time()
        inserted = 0

        if data is not None:
            # Match the DataFrame columns case insensitively: extra columns are dropped,
            # columns the frame does not have become NULL
            position_of = {str(column).lower(): index for index, column in enumerate(data.columns)}
            positions = [position_of.get(column.lower()) for column in columns]

            total_rows = len(data)
            logger.debug(f"Inserting {total_rows} rows")

            values = [
                tuple(
                    None if position is None or pd.isna(row[position]) else row[position]
                    for position in positions
                )
                for row in data.itertuples(index=False, name=None)
            ]

            for start in range(0, total_rows, batch_size):
                cursor.executemany(insert_sql, values[start:start + batch_size])
                if commit:
                    connection.commit()

                inserted = min(start + batch_size, total_rows)
                _log_progress(inserted, total_rows, start_time)

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
            logger.debug("Inserting rows from the data reader")

            while True:
                rows = data_reader.fetchmany(batch_size)
                if not rows:
                    break

                cursor.executemany(insert_sql, [
                    tuple(None if position is None else row[position] for position in positions)
                    for row in rows
                ])
                if commit:
                    connection.commit()

                inserted += len(rows)
                _log_progress(inserted, total_rows, start_time)

        logger.info("Bulk insert complete")

    except Exception as e:
        message = f"Writing table failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None

    finally:
        if cursor is not None:
            cursor.close()

        # The sibling disposes the data reader it was handed, so this does too
        if data_reader is not None:
            data_reader.close()
