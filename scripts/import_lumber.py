import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import lumber_import


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import  Yahoo LBR lumber observations"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument("--today-date")
    parser.add_argument(
        "--initial",
        action="store_true",
        help="backfill from the contract start date regardless of stored rows",
    )
    parser.add_argument(
        "--audit-path",
        type=Path,
        default=lumber_import.LUMBER_OVERLAP_AUDIT_PATH,
        help="path for the initial overlap audit JSON record",
    )
    args = parser.parse_args(argv)
    con = macro_indicators.connect(args.db_path)
    try:
        result = lumber_import.refresh_lumber(
            con,
            today_date=args.today_date,
            initial=args.initial,
            audit_path=args.audit_path,
        )
    except ValueError as exc:
        print(f" lumber import error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()
    print(
        f"series: {result['series']}, observations: {result['observations']}, "
        f"start_date: {result['start_date']}, end_date: {result['end_date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
