import logging

from invoke_sql_query import _prepare_query_and_params

logger = logging.getLogger("lib." + __name__)


# DIFFERENCE: the sibling writes one [PSCustomObject] per row to the pipeline and PowerShell
# streams it into whatever comes next. The Python counterpart of that is a generator, so this
# yields one dict per row. Two consequences the call site can see: nothing at all happens until
# the caller starts iterating, and a failure therefore surfaces on the first next() rather than
# on the call. That is the whole difference from invoke_sql_query, which fetches everything.
def read_sql_query(
    connection,
    query,
    parameter_values=None,
    enable_exception=False
):
    cursor = None

    try:
        logger.debug("Creating cursor")
        cursor = connection.cursor()

        logger.debug("Executing query")

        query, params = _prepare_query_and_params(query, parameter_values)
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        columns = [column[0] for column in cursor.description]
        row_count = 0

        # The cursor is iterated rather than fetchall()ed, so one row is in memory at a time.
        for row in cursor:
            yield dict(zip(columns, row, strict=True))
            row_count += 1

        logger.debug(f"Streamed {row_count} rows")

        # DB-API opens a transaction for a SELECT as well, the same way it does in
        # invoke_sql_query - but there the commit happens right after fetchall(), and here it
        # cannot happen until the last row has been handed over. A caller that abandons the
        # generator half way therefore leaves the transaction open, which is the price of
        # streaming rather than collecting.
        if not connection.autocommit:
            connection.commit()

    except Exception as e:
        if not connection.autocommit:
            connection.rollback()

        message = f"Query failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            # The counterpart of the contract's "return None": in a generator, returning is what
            # stops the iteration, so the caller's loop ends instead of running on as if the
            # query had worked.
            return None

    finally:
        if cursor is not None:
            cursor.close()
