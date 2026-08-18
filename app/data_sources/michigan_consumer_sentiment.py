import calendar
import csv
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

from app.http_client import HttpClient


MICHIGAN_ARCHIVE_URL = "https://data.sca.isr.umich.edu/data-archive/mine.php"
MICHIGAN_FRONT_PAGE_URL = "https://www.sca.isr.umich.edu/"
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

_FRONT_PAGE_H1_RE = re.compile(
    r"^(Preliminary|Final)\s+Results\s+for\s+([A-Za-z]+)\s+(\d{4})$"
)

_MONTH_LOOKUP = {
    name.lower(): number
    for number in range(1, 13)
    for name in (calendar.month_name[number], calendar.month_abbr[number])
}

_FRONT_PAGE_ROW_LABELS = {
    "index of consumer sentiment": "sentiment",
    "current economic conditions": "current_conditions",
    "index of consumer expectations": "expectations",
}

_FRONT_PAGE_VALUE_KEYS = ["sentiment", "current_conditions", "expectations"]


class _FrontPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1_text = None
        self.rows = []
        self._in_h1 = False
        self._h1_parts = []
        self._in_front_table = False
        self._table_depth = 0
        self._current_row = None
        self._current_cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "h1" and self.h1_text is None and not self._in_h1:
            self._in_h1 = True
            self._h1_parts = []
        if tag == "table":
            if self._in_front_table:
                self._table_depth += 1
            elif dict(attrs).get("id") == "front_table":
                self._in_front_table = True
                self._table_depth = 0
        if self._in_front_table:
            if tag == "tr":
                self._current_row = []
            elif tag in ("td", "th") and self._current_row is not None:
                self._current_cell = []

    def handle_endtag(self, tag):
        if tag == "h1" and self._in_h1:
            self._in_h1 = False
            self.h1_text = " ".join("".join(self._h1_parts).split())
        if self._in_front_table:
            if tag in ("td", "th") and self._current_cell is not None:
                self._current_row.append("".join(self._current_cell).strip())
                self._current_cell = None
            elif tag == "tr" and self._current_row is not None:
                self.rows.append(self._current_row)
                self._current_row = None
            elif tag == "table":
                if self._table_depth == 0:
                    self._in_front_table = False
                else:
                    self._table_depth -= 1

    def handle_data(self, data):
        if self._in_h1:
            self._h1_parts.append(data)
        if self._current_cell is not None:
            self._current_cell.append(data)


def _month_number(name, context):
    number = _MONTH_LOOKUP.get(str(name).strip().lower())
    if number is None:
        raise ValueError(
            f"michigan front page {context} has unrecognized month: {name!r}"
        )
    return number


def _year_number(value, context):
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            f"michigan front page {context} has non-numeric year: {value!r}"
        ) from exc


def _header_cell(row, index, label):
    if len(row) <= index:
        raise ValueError(
            f"michigan front page {label} row has only {len(row)} cells, "
            f"expected at least {index + 1}"
        )
    return row[index]


def _numeric_cell(raw, row_label):
    text = str(raw).strip()
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"michigan front page row {row_label!r} value is not numeric: {text!r}"
        ) from exc


def _extract_column_values(data_rows, column_index):
    values = {}
    for row in data_rows:
        if not row:
            continue
        key = _FRONT_PAGE_ROW_LABELS.get(row[0].strip().lower())
        if key is None:
            continue
        values[key] = _numeric_cell(_header_cell(row, column_index, "data"), row[0])
    missing = [key for key in _FRONT_PAGE_VALUE_KEYS if key not in values]
    if missing:
        raise ValueError(
            f"michigan front page table is missing rows: {', '.join(missing)}"
        )
    return values


def _parse_front_page(html_text):
    parser = _FrontPageParser()
    parser.feed(html_text)
    parser.close()
    if parser.h1_text is None:
        raise ValueError("michigan front page is missing the release h1 heading")
    match = _FRONT_PAGE_H1_RE.match(parser.h1_text)
    if match is None:
        raise ValueError(
            f"michigan front page h1 has unexpected format: {parser.h1_text!r}"
        )
    release_kind = match.group(1).lower()
    release_month = _month_number(match.group(2), "h1")
    release_year = int(match.group(3))
    rows = parser.rows
    if not rows:
        raise ValueError("michigan front page is missing table#front_table")
    if len(rows) < 2:
        raise ValueError(
            f"michigan front page table has only {len(rows)} rows, "
            "expected 2 header rows and 3 index rows"
        )
    month_header, year_header = rows[0], rows[1]
    latest_month = _month_number(
        _header_cell(month_header, 1, "month header"), "latest column header"
    )
    latest_year = _year_number(
        _header_cell(year_header, 1, "year header"), "latest column header"
    )
    previous_month = _month_number(
        _header_cell(month_header, 2, "month header"), "previous column header"
    )
    previous_year = _year_number(
        _header_cell(year_header, 2, "year header"), "previous column header"
    )
    if latest_month != release_month or latest_year != release_year:
        raise ValueError(
            f"michigan front page latest column {calendar.month_name[latest_month]} "
            f"{latest_year} does not match h1 {match.group(2)} {release_year}"
        )
    data_rows = rows[2:]
    latest_values = _extract_column_values(data_rows, 1)
    previous_values = _extract_column_values(data_rows, 2)
    return {
        "release_kind": release_kind,
        "latest": {
            "date": f"{latest_year:04d}-{latest_month:02d}-01",
            **latest_values,
        },
        "previous": {
            "date": f"{previous_year:04d}-{previous_month:02d}-01",
            **previous_values,
        },
    }


def fetch_front_page_results(http_client=None):
    client = http_client or HttpClient()
    try:
        response = client.request("GET", MICHIGAN_FRONT_PAGE_URL, timeout=60)
    except httpx.HTTPError as exc:
        raise ValueError(f"failed to fetch michigan front page: {exc}") from exc
    html_text = response.content.decode("utf-8", errors="replace")
    return _parse_front_page(html_text)


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
