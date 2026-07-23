#!/usr/bin/env python3
"""Canonical CLI for ISM report ingestion with AI extraction.

Supports manufacturing and services surveys with a unified interface
for target selection, discovery, AI extraction, and persistence.

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


def main(argv=None, fetch=None, ai_client_factory=None):
    parser = argparse.ArgumentParser(
        description="Ingest ISM survey reports with AI extraction."
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

    if ai_client_factory is None:
        from app import llm

        try:
            config = llm.load_openai_config(args, root=ROOT)
        except Exception as exc:
            print(f"failed to load AI config: {exc}", file=sys.stderr)
            return 1
        from scripts.extract_ism_report_ai import OpenAIJsonClient, llm_timeout

        def _client_factory():
            return llm.build_async_client(
                config,
                max_retries=0,
                timeout=llm_timeout(),
                error_context="ISM extraction",
            )

        client = OpenAIJsonClient(
            _client_factory(),
            config["model"],
            client_factory=_client_factory,
            progress=lambda msg: print(msg, file=sys.stderr, flush=True),
        )
        model = config["model"]
    else:
        config = {"model": "test-model"}
        try:
            client = ai_client_factory(config)
        except Exception as exc:
            print(f"failed to construct AI client: {exc}", file=sys.stderr)
            return 1
        model = config["model"]

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

        try:
            if st == "manufacturing":
                from scripts import fetch_ism_official_reports as mfg

                results, failed = mfg.import_targets(
                    args_db, targets, fetch, client, model, args.report_concurrency
                )
            else:
                from app.services.ism_services_ai_ingestion import import_targets as svc

                results, failed = svc(
                    args_db,
                    targets,
                    client,
                    model,
                    fetch=fetch,
                    report_concurrency=args.report_concurrency,
                    section_concurrency=3,
                )
        except Exception as exc:
            print(f"{st} import failed: {exc}", file=sys.stderr)
            results, failed = [], 1

        for result in results:
            if result is not None:
                all_results.append(result)
                rid = result.get("report_id", "unknown")
                src = result.get("source_name", result.get("source", "unknown"))
                metrics = result.get("metrics", result.get("at_a_glance_rows", 0))
                comments = result.get("comments", 0)
                print(f"{rid}: source={src} metrics={metrics} comments={comments}")

        total_failed += failed

    return 1 if total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
