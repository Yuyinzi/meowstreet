import csv
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


MICHIGAN_ARCHIVE_URL = "https://data.sca.isr.umich.edu/data-archive/mine.php"
AGGREGATE_TABLE_ID = 1
COMPONENTS_TABLE_ID = 5

_AGGREGATE_REQUIRED_COLUMNS = ["Month", "Year", "Index"]
_COMPONENTS_REQUIRED_COLUMNS = ["Month", "Year", "Current Index", "Expected Index"]
_REQUIRED_COLUMNS_BY_TABLE = {
    AGGREGATE_TABLE_ID: _AGGREGATE_REQUIRED_COLUMNS,
    COMPONENTS_TABLE_ID: _COMPONENTS_REQUIRED_COLUMNS,
}


class MichiganConsumerSentimentClient:
    def fetch_csv(self, destination_dir, table_id):
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / f"table_{table_id}.csv"
        data = _build_post_body(table_id).encode("utf-8")
        try:
            response = urlopen(MICHIGAN_ARCHIVE_URL, data=data, timeout=60)
            content = response.read().decode("utf-8-sig")
        except URLError as exc:
            raise ValueError(
                f"failed to fetch michigan table {table_id}: {exc}"
            ) from exc
        if not content.strip():
            raise ValueError(f"michigan table {table_id} returned empty response body")
        first_line = content.lstrip().split("\n")[0].rstrip("\r")
        if first_line.startswith("<"):
            raise ValueError(
                f"michigan table {table_id} returned non-csv response (starts with {first_line[:30]!r})"
            )
        expected = _REQUIRED_COLUMNS_BY_TABLE.get(table_id)
        if expected:
            header_cols = [c.strip() for c in first_line.split(",")]
            missing = [c for c in expected if c not in header_cols]
            if missing:
                raise ValueError(
                    f"michigan table {table_id} response missing required columns "
                    f"{missing}: got {first_line!r}"
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


def _open_csv(path):
    return Path(path).open(newline="", encoding="utf-8")


def _validate_month_value(month_val):
    try:
        month = int(month_val)
    except ValueError as exc:
        raise ValueError(f"csv has non-numeric Month: {month_val!r}") from exc
    if month < 1 or month > 12:
        raise ValueError(f"csv has invalid month: {month}")
    return month


def _validate_year_value(year_val):
    try:
        return int(year_val)
    except ValueError as exc:
        raise ValueError(f"csv has non-numeric Year: {year_val!r}") from exc


def _check_blank_value(value, column, line_num):
    if value is None or str(value).strip() == "":
        raise ValueError(f"csv has blank {column} at line {line_num}")
    return str(value).strip()


def _parse_row_date(row, line_num):
    month = _validate_month_value(row["Month"])
    year = _validate_year_value(row["Year"])
    return f"{year:04d}-{month:02d}-01"


def _check_required_columns(fieldnames, required, label, header_line):
    missing = [c for c in required if c not in (fieldnames or [])]
    if missing:
        raise ValueError(
            f"{label} csv missing required header columns {missing}: "
            f"got {header_line!r}"
        )


def parse_aggregate_csv(csv_path):
    with _open_csv(csv_path) as handle:
        first_line = handle.readline().rstrip("\r\n")
        if not first_line:
            raise ValueError("aggregate csv is empty")
        if first_line.lstrip().startswith("<"):
            raise ValueError("aggregate csv has non-csv content")
        fieldnames = first_line.split(",")
        _check_required_columns(
            fieldnames, _AGGREGATE_REQUIRED_COLUMNS, "aggregate", first_line
        )
        reader = csv.DictReader(handle, fieldnames=fieldnames)
        rows = []
        seen_dates = set()
        for line_num, row in enumerate(reader, start=2):
            month_str = _check_blank_value(row.get("Month"), "Month", line_num)
            year_str = _check_blank_value(row.get("Year"), "Year", line_num)
            index_str = _check_blank_value(row.get("Index"), "Index", line_num)
            month = _validate_month_value(month_str)
            year = _validate_year_value(year_str)
            try:
                value = float(index_str)
            except ValueError as exc:
                raise ValueError(
                    f"aggregate csv has non-numeric Index at line {line_num}: "
                    f"{index_str!r}"
                ) from exc
            date = f"{year:04d}-{month:02d}-01"
            if date in seen_dates:
                raise ValueError(
                    f"aggregate csv has duplicate date at line {line_num}: {date}"
                )
            seen_dates.add(date)
            rows.append({"date": date, "value": value})
    rows.sort(key=lambda r: r["date"])
    return rows


def parse_components_csv(csv_path):
    with _open_csv(csv_path) as handle:
        first_line = handle.readline().rstrip("\r\n")
        if not first_line:
            raise ValueError("components csv is empty")
        if first_line.lstrip().startswith("<"):
            raise ValueError("components csv has non-csv content")
        fieldnames = first_line.split(",")
        _check_required_columns(
            fieldnames,
            _COMPONENTS_REQUIRED_COLUMNS,
            "components",
            first_line,
        )
        reader = csv.DictReader(handle, fieldnames=fieldnames)
        rows = []
        seen_dates = set()
        for line_num, row in enumerate(reader, start=2):
            month_str = _check_blank_value(row.get("Month"), "Month", line_num)
            year_str = _check_blank_value(row.get("Year"), "Year", line_num)
            current_str = _check_blank_value(
                row.get("Current Index"), "Current Index", line_num
            )
            expected_str = _check_blank_value(
                row.get("Expected Index"), "Expected Index", line_num
            )
            month = _validate_month_value(month_str)
            year = _validate_year_value(year_str)
            try:
                current = float(current_str)
            except ValueError as exc:
                raise ValueError(
                    f"components csv has non-numeric Current Index at line {line_num}: "
                    f"{current_str!r}"
                ) from exc
            try:
                expected = float(expected_str)
            except ValueError as exc:
                raise ValueError(
                    f"components csv has non-numeric Expected Index at line {line_num}: "
                    f"{expected_str!r}"
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
                    "expectations": expected,
                }
            )
    rows.sort(key=lambda r: r["date"])
    return rows
