import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity

DEFAULT_CALENDAR_PATH = ROOT / "data" / "source_material" / "Video 06" / "fomc_calendar.csv"
FOMC_EVENT_TYPE = "fomc_meeting"
FOMC_SOURCE = "Federal Reserve"


def _display_month(date_value):
    return f"{date_value[:7]}-01"


def _event_id(start_date):
    return f"fomc_{start_date.replace('-', '_')}"


def _has_sep(value):
    normalized = str(value or "").strip().lower()
    return 1 if normalized in {"1", "true", "yes", "y"} else 0


def parse_calendar_csv(calendar_path=DEFAULT_CALENDAR_PATH):
    path = Path(calendar_path)
    if not path.exists():
        raise ValueError(f"fomc calendar csv is missing: {path}")
    rows = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            start_date = str(row.get("start_date") or "").strip()
            if not start_date:
                continue
            rows.append(
                {
                    "event_id": _event_id(start_date),
                    "event_type": FOMC_EVENT_TYPE,
                    "start_date": start_date,
                    "end_date": str(row.get("end_date") or "").strip() or None,
                    "display_month": _display_month(start_date),
                    "title": str(row.get("title") or "FOMC Meeting").strip(),
                    "source": FOMC_SOURCE,
                    "policy_tone": "unknown",
                    "has_sep": _has_sep(row.get("has_sep")),
                    "url": str(row.get("url") or "").strip() or None,
                }
            )
    return rows


def import_calendar(con, calendar_path=DEFAULT_CALENDAR_PATH):
    events = parse_calendar_csv(calendar_path)
    saved = us_rates_liquidity.replace_macro_events(con, FOMC_EVENT_TYPE, events)
    return {FOMC_EVENT_TYPE: saved["events"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--calendar-path", type=Path, default=DEFAULT_CALENDAR_PATH)
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    try:
        imported = import_calendar(con, args.calendar_path)
    finally:
        con.close()
    for event_type, count in imported.items():
        print(f"{event_type}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
