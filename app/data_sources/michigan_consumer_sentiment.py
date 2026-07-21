import csv
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


MICHIGAN_ARCHIVE_URL = "https://data.sca.isr.umich.edu/data-archive/mine.php"
AGGREGATE_TABLE_ID = 1
COMPONENTS_TABLE_ID = 5


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
    with path.open(newline="", encoding="utf-8") as handle:
        return [line.rstrip("\r\n") for line in handle]


def _validate_month_value(month_val, line_num):
    try:
        month = int(month_val)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric Month at line {line_num}: {month_val!r}"
        ) from exc
    if month < 1 or month > 12:
        raise ValueError(f"csv has invalid month at line {line_num}: {month}")
    return month


def _validate_year_value(year_val, line_num):
    try:
        return int(year_val)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric Year at line {line_num}: {year_val!r}"
        ) from exc


def parse_aggregate_csv(csv_path):
    lines = _read_lines(csv_path)
    if not lines:
        raise ValueError("aggregate csv is empty")
    title_line = lines[0]
    if not title_line.startswith("Month,Year,Index"):
        raise ValueError(
            "aggregate csv missing required header 'Month,Year,Index': "
            f"got {title_line!r}"
        )
    rows = []
    seen_dates = set()
    for line_num, line in enumerate(lines[1:], start=2):
        parts = line.split(",")
        month_str = parts[0].strip()
        year_str = parts[1].strip()
        index_str = parts[2].strip()
        if not month_str:
            raise ValueError(f"aggregate csv has blank Month at line {line_num}")
        if not year_str:
            raise ValueError(f"aggregate csv has blank Year at line {line_num}")
        if not index_str:
            raise ValueError(f"aggregate csv has blank Index at line {line_num}")
        month = _validate_month_value(month_str, line_num)
        year = _validate_year_value(year_str, line_num)
        try:
            value = float(index_str)
        except ValueError as exc:
            raise ValueError(
                f"aggregate csv has non-numeric Index at line {line_num}: {index_str!r}"
            ) from exc
        date = f"{year:04d}-{month:02d}-01"
        if date in seen_dates:
            raise ValueError(
                f"aggregate csv has duplicate date at line {line_num}: {date}"
            )
        seen_dates.add(date)
        rows.append({"date": date, "value": value})
    return rows


def parse_components_csv(csv_path):
    lines = _read_lines(csv_path)
    if not lines:
        raise ValueError("components csv is empty")
    title_line = lines[0]
    if not title_line.startswith("Month,Year,Current Index,Expected Index"):
        raise ValueError(
            "components csv missing required header "
            "'Month,Year,Current Index,Expected Index': "
            f"got {title_line!r}"
        )
    rows = []
    seen_dates = set()
    for line_num, line in enumerate(lines[1:], start=2):
        parts = line.split(",")
        month_str = parts[0].strip()
        year_str = parts[1].strip()
        current_str = parts[2].strip()
        expected_str = parts[3].strip()
        if not month_str:
            raise ValueError(f"components csv has blank Month at line {line_num}")
        if not year_str:
            raise ValueError(f"components csv has blank Year at line {line_num}")
        if not current_str:
            raise ValueError(
                f"components csv has blank Current Index at line {line_num}"
            )
        if not expected_str:
            raise ValueError(
                f"components csv has blank Expected Index at line {line_num}"
            )
        month = _validate_month_value(month_str, line_num)
        year = _validate_year_value(year_str, line_num)
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
    return rows
