import logging

from invoke_pg_query import _prepare_query_and_params

logger = logging.getLogger("lib." + __name__)


# DIFFERENCE: the sibling writes one [PSCustomObject] per row to the pipeline and PowerShell
# streams it into whatever comes next. The Python counterpart of that is a generator, so this
# yields one dict per row. Two consequences the call site can see: nothing at all happens until
# the caller starts iterating, and a failure therefore surfaces on the first next() rather than
# on the call. That is the whole difference from invoke_pg_query, which fetches everything.
#
# CAVEAT: psycopg's normal cursor fetches the whole result before the first row comes out, so
# this streams from the caller's point of view but not from the server's - the same caveat
# get_pg_data_reader carries. A server-side cursor, connection.cursor(name=...), is what to reach
# for if a table ever stops fitting in memory.
def read_pg_query(
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

        columns = [column.name for column in cursor.description]
        row_count = 0

        # The cursor is iterated rather than fetchall()ed, so one row is in memory at a time.
        for row in cursor:
            yield dict(zip(columns, row, strict=True))
            row_count += 1

        logger.debug(f"Streamed {row_count} rows")

        # A read opens a transaction here too, and on PostgreSQL a connection left "idle in
        # transaction" keeps its locks - so the next TRUNCATE anywhere waits for it forever. In
        # invoke_pg_query the commit happens right after fetchall(); here it cannot happen until
        # the last row has been handed over, so a caller that abandons the generator half way
        # leaves that transaction open. On this provider that is worth knowing about, because
        # nothing else says why the TRUNCATE is hanging.
        if not connection.autocommit:
            connection.commit()

    except Exception as e:
        # PostgreSQL aborts the whole transaction when a single statement fails, so without this
        # every later query on the connection answers "current transaction is aborted, commands
        # ignored until end of transaction block" instead of naming the original mistake.
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
