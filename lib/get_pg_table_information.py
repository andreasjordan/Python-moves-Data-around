import logging

import pandas as pd

from invoke_pg_query import invoke_pg_query

logger = logging.getLogger("lib." + __name__)


def _quote_identifier(name):
    return '"{}"'.format(name.lower().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


# DIFFERENCE: this is one of the three functions in lib/ that call another public lib/ function
# rather than a driver. The sibling does exactly that - Get-PgTableInformation is three
# Invoke-PgQuery calls - and dot-sourcing makes it free there, while here it needs an import.
def get_pg_table_information(
    connection,
    table=None,
    enable_exception=False
):
    try:
        # The sibling's -Table is [string[]], so it takes one name or many without the call site
        # saying which. One string is wrapped here so that both read the same.
        if isinstance(table, str):
            table = [table]

        if not table:
            logger.debug("Getting list of tables in current schema")

            # DIFFERENCE: the sibling asks for As = 'SingleValue' here and gets the whole column,
            # because PowerShell expands it into an array. as_type="single_value" returns the
            # first value of the first row and nothing else, so a column of names has to come
            # back as "list".
            #
            # The table type is spelled out rather than matched. The sibling writes
            # LIKE 'BASE_TABLE', which finds 'BASE TABLE' only because _ is a single-character
            # wildcard in LIKE - it reads like a typo that happens to work.
            rows = invoke_pg_query(
                connection=connection,
                query="""
                    SELECT table_name
                      FROM information_schema.tables
                     WHERE table_catalog = :database
                       AND table_schema = 'public'
                       AND table_type = 'BASE TABLE'
                """,
                as_type="list",
                parameter_values={"database": connection.info.dbname},
                enable_exception=True
            )
            table = sorted(row[0] for row in rows)

        information = []

        for name in table:
            # PostgreSQL folds unquoted identifiers to lower case and the tables of this
            # repository are created unquoted, so the catalog holds them lower cased. The sibling
            # calls .ToLower() here for the same reason.
            name = name.lower()
            logger.debug(f"Getting information about {name}")

            size = invoke_pg_query(
                connection=connection,
                query="SELECT pg_relation_size(quote_ident(:table))",
                as_type="single_value",
                parameter_values={"table": name},
                enable_exception=True
            )
            rows = invoke_pg_query(
                connection=connection,
                query=f"SELECT COUNT(*) FROM {_quote_table_name(name)}",
                as_type="single_value",
                enable_exception=True
            )

            # Bytes rather than pages or blocks: pg_relation_size answers in bytes, and inventing
            # a page count out of it would be arithmetic nobody asked for. The sibling names the
            # column Bytes for the same reason.
            information.append({"Table": name, "Bytes": int(size or 0), "Rows": int(rows or 0)})

        # DIFFERENCE: the sibling writes one [PSCustomObject] per table to the pipeline. A
        # DataFrame is the canonical shape for data in flight here, and it is also what a notebook
        # renders as a table without being asked.
        return pd.DataFrame(information)

    except Exception as e:
        message = f"Getting information failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            logger.error(message)
            return None
