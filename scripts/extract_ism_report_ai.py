import argparse
import asyncio
import json
import sys
import threading
import time
import weakref
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm
from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.tools import ism_ai_extraction
from app.tools import ism_official_report


def _check_report_id(extracted_report_id, expected_report_id, source_url):
    if extracted_report_id != expected_report_id:
        raise ValueError(
            f"llm report_id mismatch for {source_url}: expected "
            f"{expected_report_id}, llm returned {extracted_report_id}"
        )


def _check_report_month(extracted_report_month, expected_report_month, source_url):
    if extracted_report_month != expected_report_month:
        raise ValueError(
            f"llm report_month mismatch for {source_url}: expected "
            f"{expected_report_month}, llm returned {extracted_report_month}"
        )


SUMMARY_PROMPT_VERSION = "ism-summary-from-validated-v1"


def log_progress(message):
    print(message, file=sys.stderr, flush=True)


def generate_or_load_summary(
    con,
    factual_payload,
    source,
    client,
    force_summary=False,
    guidance="",
):
    facts_digest = ism_ai_extraction.facts_hash(factual_payload)
    existing = growth_cycle.load_latest_ism_ai_summary_run(
        con,
        source["report_id"],
    )
    if (
        existing
        and existing["status"] == "ok"
        and existing["quality_status"] == "accepted"
        and existing["facts_hash"] == facts_digest
        and not force_summary
        and not guidance
    ):
        return existing["summary_json"]
    try:
        summary = ism_ai_extraction.generate_summary_from_facts(
            factual_payload,
            client,
            guidance=guidance,
        )
        status = "ok"
        quality_status = "accepted"
        error = None
        summary_text = summary["summary_text"]
    except Exception as exc:
        summary = {}
        status = "failed"
        quality_status = "needs_review"
        error = str(exc)
        summary_text = ""
    growth_cycle.replace_ism_ai_summary_run(
        con,
        {
            "report_id": source["report_id"],
            "report_month": source["report_month"],
            "source_hash": source["source_hash"],
            "facts_hash": facts_digest,
            "status": status,
            "quality_status": quality_status,
            "summary_text": summary_text,
            "summary_json": summary,
            "guidance": guidance,
            "error": error,
            "attempt_count": (existing["attempt_count"] if existing else 0) + 1,
            "model": source["model"],
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "updated_at": source["updated_at"],
        },
    )
    if status != "ok":
        raise ValueError(error)
    return summary


def extract_one_section(report_text, client, section_name):
    section_name, section_text, prompt, model = (
        ism_ai_extraction.factual_section_definition(section_name, report_text)
    )
    return ism_ai_extraction.extract_section_with_client(
        section_text,
        client,
        section_name,
        prompt,
        model,
    )


def should_run_section(existing, force_sections, retry_failed):
    if existing is None:
        return True
    if existing["section_name"] in force_sections:
        return True
    if existing["status"] == "failed" and retry_failed:
        return True
    return existing["status"] != "ok"


def should_reuse_section(existing, force_sections, retry_failed, report_text):
    if should_run_section(existing, force_sections, retry_failed):
        return False, None
    if existing["section_name"] != "industry_signals":
        return True, None
    section_text = ism_ai_extraction.report_section_texts(report_text)[
        "industry_signals"
    ]
    try:
        ism_ai_extraction._validate_industry_signals_against_source(
            existing["payload_json"],
            section_text,
        )
    except ValueError as exc:
        return False, str(exc)
    return True, None


def extract_or_load_factual_sections(
    con,
    report_text,
    source,
    client,
    force_sections=None,
    retry_failed=True,
    sections=None,
):
    section_names = sections or ism_ai_extraction.FACTUAL_SECTION_NAMES
    force_sections = set(force_sections or [])
    rows = []
    for section_name in section_names:
        existing = growth_cycle.load_ism_ai_section_extraction(
            con,
            source["report_id"],
            source["source_url"],
            ism_ai_extraction.PROMPT_VERSION,
            section_name,
        )
        reuse, _reuse_error = should_reuse_section(
            existing,
            force_sections,
            retry_failed,
            report_text,
        )
        if reuse:
            rows.append(existing)
            continue
        attempt_count = (existing["attempt_count"] if existing else 0) + 1
        try:
            section_payload = extract_one_section(report_text, client, section_name)
            status = "ok"
            error = None
        except Exception as exc:
            section_payload = {}
            status = "failed"
            error = str(exc)
        checkpoint = {
            "report_id": source["report_id"],
            "source_url": source["source_url"],
            "report_month": source["report_month"],
            "source_hash": source["source_hash"],
            "section_name": section_name,
            "status": status,
            "payload_json": section_payload,
            "error": error,
            "attempt_count": attempt_count,
            "model": source["model"],
            "prompt_version": ism_ai_extraction.PROMPT_VERSION,
            "updated_at": source["updated_at"],
        }
        growth_cycle.replace_ism_ai_section_extraction(con, checkpoint)
        rows.append(checkpoint)
    if sections is not None:
        rows = growth_cycle.load_ism_ai_section_extractions(
            con,
            source["report_id"],
            source["source_url"],
            ism_ai_extraction.PROMPT_VERSION,
        )
    failed = [row for row in rows if row["status"] != "ok"]
    if failed:
        details = ", ".join(
            f"{row['section_name']} ({row['error'] or 'unknown error'})"
            for row in failed
        )
        raise ValueError(f"ism factual sections failed: {details}")
    return ism_ai_extraction.assemble_factual_payload_from_sections(rows)


async def extract_or_load_factual_sections_async(
    con,
    report_text,
    source,
    client,
    force_sections=None,
    retry_failed=True,
    sections=None,
    max_concurrency=3,
    progress=None,
):
    section_names = sections or ism_ai_extraction.FACTUAL_SECTION_NAMES
    force_sections = set(force_sections or [])
    pending = []
    rows_map = {}
    for section_name in section_names:
        existing = growth_cycle.load_ism_ai_section_extraction(
            con,
            source["report_id"],
            source["source_url"],
            ism_ai_extraction.PROMPT_VERSION,
            section_name,
        )
        reuse, reuse_error = should_reuse_section(
            existing,
            force_sections,
            retry_failed,
            report_text,
        )
        if reuse:
            rows_map[section_name] = existing
            continue
        if progress and reuse_error:
            progress(
                f"section {section_name} checkpoint rejected error={reuse_error}"
            )
        pending.append((section_name, existing))

    if progress:
        reused_count = len(section_names) - len(pending)
        progress(
            f"section extraction pending={len(pending)} reused={reused_count} "
            f"concurrency={max_concurrency}"
        )

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(report_text, client, section_name):
        async with semaphore:
            return await asyncio.to_thread(
                extract_one_section, report_text, client, section_name
            )

    async def run_pending(section_name, existing):
        attempt_count = (existing["attempt_count"] if existing else 0) + 1
        started = time.perf_counter()
        if progress:
            progress(f"section {section_name} started")
        try:
            section_payload = await _run_one(report_text, client, section_name)
            status = "ok"
            error = None
        except Exception as exc:
            section_payload = {}
            status = "failed"
            error = str(exc)
        if progress:
            elapsed = time.perf_counter() - started
            message = f"section {section_name} {status} {elapsed:.1f}s"
            if error:
                message = f"{message} error={error}"
            progress(message)
        checkpoint = {
            "report_id": source["report_id"],
            "source_url": source["source_url"],
            "report_month": source["report_month"],
            "source_hash": source["source_hash"],
            "section_name": section_name,
            "status": status,
            "payload_json": section_payload,
            "error": error,
            "attempt_count": attempt_count,
            "model": source["model"],
            "prompt_version": ism_ai_extraction.PROMPT_VERSION,
            "updated_at": source["updated_at"],
        }
        growth_cycle.replace_ism_ai_section_extraction(con, checkpoint)
        return checkpoint

    results = await asyncio.gather(
        *[run_pending(section_name, existing) for section_name, existing in pending]
    )
    for checkpoint in results:
        rows_map[checkpoint["section_name"]] = checkpoint

    rows = [rows_map[name] for name in section_names]
    if sections is not None:
        rows = growth_cycle.load_ism_ai_section_extractions(
            con,
            source["report_id"],
            source["source_url"],
            ism_ai_extraction.PROMPT_VERSION,
        )
    failed = [row for row in rows if row["status"] != "ok"]
    if failed:
        details = ", ".join(
            f"{row['section_name']} ({row['error'] or 'unknown error'})"
            for row in failed
        )
        raise ValueError(f"ism factual sections failed: {details}")
    return ism_ai_extraction.assemble_factual_payload_from_sections(rows)


def _load_factual_payload_from_stored(con, source):
    rows = growth_cycle.load_ism_ai_section_extractions(
        con,
        source["report_id"],
        source["source_url"],
        ism_ai_extraction.PROMPT_VERSION,
    )
    if not rows:
        raise ValueError(f"no stored factual sections for {source['report_id']}")
    return ism_ai_extraction.assemble_factual_payload_from_sections(rows)


def _write_rejected_summary_run(con, factual_payload, source, reason):
    facts_digest = ism_ai_extraction.facts_hash(factual_payload)
    existing = growth_cycle.load_latest_ism_ai_summary_run(con, source["report_id"])
    growth_cycle.replace_ism_ai_summary_run(
        con,
        {
            "report_id": source["report_id"],
            "report_month": source["report_month"],
            "source_hash": source["source_hash"],
            "facts_hash": facts_digest,
            "status": "ok",
            "quality_status": "rejected",
            "summary_text": existing["summary_text"] if existing else "",
            "summary_json": existing["summary_json"] if existing else {},
            "guidance": "",
            "error": reason,
            "attempt_count": (existing["attempt_count"] if existing else 0) + 1,
            "model": source["model"],
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "updated_at": source["updated_at"],
        },
    )


def _save_factual_dashboard_outputs(con, payload, snapshot, commit=True):
    from scripts.fetch_ism_official_reports import (
        ai_at_a_glance_rows,
        ai_comments,
        ai_report_snapshot,
        merge_ai_metrics,
    )

    merge_ai_metrics(con, payload, commit=commit)
    growth_cycle.replace_ism_at_a_glance_rows(
        con, ai_at_a_glance_rows(
            payload, snapshot["source_url"], snapshot["source_hash"]
        ), commit=commit
    )
    growth_cycle.replace_ism_report_snapshot(
        con,
        ai_report_snapshot(
            payload,
            snapshot["source_url"],
            snapshot["source_hash"],
            snapshot["fetched_at"],
        ),
        ai_comments(payload, snapshot["source_url"], snapshot["source_hash"]),
        commit=commit,
    )


def _promote_factual_dashboard_outputs(con, payload, snapshot, source):
    con.execute("begin")
    try:
        _save_factual_dashboard_outputs(con, payload, snapshot, commit=False)
        saved = growth_cycle.replace_ism_ai_report_outputs(
            con,
            payload,
            source,
            commit=False,
        )
        con.commit()
        return saved
    except BaseException:
        con.rollback()
        raise


def extract_snapshot(
    con,
    source_url,
    client,
    model,
    sections=None,
    retry_failed=True,
    force_sections=None,
    facts_only=False,
    summary_only=False,
    force_summary=False,
    summary_guidance="",
    reject_summary_reason="",
):
    log_progress(f"snapshot loading url={source_url}")
    snapshot = growth_cycle.load_ism_report_source_snapshot(con, source_url)
    if not snapshot:
        raise ValueError(f"ism source snapshot is missing: {source_url}")
    report_text = ism_official_report.extract_report_text(
        snapshot["raw_html"],
        snapshot["source_name"],
    )
    snapshot_report_id = snapshot.get("report_id")
    if snapshot_report_id:
        expected_report_id = snapshot_report_id
        expected_report_month = snapshot["report_month"]
    else:
        try:
            expected_report_month, _month_name, _year = (
                ism_official_report.report_month_from_title(report_text)
            )
            expected_report_id = ism_official_report.report_id(expected_report_month)
        except ism_official_report.IsmReportUnavailable as exc:
            raise ValueError(
                f"cannot verify llm report_id: snapshot {source_url} has no "
                f"report_id and title could not be parsed: {exc}"
            ) from exc
    source = {
        "report_id": expected_report_id,
        "report_month": expected_report_month,
        "source_url": snapshot["source_url"],
        "source_hash": snapshot["source_hash"],
        "model": model,
        "updated_at": snapshot["fetched_at"],
    }
    requested_sections = sections or ism_ai_extraction.FACTUAL_SECTION_NAMES
    log_progress(
        f"snapshot loaded report_id={expected_report_id} "
        f"report_month={expected_report_month} sections={','.join(requested_sections)}"
    )
    if summary_only:
        log_progress("stored factual sections loading")
        factual_payload = _load_factual_payload_from_stored(con, source)
    else:
        factual_payload = asyncio.run(
            extract_or_load_factual_sections_async(
                con,
                report_text,
                source,
                client,
                force_sections=force_sections,
                retry_failed=retry_failed,
                sections=sections,
                progress=log_progress,
            )
        )
    if reject_summary_reason:
        _write_rejected_summary_run(con, factual_payload, source, reject_summary_reason)
        if not summary_guidance:
            payload = ism_ai_extraction.validate_factual_extraction(factual_payload)
            _check_report_id(
                payload["report"]["report_id"], expected_report_id, source_url
            )
            _check_report_month(
                payload["report"]["report_month"], expected_report_month, source_url
            )
            return {
                "report_id": payload["report"]["report_id"],
                "industry_signals": len(payload.get("industry_signals", [])),
            }
    if facts_only:
        payload = ism_ai_extraction.validate_factual_extraction(factual_payload)
        _check_report_id(payload["report"]["report_id"], expected_report_id, source_url)
        _check_report_month(
            payload["report"]["report_month"], expected_report_month, source_url
        )
        saved = _promote_factual_dashboard_outputs(
            con,
            payload,
            snapshot,
            {
                "source_url": snapshot["source_url"],
                "source_hash": snapshot["source_hash"],
                "model": model,
                "prompt_version": ism_ai_extraction.PROMPT_VERSION,
            },
        )
        log_progress(
            f"facts saved report_id={payload['report']['report_id']} "
            f"industry_signals={saved['industry_signals']}"
        )
        return {
            "report_id": payload["report"]["report_id"],
            "industry_signals": saved["industry_signals"],
        }
    summary = generate_or_load_summary(
        con,
        factual_payload,
        source,
        client,
        force_summary=force_summary,
        guidance=summary_guidance,
    )
    payload = ism_ai_extraction.validate_extraction(
        {**factual_payload, "ai_summary": summary}
    )
    _check_report_id(payload["report"]["report_id"], expected_report_id, source_url)
    _check_report_month(
        payload["report"]["report_month"], expected_report_month, source_url
    )
    saved = _promote_factual_dashboard_outputs(
        con,
        payload,
        snapshot,
        {
            "source_url": snapshot["source_url"],
            "source_hash": snapshot["source_hash"],
            "model": model,
            "prompt_version": ism_ai_extraction.PROMPT_VERSION,
        },
    )
    return {
        "report_id": payload["report"]["report_id"],
        "industry_signals": saved["industry_signals"],
    }


def extract_snapshot_with_options(
    con,
    source_url,
    client,
    model,
    sections=None,
    retry_failed=True,
    force_sections=None,
    facts_only=False,
    summary_only=False,
    force_summary=False,
    summary_guidance="",
    reject_summary_reason="",
):
    if sections and summary_only:
        raise ValueError("--section cannot be combined with --summary-only")
    if facts_only and summary_only:
        raise ValueError("--facts-only cannot be combined with --summary-only")
    return extract_snapshot(
        con,
        source_url,
        client,
        model,
        sections=sections,
        retry_failed=retry_failed,
        force_sections=force_sections,
        facts_only=facts_only,
        summary_only=summary_only,
        force_summary=force_summary,
        summary_guidance=summary_guidance,
        reject_summary_reason=reject_summary_reason,
    )


class OpenAIJsonClient:
    def __init__(
        self,
        client,
        model,
        max_attempts=3,
        client_factory=None,
        progress=None,
    ):
        self.client = client
        self.model = model
        self.max_attempts = max_attempts
        self.client_factory = client_factory
        self.progress = progress
        self._clients_by_loop = weakref.WeakKeyDictionary()
        self._client_lock = threading.Lock()

    def _client_for_current_loop(self):
        if self.client_factory is None:
            return self.client
        loop = asyncio.get_running_loop()
        with self._client_lock:
            client = self._clients_by_loop.get(loop)
            if client is None:
                client = self.client_factory()
                self._clients_by_loop[loop] = client
            return client

    def complete_json(self, prompt):
        return asyncio.run(self.complete_json_async(prompt))

    async def complete_json_async(self, prompt):
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            if self.progress:
                self.progress(f"llm attempt={attempt}/{self.max_attempts} started")
            try:
                stream = await self._client_for_current_loop().chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    stream=True,
                )
                chunks = []
                async for chunk in stream:
                    for choice in chunk.choices:
                        content = choice.delta.content
                        if content:
                            chunks.append(content)
                return json.loads("".join(chunks))
            except Exception as exc:
                last_error = exc
                if self.progress:
                    self.progress(
                        f"llm attempt={attempt}/{self.max_attempts} failed error={exc}"
                    )
        raise last_error


def llm_timeout():
    return httpx.Timeout(connect=20.0, write=300.0, read=300.0, pool=20.0)


def build_client(config):
    def client_factory():
        return llm.build_async_client(
            config,
            max_retries=0,
            timeout=llm_timeout(),
            error_context="ISM rich report extraction",
        )

    return OpenAIJsonClient(
        client_factory(),
        config["model"],
        client_factory=client_factory,
        progress=log_progress,
    )


def main(argv=None, client_factory=build_client):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=growth_cycle.DEFAULT_DB_PATH)
    parser.add_argument("--source-url", action="append", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--openai-api-key", default=None)
    parser.add_argument("--openai-base-url", default=None)
    parser.add_argument(
        "--section", action="append", choices=ism_ai_extraction.FACTUAL_SECTION_NAMES
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--force-section",
        action="append",
        choices=ism_ai_extraction.FACTUAL_SECTION_NAMES,
    )
    parser.add_argument("--facts-only", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--force-summary", action="store_true")
    parser.add_argument("--summary-guidance", default="")
    parser.add_argument("--reject-summary", default="")
    args = parser.parse_args(argv)
    config = llm.load_openai_config(args, root=ROOT)
    client = client_factory(config)
    con = us_rates_liquidity.connect(args.db_path)
    growth_cycle.init_db(con)
    failed = 0
    try:
        for source_url in args.source_url:
            try:
                result = extract_snapshot_with_options(
                    con,
                    source_url,
                    client,
                    config["model"],
                    sections=args.section,
                    retry_failed=args.retry_failed,
                    force_sections=args.force_section,
                    facts_only=args.facts_only,
                    summary_only=args.summary_only,
                    force_summary=args.force_summary,
                    summary_guidance=args.summary_guidance,
                    reject_summary_reason=args.reject_summary,
                )
                print(
                    f"{result['report_id']}: "
                    f"industry_signals={result['industry_signals']}"
                )
            except Exception as exc:
                failed += 1
                print(f"{source_url}: failed - {exc}", file=sys.stderr)
        return 1 if failed else 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
