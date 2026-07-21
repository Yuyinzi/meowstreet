from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook


@dataclass(frozen=True)
class RankingLayout:
    sheet: str
    header_row: int
    data_row: int
    industry_column: int
    first_status_column: int


def iso_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def is_date(value):
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def parse_series_workbook(workbook_path, survey_label, series_config):
    path = Path(workbook_path)
    if not path.exists():
        raise ValueError(f"{survey_label} workbook is missing: {path}")
    workbook = load_workbook(path, read_only=True, data_only=True)
    results = []
    for series_id, config in series_config.items():
        sheet_name = config["sheet"]
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"{survey_label} sheet is missing: {sheet_name}")
        sheet = workbook[sheet_name]
        points = [
            {
                "date": iso_date(date_value),
                "value": float(level_value),
                "source": path.name,
            }
            for date_value, level_value in sheet.iter_rows(
                min_row=2, min_col=1, max_col=2, values_only=True
            )
            if is_date(date_value) and level_value not in (None, "")
        ]
        results.append(
            {
                "series": {
                    "series_id": series_id,
                    "title": config["title"],
                    "units": config["units"],
                    "source": path.name,
                },
                "points": points,
            }
        )
    return results


def _direction(value):
    values = {"Growth": "growth", "Contraction": "contraction", "Neutral": "neutral"}
    return values.get(value)


def parse_ranking_workbook(workbook_path, survey_type, survey_label, layout):
    path = Path(workbook_path)
    if not path.exists():
        raise ValueError(f"{survey_label} workbook is missing: {path}")
    workbook = load_workbook(path, read_only=True, data_only=True)
    if layout.sheet not in workbook.sheetnames:
        raise ValueError(f"{survey_label} sheet is missing: {layout.sheet}")
    sheet = workbook[layout.sheet]
    month_columns = [
        (column, iso_date(sheet.cell(layout.header_row, column).value))
        for column in range(layout.first_status_column, sheet.max_column + 1, 2)
        if is_date(sheet.cell(layout.header_row, column).value)
    ]
    rows = []
    seen = set()
    for row_index in range(layout.data_row, sheet.max_row + 1):
        industry = sheet.cell(row_index, layout.industry_column).value
        if not industry:
            continue
        for status_column, month in month_columns:
            direction = _direction(sheet.cell(row_index, status_column).value)
            rank = sheet.cell(row_index, status_column + 1).value
            key = (survey_type, month, str(industry))
            if direction is None or rank in (None, "") or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "survey_type": survey_type,
                    "date": month,
                    "industry": str(industry),
                    "direction": direction,
                    "rank": int(rank),
                    "source": path.name,
                }
            )
    return rows
