import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import non_oil_attribution_evidence_import


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import  non-oil attribution evidence facts"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    args = parser.parse_args(argv)
    con = macro_indicators.connect(args.db_path)
    try:
        result = non_oil_attribution_evidence_import.refresh_non_oil_attribution_evidence(
            con
        )
    except ValueError as exc:
        print(f"commodities non-oil attribution import error: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()
    print(f"facts: {result['facts']}, commodities: {', '.join(result['commodities'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
