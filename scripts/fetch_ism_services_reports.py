"""ISM Services Report fetcher — compatibility wrapper.

Delegates to the shared ISM ingestion service for parse-only report
fetching, parsing, and persistence. This wrapper is kept for backward
compatibility; the canonical CLI is ``fetch_ism_reports.py``.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from app.services import ism_report_ingestion as ingestion
from scripts import fetch_ism_reports as _canonical


def requested_months(count=1, today=None):
    """Return the *count* most recent report months as ``YYYY-MM-01`` strings."""
    if today is None:
        today = datetime.now()
    months = []
    for i in range(count):
        raw_month = today.month - 1 - i
        y = today.year
        m = raw_month
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}-01")
    return sorted(months)


def main(argv=None, fetch=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--months", type=int, default=1)
    args = parser.parse_args(argv)

    months = requested_months(args.months)

    targets = []
    for month in months:
        targets.extend(
            ingestion.build_targets(
                "services",
                report_month=month,
                force_latest=False,
                fetch=fetch,
            )
        )

    results, failed = ingestion.import_targets(
        str(args.db_path), "services", targets, fetch=fetch,
    )

    for result in results:
        if result is not None:
            print(
                f"{result['report_id']}: source={result['source']} "
                f"metrics={result['metrics']} rankings={result['rankings']} "
                f"comments={result['comments']}"
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
