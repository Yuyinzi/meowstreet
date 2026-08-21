import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import parse_fred_csv
from app.data_sources.fred import resample_to_weekly_sundays
from app.db import us_rates_liquidity


DEFAULT_FRED_DIR = ROOT / "data" / "downloads" / "fred"
FRED_SOURCE_SHEET = "FRED weekly Sunday resample"
RATE_SERIES_CONFIG = {
    "Fed Funds": {
        "series_id": "fed_funds",
        "title": "Fed Funds",
        "instrument_type": "policy_rate",
        "maturity_months": None,
    },
    "1mo": {
        "series_id": "treasury_1m",
        "title": "1-Month Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 1,
    },
    "3mo": {
        "series_id": "treasury_3m",
        "title": "3-Month Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 3,
    },
    "6mo": {
        "series_id": "treasury_6m",
        "title": "6-Month Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 6,
    },
    "1yr": {
        "series_id": "treasury_1y",
        "title": "1-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 12,
    },
    "2yr": {
        "series_id": "treasury_2y",
        "title": "2-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 24,
    },
    "3yr": {
        "series_id": "treasury_3y",
        "title": "3-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 36,
    },
    "5yr": {
        "series_id": "treasury_5y",
        "title": "5-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 60,
    },
    "7yr": {
        "series_id": "treasury_7y",
        "title": "7-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 84,
    },
    "10yr": {
        "series_id": "treasury_10y",
        "title": "10-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 120,
    },
    "20yr": {
        "series_id": "treasury_20y",
        "title": "20-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 240,
    },
    "30yr": {
        "series_id": "treasury_30y",
        "title": "30-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 360,
    },
    "5yr TIPS": {
        "series_id": "tips_5y",
        "title": "5-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 60,
    },
    "7yr TIPS": {
        "series_id": "tips_7y",
        "title": "7-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 84,
    },
    "10yr TIPS": {
        "series_id": "tips_10y",
        "title": "10-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 120,
    },
    "20yr TIPS": {
        "series_id": "tips_20y",
        "title": "20-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 240,
    },
    "30yr TIPS": {
        "series_id": "tips_30y",
        "title": "30-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 360,
    },
}

FRED_RATE_SERIES_CONFIG = {
    "DFF": "Fed Funds",
    "DGS1MO": "1mo",
    "DGS3MO": "3mo",
    "DGS6MO": "6mo",
    "DGS1": "1yr",
    "DGS2": "2yr",
    "DGS3": "3yr",
    "DGS5": "5yr",
    "DGS7": "7yr",
    "DGS10": "10yr",
    "DGS20": "20yr",
    "DGS30": "30yr",
    "DFII5": "5yr TIPS",
    "DFII7": "7yr TIPS",
    "DFII10": "10yr TIPS",
    "DFII20": "20yr TIPS",
    "DFII30": "30yr TIPS",
}


def _fred_series_payload(fred_series_id, csv_path):
    header = FRED_RATE_SERIES_CONFIG[fred_series_id]
    config = RATE_SERIES_CONFIG[header]
    return {
        "series_id": config["series_id"],
        "title": config["title"],
        "instrument_type": config["instrument_type"],
        "maturity_months": config["maturity_months"],
        "units": "percent",
        "source_workbook": Path(csv_path).name,
        "source_sheet": FRED_SOURCE_SHEET,
    }


def _fred_point_payload(point, csv_path):
    return {
        "date": point["date"],
        "value": point["value"],
        "source_workbook": Path(csv_path).name,
        "source_sheet": FRED_SOURCE_SHEET,
    }


def build_fred_rate_payload(csv_path, fred_series_id):
    if fred_series_id not in FRED_RATE_SERIES_CONFIG:
        raise ValueError(f"fred rate series is unsupported: {fred_series_id}")
    rows = parse_fred_csv(csv_path, fred_series_id)
    points = [
        _fred_point_payload(point, csv_path)
        for point in resample_to_weekly_sundays(rows)
    ]
    return {
        "series": _fred_series_payload(fred_series_id, csv_path),
        "points": points,
    }


def fetch_fred_csvs(fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_RATE_SERIES_CONFIG)
    for fred_series_id in series_ids:
        if fred_series_id not in FRED_RATE_SERIES_CONFIG:
            raise ValueError(f"fred rate series is unsupported: {fred_series_id}")
    client = FredClient(fred_dir)
    return client.fetch_csvs(series_ids)


def import_fred_csvs(con, fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_RATE_SERIES_CONFIG)
    inserted = {}
    for fred_series_id in series_ids:
        csv_path = Path(fred_dir) / f"{fred_series_id}.csv"
        payload = build_fred_rate_payload(csv_path, fred_series_id)
        saved = us_rates_liquidity.replace_rate_series_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[payload["series"]["series_id"]] = saved["points"]
    return inserted


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import US rates and liquidity series from FRED"
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
