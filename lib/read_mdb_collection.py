import pandas as pd


def read_mdb_collection(
    connection,
    collection,
    filter=None,  # noqa: A002 - the sibling parameter is -Filter, and the names are kept
    first=None,
    skip=None,
    project=None,
    sort=None,
    as_type="DataFrame",  # DataFrame, dict
    enable_exception=False
):
    try:
        print(f"[VERBOSE] Reading collection {collection}")

        # The filter, the projection and the sort are passed straight through. They are
        # dictionaries here and hashtables in the sibling, so a call site is almost the same:
        # -Filter @{ Location = 'Canada' } becomes filter={"Location": "Canada"}.
        cursor = connection[collection].find(filter or {}, project)

        if sort:
            cursor = cursor.sort(sort)

        if skip:
            cursor = cursor.skip(skip)

        if first:
            cursor = cursor.limit(first)

        documents = list(cursor)
        print(f"[VERBOSE] Retrieved {len(documents)} documents")

        if as_type == "dict":
            # A document already is a dict, so unlike the invoke_*_query functions there is
            # nothing to build here - this is what pymongo handed over.
            return documents

        elif as_type == "DataFrame":
            # Every document may have a different set of keys, and pandas fills the gaps with
            # NaN, exactly as it did when the XML rows were read in the first place.
            return pd.DataFrame(documents)

        else:
            raise Exception(f"Unknown as_type '{as_type}', use DataFrame or dict")

    except Exception as e:
        message = f"Reading collection failed: {str(e)}"
        if enable_exception:
            raise Exception(message)
        else:
            print(f"[ERROR] {message}")
            return None
