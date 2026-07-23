#!/usr/bin/env python3
"""Offline ISM Services AI extraction and retry script.

Usage:
  extract_ism_services_report_ai.py --source-url URL [--db-path PATH] [--section-concurrency N]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from app.services.ism_services_ai_ingestion import import_report_url


def _normalize_report_month(raw):
    if raw and len(raw) == 7 and raw.count("-") == 1:
        return f"{raw}-01"
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract ISM Services report sections using AI."
    )
    parser.add_argument("--source-url", required=True, help="Source URL for the report")
    parser.add_argument(
        "--source-name",
        default="ismworld",
        choices=["ismworld", "prnewswire"],
    )
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--section-concurrency",
        type=int,
        default=3,
        help="Number of concurrent AI section extractions (default: 3)",
    )
    parser.add_argument(
        "--report-month", help="Report month in YYYY-MM or YYYY-MM-01 format"
    )
    args = parser.parse_args(argv)

    target = {
        "url": args.source_url,
        "source_name": args.source_name,
        "report_month": _normalize_report_month(args.report_month),
        "report_id": None,
    }

    from app import llm

    config = llm.load_openai_config(args, root=ROOT)
    from scripts.extract_ism_report_ai import OpenAIJsonClient, llm_timeout

    def client_factory():
        return llm.build_async_client(
            config,
            max_retries=0,
            timeout=llm_timeout(),
            error_context="ISM Services extraction",
        )

    client = OpenAIJsonClient(
        client_factory(),
        config["model"],
        client_factory=client_factory,
        progress=lambda msg: print(msg, file=sys.stderr, flush=True),
    )

    result = import_report_url(
        str(args.db_path),
        target,
        client,
        config["model"],
        section_concurrency=args.section_concurrency,
    )

    print(f"report_id={result['report_id']} source={result['source']}")
    print(f"at_a_glance_rows={result['at_a_glance_rows']}")
    print(
        f"comments={result['comments']} industry_signals={result['industry_signals']}"
    )
    print(
        f"commodities={result['commodities']} section_calls={result['section_calls']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
