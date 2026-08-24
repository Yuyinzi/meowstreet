import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import housing_permits_import

DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"
DEFAULT_CACHE_PATH = ROOT / "data" / "census" / "permits_cust.xlsx"


def fetch_building_permits(artifacts, *, fetcher=None, destination=None, http_client=None):
    from app.services import macro_refresh_official

    return macro_refresh_official.fetch_building_permits(
        artifacts,
        fetcher=fetcher,
        destination=destination,
        http_client=http_client,
    )


def persist_building_permits(db_path, artifacts, *, release_date=None):
    from app.services import macro_refresh_official

    return macro_refresh_official.persist_building_permits(
        db_path, artifacts, release_date=release_date
    )


fetch_us_building_permits = fetch_building_permits
persist_us_building_permits = persist_building_permits


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--census-cache-path", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--release-date", type=str, default=None)
    parser.add_argument("--fetch-census-workbook", action="store_true")
    parser.add_argument("--import-census-workbook", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch_census_workbook:
        dest = housing_permits_import.fetch_official_workbook(args.census_cache_path)
        print(f"downloaded census workbook to {dest}")
        return 0
    con = macro_indicators.connect(args.db_path)
    try:
        if args.import_census_workbook:
            count = housing_permits_import.import_cached_official_workbook(
                con, args.census_cache_path, release_date=args.release_date
            )
        else:
            count = housing_permits_import.refresh_official_history(
                con, args.census_cache_path, release_date=args.release_date
            )
    finally:
        con.close()
    print(f"building_permits_saar: {count} observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
