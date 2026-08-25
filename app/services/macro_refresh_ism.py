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
    from app.services.ism_services_ai_ingestion import stage_sections_without_db

    return await stage_sections_without_db(
        prepared,
        client,
        model,
        source_hash=prepared["source_hash"],
        updated_at=prepared["fetched_at"],
        checkpoints=prepared.get("checkpoints"),
    )


def _checkpoint_matches(snapshot, checkpoint, prompt_version):
    return (
        checkpoint.get("report_id") == snapshot.get("report_id")
        and checkpoint.get("source_url") == snapshot.get("source_url")
        and checkpoint.get("source_hash") == snapshot.get("source_hash")
        and checkpoint.get("prompt_version") == prompt_version
    )


def _checkpoint_prompt_versions(survey_type):
    if survey_type == "manufacturing":
        from app.tools import ism_ai_extraction

        return {
            section_name: ism_ai_extraction.PROMPT_VERSION
            for section_name in ism_ai_extraction.FACTUAL_SECTION_NAMES
        }
    if survey_type == "services":
        from app.tools.ism_services_ai_extraction import SECTION_PROMPT_VERSIONS

        return SECTION_PROMPT_VERSIONS
    raise ValueError(f"ism survey type is unsupported: {survey_type}")


def _matching_checkpoints(snapshot, survey_type, checkpoints):
    prompt_versions = _checkpoint_prompt_versions(survey_type)
    return [
        checkpoint
        for checkpoint in checkpoints
        if checkpoint.get("section_name") in prompt_versions
        and _checkpoint_matches(
            snapshot,
            checkpoint,
            prompt_versions[checkpoint["section_name"]],
        )
    ]


def _section_error(checkpoints):
    failed = [checkpoint for checkpoint in checkpoints if checkpoint["status"] != "ok"]
    if not failed:
        return None
    details = ", ".join(
        f"{checkpoint['section_name']} ({checkpoint.get('error') or 'unknown error'})"
        for checkpoint in failed
    )
    return f"ism factual sections failed: {details}"


def _stage_manufacturing_sections(snapshot, client, model, checkpoints):
    from app.tools import ism_ai_extraction
    from app.tools import ism_official_report
    from scripts import extract_ism_report_ai

    report_text = ism_official_report.extract_report_text(
        snapshot["raw_html"], snapshot.get("source_name", "ismworld")
    )
    existing_by_section = {
        checkpoint["section_name"]: checkpoint
        for checkpoint in checkpoints
        if _checkpoint_matches(snapshot, checkpoint, ism_ai_extraction.PROMPT_VERSION)
    }
    rows = []
    call_counts = {}
    for section_name in ism_ai_extraction.FACTUAL_SECTION_NAMES:
        existing = existing_by_section.get(section_name)
        if existing is not None:
            rows.append(dict(existing))
            call_counts[section_name] = 0
            continue
        attempt_count = (existing["attempt_count"] if existing else 0) + 1
        payload = {}
        error = None
        try:
            payload = extract_ism_report_ai.extract_one_section(
                report_text, client, section_name
            )
        except Exception as exc:
            error = str(exc)
        rows.append(
            {
                "report_id": snapshot["report_id"],
                "source_url": snapshot["source_url"],
                "report_month": snapshot["report_month"],
                "source_hash": snapshot["source_hash"],
                "section_name": section_name,
                "status": "ok" if error is None else "failed",
                "payload_json": payload,
                "error": error,
                "attempt_count": attempt_count,
                "model": model,
                "prompt_version": ism_ai_extraction.PROMPT_VERSION,
                "updated_at": snapshot["fetched_at"],
            }
        )
        call_counts[section_name] = 1
    error = _section_error(rows)
    if error:
        return None, call_counts, rows, error
    extraction = ism_ai_extraction.assemble_factual_payload_from_sections(rows)
    return extraction, call_counts, rows, None


def _prepare_failure(snapshot, survey_type, model, error, checkpoints, call_counts):
    return {
        "status": "failed",
        "survey_type": survey_type,
        "snapshot": dict(snapshot),
        "extraction": None,
        "call_counts": call_counts,
        "model": model,
        "source_url": snapshot.get("source_url"),
        "report_id": snapshot.get("report_id"),
        "report_month": snapshot.get("report_month"),
        "error": str(error),
        "checkpoints": checkpoints,
    }


def prepare_ism_enrichment(
    snapshot, *, client, model, survey_type, checkpoints=None
):
    checkpoints = [dict(checkpoint) for checkpoint in checkpoints or []]
    try:
        matching_checkpoints = _matching_checkpoints(
            snapshot, survey_type, checkpoints
        )
        existing_error = _section_error(matching_checkpoints)
        if existing_error:
            return _prepare_failure(
                snapshot,
                survey_type,
                model,
                existing_error,
                matching_checkpoints,
                {
                    checkpoint["section_name"]: 0
                    for checkpoint in matching_checkpoints
                },
            )
        if survey_type == "services":
            import asyncio
            import inspect

            prepared = _prepare_services(snapshot)
            result = _run_services_extraction(
                {
                    **prepared,
                    "source_hash": snapshot["source_hash"],
                    "fetched_at": snapshot["fetched_at"],
                    "checkpoints": checkpoints,
                },
                client,
                model,
            )
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            if isinstance(result, tuple):
                extraction, call_counts = result
                staged_checkpoints = checkpoints
                error = _section_error(staged_checkpoints)
            else:
                staged_checkpoints = result["checkpoints"]
                call_counts = result["call_counts"]
                error = result["error"]
                extraction = None
                if error is None:
                    from app.tools.ism_services_ai_extraction import (
                        assemble_factual_extraction,
                    )

                    extraction = assemble_factual_extraction(result["section_payloads"])
        elif survey_type == "manufacturing":
            extraction, call_counts, staged_checkpoints, error = (
                _stage_manufacturing_sections(
                    snapshot, client, model, checkpoints
                )
            )
        else:
            raise ValueError(f"ism survey type is unsupported: {survey_type}")
        if error:
            return _prepare_failure(
                snapshot,
                survey_type,
                model,
                error,
                staged_checkpoints,
                call_counts,
            )
        _validate_enrichment_identity(snapshot, extraction)
    except Exception as exc:
        return _prepare_failure(
            snapshot, survey_type, model, exc, checkpoints, {}
        )
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
        "checkpoints": staged_checkpoints,
    }


def load_ism_enrichment_checkpoints(db_path, snapshot, survey_type):
    prompt_versions = list(_checkpoint_prompt_versions(survey_type).values())
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    try:
        checkpoints = []
        for prompt_version in prompt_versions:
            checkpoints.extend(
                growth_cycle.load_ism_ai_section_extractions(
                    con,
                    snapshot["report_id"],
                    snapshot["source_url"],
                    prompt_version,
                )
            )
        return checkpoints
    finally:
        con.close()


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
        for checkpoint in prepared_extraction.get("checkpoints", []):
            growth_cycle.replace_ism_ai_section_extraction(con, checkpoint)
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
        if survey_type == "manufacturing":
            from app.tools.ism_ai_extraction import PROMPT_VERSION

            source["prompt_version"] = PROMPT_VERSION
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
