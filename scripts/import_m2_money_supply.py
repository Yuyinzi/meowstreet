import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import parse_fred_csv
from app.db import macro_indicators
from app.db import us_rates_liquidity

M2_SERIES_ID = "m2_money_stock"
FRED_M2_SERIES_ID = "M2SL"
DEFAULT_FRED_DIR = ROOT / "data" / "downloads" / "fred"
COMBINED_SOURCE = "historical reference data + FRED"


def _fred_series_payload():
    return {
        "series_id": M2_SERIES_ID,
        "title": "M2 Money Stock",
        "units": "billions_usd",
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


def build_fred_m2_payload(csv_path):
    rows = parse_fred_csv(csv_path, FRED_M2_SERIES_ID)
    return {
        "series": _fred_series_payload(),
        "points": _fred_points_payload(rows, csv_path),
    }


def import_fred_csvs(con, fred_dir=DEFAULT_FRED_DIR):
    payload = build_fred_m2_payload(Path(fred_dir) / f"{FRED_M2_SERIES_ID}.csv")
    saved = macro_indicators.merge_macro_indicator_points(
        con,
        payload["series"],
        payload["points"],
    )
    return {payload["series"]["series_id"]: saved["points"]}


def fetch_fred_csvs(fred_dir=DEFAULT_FRED_DIR):
    client = FredClient(fred_dir)
    return client.fetch_csvs([FRED_M2_SERIES_ID])


def _generate_interpretation(db_path):
    from scripts import generate_m2_ai_interpretation

    return generate_m2_ai_interpretation.main(["--db-path", str(db_path)])


def main(argv=None, generate_interpretation=_generate_interpretation):
    parser = argparse.ArgumentParser(
        description="Refresh M2 money supply from FRED"
    )
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--fred-dir", type=Path, default=DEFAULT_FRED_DIR)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch-fred-csv", action="store_true")
    mode.add_argument("--fred-csv-merge", action="store_true")
    parser.add_argument("--generate-interpretation", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch_fred_csv:
        fetched = fetch_fred_csvs(args.fred_dir)
        for series_id, path in fetched.items():
            print(f"{series_id}: {path}")
        return 0
    con = us_rates_liquidity.connect(args.db_path)
    try:
        inserted = import_fred_csvs(con, args.fred_dir)
    finally:
        con.close()
    for series_id, count in inserted.items():
        print(f"{series_id}: {count}")
    if args.generate_interpretation:
        return generate_interpretation(args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
