import re
import pyodbc
import pandas as pd


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

        query_with_placeholders = re.sub(
            r"(?:\:(?P<name1>[A-Za-z_][A-Za-z0-9_]*)|(?<!@)@(?P<name2>[A-Za-z_][A-Za-z0-9_]*))",
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


def invoke_sql_query(
    connection,
    query,
# TODO: Add query timeout support (pyodbc does not have built-in support, but we can implement it with a timer and connection cancellation)
#    query_timeout=600,
    as_type="DataFrame",  # DataFrame, dict, list, single_value
    parameter_values=None,
    enable_exception=False
):
    try:
        print("[VERBOSE] Creating cursor")
        cursor = connection.cursor()

#        # Timeout
#        cursor.timeout = query_timeout

        print("[VERBOSE] Executing query")

        query, params = _prepare_query_and_params(query, parameter_values)
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # DIFFERENCE: We need to check if the query returns rows (e.g. SELECT) or is a non-query (e.g. INSERT/UPDATE/DDL)
        # Only fetch result rows for queries that return columns
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            print(f"[VERBOSE] Retrieved {len(rows)} rows")

            if as_type == "list":
                return rows

            elif as_type == "dict":
                # Like PSObject (column -> value)
                result = []
                for row in rows:
                    result.append(dict(zip(columns, row)))
                return result

            elif as_type == "DataFrame":
                return pd.DataFrame.from_records(rows, columns=columns)

            elif as_type == "single_value":
                if rows:
                    return rows[0][0]
                return None

            else:
                return rows

        else:
            # Non-query SQL (DDL/DML) executed successfully
            if not connection.autocommit:
                connection.commit()
            print(f"[VERBOSE] Non-query executed, rowcount={cursor.rowcount}")
            return None
        
    except Exception as e:
        message = f"Query failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
