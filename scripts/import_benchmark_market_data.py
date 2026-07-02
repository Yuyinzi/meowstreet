import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import benchmark_market_data


DEFAULT_WORKBOOK_PATH = ROOT / "data" / "materials" / "Video 02" / "Bull_Bear_Markets.xlsx"
WORKBOOK_BENCHMARK_SHEETS = [
    {"benchmark_id": "us_sp500", "sheet": "S&P 500"},
    {"benchmark_id": "us_nasdaq_100", "sheet": "Nasdaq 100"},
    {"benchmark_id": "us_nasdaq_composite", "sheet": "Nasdaq Composite"},
    {"benchmark_id": "us_djia", "sheet": "DJIA"},
    {"benchmark_id": "europe_stoxx_50", "sheet": "Eurostoxx 50"},
    {"benchmark_id": "europe_stoxx_600", "sheet": "Eurostoxx 600"},
    {"benchmark_id": "uk_ftse_100", "sheet": "FTSE 100"},
    {"benchmark_id": "uk_ftse_250", "sheet": "FTSE 250"},
    {"benchmark_id": "uk_ftse_350", "sheet": "FTSE 350"},
    {"benchmark_id": "germany_dax_40", "sheet": "DAX 40"},
    {"benchmark_id": "hong_kong_hsi", "sheet": "HSI"},
    {"benchmark_id": "hong_kong_hscei", "sheet": "HSCEI"},
    {"benchmark_id": "japan_nikkei_225", "sheet": "Nikkei 225"},
    {"benchmark_id": "australia_asx_200", "sheet": "ASX 200"},
]


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
    source = Path(workbook_path).name
    for config in WORKBOOK_BENCHMARK_SHEETS:
        rows = parse_workbook_sheet(workbook_path, config["sheet"])
        inserted[config["benchmark_id"]] = import_price_rows(
            con,
            config["benchmark_id"],
            rows,
            source=source,
        )
    return inserted


def main():
    con = benchmark_market_data.connect()
    inserted = import_workbook(con)
    for benchmark_id, count in inserted.items():
        print(f"{benchmark_id}: {count}")


if __name__ == "__main__":
    main()
