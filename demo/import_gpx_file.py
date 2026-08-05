import xml.etree.ElementTree as ET
from glob import glob
from pathlib import Path

import pandas as pd


def _position(element):
    # A GPX point carries its position in two attributes, and WKT wants them as "lon lat"
    return f"{element.get('lon')} {element.get('lat')}"


def _name_of(element):
    # ElementTree hands over the text of a CDATA section like any other text, so the
    # '#cdata-section' special case that the sibling function needs has no counterpart here
    name = element.find("{*}name")
    return None if name is None else name.text


def import_gpx_file(path):
    """Read GPX files and return type, name and WKT geometry as a DataFrame."""

    rows = []

    # The path is a file pattern, not a directory, the same as the -Path of the sibling function
    for file in sorted(Path(name) for name in glob(path)):
        # These files come from two sources and use two different GPX namespaces - 1/1 and 1/0.
        # So every tag is matched with the "{*}" wildcard, which accepts any namespace. A fixed
        # namespace would find nothing in the 1/0 files and report no rows for them, without an
        # error. PowerShell never has to think about this: $gpx.trk ignores the namespace.
        root = ET.parse(file).getroot()

        tracks = root.findall("{*}trk")
        routes = root.findall("{*}rte")
        waypoints = root.findall("{*}wpt")

        print(f"📄 File: {file.name}")
        print(f"   ↳ {len(tracks)} tracks, {len(routes)} routes, {len(waypoints)} waypoints")

        for track in tracks:
            # A track is a list of segments, and each segment is a line. One segment is a
            # LINESTRING, several are a MULTILINESTRING.
            segments = []
            for segment in track.findall("{*}trkseg"):
                positions = [_position(point) for point in segment.findall("{*}trkpt")]
                if len(positions) > 1:
                    segments.append("(" + ", ".join(positions) + ")")

            if len(segments) > 1:
                wkt = "MULTILINESTRING (" + ", ".join(segments) + ")"
            elif len(segments) == 1:
                wkt = "LINESTRING " + segments[0]
            else:
                wkt = ""

            rows.append({"type": "Track", "name": _name_of(track), "wkt": wkt})

        for route in routes:
            positions = [_position(point) for point in route.findall("{*}rtept")]
            if len(positions) > 1:
                wkt = "LINESTRING (" + ", ".join(positions) + ")"
            else:
                wkt = ""

            rows.append({"type": "Route", "name": _name_of(route), "wkt": wkt})

        for waypoint in waypoints:
            rows.append({
                "type": "Waypoint",
                "name": _name_of(waypoint),
                "wkt": f"POINT ({_position(waypoint)})"
            })

    return pd.DataFrame(rows, columns=["type", "name", "wkt"])
