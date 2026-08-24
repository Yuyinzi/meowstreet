#!/usr/bin/env python3
"""Canonical CLI for deterministic ISM ingestion and optional enrichment."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm
from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.services import ism_ai_enrichment
from app.services import ism_report_ingestion as ingestion
from app.services import ism_services_ai_ingestion


def positive_int(value):
    return ingestion.positive_int(value)


def _print_results(results):
    for result in results:
        if result is None:
            continue
        report_id = result.get("report_id", "unknown")
        source = result.get("source_name", result.get("source", "unknown"))
        metrics = result.get("metrics", result.get("at_a_glance_rows", 0))
        comments = result.get("comments", 0)
        print(f"{report_id}: source={source} metrics={metrics} comments={comments}")


def _build_core_targets(args, survey_type, fetch):
    con = us_rates_liquidity.connect(args.db_path)
    try:
        growth_cycle.init_db(con)
        existing_months = growth_cycle.load_existing_ism_report_months(
            con, survey_type
        )
    finally:
        con.close()
    has_precise_target = args.report_month is not None or bool(args.url)
    return ingestion.build_targets(
        survey_type,
        latest_only=args.latest_only,
        report_month=args.report_month,
        current_year=datetime.now().year if args.current_year else None,
        backfill_since=args.backfill_since,
        missing_only=args.missing_only,
        existing_months=existing_months,
        force_latest=not has_precise_target or args.force,
        fetch=fetch,
        repair_urls=args.url or None,
    )


def _run_core(args, survey_type, fetch):
    targets = _build_core_targets(args, survey_type, fetch)
    results, failed = ingestion.import_targets(
        str(args.db_path),
        survey_type,
        targets,
        fetch=fetch,
        report_concurrency=args.report_concurrency,
    )
    _print_results(results)
    return failed


def _select_enrichment_snapshots(args, survey_type):
    con = us_rates_liquidity.connect(args.db_path)
    try:
        growth_cycle.init_db(con)
        snapshots = growth_cycle.load_ism_report_source_snapshots(con, survey_type)
    finally:
        con.close()
    report_month = (
        ingestion.normalize_report_month(args.report_month)
        if args.report_month
        else None
    )
    latest_month = None
    if (args.latest_only and not args.url) or args.force or (
        not report_month
        and not args.current_year
        and not args.backfill_since
        and not args.url
    ):
        latest_month = ingestion.latest_released_report_month()
    current_year = datetime.now().year if args.current_year else None
    return ism_ai_enrichment.select_snapshots(
        snapshots,
        latest_month=latest_month,
        report_month=report_month,
        current_year=current_year,
        backfill_since=args.backfill_since,
        source_urls=args.url or None,
    )


def _build_ai_client(args, ai_client_factory):
    if ai_client_factory is not None:
        config = {"model": "test-model"}
        try:
            return ai_client_factory(config), config["model"], None
        except Exception as exc:
            return None, config["model"], f"failed to construct AI client: {exc}"
    try:
        config = llm.load_openai_config(args, root=ROOT)
    except Exception as exc:
        return None, None, f"failed to load AI config: {exc}"
    if not config.get("api_key"):
        return None, config["model"], "OPENAI_API_KEY is not configured"
    try:
        from scripts.extract_ism_report_ai import OpenAIJsonClient, llm_timeout

        def client_factory():
            return llm.build_async_client(
                config,
                max_retries=0,
                timeout=llm_timeout(),
                error_context="ISM extraction",
            )

        client = OpenAIJsonClient(
            client_factory(),
            config["model"],
            client_factory=client_factory,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except Exception as exc:
        return None, config["model"], f"failed to construct AI client: {exc}"
    return client, config["model"], None


def _enrich_manufacturing_snapshot(db_path, snapshot, client, model):
    from scripts.extract_ism_report_ai import extract_snapshot

    con = us_rates_liquidity.connect(db_path)
    try:
        return extract_snapshot(
            con,
            snapshot["source_url"],
            client,
            model,
            facts_only=True,
        )
    finally:
        con.close()


def _enrich_services_snapshot(db_path, snapshot, client, model):
    return ism_services_ai_ingestion.enrich_snapshot(
        db_path,
        snapshot,
        client,
        model,
        section_concurrency=3,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )


def _run_enrichment(args, survey_type, ai_client_factory, client_state):
    snapshots = _select_enrichment_snapshots(args, survey_type)
    if not snapshots:
        print(f"{survey_type} ai_enrichment: skipped - no eligible core snapshot")
        return 0
    if not client_state["initialized"]:
        client_state["initialized"] = True
        client, model, error = _build_ai_client(args, ai_client_factory)
        client_state["client"] = client
        client_state["model"] = model
        client_state["error"] = error
    client = client_state["client"]
    model = client_state["model"]
    if client is None:
        if client_state["error"]:
            if "OPENAI_API_KEY is not configured" in client_state["error"]:
                print(
                    f"{survey_type} ai_enrichment: skipped - "
                    "OPENAI_API_KEY is not configured"
                )
                return 0
            print(
                f"{survey_type} ai_enrichment: {client_state['error']}",
                file=sys.stderr,
            )
            return 1
        return 0
    enrich_one = (
        _enrich_manufacturing_snapshot
        if survey_type == "manufacturing"
        else _enrich_services_snapshot
    )
    results, failed = ism_ai_enrichment.enrich_snapshots(
        snapshots,
        lambda snapshot: enrich_one(str(args.db_path), snapshot, client, model),
        report_concurrency=args.report_concurrency,
    )
    _print_results(results)
    if failed:
        print(
            f"{survey_type} ai_enrichment: failed - {failed} snapshot(s)",
            file=sys.stderr,
        )
    return failed


def main(argv=None, fetch=None, ai_client_factory=None):
    parser = argparse.ArgumentParser(
        description="Ingest ISM survey reports with optional AI enrichment."
    )
    parser.add_argument(
        "--survey",
        required=True,
        choices=["manufacturing", "services", "all"],
        help="Survey type to ingest (or 'all' for both)",
    )
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--latest-only", action="store_true")
    parser.add_argument("--report-month")
    parser.add_argument("--current-year", action="store_true")
    parser.add_argument("--backfill-since", type=int, metavar="YEAR")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--url", action="append", metavar="URL")
    parser.add_argument(
        "--report-concurrency",
        type=positive_int,
        default=1,
        metavar="N",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--core-only", action="store_true")
    mode.add_argument("--enrichment-only", action="store_true")
    args = parser.parse_args(argv)
    survey_types = (
        ["manufacturing", "services"]
        if args.survey == "all"
        else [args.survey]
    )

    if args.enrichment_only:
        client_state = {"initialized": False, "client": None, "model": None}
        total_failed = sum(
            _run_enrichment(args, survey_type, ai_client_factory, client_state)
            for survey_type in survey_types
        )
        return 1 if total_failed else 0

    core_failures = []
    for survey_type in survey_types:
        try:
            failed = _run_core(args, survey_type, fetch)
        except Exception as exc:
            print(f"{survey_type} import failed: {exc}", file=sys.stderr)
            failed = 1
        core_failures.append(failed)
    if args.core_only:
        return 1 if any(core_failures) else 0

    client_state = {"initialized": False, "client": None, "model": None}
    total_failed = sum(core_failures)
    for survey_type, failed in zip(survey_types, core_failures):
        if failed:
            print(
                f"{survey_type} ai_enrichment: skipped - core import failed",
                file=sys.stderr,
            )
            continue
        total_failed += _run_enrichment(
            args, survey_type, ai_client_factory, client_state
        )
    return 1 if total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
