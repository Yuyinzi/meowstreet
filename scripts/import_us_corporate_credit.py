import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import parse_fred_csv
from app.db import macro_indicators
from app.db import us_rates_liquidity

DEFAULT_FRED_DIR = ROOT / "data" / "downloads" / "fred"
COMBINED_SOURCE = "historical reference data + FRED"

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
        saved = macro_indicators.merge_macro_indicator_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[payload["series"]["series_id"]] = saved["points"]
    return inserted


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import US corporate credit yields from FRED"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch-fred-csv", action="store_true")
    mode.add_argument("--fred-csv-merge", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch_fred_csv:
        fetched = fetch_fred_csvs()
        for series_id, path in fetched.items():
            print(f"{series_id}: {path}")
        return
    con = us_rates_liquidity.connect()
    try:
        inserted = import_fred_csvs(con)
        for series_id, count in inserted.items():
            print(f"{series_id}: {count}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
