import logging

import oracledb

from invoke_ora_query import _prepare_query_and_params

logger = logging.getLogger("lib." + __name__)


# Oracle folds unquoted identifiers to UPPER CASE, the inverse of PostgreSQL, and the tables of
# this repository are created unquoted. So we upper case the name and quote it, which is what
# the data dictionary holds.
def _quote_identifier(name):
    return '"{}"'.format(name.upper().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


def get_ora_data_reader(
    connection,
    table=None,
    query=None,
    parameter_values=None,
    enable_exception=False
):
    cursor = None

    try:
        if table:
            query = f"SELECT * FROM {_quote_table_name(table)}"

        if not query:
            raise Exception("Neither table nor query is used, so there is nothing to read")

        logger.debug(f"Getting data reader for [{query}]")

        # DIFFERENCE: the sibling returns an OracleDataReader and disposes the command that
        # created it. Here the cursor is both, so it is returned as it is - and whoever writes
        # it into a table closes it, exactly as Write-OraTable disposes the reader it was handed.
        query, params = _prepare_query_and_params(query, parameter_values)

        cursor = connection.cursor()

        # A long string parameter has to be declared as a CLOB, the same guard invoke_ora_query and
        # read_ora_query carry - Get-OraDataReader has it too, and this file was the one place in the
        # family without it. The limit is 4000 characters because that is where a VARCHAR2 bind stops;
        # what it prevents here is ORA-01460 "unimplemented or unreasonable conversion requested",
        # measured from about 250000 characters, while invoke_ora_query took the same value at 1.27 MB.
        # The error the sibling names is ORA-01461, which is what the .NET provider raises instead.
        if isinstance(params, dict):
            long_parameters = {
                name: oracledb.DB_TYPE_CLOB
                for name, value in params.items()
                if isinstance(value, str) and len(value) > 4000
            }
            if long_parameters:
                cursor.setinputsizes(**long_parameters)

        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        logger.debug(f"Returning data reader with {len(cursor.description)} columns")
        return cursor

    except Exception as e:
        if cursor is not None:
            cursor.close()

        message = f"Getting data reader failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
