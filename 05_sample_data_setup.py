import json
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

timesheets_path = Path(__file__).parent / "data" / "timesheets"
stackexchange_path = Path(__file__).parent / "data" / "stackexchange"
geodata_path = Path(__file__).parent / "data" / "geodata"

# TimeSheets
# Excel files will be generated from sample.json
print("Setting up Excel files for TimeSheets")

sample_data = json.loads((timesheets_path / "sample.json").read_text(encoding="utf-8"))

# One workbook per department, one worksheet per person inside it
departments = sorted({row["Department"] for row in sample_data})

for department in departments:
    department_data = [row for row in sample_data if row["Department"] == department]
    persons = sorted({row["Person"] for row in department_data})

    workbook = Workbook()
    workbook.remove(workbook.active)

    for person in persons:
        person_data = [row for row in department_data if row["Person"] == person]
        worksheet = workbook.create_sheet(title=person)

        # The note that the employees are supposed to read
        worksheet["A1"] = "Please fill out this form weekly and send it to HR. Thanks!"
        worksheet["A1"].font = Font(size=14, bold=True)

        # The header row - the importer skips the first two rows and reads this one
        for column, header in enumerate(["date", "time_from", "time_to", "project", "task"], start=1):
            cell = worksheet.cell(row=3, column=column, value=header)
            cell.font = Font(bold=True)
            if column <= 3:
                cell.alignment = Alignment(horizontal="right")

        # One row per booking, starting right below the header
        for index, row in enumerate(person_data, start=4):
            start = datetime.fromisoformat(row["Start"])
            end = datetime.fromisoformat(row["End"])

            worksheet.cell(row=index, column=1, value=start.date()).number_format = "dd.mm.yyyy"
            worksheet.cell(row=index, column=2, value=start.time()).number_format = "HH:mm"
            worksheet.cell(row=index, column=3, value=end.time()).number_format = "HH:mm"
            worksheet.cell(row=index, column=4, value=row["Project"])
            worksheet.cell(row=index, column=5, value=row["Task"])

        # Make the columns wide enough to read
        for column, width in {"A": 12, "B": 12, "C": 12, "D": 20, "E": 20}.items():
            worksheet.column_dimensions[column].width = width

    file = timesheets_path / f"{department}.xlsx"
    workbook.save(file)
    print(f"Created {file.name} with {len(persons)} worksheets and {len(department_data)} rows")


# StackExchange
# XML files will be downloaded from archive.org/download/stackexchange
site = "dba.meta"
archive = stackexchange_path / "tmp.7z"

print(f"Downloading StackExchange data for {site}")

url = f"https://archive.org/download/stackexchange/{site}.stackexchange.com.7z"
with urllib.request.urlopen(url) as response, archive.open("wb") as file:
    shutil.copyfileobj(response, file)

print(f"Downloaded {archive.name} with {archive.stat().st_size / 1024 / 1024:.1f} MB")

# 7za is installed by 02_wsl2_setup.sh, the same way the sibling repository uses it.
# "e" extracts all files of the archive into the working directory.
subprocess.run(["7za", "e", "-y", archive.name], cwd=stackexchange_path, check=True, capture_output=True)

archive.unlink()

for file in sorted(stackexchange_path.glob("*.xml")):
    print(f"Created {file.name} with {file.stat().st_size / 1024 / 1024:.1f} MB")


# Geodata
# GPX files will be downloaded from https://www.berlin.de/sen/uvk/mobilitaet-und-verkehr/verkehrsplanung/radverkehr/radverkehrsnetz/radrouten/gpx/
# One GPX file will be downloaded from https://www.michael-mueller-verlag.de/de/reisefuehrer/deutschland/berlin-city/gps-daten/
# GeoJSON file will be downloaded from datahub.io/core/geo-countries
radrouten_path = geodata_path / "radrouten-berlin"

# Start from a clean directory, so a renamed file in the archive does not linger
for file in list(geodata_path.glob("*.gpx")) + list(geodata_path.glob("*.geojson")):
    file.unlink()
if radrouten_path.exists():
    shutil.rmtree(radrouten_path)
radrouten_path.mkdir()

print("Downloading GPX data from berlin.de")

archive = radrouten_path / "tmp.7z"
with urllib.request.urlopen(
    "https://www.berlin.de/sen/uvk/_assets/verkehr/verkehrsplanung/radverkehr/radrouten/radrouten_komplett.7z"
) as response, archive.open("wb") as file:
    shutil.copyfileobj(response, file)

subprocess.run(["7za", "e", "-y", archive.name], cwd=radrouten_path, check=True, capture_output=True)

archive.unlink()

print(f"Created radrouten-berlin with {len(list(radrouten_path.glob('*.gpx')))} GPX files")

print("Downloading GPX data from michael-mueller-verlag.de")

single_gpx = geodata_path / "michael-mueller-verlag-berlin.gpx"
with urllib.request.urlopen("https://mmv.me/52630/00.gpx") as response, single_gpx.open("wb") as file:
    shutil.copyfileobj(response, file)

print(f"Created {single_gpx.name} with {single_gpx.stat().st_size / 1024:.0f} KB")

print("Downloading GeoJSON data from datahub.io")

countries = geodata_path / "countries.geojson"
with urllib.request.urlopen("https://datahub.io/core/geo-countries/r/0.geojson") as response, countries.open("wb") as file:
    shutil.copyfileobj(response, file)

print(f"Created {countries.name} with {countries.stat().st_size / 1024 / 1024:.1f} MB")

print("Finished")
