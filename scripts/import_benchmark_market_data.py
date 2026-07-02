import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import benchmark_market_data
from app.db.benchmark_market_data import BENCHMARKS


DEFAULT_WORKBOOK_PATH = ROOT / "data" / "materials" / "Video 02" / "Bull_Bear_Markets.xlsx"


def _float_or_none(value):
    if value in (None, ""):
        return None
    return float(value)


def normalize_price_rows(raw_rows):
    return [
        {
            "date": str(row["date"]),
            "open": _float_or_none(row.get("open")),
            "high": _float_or_none(row.get("high")),
            "low": _float_or_none(row.get("low")),
            "close": float(row["close"]),
        }
        for row in raw_rows
        if row.get("date") and row.get("close") not in (None, "")
    ]


def parse_workbook_sheet(workbook_path, sheet_name):
    path = Path(workbook_path)
    if not path.exists():
        raise ValueError(f"workbook does not exist: {path}")
    workbook = openpyxl.load_workbook(path, data_only=False, read_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"workbook sheet is missing: {sheet_name}")
    sheet = workbook[sheet_name]
    raw_rows = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        if values[0] is None:
            continue
        if sheet_name == "S&P 500":
            date_value, open_value, high_value, low_value, close_value = values[:5]
        else:
            date_value = values[0]
            open_value = None
            high_value = values[1]
            low_value = None
            close_value = values[1]
        raw_rows.append(
            {
                "date": date_value.date().isoformat(),
                "open": open_value,
                "high": high_value if high_value is not None else close_value,
                "low": low_value,
                "close": close_value,
            }
        )
    return normalize_price_rows(reversed(raw_rows))


def import_price_rows(con, benchmark_id, rows, source):
    return benchmark_market_data.save_benchmark_prices(
        con,
        benchmark_id,
        rows,
        source=source,
    )


def import_workbook(con, workbook_path=DEFAULT_WORKBOOK_PATH):
    inserted = {}
    errors = {}
    source = Path(workbook_path).name
    for config in BENCHMARKS:
        try:
            rows = parse_workbook_sheet(workbook_path, config["sheet"])
            inserted[config["id"]] = import_price_rows(
                con,
                config["id"],
                rows,
                source=source,
            )
        except ValueError as exc:
            errors[config["id"]] = str(exc)
    return inserted, errors


def main():
    con = benchmark_market_data.connect()
    inserted, errors = import_workbook(con)
    for benchmark_id, count in inserted.items():
        print(f"{benchmark_id}: {count}")
    for benchmark_id, message in errors.items():
        print(f"ERROR {benchmark_id}: {message}", file=sys.stderr)


if __name__ == "__main__":
    main()
