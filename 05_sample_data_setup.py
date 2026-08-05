import json
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

data_path = Path(__file__).parent / "data" / "timesheets"

# TimeSheets
# Excel files will be generated from sample.json
print("Setting up Excel files for TimeSheets")

sample_data = json.loads((data_path / "sample.json").read_text(encoding="utf-8"))

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

    file = data_path / f"{department}.xlsx"
    workbook.save(file)
    print(f"Created {file.name} with {len(persons)} worksheets and {len(department_data)} rows")

print("Finished")
