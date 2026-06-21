import datetime
import pandas as pd
from pathlib import Path


def import_xls_timesheet(path):
    """Read Excel timesheets and return a clean DataFrame."""

    frames = []
    path = Path(path)

    for file in path.glob("*.xlsx"):
        print(f"📄 File: {file.name}")

        excel = pd.ExcelFile(file)

        for sheet_name in excel.sheet_names:
            print(f"   ↳ Sheet: {sheet_name}")

            input_frame = excel.parse(
                sheet_name=sheet_name,
                skiprows=2,
            )

            output_frame = input_frame.assign(
                Department=file.stem,
                Person=sheet_name,
                Start=input_frame["date"] + pd.to_timedelta(input_frame["time_from"].astype(str)),
                End=input_frame["date"] + pd.to_timedelta(input_frame["time_to"].astype(str)),
                Project=input_frame.get("project"),
                Task=input_frame.get("task"),
            )[["Department", "Person", "Start", "End", "Project", "Task"]]

            frames.append(output_frame)

    if not frames:
        return pd.DataFrame(
            columns=["Department", "Person", "Start", "End", "Project", "Task", "Hours"]
        )

    return pd.concat(frames, ignore_index=True)