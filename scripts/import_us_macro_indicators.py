import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import compute_yoy
from app.data_sources.fred import date_iso
from app.data_sources.fred import parse_fred_csv
from app.data_sources.fred import resample_to_weekly_sundays
from app.db import macro_indicators
from app.db import us_rates_liquidity


DEFAULT_FRED_DIR = ROOT / "data" / "downloads" / "fred"
FRED_SOURCE = "FRED weekly Sunday resample"
FRED_MONTHLY_SOURCE = "FRED monthly"
FRED_WEEKLY_SOURCE = "FRED weekly"
SERIES_CONFIG = {
    "cpi_yoy": {"title": "CPI YoY", "units": "percent"},
    "vix": {"title": "VIX", "units": "index"},
    "core_pce_price_index": {"title": "Core PCE Price Index", "units": "index"},
    "fed_total_assets": {
        "title": "Federal Reserve Total Assets",
        "units": "millions_usd",
    },
    "fed_treasury_holdings": {
        "title": "Federal Reserve Treasury Holdings",
        "units": "millions_usd",
    },
    "fed_mbs_holdings": {
        "title": "Federal Reserve MBS Holdings",
        "units": "millions_usd",
    },
}

FRED_MACRO_SERIES_CONFIG = {
    "CPIAUCSL": "cpi_yoy",
    "PCEPILFE": "core_pce_price_index",
    "VIXCLS": "vix",
    "WALCL": "fed_total_assets",
    "TREAST": "fed_treasury_holdings",
    "WSHOMCB": "fed_mbs_holdings",
}


def _fred_series_payload(series_id):
    config = SERIES_CONFIG[series_id]
    return {
        "series_id": series_id,
        "title": config["title"],
        "units": config["units"],
        "source": FRED_SOURCE,
    }


def _fred_points_payload(points):
    return [
        {
            "date": point["date"],
            "value": point["value"],
            "source": FRED_SOURCE,
        }
        for point in points
    ]


def _fred_monthly_points_payload(rows):
    return [
        {
            "date": date_key,
            "value": value,
            "source": FRED_MONTHLY_SOURCE,
        }
        for date_key, value in rows.items()
    ]


def _fred_weekly_points_payload(rows):
    return [
        {
            "date": date_key,
            "value": value,
            "source": FRED_WEEKLY_SOURCE,
        }
        for date_key, value in rows.items()
    ]


def fetch_fred_csvs(fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_MACRO_SERIES_CONFIG)
    for fred_series_id in series_ids:
        if fred_series_id not in FRED_MACRO_SERIES_CONFIG:
            raise ValueError(f"fred macro series is unsupported: {fred_series_id}")
    client = FredClient(fred_dir)
    return client.fetch_csvs(series_ids)


def import_fred_macro_csvs(
    con,
    fred_dir=DEFAULT_FRED_DIR,
    start_date=None,
    end_date=None,
):
    cpi_rows = parse_fred_csv(Path(fred_dir) / "CPIAUCSL.csv", "CPIAUCSL")
    cpi_yoy = compute_yoy(cpi_rows)
    vix_rows = parse_fred_csv(Path(fred_dir) / "VIXCLS.csv", "VIXCLS")
    core_pce_rows = parse_fred_csv(Path(fred_dir) / "PCEPILFE.csv", "PCEPILFE")
    fed_total_assets_rows = parse_fred_csv(Path(fred_dir) / "WALCL.csv", "WALCL")
    fed_treasury_rows = parse_fred_csv(Path(fred_dir) / "TREAST.csv", "TREAST")
    fed_mbs_rows = parse_fred_csv(Path(fred_dir) / "WSHOMCB.csv", "WSHOMCB")
    payloads = {
        "cpi_yoy": _fred_points_payload(
            resample_to_weekly_sundays(
                cpi_yoy,
                start_date=start_date,
                end_date=end_date or date_iso(date.today()),
            )
        ),
        "vix": _fred_points_payload(
            resample_to_weekly_sundays(
                vix_rows,
                start_date=start_date,
                end_date=end_date,
            )
        ),
        "core_pce_price_index": _fred_monthly_points_payload(core_pce_rows),
        "fed_total_assets": _fred_weekly_points_payload(fed_total_assets_rows),
        "fed_treasury_holdings": _fred_weekly_points_payload(fed_treasury_rows),
        "fed_mbs_holdings": _fred_weekly_points_payload(fed_mbs_rows),
    }
    inserted = {}
    for series_id, points in payloads.items():
        saved = macro_indicators.replace_macro_indicator_points(
            con,
            _fred_series_payload(series_id),
            points,
        )
        inserted[series_id] = saved["points"]
    return inserted


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import US macro indicators from FRED"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch-fred-csv", action="store_true")
    mode.add_argument("--fred-csv-merge", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch_fred_csv:
        fetched = fetch_fred_csvs()
        for series_id, path in fetched.items():
            print(f"{series_id}: {path}")
        return 0
    con = us_rates_liquidity.connect()
    try:
        inserted = import_fred_macro_csvs(con)
        for series_id, count in inserted.items():
            print(f"{series_id}: {count}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
