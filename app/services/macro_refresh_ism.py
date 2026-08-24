import hashlib
from datetime import datetime, timezone

from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.services import ism_report_ingestion
from app.tools import ism_report_config


def _fetched_at_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _source_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_target_identity(target, parsed):
    report = parsed["report"]
    if target.get("report_id") and report["report_id"] != target["report_id"]:
        raise ValueError(
            f"ism report id mismatch: expected {target['report_id']}, got {report['report_id']}"
        )
    if target.get("report_month") and report["report_month"] != target["report_month"]:
        raise ValueError(
            f"ism report month mismatch: expected {target['report_month']}, got {report['report_month']}"
        )


def prepare_ism_reports(targets, *, fetcher):
    prepared = []
    for target in targets:
        html = fetcher(target["url"])
        fetched_at = _fetched_at_now()
        survey_type = target["survey_type"]
        config = ism_report_config.load_survey_config(survey_type)
        parsed = config["parse_report"](
            html,
            target["url"],
            fetched_at,
            target.get("source_name", "ismworld"),
        )
        normalized = ism_report_ingestion.normalize_parsed(parsed, survey_type)
        _validate_target_identity(target, normalized)
        snapshot = {
            "source_url": target["url"],
            "source_name": target.get("source_name", "ismworld"),
            "survey_type": survey_type,
            "source_hash": _source_hash(html),
            "fetched_at": fetched_at,
            "raw_html": html,
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": normalized["report"]["report_id"],
            "report_month": normalized["report"]["report_month"],
        }
        prepared.append(
            {
                "target": dict(target),
                "snapshot": snapshot,
                "parsed": normalized,
            }
        )
    return prepared


def persist_ism_reports(db_path, prepared_reports):
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    results = []
    try:
        for prepared in prepared_reports:
            target = prepared["target"]
            snapshot = dict(prepared["snapshot"])
            try:
                growth_cycle.replace_ism_report_source_snapshot(con, snapshot)
                result = ism_report_ingestion.persist_parsed_report(
                    con, target["survey_type"], prepared["parsed"]
                )
                snapshot["parse_status"] = "ok"
                growth_cycle.replace_ism_report_source_snapshot(con, snapshot)
                results.append(result)
            except BaseException as exc:
                con.rollback()
                failed = dict(snapshot)
                failed["parse_status"] = "failed"
                failed["parse_error"] = str(exc)
                growth_cycle.replace_ism_report_source_snapshot(con, failed)
                raise
    finally:
        con.close()
    return results


def _prepare_services(snapshot):
    from app.tools.ism_services_report import prepare_report_for_ai

    return prepare_report_for_ai(
        snapshot["raw_html"],
        snapshot["source_url"],
        snapshot["fetched_at"],
        snapshot.get("source_name", "ismworld"),
    )


async def _run_services_extraction(prepared, client, model):
    from app.services.ism_services_ai_ingestion import extract_sections_without_db

    return await extract_sections_without_db(prepared, client, model)


def prepare_ism_enrichment(snapshot, *, client, model, survey_type):
    if survey_type == "services":
        import asyncio
        import inspect

        prepared = _prepare_services(snapshot)
        result = _run_services_extraction(prepared, client, model)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        extraction, call_counts = result
    elif survey_type == "manufacturing":
        from scripts.extract_ism_report_ai import prepare_ism_enrichment as prepare_ai

        extraction, call_counts = prepare_ai(
            snapshot, client=client, model=model, survey_type=survey_type
        )
    else:
        raise ValueError(f"ism survey type is unsupported: {survey_type}")
    return {
        "survey_type": survey_type,
        "snapshot": dict(snapshot),
        "extraction": extraction,
        "call_counts": call_counts,
        "model": model,
    }


def persist_ism_enrichment(db_path, prepared_extraction):
    survey_type = prepared_extraction["survey_type"]
    snapshot = prepared_extraction["snapshot"]
    extraction = prepared_extraction["extraction"]
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        source = {
            "report_id": extraction["report"]["report_id"],
            "report_month": extraction["report"]["report_month"],
            "source_url": snapshot["source_url"],
            "source_hash": snapshot["source_hash"],
            "model": prepared_extraction["model"],
            "updated_at": snapshot["fetched_at"],
        }
        if survey_type == "services":
            from app.db.ism_services_ai import promote_services_extraction

            return promote_services_extraction(con, extraction, source)
        from scripts.extract_ism_report_ai import _promote_factual_dashboard_outputs

        return _promote_factual_dashboard_outputs(con, extraction, snapshot, source)
    finally:
        con.close()
