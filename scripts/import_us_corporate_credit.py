import sys
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import parse_fred_csv
from app.db import us_rates_liquidity

DEFAULT_WORKBOOK_PATH = (
    ROOT / "data" / "materials" / "Video 05" / "Corporate_Bond_Indices.xlsm"
)
DEFAULT_FRED_DIR = DEFAULT_WORKBOOK_PATH.parent / "fred"
COMBINED_SOURCE = "P05 workbook + FRED"
DATA_SHEET_NAME = "Data - US Corp Yields"
ID_ROW = 1
DATA_START_ROW = 8

FRED_SERIES_MAP = {
    "BAMLC0A1CAAAEY": "aaa_corporate_yield",
    "BAMLC0A4CBBBEY": "bbb_corporate_yield",
    "BAMLH0A3HYCEY": "ccc_corporate_yield",
}

SERIES_TITLES = {
    "aaa_corporate_yield": "AAA Corporate Yield",
    "bbb_corporate_yield": "BBB Corporate Yield",
    "ccc_corporate_yield": "CCC Corporate Yield",
}


def _float_or_none(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip().upper() in ("#N/A", "", "NA", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_iso(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def _parse_date_cell(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        return value.strip()
    return None


def parse_workbook(workbook_path=DEFAULT_WORKBOOK_PATH):
    path = Path(workbook_path)
    if not path.exists():
        raise ValueError(f"workbook does not exist: {path}")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[DATA_SHEET_NAME]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    id_row = rows[ID_ROW - 1]
    series_columns = {}
    for col_index, cell_value in enumerate(id_row):
        if cell_value and str(cell_value).strip() in FRED_SERIES_MAP:
            fred_id = str(cell_value).strip()
            series_columns[col_index] = FRED_SERIES_MAP[fred_id]
    parsed = {}
    for col_index, series_id in series_columns.items():
        parsed[series_id] = {
            "series": {
                "series_id": series_id,
                "title": SERIES_TITLES[series_id],
                "units": "percent",
                "source": path.name,
            },
            "points": [],
        }
    for row in rows[DATA_START_ROW - 1 :]:
        for col_index, series_id in series_columns.items():
            date_val = _parse_date_cell(row[col_index])
            value_val = _float_or_none(row[col_index + 1])
            if date_val and value_val is not None:
                parsed[series_id]["points"].append(
                    {
                        "date": date_val,
                        "value": value_val,
                        "source": path.name,
                    }
                )
    for payload in parsed.values():
        payload["points"] = sorted(payload["points"], key=lambda p: p["date"])
    return parsed


def import_workbook(con, workbook_path=DEFAULT_WORKBOOK_PATH):
    parsed = parse_workbook(workbook_path)
    inserted = {}
    for series_id, payload in parsed.items():
        saved = us_rates_liquidity.replace_macro_indicator_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[series_id] = saved["points"]
    return inserted


def _fred_series_payload(fred_series_id):
    series_id = FRED_SERIES_MAP[fred_series_id]
    return {
        "series_id": series_id,
        "title": SERIES_TITLES[series_id],
        "units": "percent",
        "source": COMBINED_SOURCE,
    }


def _fred_points_payload(rows, csv_path):
    return [
        {
            "date": date_key,
            "value": value,
            "source": Path(csv_path).name,
        }
        for date_key, value in rows.items()
    ]


def build_fred_corporate_credit_payload(csv_path, fred_series_id):
    if fred_series_id not in FRED_SERIES_MAP:
        raise ValueError(
            f"fred corporate credit series is unsupported: {fred_series_id}"
        )
    rows = parse_fred_csv(csv_path, fred_series_id)
    return {
        "series": _fred_series_payload(fred_series_id),
        "points": _fred_points_payload(rows, csv_path),
    }


def fetch_fred_csvs(fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_SERIES_MAP)
    for fred_series_id in series_ids:
        if fred_series_id not in FRED_SERIES_MAP:
            raise ValueError(
                f"fred corporate credit series is unsupported: {fred_series_id}"
            )
    client = FredClient(fred_dir)
    return client.fetch_csvs(series_ids)


def import_fred_csvs(con, fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_SERIES_MAP)
    inserted = {}
    for fred_series_id in series_ids:
        payload = build_fred_corporate_credit_payload(
            Path(fred_dir) / f"{fred_series_id}.csv",
            fred_series_id,
        )
        saved = us_rates_liquidity.merge_macro_indicator_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[payload["series"]["series_id"]] = saved["points"]
    return inserted


def main():
    args = set(sys.argv[1:])
    con = us_rates_liquidity.connect()
    try:
        if "--fetch-fred-csv" in args:
            fetched = fetch_fred_csvs()
            for series_id, path in fetched.items():
                print(f"{series_id}: {path}")
            return
        if "--fred-csv-merge" in args:
            inserted = import_fred_csvs(con)
        else:
            inserted = import_workbook(con)
        for series_id, count in inserted.items():
            print(f"{series_id}: {count}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
