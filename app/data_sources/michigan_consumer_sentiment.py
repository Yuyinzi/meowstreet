from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


MICHIGAN_ARCHIVE_URL = "https://data.sca.isr.umich.edu/data-archive/mine.php"
AGGREGATE_TABLE_ID = 1
COMPONENTS_TABLE_ID = 5

TABLE_1_HEADER = "Month,Year,Index"
TABLE_5_HEADER = "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index"

_CURRENT_INDEX_OFFSET = 7
_EXPECTED_INDEX_OFFSET = 8


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


def _extract_by_index(parts, index, name, line_num):
    if index >= len(parts):
        raise ValueError(
            f"{name} column missing at line {line_num}: got {len(parts)} columns"
        )
    raw = parts[index].strip()
    if not raw:
        raise ValueError(f"csv has blank {name} at line {line_num}")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric {name} at line {line_num}: {raw!r}"
        ) from exc


def _parse_date(parts, line_num):
    month_str = parts[0].strip()
    year_str = parts[1].strip()
    if not month_str:
        raise ValueError(f"csv has blank Month at line {line_num}")
    if not year_str:
        raise ValueError(f"csv has blank Year at line {line_num}")
    try:
        month = int(month_str)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric Month at line {line_num}: {month_str!r}"
        ) from exc
    try:
        year = int(year_str)
    except ValueError as exc:
        raise ValueError(
            f"csv has non-numeric Year at line {line_num}: {year_str!r}"
        ) from exc
    if month < 1 or month > 12:
        raise ValueError(f"csv has invalid month at line {line_num}: {month}")
    return f"{year:04d}-{month:02d}-01"


def parse_aggregate_csv(csv_path):
    lines = _read_lines(csv_path)
    if len(lines) < 3:
        raise ValueError(
            f"aggregate csv has only {len(lines)} lines, expected title + header + data"
        )
    header = lines[1].rstrip(",")
    if not header.startswith(TABLE_1_HEADER):
        raise ValueError(
            f"aggregate csv missing required header {TABLE_1_HEADER!r}: got {header!r}"
        )
    rows = []
    seen_dates = set()
    for line_num, line in enumerate(lines[2:], start=3):
        parts = line.split(",")
        date = _parse_date(parts, line_num)
        if date in seen_dates:
            raise ValueError(
                f"aggregate csv has duplicate date at line {line_num}: {date}"
            )
        seen_dates.add(date)
        value = _extract_by_index(parts, 2, "Index", line_num)
        rows.append({"date": date, "value": value})
    return rows


def parse_components_csv(csv_path):
    lines = _read_lines(csv_path)
    if len(lines) < 3:
        raise ValueError(
            f"components csv has only {len(lines)} lines, expected title + header + data"
        )
    header = lines[1].rstrip(",")
    if not header.startswith(TABLE_5_HEADER):
        raise ValueError(
            f"components csv missing required header {TABLE_5_HEADER!r}: got {header!r}"
        )
    rows = []
    seen_dates = set()
    for line_num, line in enumerate(lines[2:], start=3):
        parts = line.split(",")
        date = _parse_date(parts, line_num)
        if date in seen_dates:
            raise ValueError(
                f"components csv has duplicate date at line {line_num}: {date}"
            )
        seen_dates.add(date)
        current = _extract_by_index(
            parts, _CURRENT_INDEX_OFFSET, "Current Index", line_num
        )
        expected = _extract_by_index(
            parts, _EXPECTED_INDEX_OFFSET, "Expected Index", line_num
        )
        rows.append(
            {
                "date": date,
                "current_conditions": current,
                "expectations": expected,
            }
        )
    return rows
