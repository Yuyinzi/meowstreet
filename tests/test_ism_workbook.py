from datetime import datetime

import pytest
from openpyxl import Workbook

from app.tools import ism_workbook


def test_parse_series_workbook_reads_configured_sheet(tmp_path):
    path = tmp_path / "survey.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Activity"
    sheet.append(["Date", "Activity"])
    sheet.append([datetime(2026, 5, 1), 54.2])
    workbook.save(path)

    result = ism_workbook.parse_series_workbook(
        path,
        "ism services",
        {
            "ism_services_business_activity": {
                "sheet": "Activity",
                "title": "ISM Services Business Activity",
                "units": "index",
            }
        },
    )

    assert result[0]["points"] == [
        {"date": "2026-05-01", "value": 54.2, "source": "survey.xlsx"}
    ]


def test_parse_series_workbook_rejects_missing_sheet(tmp_path):
    path = tmp_path / "survey.xlsx"
    Workbook().save(path)

    with pytest.raises(ValueError, match="ism services sheet is missing: Activity"):
        ism_workbook.parse_series_workbook(
            path,
            "ism services",
            {"activity": {"sheet": "Activity", "title": "Activity", "units": "index"}},
        )
