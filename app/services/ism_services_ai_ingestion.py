import asyncio
import hashlib
import sys
import time
from datetime import datetime, timezone
from subprocess import CalledProcessError, TimeoutExpired

from app.db import growth_cycle, us_rates_liquidity
from app.db.ism_services_ai import promote_services_extraction
from app.services.ism_ai_section_runner import extract_sections
from app.tools.ism_services_ai_extraction import (
    FACTUAL_SECTION_NAMES,
    SECTION_PROMPT_VERSIONS,
    BUILD_PROMPT_FOR_SECTION,
    SECTION_RESPONSE_MODELS,
    validate_section_payload,
    assemble_factual_extraction,
)
from app.tools.ism_services_report import prepare_report_for_ai
from app.services import ism_report_ingestion as ingestion

_IMPORT_ERRORS = (ValueError, CalledProcessError, TimeoutExpired)


def _build_prompt(section_name, source_text):
    builder = BUILD_PROMPT_FOR_SECTION.get(section_name)
    if builder is None:
        raise ValueError(f"unknown section: {section_name}")
    return builder(source_text)


def _validate_section(section_name, payload, source_text):
    return validate_section_payload(section_name, payload, source_text)


def _source_hash(html):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def _fetched_at_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _fetch_report(target, fetch=None):
    if fetch is None:
        from scripts.fetch_ism_official_reports import fetch_text

        fetch = fetch_text
    html = fetch(target["url"])
    fetched_at = _fetched_at_now()
    return html, fetched_at


def _save_source_snapshot(con, target, html, fetched_at):
    snapshot = {
        "source_url": target["url"],
        "source_name": target["source_name"],
        "survey_type": "services",
        "source_hash": _source_hash(html),
        "fetched_at": fetched_at,
        "raw_html": html,
        "parse_status": "fetched",
        "parse_error": None,
        "report_id": None,
        "report_month": None,
    }
    growth_cycle.replace_ism_report_source_snapshot(con, snapshot, commit=True)
    return snapshot


def _validate_target_identity(target, extraction):
    expected_rid = target.get("report_id")
    expected_month = target.get("report_month")
    actual_rid = extraction["report"]["report_id"]
    actual_month = extraction["report"]["report_month"]
    if expected_rid and actual_rid != expected_rid:
        raise ValueError(
            f"report_id mismatch: expected {expected_rid}, got {actual_rid}"
        )
    if expected_month and actual_month != expected_month:
        raise ValueError(
            f"report_month mismatch: expected {expected_month}, got {actual_month}"
        )


def _result_summary(extraction, call_counts):
    return {
        "report_id": extraction["report"]["report_id"],
        "source": extraction["report"]["source_name"],
        "section_calls": call_counts,
        "at_a_glance_rows": len(extraction["at_a_glance_rows"]),
        "comments": len(extraction.get("respondent_comments", [])),
        "industry_signals": len(extraction.get("industry_signals", [])),
        "commodities": len(extraction.get("commodities", [])),
    }


async def extract_prepared_report(
    db_path, prepared, client, model, section_concurrency=3
):
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        section_result = await extract_sections(
            con,
            client,
            prepared,
            FACTUAL_SECTION_NAMES,
            SECTION_PROMPT_VERSIONS,
            _build_prompt,
            _validate_section,
            _validate_section,
            section_concurrency,
        )
        extraction = assemble_factual_extraction(section_result["section_payloads"])
        return extraction, section_result["call_counts"]
    finally:
        con.close()


def import_report_url(
    db_path, target, client, model, fetch=None, section_concurrency=3
):
    html, fetched_at = _fetch_report(target, fetch)
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        _save_source_snapshot(con, target, html, fetched_at)
        prepared = prepare_report_for_ai(
            html, target["url"], fetched_at, target["source_name"]
        )
        source = {
            "report_id": prepared["report_id"],
            "report_month": prepared["report_month"],
            "source_url": target["url"],
            "source_hash": _source_hash(html),
            "model": model,
            "updated_at": fetched_at,
        }
        growth_cycle.replace_ism_report_source_snapshot(
            con,
            {
                "source_url": target["url"],
                "source_name": target["source_name"],
                "survey_type": "services",
                "source_hash": _source_hash(html),
                "fetched_at": fetched_at,
                "raw_html": html,
                "parse_status": "prepared",
                "parse_error": None,
                "report_id": prepared["report_id"],
                "report_month": prepared["report_month"],
            },
        )
        extraction, call_counts = asyncio.run(
            extract_prepared_report(
                db_path, prepared, client, model, section_concurrency
            )
        )
        _validate_target_identity(target, extraction)
        promote_services_extraction(con, extraction, source)
        return _result_summary(extraction, call_counts)
    finally:
        con.close()


def import_target(db_path, target, client, model, fetch=None, section_concurrency=3):
    started = time.perf_counter()
    result = import_report_url(
        db_path, target, client, model, fetch, section_concurrency
    )
    elapsed = time.perf_counter() - started
    ingestion.log_progress(
        f"[report] {result['report_id']} source={result['source']} "
        f"at_a_glance={result['at_a_glance_rows']} "
        f"comments={result['comments']} signals={result['industry_signals']} "
        f"commodities={result['commodities']} {elapsed:.1f}s"
    )
    return result


def import_targets(
    db_path,
    targets,
    client,
    model,
    fetch=None,
    report_concurrency=1,
    section_concurrency=3,
):
    if not targets:
        return [], 0
    ingestion.log_progress(
        f"report concurrency={report_concurrency} targets={len(targets)}"
    )
    results = []
    failed = 0
    for target in targets:
        try:
            result = import_target(
                db_path, target, client, model, fetch, section_concurrency
            )
            results.append(result)
        except _IMPORT_ERRORS as exc:
            ingestion.log_progress(f"ism_services_ai/{target['url']}: failed - {exc}")
            results.append(None)
            failed += 1
    return results, failed
