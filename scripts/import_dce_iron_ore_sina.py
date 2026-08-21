import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import dce_iron_ore_sina_import


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import Sina DCE iron ore I0 continuous daily close via AKShare"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument("--today-date", type=str)
    parser.add_argument("--initial", action="store_true")
    args = parser.parse_args(argv)

    con = macro_indicators.connect(args.db_path)
    try:
        result = dce_iron_ore_sina_import.refresh_dce_iron_ore_sina(
            con,
            today_date=args.today_date,
            initial=args.initial,
        )
    except ValueError as exc:
        print(f"commodities dce iron ore sina error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()
    print(
        f"series: {result['series']}\n"
        f"observations: {result['observations']}\n"
        f"start_date: {result['start_date']}\n"
        f"end_date: {result['end_date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
