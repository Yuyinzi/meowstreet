import asyncio
import hashlib
import json
from datetime import datetime, timezone


def _source_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _checkpoint_key(checkpoint):
    return (
        checkpoint["report_id"],
        checkpoint["source_url"],
        checkpoint["prompt_version"],
        checkpoint["section_name"],
    )


def _load_existing_checkpoints(
    con, report_id, source_url, prompt_versions, source_hash
):
    existing = {}
    for section_name, prompt_version in prompt_versions.items():
        row = load_ism_ai_section_extraction(
            con, report_id, source_url, prompt_version, section_name
        )
        if row is not None:
            existing[_checkpoint_key(row)] = row
    return existing


from app.db.growth_cycle import (
    load_ism_ai_section_extraction,
    replace_ism_ai_section_extraction,
)


async def extract_sections(
    con,
    client,
    prepared_report,
    section_names,
    prompt_versions,
    build_prompt,
    response_model_for_section,
    validate_section,
    section_concurrency=3,
):
    report_id = prepared_report["report_id"]
    report_month = prepared_report["report_month"]
    source_url = prepared_report["source_url"]
    source_text = prepared_report["source_text"]
    content_hash = _source_hash(source_text)
    updated_at = _now()

    existing = _load_existing_checkpoints(
        con, report_id, source_url, prompt_versions, content_hash
    )

    section_results = {}
    semaphore = asyncio.Semaphore(section_concurrency)

    async def process_section(section_name):
        prompt_version = prompt_versions[section_name]
        key = (report_id, source_url, prompt_version, section_name)
        existing_chk = existing.get(key)

        if existing_chk is not None:
            if (
                existing_chk["status"] == "ok"
                and existing_chk["source_hash"] == content_hash
            ):
                try:
                    raw = existing_chk["payload_json"]
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                    validated = validate_section(section_name, payload, source_text)
                    return section_name, validated, False
                except (ValueError, json.JSONDecodeError, TypeError):
                    pass

        prompt = build_prompt(section_name, source_text)
        model_name = getattr(client, "model", "default")

        async with semaphore:
            try:
                response = await client.request_structured_output(prompt)
                parsed = json.loads(response) if isinstance(response, str) else response
                validated = validate_section(section_name, parsed, source_text)
                status = "ok"
                error = None
            except BaseException as exc:
                validated = None
                status = "failed"
                error = str(exc)

            checkpoint = {
                "report_id": report_id,
                "source_url": source_url,
                "report_month": report_month,
                "source_hash": content_hash,
                "section_name": section_name,
                "status": status,
                "payload_json": validated if validated is not None else {},
                "error": error,
                "attempt_count": 1,
                "model": model_name,
                "prompt_version": prompt_version,
                "updated_at": updated_at,
            }
            replace_ism_ai_section_extraction(con, checkpoint)

            if validated is not None:
                return section_name, validated, True
            raise ValueError(f"section {section_name} extraction failed: {error}")

    tasks = [process_section(name) for name in section_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    section_payloads = []
    call_counts = {}
    for section_name, result in zip(section_names, results):
        if isinstance(result, BaseException):
            raise ValueError(f"section {section_name} extraction error") from result
        sname, payload, called = result
        section_payloads.append({"section_name": sname, "payload": payload})
        call_counts[sname] = 1 if called else 0

    return {
        "section_payloads": section_payloads,
        "call_counts": call_counts,
    }
