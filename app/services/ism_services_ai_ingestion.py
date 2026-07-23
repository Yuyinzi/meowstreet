import asyncio
import concurrent.futures
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
from app.tools.ism_services_report import (
    _extract_at_a_glance_region,
    _extract_comments_commodities_region,
    _extract_industry_signals_region,
    _extract_narrative_region,
    prepare_report_for_ai,
)
from app.services import ism_report_ingestion as ingestion

_IMPORT_ERRORS = (
    ValueError,
    CalledProcessError,
    TimeoutExpired,
    RuntimeError,
)

_SECTION_REGIONS = {
    "report": lambda text: text[:240],
    "at_a_glance_rows": _extract_at_a_glance_region,
    "industry_signals": _extract_industry_signals_region,
    "comments_commodities": _extract_comments_commodities_region,
    "narrative_facts": _extract_narrative_region,
}

_MAX_REGION_FRACTION = 0.6
_MAX_TOTAL_FRACTION = 1.5


def _enforce_budget(section_regions, cleaned_length):
    for name, text in section_regions.items():
        if name == "report":
            continue
        fraction = len(text) / cleaned_length
        if fraction > _MAX_REGION_FRACTION:
            raise ValueError(
                f"{name} region is {len(text)} chars ({fraction:.1%}), "
                f"exceeds {_MAX_REGION_FRACTION:.0%} budget"
            )
    total = sum(len(t) for t in section_regions.values())
    total_fraction = total / cleaned_length
    if total_fraction > _MAX_TOTAL_FRACTION:
        raise ValueError(
            f"total region is {total} chars ({total_fraction:.1%}), "
            f"exceeds {_MAX_TOTAL_FRACTION:.0%} budget"
        )


def _extract_all_regions(source_text):
    regions = {}
    for name, fn in _SECTION_REGIONS.items():
        try:
            regions[name] = fn(source_text)
        except ValueError as exc:
            raise ValueError(f"failed to extract {name} region: {exc}") from exc
    _enforce_budget(regions, len(source_text))
    return regions


def _make_prompt_builder(source_text, source_url, source_name):
    regions = _extract_all_regions(source_text)
    regions["report"] += (
        f"\nSource name: {source_name}\nSource URL: {source_url}"
    )

    def _build(section_name, _source_text):
        builder = BUILD_PROMPT_FOR_SECTION.get(section_name)
        if builder is None:
            raise ValueError(f"unknown section: {section_name}")
        return builder(regions[section_name])

    return _build


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
        "metrics": len(extraction["at_a_glance_rows"]),
        "at_a_glance_rows": len(extraction["at_a_glance_rows"]),
        "comments": len(extraction.get("respondent_comments", [])),
        "industry_signals": len(extraction.get("industry_signals", [])),
        "commodities": len(extraction.get("commodities", [])),
        "rankings": len(extraction.get("industry_signals", [])),
    }


async def extract_prepared_report(
    db_path, prepared, client, model, section_concurrency=3, progress=None
):
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        build_prompt = _make_prompt_builder(
            prepared["source_text"],
            prepared["source_url"],
            prepared["source_name"],
        )
        section_result = await extract_sections(
            con,
            client,
            prepared,
            FACTUAL_SECTION_NAMES,
            SECTION_PROMPT_VERSIONS,
            build_prompt,
            _validate_section,
            _validate_section,
            section_concurrency,
            progress=progress,
        )
        extraction = assemble_factual_extraction(section_result["section_payloads"])
        return extraction, section_result["call_counts"]
    finally:
        con.close()


def _record_extraction_failure(con, target, message):
    con.execute(
        "update ism_report_source_snapshots "
        "set parse_status = 'failed', parse_error = ? "
        "where source_url = ?",
        (str(message)[:500], target["url"]),
    )
    con.commit()


def import_report_url(
    db_path,
    target,
    client,
    model,
    fetch=None,
    section_concurrency=3,
    progress=None,
    progress_prefix="services",
):
    started = time.perf_counter()
    html, fetched_at = _fetch_report(target, fetch)
    if progress is not None:
        progress(
            f"{progress_prefix} fetched chars={len(html)} "
            f"{time.perf_counter() - started:.1f}s"
        )
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        _save_source_snapshot(con, target, html, fetched_at)
        prepared = prepare_report_for_ai(
            html, target["url"], fetched_at, target["source_name"]
        )
        if progress is not None:
            progress(
                f"{progress_prefix} prepared report_id={prepared['report_id']} "
                f"chars={len(prepared['source_text'])}"
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
        try:
            extraction, call_counts = asyncio.run(
                extract_prepared_report(
                    db_path,
                    prepared,
                    client,
                    model,
                    section_concurrency,
                    progress=progress,
                )
            )
        except BaseException as exc:
            _record_extraction_failure(con, target, exc)
            raise
        _validate_target_identity(target, extraction)
        if progress is not None:
            progress(
                f"{progress_prefix} promotion started "
                f"report_id={prepared['report_id']}"
            )
        promoted = promote_services_extraction(con, extraction, source)
        if progress is not None:
            progress(
                f"{progress_prefix} promotion ok report_id={prepared['report_id']} "
                f"signals={promoted['industry_signals']} "
                f"coverage={promoted['signal_coverage']} "
                f"comments={promoted['comments']} "
                f"commodities={promoted['commodities']}"
            )
        return _result_summary(extraction, call_counts)
    except BaseException as exc:
        _record_extraction_failure(con, target, exc)
        raise
    finally:
        con.close()


def import_target(
    db_path,
    target,
    client,
    model,
    fetch=None,
    section_concurrency=3,
    index=1,
    total=1,
):
    started = time.perf_counter()
    report_month = target.get("report_month") or "unknown"
    progress_prefix = f"[{index}/{total}] services {report_month[:7]}"
    ingestion.log_progress(
        f"{progress_prefix} fetching source={target.get('source_name', 'unknown')} "
        f"url={target['url']}"
    )
    result = import_report_url(
        db_path,
        target,
        client,
        model,
        fetch,
        section_concurrency,
        progress=ingestion.log_progress,
        progress_prefix=progress_prefix,
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
    if report_concurrency <= 1:
        results = []
        failed = 0
        total = len(targets)
        for index, target in enumerate(targets, start=1):
            try:
                result = import_target(
                    db_path,
                    target,
                    client,
                    model,
                    fetch,
                    section_concurrency,
                    index,
                    total,
                )
                results.append(result)
            except _IMPORT_ERRORS as exc:
                ingestion.log_progress(
                    f"ism_services_ai/{target['url']}: failed - {exc}"
                )
                results.append(None)
                failed += 1
        return results, failed
    results_map = {}
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=report_concurrency
    ) as executor:
        futures = {
            executor.submit(
                import_target,
                db_path,
                t,
                client,
                model,
                fetch,
                section_concurrency,
                idx + 1,
                len(targets),
            ): idx
            for idx, t in enumerate(targets)
        }
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                results_map[idx] = future.result()
            except _IMPORT_ERRORS as exc:
                ingestion.log_progress(
                    f"ism_services_ai/{targets[idx]['url']}: failed - {exc}"
                )
                results_map[idx] = None
                failed += 1
    return [results_map[i] for i in range(len(targets))], failed
