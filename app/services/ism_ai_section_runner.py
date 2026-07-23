import asyncio
import hashlib
import json
import time
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
    progress=None,
    heartbeat_interval=15.0,
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

    def report_progress(message):
        if progress is not None:
            progress(message)

    reusable = {}
    for section_name in section_names:
        prompt_version = prompt_versions[section_name]
        key = (report_id, source_url, prompt_version, section_name)
        existing_checkpoint = existing.get(key)
        if existing_checkpoint is None:
            continue
        if existing_checkpoint["status"] != "ok":
            continue
        if existing_checkpoint["source_hash"] != content_hash:
            continue
        try:
            raw = existing_checkpoint["payload_json"]
            payload = json.loads(raw) if isinstance(raw, str) else raw
            reusable[section_name] = validate_section(
                section_name, payload, source_text
            )
        except (ValueError, json.JSONDecodeError, TypeError):
            report_progress(f"section {section_name} checkpoint rejected")

    report_progress(
        f"section extraction pending={len(section_names) - len(reusable)} "
        f"reused={len(reusable)} concurrency={section_concurrency}"
    )

    section_results = {}
    semaphore = asyncio.Semaphore(section_concurrency)

    async def process_section(section_name):
        if section_name in reusable:
            report_progress(f"section {section_name} reused checkpoint")
            return section_name, reusable[section_name], False

        prompt_version = prompt_versions[section_name]
        prompt = build_prompt(section_name, source_text)
        model_name = getattr(client, "model", "default")

        async with semaphore:
            started = time.perf_counter()
            report_progress(
                f"section {section_name} started prompt_chars={len(prompt)}"
            )

            async def emit_heartbeats():
                while True:
                    await asyncio.sleep(heartbeat_interval)
                    elapsed = time.perf_counter() - started
                    report_progress(
                        f"section {section_name} running elapsed={elapsed:.1f}s"
                    )

            heartbeat = None
            if progress is not None and heartbeat_interval > 0:
                heartbeat = asyncio.create_task(emit_heartbeats())
            try:
                response = await client.complete_json_async(prompt)
                parsed = json.loads(response) if isinstance(response, str) else response
                validated = validate_section(section_name, parsed, source_text)
                status = "ok"
                error = None
            except BaseException as exc:
                validated = None
                status = "failed"
                error = str(exc)
            finally:
                if heartbeat is not None:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)

            elapsed = time.perf_counter() - started

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
                report_progress(f"section {section_name} ok {elapsed:.1f}s")
                return section_name, validated, True
            report_progress(
                f"section {section_name} failed {elapsed:.1f}s "
                f"error={error[:300]}"
            )
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
