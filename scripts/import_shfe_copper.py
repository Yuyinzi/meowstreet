import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import shfe_copper_import


def _parse_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date: {value}") from exc


def _print_progress(event):
    print(
        f"SHFE CU {event['date']}: received {event['contracts_received']} contracts "
        f"({event['completed']}/{event['total']})",
        flush=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import SHFE copper main-contract series via AKShare"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument("--start-date", type=_parse_date)
    parser.add_argument("--end-date", type=_parse_date)
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="refresh from the latest raw date minus 14 calendar days",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and report without writing any table",
    )
    args = parser.parse_args(argv)

    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            print(
                " shfe copper error: both --start-date and --end-date are required",
                file=sys.stderr,
            )
            return 1
        if args.start_date > args.end_date:
            print(
                " shfe copper error: start date is after end date",
                file=sys.stderr,
            )
            return 1
        if args.start_date > date.today().isoformat():
            print(
                " shfe copper error: start date is in the future",
                file=sys.stderr,
            )
            return 1
        if args.incremental:
            print(
                " shfe copper error: --incremental cannot be combined with explicit dates",
                file=sys.stderr,
            )
            return 1
        explicit = True
    else:
        explicit = False

    con = macro_indicators.connect(args.db_path)
    try:
        refresh_kwargs = {"progress_callback": _print_progress}
        if args.dry_run:
            refresh_kwargs["dry_run"] = True
        if explicit:
            result = shfe_copper_import.refresh_shfe_cu_main(
                con,
                start_date=args.start_date,
                end_date=args.end_date,
                **refresh_kwargs,
            )
        else:
            result = shfe_copper_import.refresh_shfe_cu_main(con, **refresh_kwargs)
        print(
            f"raw_dates_requested: {result['raw_dates_requested']}\n"
            f"raw_dates_published: {result['raw_dates_published']}\n"
            f"raw_observations: {result['raw_observations']}\n"
            f"derived_observations: {result['derived_observations']}\n"
            f"rebuild_start_date: {result['rebuild_start_date']}\n"
            f"rebuild_end_date: {result['rebuild_end_date']}"
        )
        return 0
    except ValueError as exc:
        print(f" shfe copper error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
