import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from scripts import import_benchmark_market_data


DEFAULT_CSV_PATH = ROOT / "data" / "materials" / "Video 04" / "US_P4_Macro_Indicators.csv"
SERIES_CONFIG = {
    "cpi_yoy": {"title": "CPI YoY", "units": "percent"},
    "vix": {"title": "VIX", "units": "index"},
    "sp500_pe": {"title": "S&P 500 PE Ratio", "units": "multiple"},
}


def _series_payload(series_id, csv_path):
    config = SERIES_CONFIG[series_id]
    return {
        "series_id": series_id,
        "title": config["title"],
        "units": config["units"],
        "source": Path(csv_path).name,
    }


def _point_payload(row, series_id, csv_path):
    return {
        "date": row["date"],
        "value": import_benchmark_market_data.float_or_none(row.get(series_id)),
        "source": Path(csv_path).name,
    }


def parse_csv(csv_path=DEFAULT_CSV_PATH):
    path = Path(csv_path)
    if not path.exists():
        raise ValueError(f"csv does not exist: {path}")
    parsed = {
        series_id: {"series": _series_payload(series_id, path), "points": []}
        for series_id in SERIES_CONFIG
    }
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("date"):
                continue
            for series_id in SERIES_CONFIG:
                point = _point_payload(row, series_id, path)
                if point["value"] is None:
                    continue
                parsed[series_id]["points"].append(point)
    for payload in parsed.values():
        payload["points"] = sorted(payload["points"], key=lambda point: point["date"])
    return parsed


def import_csv(con, csv_path=DEFAULT_CSV_PATH):
    parsed = parse_csv(csv_path)
    inserted = {}
    for series_id, payload in parsed.items():
        saved = us_rates_liquidity.replace_macro_indicator_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[series_id] = saved["points"]
    return inserted


def main():
    con = us_rates_liquidity.connect()
    try:
        inserted = import_csv(con)
        for series_id, count in inserted.items():
            print(f"{series_id}: {count}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
