import re

import oracledb
import pandas as pd


# DIFFERENCE: the same regex as in the two sibling functions, but the least work of the three.
# Oracle's own bind variable syntax is :name, so a query that already uses it is passed through
# untouched and only @name has to be renamed. pyodbc has to count positions and reorder the
# values, psycopg has to rewrite to %(name)s, and here the dictionary is handed over unchanged.
def _prepare_query_and_params(query, parameter_values):
    if parameter_values is None:
        return query, None

    if isinstance(parameter_values, dict):

        def _replace_named(match):
            name = match.group("name1") or match.group("name2")
            if name not in parameter_values:
                raise KeyError(f"Named parameter '{name}' not provided")
            return f":{name}"

        # The (?<!:) keeps a doubled colon out of it, the same way it does in the two sibling
        # functions - a cast written value::numeric would otherwise look like a parameter.
        query_with_placeholders = re.sub(
            r"(?:(?<!:):(?P<name1>[A-Za-z_][A-Za-z0-9_]*)|(?<!@)@(?P<name2>[A-Za-z_][A-Za-z0-9_]*))",
            _replace_named,
            query,
        )

        return query_with_placeholders, parameter_values

    if isinstance(parameter_values, (list, tuple)):
        return query, parameter_values

    raise TypeError("parameter_values must be a dict, list, or tuple")


# DIFFERENCE: the sibling takes a -Transaction and hands it to the command. In Python the
# transaction belongs to the connection, so there is nothing to hand over - the only question is
# who ends it. With commit=False this function neither commits nor rolls back, so several calls
# make up one unit of work and the caller commits the connection.
def invoke_ora_query(
    connection,
    query,
    as_type="DataFrame",  # DataFrame, dict, list, single_value
    parameter_values=None,
    commit=True,
    enable_exception=False
):
    cursor = None

    try:
        print("[VERBOSE] Creating cursor")
        cursor = connection.cursor()

        print("[VERBOSE] Executing query")

        query, params = _prepare_query_and_params(query, parameter_values)

        # A value longer than 4000 characters has to be declared as a CLOB, or Oracle answers
        # "ORA-01461: can bind a LONG value only for insert into a LONG column". The sibling has
        # the same guard, with the same limit. Note that this is the opposite of what the bulk
        # path wants: declaring a CLOB in write_ora_table costs 30x, and here it is the only way
        # the value gets in at all.
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

        # Only fetch result rows for queries that return columns
        if cursor.description:
            columns = [column.name for column in cursor.description]
            rows = cursor.fetchall()
            print(f"[VERBOSE] Retrieved {len(rows)} rows")

            # DB-API opens a transaction for a SELECT as well, and it stays open until it is
            # ended. Oracle does not take read locks, so this hurts even less than it does on
            # SQL Server, but the open transaction is the same and the two sibling functions
            # both end it, so this one does too.
            if commit and not connection.autocommit:
                connection.commit()

            if as_type == "list":
                return rows

            elif as_type == "dict":
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
                raise Exception(f"Unknown as_type '{as_type}', use DataFrame, dict, list or single_value")

        else:
            # Non-query SQL (DDL/DML) executed successfully
            if commit and not connection.autocommit:
                connection.commit()
            print(f"[VERBOSE] Non-query executed, rowcount={cursor.rowcount}")
            return None

    except Exception as e:
        # Oracle does not abort the surrounding transaction the way PostgreSQL does, so this is
        # not strictly needed here either - see the note in invoke_pg_query, which cannot do
        # without it.
        # With commit=False the transaction is not ours to end, so the caller rolls it back.
        if commit and not connection.autocommit:
            connection.rollback()

        message = f"Query failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None

    finally:
        if cursor is not None:
            cursor.close()
