import csv
from pathlib import Path

import httpx

from app.http_client import HttpClient


MICHIGAN_ARCHIVE_URL = "https://data.sca.isr.umich.edu/data-archive/mine.php"
AGGREGATE_TABLE_ID = 1
COMPONENTS_TABLE_ID = 5

TABLE_1_HEADER = "Month,Year,Index"
TABLE_5_HEADER = "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index"

_AGGREGATE_REQUIRED_COLUMNS = ["Month", "Year", "Index"]
_COMPONENTS_REQUIRED_COLUMNS = ["Month", "Year", "Current Index", "Expected Index"]
_REQUIRED_COLUMNS_BY_TABLE = {
    AGGREGATE_TABLE_ID: _AGGREGATE_REQUIRED_COLUMNS,
    COMPONENTS_TABLE_ID: _COMPONENTS_REQUIRED_COLUMNS,
}


class MichiganConsumerSentimentClient:
    def __init__(self, http_client=None):
        self._http_client = http_client

    def fetch_csv(self, destination_dir, table_id):
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / f"table_{table_id}.csv"
        data = _build_post_body(table_id)
        try:
            client = self._http_client or HttpClient()
            response = client.request(
                "POST", MICHIGAN_ARCHIVE_URL, data=data, timeout=60
            )
            content = response.content.decode("utf-8-sig")
        except httpx.HTTPError as exc:
            raise ValueError(
                f"failed to fetch michigan table {table_id}: {exc}"
            ) from exc
        if not content.strip():
            raise ValueError(f"michigan table {table_id} returned empty response body")
        lines = content.splitlines()
        if lines[0].lstrip().startswith("<"):
            raise ValueError(
                f"michigan table {table_id} returned non-csv response "
                f"(starts with {lines[0][:30]!r})"
            )
        required = _REQUIRED_COLUMNS_BY_TABLE.get(table_id)
        if required:
            _find_header_index(
                lines,
                required,
                f"michigan table {table_id} response missing required columns",
            )
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def fetch_csvs(self, destination_dir):
        return {
            AGGREGATE_TABLE_ID: self.fetch_csv(destination_dir, AGGREGATE_TABLE_ID),
            COMPONENTS_TABLE_ID: self.fetch_csv(destination_dir, COMPONENTS_TABLE_ID),
        }


def _build_post_body(table_id):
    return (
        f"table={table_id}&year=1978&qorm=M&order=asc"
        f"&format=Comma-Separated%20%28CSV%29"
    )


def _read_lines(csv_path):
    path = Path(csv_path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [line.rstrip("\r\n") for line in handle]


def _find_header_index(lines, required, error_prefix):
    for index, line in enumerate(lines[:2]):
        columns = [column.strip() for column in next(csv.reader([line]))]
        if all(column in columns for column in required):
            return index
    received = lines[:2]
    raise ValueError(f"{error_prefix}: got {received!r}")


def _validate_month_value(value, line_num):
    try:
        month = int(value)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric Month at line {line_num}: {value!r}"
        ) from exc
    if month < 1 or month > 12:
        raise ValueError(f"csv has invalid month at line {line_num}: {month}")
    return month


def _validate_year_value(value, line_num):
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric Year at line {line_num}: {value!r}"
        ) from exc


def _required_value(row, column, line_num):
    value = row.get(column)
    if value is None or not str(value).strip():
        raise ValueError(f"csv has blank {column} at line {line_num}")
    return str(value).strip()


def _parse_rows(csv_path, required, label):
    lines = _read_lines(csv_path)
    if not lines:
        raise ValueError(f"{label} csv is empty")
    if lines[0].lstrip().startswith("<"):
        raise ValueError(f"{label} csv has non-csv content")
    if len(lines) < 2:
        raise ValueError(
            f"{label} csv has only {len(lines)} lines, expected header and data"
        )
    header_index = _find_header_index(
        lines, required, f"{label} csv missing required header"
    )
    fieldnames = next(csv.reader([lines[header_index]]))
    reader = csv.DictReader(lines[header_index + 1 :], fieldnames=fieldnames)
    return reader, header_index + 2


def parse_aggregate_csv(csv_path):
    reader, first_line_num = _parse_rows(
        csv_path, _AGGREGATE_REQUIRED_COLUMNS, "aggregate"
    )
    rows = []
    seen_dates = set()
    for line_num, row in enumerate(reader, start=first_line_num):
        month_value = _required_value(row, "Month", line_num)
        year_value = _required_value(row, "Year", line_num)
        index_value = _required_value(row, "Index", line_num)
        month = _validate_month_value(month_value, line_num)
        year = _validate_year_value(year_value, line_num)
        try:
            value = float(index_value)
        except ValueError as exc:
            raise ValueError(
                f"csv has non-numeric Index at line {line_num}: {index_value!r}"
            ) from exc
        date = f"{year:04d}-{month:02d}-01"
        if date in seen_dates:
            raise ValueError(
                f"aggregate csv has duplicate date at line {line_num}: {date}"
            )
        seen_dates.add(date)
        rows.append({"date": date, "value": value})
    rows.sort(key=lambda row: row["date"])
    return rows


def parse_components_csv(csv_path):
    reader, first_line_num = _parse_rows(
        csv_path, _COMPONENTS_REQUIRED_COLUMNS, "components"
    )
    rows = []
    seen_dates = set()
    for line_num, row in enumerate(reader, start=first_line_num):
        month_value = _required_value(row, "Month", line_num)
        year_value = _required_value(row, "Year", line_num)
        current_value = _required_value(row, "Current Index", line_num)
        expectations_value = _required_value(row, "Expected Index", line_num)
        month = _validate_month_value(month_value, line_num)
        year = _validate_year_value(year_value, line_num)
        try:
            current = float(current_value)
        except ValueError as exc:
            raise ValueError(
                f"csv has non-numeric Current Index at line {line_num}: "
                f"{current_value!r}"
            ) from exc
        try:
            expectations = float(expectations_value)
        except ValueError as exc:
            raise ValueError(
                f"csv has non-numeric Expected Index at line {line_num}: "
                f"{expectations_value!r}"
            ) from exc
        date = f"{year:04d}-{month:02d}-01"
        if date in seen_dates:
            raise ValueError(
                f"components csv has duplicate date at line {line_num}: {date}"
            )
        seen_dates.add(date)
        rows.append(
            {
                "date": date,
                "current_conditions": current,
                "expectations": expectations,
            }
        )
    rows.sort(key=lambda row: row["date"])
    return rows
