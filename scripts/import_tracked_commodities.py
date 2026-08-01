import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.tracked_commodities import (
    ACTIVE_MARKET_SERIES,
    MARKET_SERIES,
    free_web_series,
)
from app.db import macro_indicators
from app.services import tracked_commodities_import


def _parse_csv_arg(csv_arg):
    result = {}
    for entry in csv_arg:
        if "=" not in entry:
            raise ValueError(f"--csv entry must be market_id=path, got: {entry}")
        market_id, path = entry.split("=", 1)
        if market_id not in MARKET_SERIES:
            raise ValueError(f"unknown method commodity market: {market_id}")
        if market_id not in ACTIVE_MARKET_SERIES:
            raise ValueError(
                f"archived method commodity market cannot be imported: {market_id}"
            )
        if market_id not in free_web_series():
            raise ValueError(
                f"method commodity market is not an Investing method market: {market_id}"
            )
        result[market_id] = Path(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Incrementally refresh  method-specified commodity prices "
        "from the rendered Investing.com history table"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--markets",
        nargs="*",
        default=list(free_web_series()),
        choices=list(free_web_series()),
        help="specific markets to refresh (default: all active Investing method markets)",
    )
    parser.add_argument(
        "--cdp-endpoint",
        default="http://127.0.0.1:9222",
        help="Chrome CDP endpoint (default: http://127.0.0.1:9222)",
    )
    parser.add_argument(
        "--csv",
        nargs="*",
        default=None,
        help="import full history from downloaded CSV files. Format: market_id=path/to/file.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print parsed observations without writing to database",
    )
    args = parser.parse_args(argv)
    markets_arg = args.markets

    if args.csv is not None:
        if not args.csv:
            print(
                " method commodity error: --csv requires at least one market_id=path.csv entry",
                file=sys.stderr,
            )
            return 1
        try:
            csv_paths_by_market = _parse_csv_arg(args.csv)
        except ValueError as exc:
            print(f" method commodity csv error: {exc}", file=sys.stderr)
            return 1
        if args.dry_run:
            from app.data_sources.tracked_commodities import (
                parse_commodity_csv,
            )

            any_error = False
            for market_id, csv_path in csv_paths_by_market.items():
                text = csv_path.read_text(encoding="utf-8")
                try:
                    observations = parse_commodity_csv(text, market_id)
                except ValueError as exc:
                    any_error = True
                    print(f"{market_id}: CSV ERROR: {exc}", file=sys.stderr)
                    continue
                if not observations:
                    print(f"{market_id}: 0 observations parsed from CSV")
                else:
                    print(
                        f"{market_id}: {len(observations)} observations "
                        f"({observations[0]['date']} to {observations[-1]['date']})"
                    )
            return 1 if any_error else 0
        con = macro_indicators.connect(args.db_path)
        try:
            result = tracked_commodities_import.import_commodity_csv_files(
                con, csv_paths_by_market
            )
            print(f"series: {result['series']}, observations: {result['observations']}")
            return 0
        except ValueError as exc:
            print(f" method commodity csv error: {exc}", file=sys.stderr)
            return 1
        finally:
            con.close()

    con = macro_indicators.connect(args.db_path)
    try:
        kwargs = {
            "markets": markets_arg,
            "cdp_endpoint": args.cdp_endpoint,
        }
        if args.dry_run:
            kwargs["dry_run"] = True
        result = tracked_commodities_import.import_commodity_browser_rows(
            con, **kwargs
        )
        if args.dry_run:
            for market_id, date_range in result["ranges"].items():
                print(
                    f"{market_id}: {date_range['start_date']} to {date_range['end_date']}"
                )
        for market_id in result.get("no_new_data", []):
            print(f"{market_id}: no new data (already up to date)")
        print(f"series: {result['series']}, observations: {result['observations']}")
        return 0
    except ValueError as exc:
        print(f" method commodity rendered refresh error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
