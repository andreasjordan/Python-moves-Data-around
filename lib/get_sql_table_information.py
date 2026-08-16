import logging

import pandas as pd

from invoke_sql_query import invoke_sql_query

logger = logging.getLogger("lib." + __name__)

# Query might be wrong, please test and give feedback - the same note the sibling carries here.
_PAGES_QUERY = """
SELECT SUM(u.used_pages)
  FROM sys.tables AS t
     , sys.partitions AS p
     , sys.allocation_units AS u
 WHERE t.object_id = p.object_id
   AND p.hobt_id = u.container_id
   AND t.name = @name
   AND p.index_id <= 1
"""


def _quote_identifier(name):
    return f"[{name.replace(']', ']]')}]"


def _quote_table_name(table):
    return ".".join(_quote_identifier(part) for part in table.split('.'))


# DIFFERENCE: this is the first function in lib/ that calls another public lib/ function rather
# than a driver. The sibling does exactly that - Get-SqlTableInformation is three Invoke-SqlQuery
# calls - and dot-sourcing makes it free there, while here it needs an import. Reimplementing the
# queries against a raw cursor would have hidden the very thing the two files have in common.
def get_sql_table_information(
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
            # back as "list" - this is the first caller to notice that the two are not the same.
            rows = invoke_sql_query(
                connection=connection,
                query="SELECT name FROM sys.tables",
                as_type="list",
                enable_exception=True
            )
            table = sorted(row[0] for row in rows)

        information = []

        for name in table:
            logger.debug(f"Getting information about {name}")

            pages = invoke_sql_query(
                connection=connection,
                query=_PAGES_QUERY,
                as_type="single_value",
                parameter_values={"name": name},
                enable_exception=True
            )
            rows = invoke_sql_query(
                connection=connection,
                query=f"SELECT COUNT(*) FROM {_quote_table_name(name)}",
                as_type="single_value",
                enable_exception=True
            )

            # The SUM is NULL for a table that has no pages allocated yet, and the sibling casts
            # that to 0 by writing [int]$null. "or 0" is the same statement in Python.
            information.append({"Table": name, "Pages": int(pages or 0), "Rows": int(rows or 0)})

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
