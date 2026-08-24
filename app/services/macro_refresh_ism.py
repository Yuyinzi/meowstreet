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
        fetched_at = _fetched_at_now()
        html = ""
        normalized = None
        error = None
        try:
            html = fetcher(target["url"])
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
        except BaseException as exc:
            error = str(exc)
        report = normalized.get("report", {}) if normalized and error is None else {}
        report_id = report.get("report_id") or target.get("report_id")
        report_month = report.get("report_month") or target.get("report_month")
        snapshot = {
            "source_url": target["url"],
            "source_name": target.get("source_name", "ismworld"),
            "survey_type": target["survey_type"],
            "source_hash": _source_hash(html),
            "fetched_at": fetched_at,
            "raw_html": html,
            "parse_status": "failed" if error else "prepared",
            "parse_error": error,
            "report_id": report_id,
            "report_month": report_month,
        }
        prepared.append(
            {
                "target": dict(target),
                "snapshot": snapshot,
                "parsed": normalized,
                "status": "failed" if error else "ok",
                "error": error,
                "source_url": target["url"],
                "report_id": report_id,
                "report_month": report_month,
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
            if prepared.get("status") == "failed":
                growth_cycle.replace_ism_report_source_snapshot(con, snapshot)
                results.append(
                    {
                        "status": "failed",
                        "source_url": prepared["source_url"],
                        "report_id": prepared.get("report_id"),
                        "report_month": prepared.get("report_month"),
                        "error": prepared.get("error", "ism report preparation failed"),
                    }
                )
                continue
            try:
                growth_cycle.replace_ism_report_source_snapshot(con, snapshot)
                result = ism_report_ingestion.persist_parsed_report(
                    con, target["survey_type"], prepared["parsed"]
                )
                snapshot["parse_status"] = "ok"
                growth_cycle.replace_ism_report_source_snapshot(con, snapshot)
                results.append({**result, "status": "ok"})
            except BaseException as exc:
                con.rollback()
                failed = dict(snapshot)
                failed["parse_status"] = "failed"
                failed["parse_error"] = str(exc)
                growth_cycle.replace_ism_report_source_snapshot(con, failed)
                results.append(
                    {
                        "status": "failed",
                        "source_url": snapshot["source_url"],
                        "report_id": snapshot.get("report_id"),
                        "report_month": snapshot.get("report_month"),
                        "error": str(exc),
                    }
                )
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
    try:
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
        _validate_enrichment_identity(snapshot, extraction)
    except BaseException as exc:
        return {
            "status": "failed",
            "survey_type": survey_type,
            "snapshot": dict(snapshot),
            "extraction": None,
            "call_counts": {},
            "model": model,
            "source_url": snapshot.get("source_url"),
            "report_id": snapshot.get("report_id"),
            "report_month": snapshot.get("report_month"),
            "error": str(exc),
        }
    return {
        "status": "ok",
        "survey_type": survey_type,
        "snapshot": dict(snapshot),
        "extraction": extraction,
        "call_counts": call_counts,
        "model": model,
        "source_url": snapshot.get("source_url"),
        "report_id": extraction.get("report", {}).get("report_id")
        or extraction.get("report_id"),
        "report_month": extraction.get("report", {}).get("report_month")
        or extraction.get("report_month"),
        "error": None,
    }


def _validate_enrichment_identity(snapshot, extraction):
    report = extraction.get("report", {})
    if not report and extraction.get("report_id"):
        report = {
            "report_id": extraction.get("report_id"),
            "report_month": extraction.get("report_month"),
        }
    expected_id = snapshot.get("report_id")
    expected_month = snapshot.get("report_month")
    if expected_id and report.get("report_id") != expected_id:
        raise ValueError(
            f"ism report_id mismatch: expected {expected_id}, got {report.get('report_id')}"
        )
    if expected_month and report.get("report_month") != expected_month:
        raise ValueError(
            f"ism report_month mismatch: expected {expected_month}, got {report.get('report_month')}"
        )


def persist_ism_enrichment(db_path, prepared_extraction):
    survey_type = prepared_extraction["survey_type"]
    snapshot = prepared_extraction["snapshot"]
    extraction = prepared_extraction["extraction"]
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        if prepared_extraction.get("status") == "failed":
            failed_snapshot = dict(snapshot)
            failed_snapshot["parse_error"] = prepared_extraction.get(
                "error", "ism enrichment preparation failed"
            )
            growth_cycle.replace_ism_report_source_snapshot(con, failed_snapshot)
            return {
                "status": "failed",
                "source_url": prepared_extraction.get("source_url"),
                "report_id": prepared_extraction.get("report_id"),
                "report_month": prepared_extraction.get("report_month"),
                "error": prepared_extraction.get("error"),
            }
        source = {
            "report_id": extraction.get("report", {}).get("report_id")
            or extraction.get("report_id"),
            "report_month": extraction.get("report", {}).get("report_month")
            or extraction.get("report_month"),
            "source_url": snapshot["source_url"],
            "source_hash": snapshot["source_hash"],
            "model": prepared_extraction["model"],
            "updated_at": snapshot["fetched_at"],
        }
        if survey_type == "services":
            from app.db.ism_services_ai import promote_services_extraction

            return {
                **promote_services_extraction(con, extraction, source),
                "status": "ok",
            }
        from scripts.extract_ism_report_ai import _promote_factual_dashboard_outputs

        return {
            **_promote_factual_dashboard_outputs(con, extraction, snapshot, source),
            "status": "ok",
        }
    finally:
        con.close()
