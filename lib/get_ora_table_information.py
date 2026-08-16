import logging

import pandas as pd

from invoke_ora_query import invoke_ora_query

logger = logging.getLogger("lib." + __name__)


# Oracle folds unquoted identifiers to UPPER CASE, the inverse of PostgreSQL, and the tables of
# this repository are created unquoted. So we upper case the name and quote it, which is what the
# data dictionary holds.
def _quote_identifier(name):
    return '"{}"'.format(name.upper().replace('"', '""'))


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split("."))


# DIFFERENCE: this is one of the three functions in lib/ that call another public lib/ function
# rather than a driver. The sibling does exactly that - Get-OraTableInformation is three
# Invoke-OraQuery calls - and dot-sourcing makes it free there, while here it needs an import.
def get_ora_table_information(
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
            rows = invoke_ora_query(
                connection=connection,
                query="SELECT table_name FROM user_tables",
                as_type="list",
                enable_exception=True
            )
            table = sorted(row[0] for row in rows)

        information = []

        for name in table:
            # user_segments holds the name as Oracle folded it, so a caller that passes "users"
            # has to be upper cased or the SUM finds nothing and the row reads Blocks = 0. This is
            # the mirror of the .lower() in get_pg_table_information.
            name = name.upper()
            logger.debug(f"Getting information about {name}")

            blocks = invoke_ora_query(
                connection=connection,
                query="SELECT NVL(SUM(blocks), 0) FROM user_segments WHERE segment_name = :segment_name",
                as_type="single_value",
                parameter_values={"segment_name": name},
                enable_exception=True
            )
            rows = invoke_ora_query(
                connection=connection,
                query=f"SELECT COUNT(*) FROM {_quote_table_name(name)}",
                as_type="single_value",
                enable_exception=True
            )

            # Blocks rather than pages or bytes: user_segments counts in Oracle blocks, and the
            # sibling names the column Blocks for the same reason. The three providers answer the
            # same question in three units, which is worth showing rather than normalising away.
            information.append({"Table": name, "Blocks": int(blocks or 0), "Rows": int(rows or 0)})

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
