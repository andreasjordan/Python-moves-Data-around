import datetime
import decimal
import json
import logging
import time
import uuid

logger = logging.getLogger("lib." + __name__)


def _quote_identifier(name):
    return '"{}"'.format(name.lower().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


def _log_progress(exported, total_rows, start_time):
    elapsed = time.time() - start_time
    rate = exported / elapsed if elapsed > 0 else 0

    logger.info(
        f"{exported}/{total_rows} rows exported "
        f"({exported / total_rows * 100:.1f}%) "
        f"- {int(rate)} rows/sec"
    )


# json.dumps refuses a datetime, a Decimal and a UUID, and the tables of this repository hold all
# three. str() is the decision write_kfk_topic already makes, and it is the one that reads back:
# str(datetime) is exactly what datetime.fromisoformat accepts, so import_*_table can load the
# file this function wrote.
def _json_default(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time, decimal.Decimal, uuid.UUID)):
        return str(value)

    # A bytea column would become "b'\\x89PNG...'", which looks like a value and is not one. So
    # this is an error rather than a silent passthrough - the same choice import_sql_table makes
    # for a column type it has no converter for.
    raise TypeError(f"No JSON representation for a value of type {type(value).__name__}")


def export_pg_table(
    connection,
    table,
    path,
    batch_size=1000,
    encoding="utf-8",
    enable_exception=False
):
    cursor = None

    try:
        quoted_table = _quote_table_name(table)
        logger.debug(f"Exporting {quoted_table} to {path}")

        logger.debug("Creating cursor")
        cursor = connection.cursor()

        # The row count only feeds the progress output, which is the one reason to ask for it
        logger.debug("Getting number of rows")
        cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")
        num_rows = cursor.fetchone()[0]

        logger.debug(f"Exporting {num_rows} rows")

        cursor.execute(f"SELECT * FROM {quoted_table}")
        columns = [column.name for column in cursor.description]

        start_time = time.time()
        row_count = 0

        # One JSON object per line, which is one of the two formats import_*_table reads - so a
        # table exported here can be loaded straight back into another database system.
        #
        # DIFFERENCE: the sibling opens its StreamWriter first and closes it in a finally block.
        # A with block is the same guarantee with less around it, which is why the file is opened
        # here rather than at the top.
        with open(path, "w", encoding=encoding, newline="\n") as file:
            for row in cursor:
                file.write(json.dumps(dict(zip(columns, row, strict=True)), default=_json_default))
                file.write("\n")
                row_count += 1

                if row_count % batch_size == 0:
                    _log_progress(row_count, num_rows, start_time)

        logger.info(f"Exported {row_count} rows in {time.time() - start_time:.1f} seconds")

        # A read opens a transaction on this provider too, and a connection left "idle in
        # transaction" keeps its locks - so end it, exactly as invoke_pg_query does.
        if not connection.autocommit:
            connection.commit()

    except Exception as e:
        if not connection.autocommit:
            connection.rollback()

        message = f"Exporting table failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None

    finally:
        if cursor is not None:
            cursor.close()
