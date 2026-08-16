"""Reproduces the Geodata numbers from AGENTS.md: countries.geojson is 14643643 bytes with 258
features, and PostGIS converts 258 of 258 with 0 invalid.

The Oracle read-back is DELIBERATELY NOT ASSERTED. SDO_UTIL.TO_WKTGEOMETRY fails with ORA-13199 for a
varying subset of the same 258 rows - seen at 26, 31, 39, 40, 42 and 64 - and that non-determinism is
documented in DIFFERENCES.md with four rejected explanations. This script prints the count and asserts
only that the import worked and that the failure is not total. Do not turn the printed number into an
expected value.

Needs SQL Server, PostgreSQL and Oracle running. Creates Verify_* tables and drops them again.

Takes several minutes: 258 geometries into Oracle one at a time, and Canada alone is 1.5 MB of JSON.
Pass --report-path to watch it while it runs.
"""

import argparse
import json

from verify_common import add_repository_paths, complete_verify, fact, line, start_verify

root = add_repository_paths()

from connect_ora_instance import connect_ora_instance  # noqa: E402
from connect_pg_instance import connect_pg_instance  # noqa: E402
from connect_sql_instance import connect_sql_instance  # noqa: E402
from import_gpx_file import import_gpx_file  # noqa: E402
from invoke_ora_query import invoke_ora_query  # noqa: E402
from invoke_pg_query import invoke_pg_query  # noqa: E402
from invoke_sql_query import invoke_sql_query  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--report-path")
args = parser.parse_args()

start_verify("Geodata", args.report_path)

sql_connection = connect_sql_instance(instance="127.0.0.1", database="Geodata",
                                      username="Geodata", password="Passw0rd!",
                                      enable_exception=True)
pg_connection = connect_pg_instance(instance="127.0.0.1", database="geodata",
                                    username="geodata", password="Passw0rd!",
                                    enable_exception=True)
ora_connection = connect_ora_instance(instance="127.0.0.1/XEPDB1", username="geodata",
                                      password="Passw0rd!", enable_exception=True)

###############################################################################
# GPX into SQL Server, through WKT
###############################################################################

tracks = import_gpx_file(str(root / "data" / "geodata" / "radrouten-berlin" / "*.gpx"))
fact("the Berlin GPX files parse into tracks", len(tracks) > 0, f"{len(tracks)} rows")

# A track with an empty WKT would satisfy every count below without carrying any geometry
with_wkt = int((tracks["wkt"].str.len() > 20).sum())
fact("every parsed track carries a WKT string", with_wkt == len(tracks), f"{with_wkt} of {len(tracks)}")

invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_berlin_tours",
                 enable_exception=True)
invoke_sql_query(connection=sql_connection, enable_exception=True, query=(
    "CREATE TABLE dbo.Verify_berlin_tours (type VARCHAR(10), name VARCHAR(250), geometry GEOMETRY)"))

try:
    for _, row in tracks.iterrows():
        invoke_sql_query(
            connection=sql_connection, enable_exception=True,
            query="INSERT INTO dbo.Verify_berlin_tours "
                  "VALUES (:type, :name, geometry::STGeomFromText(:wkt, 4326).MakeValid())",
            parameter_values={"type": row["type"], "name": row["name"], "wkt": row["wkt"]}
        )

    loaded = invoke_sql_query(
        connection=sql_connection, as_type="dict", enable_exception=True,
        query="SELECT name, geometry.STNumPoints() AS points FROM dbo.Verify_berlin_tours")
    fact("every track lands in SQL Server", len(loaded) == len(tracks),
         f"{len(loaded)} of {len(tracks)} rows")

    empty = [r for r in loaded if int(r["points"]) == 0]
    fact("no geometry landed empty", len(empty) == 0, f"{len(empty)} with 0 points")

    # Point counts against the source WKT, so that a geometry silently truncated on the way in is
    # caught. A row count would not notice it.
    source_points = {row["name"]: row["wkt"].count(",") + 1 for _, row in tracks.iterrows()}
    points_differ = sum(1 for r in loaded if int(r["points"]) != source_points[r["name"]])
    fact("point counts match the source WKT", points_differ == 0,
         f"{points_differ} of {len(loaded)} differ")
finally:
    invoke_sql_query(connection=sql_connection, query="DROP TABLE IF EXISTS dbo.Verify_berlin_tours",
                     enable_exception=True)

###############################################################################
# countries.geojson
###############################################################################

geojson_path = root / "data" / "geodata" / "countries.geojson"
size = geojson_path.stat().st_size
fact("countries.geojson is 14643643 bytes", size == 14643643, f"{size} bytes")

geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
features = geojson["features"]
fact("countries.geojson holds 258 features, the whole world and not only the EU",
     len(features) == 258, f"{len(features)} features")

###############################################################################
# PostGIS: 258 of 258, 0 invalid
###############################################################################

# separators=(",", ":") is not cosmetic, and the notebook passes it for the same reason.
# json.dumps defaults to ", " and ": ", which inflates a large coordinate array by about a
# third - and Oracle then rejects Indonesia with ORA-40441, a JSON syntax error raised inside
# SDO_UTIL.FROM_GEOJSON. Measured by leaving it out: 257 of 258 land and Indonesia does not.
# The compact form is what the sibling's ConvertTo-Json -Compress produces.

invoke_pg_query(connection=pg_connection, query="DROP TABLE IF EXISTS Verify_countries",
                enable_exception=True)
invoke_pg_query(connection=pg_connection, enable_exception=True, query=(
    "CREATE TABLE Verify_countries (name VARCHAR(50), iso CHAR(3), geometry GEOMETRY)"))

try:
    pg_failures = 0
    for feature in features:
        try:
            invoke_pg_query(
                connection=pg_connection, enable_exception=True,
                query="INSERT INTO Verify_countries VALUES (:name, :iso, "
                      "ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326)))",
                parameter_values={
                    "name": feature["properties"].get("name"),
                    "iso": feature["properties"].get("ISO3166-1-Alpha-3"),
                    "geometry": json.dumps(feature["geometry"], separators=(",", ":")),
                }
            )
        except Exception as e:
            pg_failures += 1
            line(f"      PostGIS refused [{feature['properties'].get('name')}]: {' '.join(str(e).split())}")

    fact("PostGIS converts 258 of 258", pg_failures == 0, f"{pg_failures} failed")

    pg_rows = invoke_pg_query(connection=pg_connection, as_type="single_value", enable_exception=True,
                              query="SELECT COUNT(*) FROM Verify_countries")
    fact("258 rows in PostGIS", pg_rows == 258, f"{pg_rows} rows")

    invalid = invoke_pg_query(connection=pg_connection, as_type="single_value", enable_exception=True,
                              query="SELECT COUNT(*) FROM Verify_countries WHERE NOT ST_IsValid(geometry)")
    fact("0 invalid geometries in PostGIS", invalid == 0, f"{invalid} invalid")

    # ST_IsValid is true for an empty geometry too, so without this the line above could pass over
    # 258 rows that hold nothing at all
    empty = invoke_pg_query(
        connection=pg_connection, as_type="single_value", enable_exception=True,
        query="SELECT COUNT(*) FROM Verify_countries WHERE ST_IsEmpty(geometry) OR ST_NPoints(geometry) = 0")
    fact("no PostGIS geometry is empty", empty == 0, f"{empty} empty")
finally:
    invoke_pg_query(connection=pg_connection, query="DROP TABLE IF EXISTS Verify_countries",
                    enable_exception=True)

###############################################################################
# Oracle: the import is deterministic, the read-back is not
###############################################################################


def drop_oracle_table_if_present():
    """Oracle has no DROP TABLE IF EXISTS, and swallowing the exception would also swallow a real
    failure - so the table is asked about first."""
    exists = invoke_ora_query(
        connection=ora_connection, as_type="single_value", enable_exception=True,
        query="SELECT COUNT(*) FROM user_tables WHERE table_name = 'VERIFY_COUNTRIES'")
    if exists:
        invoke_ora_query(connection=ora_connection, query="DROP TABLE Verify_countries",
                         enable_exception=True)


drop_oracle_table_if_present()
invoke_ora_query(connection=ora_connection, enable_exception=True, query=(
    "CREATE TABLE Verify_countries (name VARCHAR2(50), iso CHAR(3), geometry SDO_GEOMETRY)"))

try:
    line("      importing 258 geometries into Oracle, one at a time - this is the slow part")
    ora_failures = 0
    for feature in features:
        try:
            invoke_ora_query(
                connection=ora_connection, enable_exception=True,
                query="INSERT INTO Verify_countries VALUES (:name, :iso, SDO_UTIL.FROM_GEOJSON(:geometry))",
                parameter_values={
                    "name": feature["properties"].get("name"),
                    "iso": feature["properties"].get("ISO3166-1-Alpha-3"),
                    "geometry": json.dumps(feature["geometry"], separators=(",", ":")),
                }
            )
        except Exception as e:
            ora_failures += 1
            line(f"      Oracle refused [{feature['properties'].get('name')}]: {' '.join(str(e).split())}")

    fact("Oracle accepts 258 of 258 on the way in", ora_failures == 0, f"{ora_failures} failed")

    ora_rows = invoke_ora_query(connection=ora_connection, as_type="single_value",
                                enable_exception=True,
                                query="SELECT COUNT(*) FROM Verify_countries")
    fact("258 rows in Oracle", ora_rows == 258, f"{ora_rows} rows")

    # Row by row, because one failing row aborts a whole-table SELECT and the count is what we are
    # after. The number below is INFORMATION, not an expectation.
    wkt_ok = wkt_failures = 0
    for row_number in range(1, ora_rows + 1):
        try:
            invoke_ora_query(
                connection=ora_connection, as_type="single_value", enable_exception=True,
                query="SELECT SDO_UTIL.TO_WKTGEOMETRY(geometry) FROM "
                      "(SELECT ROWNUM AS rn, geometry FROM Verify_countries) WHERE rn = :rn",
                parameter_values={"rn": row_number})
            wkt_ok += 1
        except Exception:
            wkt_failures += 1

    line(f"      Oracle TO_WKTGEOMETRY: {wkt_ok} of 258 converted, {wkt_failures} failed with ORA-13199")
    line("      That count is non-deterministic on purpose - seen at 26, 31, 39, 40, 42 and 64 over")
    line("      the same 258 rows. Do not turn it into an expected value; see DIFFERENCES.md.")

    fact("Oracle converts at least some geometries back to WKT", wkt_ok > 0,
         f"{wkt_ok} of 258 - a total failure would be a regression, a partial one is documented")
finally:
    drop_oracle_table_if_present()

sql_connection.close()
pg_connection.close()
ora_connection.close()

complete_verify()
