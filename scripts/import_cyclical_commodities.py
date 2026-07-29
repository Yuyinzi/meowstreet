import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import cyclical_commodities_import

DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"
DEFAULT_CACHE_DIR = ROOT / "data" / ""


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--fetch-cot", action="store_true")
    parser.add_argument("--import-cot", action="store_true")
    parser.add_argument("--fetch-usd", action="store_true")
    parser.add_argument("--import-usd", action="store_true")
    parser.add_argument("--cot-years", type=str, default=None)
    args = parser.parse_args(argv)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.cot_years:
        years = [int(y.strip()) for y in args.cot_years.split(",")]
    elif args.start_year and args.end_year:
        years = list(range(args.start_year, args.end_year + 1))
    else:
        years = [2026]

    con = macro_indicators.connect(args.db_path)
    try:
        if args.fetch_cot:
            cyclical_commodities_import.fetch_cot_zips(cache_dir, years)
            print("cot: fetched")
            return 0

        if args.import_cot:
            result = (
                cyclical_commodities_import.import_cached_official_cot_only(
                    con, cache_dir, years
                )
            )
            print(f"cot: {result['cot_observations']} observations")
            return 0

        if args.fetch_usd:
            cyclical_commodities_import._fetch_fred_csvs(cache_dir)
            print("usd: fetched")
            return 0

        if args.import_usd:
            result = (
                cyclical_commodities_import.import_cached_official_usd_only(
                    con, cache_dir
                )
            )
            print(f"usd: {result['usd_observations']} observations")
            return 0

        result = cyclical_commodities_import.refresh_official_(
            con, cache_dir, years
        )
    except ValueError as exc:
        print(f" error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()

    print(f"cot: {result['cot_observations']} observations")
    print(f"usd: {result['usd_observations']} observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
