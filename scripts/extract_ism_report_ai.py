import argparse
import asyncio
import json
import sys
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


def extract_or_load_factual_sections(
    con,
    report_text,
    source,
    client,
    force_sections=None,
    retry_failed=True,
):
    force_sections = set(force_sections or [])
    rows = []
    for section_name in ism_ai_extraction.FACTUAL_SECTION_NAMES:
        existing = growth_cycle.load_ism_ai_section_extraction(
            con,
            source["report_id"],
            source["source_url"],
            ism_ai_extraction.PROMPT_VERSION,
            section_name,
        )
        if not should_run_section(existing, force_sections, retry_failed):
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
    failed = [row for row in rows if row["status"] != "ok"]
    if failed:
        names = ", ".join(row["section_name"] for row in failed)
        raise ValueError(f"ism factual sections failed: {names}")
    return ism_ai_extraction.assemble_factual_payload_from_sections(rows)


def extract_snapshot(con, source_url, client, model):
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
    factual_payload = extract_or_load_factual_sections(
        con,
        report_text,
        source,
        client,
    )
    summary = ism_ai_extraction.generate_summary_from_facts(
        factual_payload,
        client,
    )
    payload = ism_ai_extraction.validate_extraction(
        {**factual_payload, "ai_summary": summary}
    )
    _check_report_id(payload["report"]["report_id"], expected_report_id, source_url)
    _check_report_month(
        payload["report"]["report_month"], expected_report_month, source_url
    )
    from scripts.fetch_ism_official_reports import (
        ai_at_a_glance_rows,
        ai_report_snapshot,
        ai_comments,
        merge_ai_metrics,
    )

    merge_ai_metrics(con, payload)
    growth_cycle.replace_ism_at_a_glance_rows(
        con,
        ai_at_a_glance_rows(payload, snapshot["source_url"], snapshot["source_hash"]),
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
    )
    saved = growth_cycle.replace_ism_ai_report_outputs(
        con,
        payload,
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


class OpenAIJsonClient:
    def __init__(self, client, model, max_attempts=3):
        self.client = client
        self.model = model
        self.max_attempts = max_attempts

    def complete_json(self, prompt):
        return asyncio.run(self.complete_json_async(prompt))

    async def complete_json_async(self, prompt):
        last_error = None
        for _attempt in range(self.max_attempts):
            try:
                stream = await self.client.chat.completions.create(
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
        raise last_error


def llm_timeout():
    return httpx.Timeout(connect=20.0, write=300.0, read=300.0, pool=20.0)


def build_client(config):
    client = llm.build_async_client(
        config,
        max_retries=0,
        timeout=llm_timeout(),
        error_context="ISM rich report extraction",
    )
    return OpenAIJsonClient(client, config["model"])


def main(argv=None, client_factory=build_client):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=growth_cycle.DEFAULT_DB_PATH)
    parser.add_argument("--source-url", action="append", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--openai-api-key", default="")
    parser.add_argument("--openai-base-url", default="")
    args = parser.parse_args(argv)
    config = llm.load_openai_config(args, root=ROOT)
    client = client_factory(config)
    con = us_rates_liquidity.connect(args.db_path)
    growth_cycle.init_db(con)
    failed = 0
    try:
        for source_url in args.source_url:
            try:
                result = extract_snapshot(con, source_url, client, config["model"])
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
