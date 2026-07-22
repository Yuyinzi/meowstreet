#!/usr/bin/env python3
"""Canonical CLI for ISM report ingestion (parse-only, no AI extraction).

Supports manufacturing and services surveys with a unified interface
for target selection, discovery, fetching, parsing, and persistence.

Usage:
  fetch_ism_reports.py --survey manufacturing|services|all [options]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.services import ism_report_ingestion as ingestion
from app.tools import ism_report_config


def positive_int(value):
    return ingestion.positive_int(value)


def main(argv=None, fetch=None):
    parser = argparse.ArgumentParser(
        description="Ingest ISM survey reports (parse-only, no AI extraction)."
    )
    parser.add_argument(
        "--survey",
        required=True,
        choices=["manufacturing", "services", "all"],
        help="Survey type to ingest (or 'all' for both)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=us_rates_liquidity.DEFAULT_DB_PATH,
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Only import the latest released report",
    )
    parser.add_argument(
        "--report-month",
        help="Import a specific report month (YYYY-MM format)",
    )
    parser.add_argument(
        "--current-year",
        action="store_true",
        help="Import all months from January to latest released this year",
    )
    parser.add_argument(
        "--backfill-since",
        type=int,
        metavar="YEAR",
        help="Backfill historical reports from YEAR (e.g. 2022)",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only import months not already in the database",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Import even if the report month already exists",
    )
    parser.add_argument(
        "--url",
        action="append",
        metavar="URL",
        help="Direct URL to import (may be repeated)",
    )
    parser.add_argument(
        "--report-concurrency",
        type=positive_int,
        default=1,
        metavar="N",
        help="Number of concurrent report imports (default: 1)",
    )
    args = parser.parse_args(argv)

    survey_types = (
        ["manufacturing", "services"] if args.survey == "all" else [args.survey]
    )

    repair_urls = args.url or None
    has_precise_target = args.report_month is not None or bool(args.url)
    force_latest = not has_precise_target or args.force

    all_results = []
    total_failed = 0

    for st in survey_types:
        args_db = str(args.db_path)
        con = us_rates_liquidity.connect(args_db)
        growth_cycle.init_db(con)
        existing_months = growth_cycle.load_existing_ism_report_months(con, st)
        con.close()

        targets = ingestion.build_targets(
            st,
            latest_only=args.latest_only,
            report_month=args.report_month,
            current_year=datetime.now().year if args.current_year else None,
            backfill_since=args.backfill_since,
            missing_only=args.missing_only,
            existing_months=existing_months,
            force_latest=force_latest,
            fetch=fetch,
            repair_urls=repair_urls,
        )

        results, failed = ingestion.import_targets(
            args_db,
            st,
            targets,
            fetch=fetch,
            report_concurrency=args.report_concurrency,
        )

        for result in results:
            if result is not None:
                all_results.append(result)
                line = (
                    f"{result['report_id']}: "
                    f"source={result['source']} metrics={result['metrics']} "
                    f"rankings={result['rankings']} comments={result['comments']}"
                )
                if args.survey == "all":
                    line = (
                        f"{result['report_id']}: "
                        f"survey_type={result['survey_type']} "
                        f"source={result['source']} metrics={result['metrics']} "
                        f"rankings={result['rankings']} comments={result['comments']}"
                    )
                print(line)

        total_failed += failed

    return 1 if total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
