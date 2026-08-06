import re

import pandas as pd


# DIFFERENCE: psycopg has real named parameters, written as %(name)s. So unlike the pyodbc
# version, which has to count positions and reorder the values, we only rewrite the names and
# hand the dictionary over unchanged.
def _prepare_query_and_params(query, parameter_values):
    if parameter_values is None:
        return query, None

    if isinstance(parameter_values, dict):

        def _replace_named(match):
            name = match.group("name1") or match.group("name2")
            if name not in parameter_values:
                raise KeyError(f"Named parameter '{name}' not provided")
            return f"%({name})s"

        # The (?<!:) keeps a doubled colon out of it. PostgreSQL writes value::numeric and
        # SQL Server writes geometry::STGeomFromText(...), and without this the second colon
        # looks exactly like a named parameter.
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
def invoke_pg_query(
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
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # Only fetch result rows for queries that return columns
        if cursor.description:
            columns = [column.name for column in cursor.description]
            rows = cursor.fetchall()
            print(f"[VERBOSE] Retrieved {len(rows)} rows")

            # DIFFERENCE: DB-API opens a transaction for a SELECT as well, and it stays open
            # until it is ended. A connection left "idle in transaction" keeps its locks, so the
            # next TRUNCATE anywhere - a second run of the notebook, the sibling demo - waits for
            # it forever. An ADO.NET command without an explicit transaction commits itself, so
            # the sibling never has to think about this.
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
        # PostgreSQL aborts the whole transaction when a single statement fails, so without this
        # the connection is unusable for everything that follows: every later query answers
        # "current transaction is aborted, commands ignored until end of transaction block".
        # import_pg_table and write_pg_table already roll back on failure; this one did not.
        # With commit=False the transaction is not ours to end, so the caller has to roll back -
        # and on PostgreSQL it really has to, because everything else on that connection fails
        # until it does.
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
