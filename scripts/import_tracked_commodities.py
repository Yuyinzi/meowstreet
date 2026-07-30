import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.tracked_commodities import MARKET_SERIES
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
        result[market_id] = Path(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import  method-specified commodity prices"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--markets",
        nargs="*",
        default=list(MARKET_SERIES),
        choices=list(MARKET_SERIES),
        help="specific markets to import (default: all six)",
    )
    parser.add_argument("--start-date", help="inclusive start date YYYY-MM-DD")
    parser.add_argument("--end-date", help="inclusive end date YYYY-MM-DD")
    parser.add_argument(
        "--cdp-endpoint",
        default="http://127.0.0.1:9222",
        help="Chrome CDP endpoint (default: http://127.0.0.1:9222)",
    )
    parser.add_argument(
        "--csv",
        nargs="*",
        default=None,
        help="import from downloaded CSV files. Format: market_id=path/to/file.csv",
    )
    parser.add_argument(
        "--browser-download",
        action="store_true",
        help="import via browser download (navigates existing Investing tab and clicks Download Data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print parsed observations without writing to database",
    )
    args = parser.parse_args(argv)
    markets_arg = args.markets

    if args.browser_download and args.csv is not None:
        print(
            " method commodity error: --browser-download and --csv are mutually exclusive",
            file=sys.stderr,
        )
        return 1
    if args.browser_download and args.dry_run:
        print(
            " method commodity error: --browser-download and --dry-run are mutually exclusive",
            file=sys.stderr,
        )
        return 1

    if args.browser_download:
        con = macro_indicators.connect(args.db_path)
        try:
            result = (
                tracked_commodities_import.import_commodity_browser_downloads(
                    con,
                    markets=markets_arg,
                    cdp_endpoint=args.cdp_endpoint,
                )
            )
            print(f"series: {result['series']}, observations: {result['observations']}")
            return 0
        except ValueError as exc:
            print(
                f" method commodity browser download error: {exc}", file=sys.stderr
            )
            return 1
        finally:
            con.close()

    if args.csv is not None:
        if not args.csv:
            print(
                " method commodity error: --csv requires at least one market_id=path.csv entry",
                file=sys.stderr,
            )
            return 1
        csv_paths_by_market = _parse_csv_arg(args.csv)
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

    if args.dry_run:
        from app.data_sources import investing_chrome
        from app.data_sources.tracked_commodities import (
            parse_investing_history_payload,
        )

        any_error = False
        for market_id in markets_arg:
            meta = MARKET_SERIES[market_id]
            result = investing_chrome.fetch_investing_history(
                meta,
                args.start_date,
                args.end_date,
                cdp_endpoint=args.cdp_endpoint,
            )
            if result["status"] != "ok":
                any_error = True
                print(
                    f"{market_id}: {meta['display_name']} — {result['message']}",
                    file=sys.stderr,
                )
                continue
            observations = parse_investing_history_payload(
                result["payload"],
                market_id,
                retrieved_at=result["retrieved_at"],
            )
            if not observations:
                print(f"{market_id}: {meta['display_name']} — 0 observations")
            else:
                print(
                    f"{market_id}: {meta['display_name']} — "
                    f"{len(observations)} observations "
                    f"({observations[0]['date']} to {observations[-1]['date']})"
                )
        return 1 if any_error else 0

    con = macro_indicators.connect(args.db_path)
    try:
        result = tracked_commodities_import.refresh_tracked_commodities(
            con,
            start_date=args.start_date,
            end_date=args.end_date,
            markets=markets_arg,
            cdp_endpoint=args.cdp_endpoint,
        )
        print(f"series: {result['series']}, observations: {result['observations']}")
        return 0
    except ValueError as exc:
        print(f" method commodity error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
