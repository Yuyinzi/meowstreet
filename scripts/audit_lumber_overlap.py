import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.lumber import (
    _LUMBER_START_DATE,
    fetch_lumber_series,
)
from app.db import macro_indicators
from app.services import lumber_import

DEFAULT_AUDIT_PATH = (
    ROOT / "data" / "local_system" / "audits" / "lumber_overlap_v1.json"
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit Investing lumber archive vs Yahoo LBR overlap"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument("--today-date")
    parser.add_argument("--out-path", type=Path, default=DEFAULT_AUDIT_PATH)
    args = parser.parse_args(argv)
    effective_today = args.today_date or date.today().isoformat()
    end_date = (date.fromisoformat(effective_today) + timedelta(days=1)).isoformat()
    con = macro_indicators.connect(args.db_path)
    try:
        archived_rows = macro_indicators.load_macro_indicator_observations(
            con, lumber_import.ARCHIVED_LUMBER_SERIES_ID
        )
        payload = fetch_lumber_series(_LUMBER_START_DATE, end_date)
        audit = lumber_import.audit_lumber_overlap(
            archived_rows, payload["observations"]
        )
    except ValueError as exc:
        print(f" lumber overlap audit failed: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()
    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    args.out_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
