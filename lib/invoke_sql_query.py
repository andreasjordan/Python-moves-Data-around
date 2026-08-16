import logging
import re

import pandas as pd

logger = logging.getLogger("lib." + __name__)


# PROBLEM: pyodbc does not support named parameters, only positional "?" placeholders.
# SOLUTION: We can implement a simple pre-processing step to convert named parameters in the query
# RISK: This is a basic implementation and may not cover all edge cases (e.g. parameter names in string literals).
def _prepare_query_and_params(query, parameter_values):
    if parameter_values is None:
        return query, None

    if isinstance(parameter_values, dict):
        ordered_params = []

        def _replace_named(match):
            name = match.group("name1") or match.group("name2")
            if name not in parameter_values:
                raise KeyError(f"Named parameter '{name}' not provided")
            ordered_params.append(parameter_values[name])
            return "?"

        # The (?<!:) keeps a doubled colon out of it. SQL Server writes
        # geometry::STGeomFromText(...) and PostgreSQL writes value::numeric, and without this
        # the second colon looks exactly like a named parameter.
        query_with_placeholders = re.sub(
            r"(?:(?<!:):(?P<name1>[A-Za-z_][A-Za-z0-9_]*)|(?<!@)@(?P<name2>[A-Za-z_][A-Za-z0-9_]*))",
            _replace_named,
            query,
        )

        if ordered_params:
            return query_with_placeholders, ordered_params

        if "?" in query:
            raise ValueError(
                "Query uses '?' positional placeholders but parameter_values is a dict. "
                "Use named parameters like :name/@name, or pass a list/tuple of values."
            )

        return query, None

    if isinstance(parameter_values, (list, tuple)):
        return query, parameter_values

    raise TypeError("parameter_values must be a dict, list, or tuple")


# DIFFERENCE: the sibling takes a -Transaction and hands it to the command. In Python the
# transaction belongs to the connection, so there is nothing to hand over - the only question is
# who ends it. With commit=False this function neither commits nor rolls back, so several calls
# make up one unit of work and the caller commits the connection.
def invoke_sql_query(
    connection,
    query,
# TODO: Add query timeout support (pyodbc does not have built-in support, but we can
# implement it with a timer and connection cancellation)
#    query_timeout=600,
    as_type="DataFrame",  # DataFrame, dict, list, single_value
    parameter_values=None,
    commit=True,
    enable_exception=False
):
    cursor = None

    try:
        logger.debug("Creating cursor")
        cursor = connection.cursor()

#        # Timeout
#        cursor.timeout = query_timeout

        logger.debug("Executing query")

        query, params = _prepare_query_and_params(query, parameter_values)
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # DIFFERENCE: We need to check if the query returns rows (e.g. SELECT) or is a
        # non-query (e.g. INSERT/UPDATE/DDL)
        # Only fetch result rows for queries that return columns
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            logger.debug(f"Retrieved {len(rows)} rows")

            # DB-API opens a transaction for a SELECT as well, and it stays open until it is
            # ended. SQL Server releases the read locks at the end of the statement, so this is
            # far less painful than it is on PostgreSQL, but the open transaction is the same
            # and invoke_pg_query has to do it, so this does too.
            if commit and not connection.autocommit:
                connection.commit()

            if as_type == "list":
                return rows

            elif as_type == "dict":
                # Like PSObject (column -> value)
                result = []
                for row in rows:
                    result.append(dict(zip(columns, row, strict=True)))
                return result

            elif as_type == "DataFrame":
                return pd.DataFrame.from_records(rows, columns=columns)

            elif as_type == "single_value":
                if rows:
                    return rows[0][0]
                return None

            else:
                # The counterpart of the [ValidateSet] on the -As parameter of the sibling function.
                # Without this, a typo would silently return a different type than the caller expects.
                raise Exception(f"Unknown as_type '{as_type}', use DataFrame, dict, list or single_value")

        else:
            # Non-query SQL (DDL/DML) executed successfully
            if commit and not connection.autocommit:
                connection.commit()
            logger.debug(f"Non-query executed, rowcount={cursor.rowcount}")
            return None

    except Exception as e:
        # SQL Server does not abort the surrounding transaction the way PostgreSQL does, so this
        # is not strictly needed here - but a failed statement should not leave anything behind,
        # and invoke_pg_query cannot do without it, so the three functions stay siblings.
        # With commit=False the transaction is not ours to end, so the caller rolls it back.
        if commit and not connection.autocommit:
            connection.rollback()

        message = f"Query failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None

    finally:
        if cursor is not None:
            cursor.close()
