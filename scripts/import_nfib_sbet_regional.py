import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import nfib_sbet_regional_import


def main(argv=None):
    current_year = date.today().year
    parser = argparse.ArgumentParser(
        description="Import official NFIB SBET regional API data"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=current_year)
    args = parser.parse_args(argv)

    con = macro_indicators.connect(args.db_path)
    try:
        count = nfib_sbet_regional_import.import_official_regional_sbet(
            con, args.start_year, args.end_year
        )
    finally:
        con.close()

    print(f"imported {count} nfib regional observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
