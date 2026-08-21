import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.llm import load_env
from app.services import oil_import


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import  oil evidence from EIA")
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--backfill-price-history",
        action="store_true",
        help="paginate and import complete official EIA WTI and Brent price history",
    )
    args = parser.parse_args(argv)
    load_env(ROOT)
    api_key = os.getenv("EIA_KEY", "").strip()
    if not api_key:
        print("commodities oil error: EIA_KEY is not set", file=sys.stderr)
        return 1
    con = macro_indicators.connect(args.db_path)
    try:
        result = oil_import.refresh_official_oil(
            con, api_key, full_price_history=args.backfill_price_history
        )
        print(f"series: {result['series']}, observations: {result['observations']}")
        return 0
    except ValueError as exc:
        print(f"commodities oil error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
