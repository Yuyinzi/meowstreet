import asyncio
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.ism_ai_section_runner import extract_sections


ROOT = Path(__file__).resolve().parents[1]


class FakeAiClient:
    def __init__(self, responses=None):
        self.model = "test-model"
        self.call_count = 0
        self.responses = responses or {}

    async def complete_json_async(self, prompt):
        self.call_count += 1
        for key, response in self.responses.items():
            if key in prompt:
                return response
        return {"error": "no matching response"}


class SequenceAiClient:
    def __init__(self, responses):
        self.model = "test-model"
        self.responses = list(responses)
        self.prompts = []

    async def complete_json_async(self, prompt):
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


SERVICES_COMPONENTS = sorted(
    [
        "ism_services_pmi",
        "ism_services_business_activity",
        "ism_services_new_orders",
        "ism_services_employment",
        "ism_services_supplier_deliveries",
        "ism_services_inventories",
        "ism_services_inventory_sentiment",
        "ism_services_prices",
        "ism_services_order_backlog",
        "ism_services_new_export_orders",
        "ism_services_imports",
    ]
)


def _valid_at_a_glance_rows():
    return [
        {
            "series_id": sid,
            "label": sid.replace("ism_services_", "").replace("_", " ").title(),
            "current_value": 50.0 + i,
            "previous_value": 49.0 + i,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        }
        for i, sid in enumerate(SERVICES_COMPONENTS)
    ]


SECTION_RESPONSES = {
    "report": {
        "report": {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_name": "ismworld",
            "source_url": "https://example.test/services/",
        }
    },
    "at_a_glance_rows": {"at_a_glance_rows": _valid_at_a_glance_rows()},
    "industry_signals": {"industry_signals": []},
    "comments_commodities": {"respondent_comments": [], "commodities": []},
    "narrative_facts": {
        "narrative_facts": {
            "consecutive_expansion_months": None,
            "services_economy_gdp_share_percent": None,
            "broad_based_expansion_mentioned": False,
            "inflationary_pressure_mentioned": False,
        }
    },
}

SECTION_NAMES = [
    "report",
    "at_a_glance_rows",
    "industry_signals",
    "comments_commodities",
    "narrative_facts",
]

PROMPT_VERSIONS = {
    "report": "ism-services-report-v1",
    "at_a_glance_rows": "ism-services-glance-v1",
    "industry_signals": "ism-services-industries-v1",
    "comments_commodities": "ism-services-comments-v1",
    "narrative_facts": "ism-services-narrative-v1",
}


def _fake_build_prompt(section_name, source_text):
    return f"extract {section_name} from: {source_text[:50]}"


def _fake_validate(section_name, payload, source_text):
    from app.tools.ism_services_ai_extraction import validate_section_payload

    return validate_section_payload(section_name, payload, source_text)


def _fake_model_for_section(section_name):
    from app.tools.ism_services_ai_extraction import SECTION_RESPONSE_MODELS

    return SECTION_RESPONSE_MODELS[section_name]


@pytest.fixture
def db_conn(tmp_path):
    db_path = tmp_path / "test.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    _init_ai_section_tables(con)
    yield con
    con.close()


def _init_ai_section_tables(con):
    con.executescript(
        """
        create table if not exists ism_ai_section_extractions (
            report_id text not null,
            source_url text not null,
            report_month text not null,
            source_hash text not null,
            section_name text not null,
            status text not null,
            payload_json text not null,
            error text,
            attempt_count integer not null,
            model text not null,
            prompt_version text not null,
            updated_at text not null,
            primary key(report_id, source_url, prompt_version, section_name)
        );
        """
    )
    con.commit()


@pytest.fixture
def prepared_report():
    return {
        "report_id": "ism_services_2026_06",
        "report_month": "2026-06-01",
        "source_url": "https://example.test/services/",
        "source_name": "ismworld",
        "fetched_at": "2026-07-03T14:00:00Z",
        "source_text": (
            "June 2026 ISM Services PMI Report "
            "Services PMI registered 50.0 percent. "
            "Business Activity Index at 51.0 percent. "
            "New Orders Index at 52.0 percent. "
            "Employment Index at 53.0 percent. "
            "Supplier Deliveries Index at 54.0 percent. "
            "Inventories Index at 55.0 percent. "
            "Inventory Sentiment Index at 56.0 percent. "
            "Prices Index at 57.0 percent. "
            "Backlog of Orders Index at 58.0 percent. "
            "New Export Orders Index at 59.0 percent. "
            "Imports Index at 60.0 percent. "
            "SERVICES AT A GLANCE "
            "Services PMI 50.0 49.0 +1.0 Growing Faster 1 "
            "Business Activity 51.0 50.0 +1.0 Growing Faster 1 "
            "New Orders 52.0 51.0 +1.0 Growing Faster 1 "
            "Employment 53.0 52.0 +1.0 Growing Faster 1 "
            "Supplier Deliveries 54.0 53.0 +1.0 Slowing Faster 1 "
            "Inventories 55.0 54.0 +1.0 Growing From Contracting 1 "
            "Inventory Sentiment 56.0 55.0 +1.0 Too Low Faster 1 "
            "Prices 57.0 56.0 +1.0 Increasing Faster 1 "
            "Backlog of Orders 58.0 57.0 +1.0 Growing Faster 2 "
            "New Export Orders 59.0 58.0 +1.0 Growing Faster 1 "
            "Imports 60.0 59.0 +1.0 Growing Faster 1 "
            "INDUSTRY PERFORMANCE "
            "The 2 services industries reporting growth in June are: "
            "Construction; and Retail Trade. "
            "COMMODITIES REPORTED "
            "Commodities Up in Price: Construction Labor; Fuel "
            "Tempe, Arizona narrative paragraph here."
        ),
    }


@pytest.mark.asyncio
async def test_first_run_calls_all_five_sections(db_conn, prepared_report):
    client = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert len(result["section_payloads"]) == 5
    assert client.call_count == 5
    for sp in result["section_payloads"]:
        assert "payload" in sp
        assert "section_name" in sp


@pytest.mark.asyncio
async def test_second_run_makes_zero_calls(db_conn, prepared_report):
    client = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert client.call_count == 5

    client2 = FakeAiClient(SECTION_RESPONSES)
    result2 = await extract_sections(
        db_conn,
        client2,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert client2.call_count == 0
    assert len(result2["section_payloads"]) == 5


@pytest.mark.asyncio
async def test_section_progress_names_work_and_emits_heartbeats(
    db_conn, prepared_report
):
    messages = []

    class SlowAiClient(FakeAiClient):
        async def complete_json_async(self, prompt):
            await asyncio.sleep(0.03)
            return await super().complete_json_async(prompt)

    await extract_sections(
        db_conn,
        SlowAiClient(SECTION_RESPONSES),
        prepared_report,
        ["report"],
        {"report": PROMPT_VERSIONS["report"]},
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=1,
        progress=messages.append,
        heartbeat_interval=0.01,
    )

    assert any(
        "section extraction pending=1 reused=0 concurrency=1" in m for m in messages
    )
    assert any("section report started prompt_chars=" in m for m in messages)
    assert any("section report running elapsed=" in m for m in messages)
    assert any("section report ok" in m for m in messages)


@pytest.mark.asyncio
async def test_section_progress_reports_checkpoint_reuse(db_conn, prepared_report):
    client = FakeAiClient(SECTION_RESPONSES)
    await extract_sections(
        db_conn,
        client,
        prepared_report,
        ["report"],
        {"report": PROMPT_VERSIONS["report"]},
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=1,
    )
    messages = []

    await extract_sections(
        db_conn,
        FakeAiClient(SECTION_RESPONSES),
        prepared_report,
        ["report"],
        {"report": PROMPT_VERSIONS["report"]},
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=1,
        progress=messages.append,
    )

    assert "section extraction pending=0 reused=1 concurrency=1" in messages
    assert "section report reused checkpoint" in messages


@pytest.mark.asyncio
async def test_changing_one_prompt_version_reruns_only_that_section(
    db_conn, prepared_report
):
    client = FakeAiClient(SECTION_RESPONSES)
    await extract_sections(
        db_conn,
        client,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )

    modified_versions = dict(PROMPT_VERSIONS)
    modified_versions["industry_signals"] = "ism-services-industries-v2"
    client2 = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client2,
        prepared_report,
        SECTION_NAMES,
        modified_versions,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert client2.call_count == 1
    call_sections = [sp["section_name"] for sp in result["section_payloads"]]
    assert "industry_signals" in call_sections


@pytest.mark.asyncio
async def test_changed_source_hash_reruns_all_sections(db_conn, prepared_report):
    client = FakeAiClient(SECTION_RESPONSES)
    await extract_sections(
        db_conn,
        client,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )

    modified = dict(prepared_report)
    modified["source_text"] = prepared_report["source_text"] + " new content"
    client2 = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client2,
        modified,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert client2.call_count == 5


@pytest.mark.asyncio
async def test_different_source_url_does_not_reuse_checkpoints(
    db_conn, prepared_report
):
    client = FakeAiClient(SECTION_RESPONSES)
    await extract_sections(
        db_conn,
        client,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )

    different_url = dict(prepared_report)
    different_url["source_url"] = "https://different.example/services/"
    client2 = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client2,
        different_url,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert client2.call_count == 5


@pytest.mark.asyncio
async def test_invalid_saved_payload_is_re_extracted(db_conn, prepared_report):
    from app.db.growth_cycle import replace_ism_ai_section_extraction

    invalid_checkpoint = {
        "report_id": prepared_report["report_id"],
        "source_url": prepared_report["source_url"],
        "report_month": prepared_report["report_month"],
        "source_hash": "deadbeef",
        "section_name": "report",
        "status": "ok",
        "payload_json": {"bad": "data"},
        "error": None,
        "attempt_count": 1,
        "model": "test-model",
        "prompt_version": PROMPT_VERSIONS["report"],
        "updated_at": "2026-07-03T14:00:00Z",
    }
    replace_ism_ai_section_extraction(db_conn, invalid_checkpoint)

    client = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert len(result["section_payloads"]) == 5
    assert (
        result["section_payloads"][0]["payload"]["report"]["report_id"]
        == "ism_services_2026_06"
    )


@pytest.mark.asyncio
async def test_failed_call_preserves_successful_checkpoints_for_retry(
    db_conn, prepared_report
):
    successful_responses = {
        k: v for k, v in SECTION_RESPONSES.items() if k != "narrative_facts"
    }
    client = FakeAiClient(successful_responses)
    with pytest.raises(ValueError):
        await extract_sections(
            db_conn,
            client,
            prepared_report,
            SECTION_NAMES,
            PROMPT_VERSIONS,
            _fake_build_prompt,
            _fake_model_for_section,
            _fake_validate,
            section_concurrency=5,
        )

    client2 = FakeAiClient(SECTION_RESPONSES)
    result = await extract_sections(
        db_conn,
        client2,
        prepared_report,
        SECTION_NAMES,
        PROMPT_VERSIONS,
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=5,
    )
    assert len(result["section_payloads"]) == 5
    assert client2.call_count == 1


@pytest.mark.asyncio
async def test_schema_invalid_response_is_repaired_once(db_conn, prepared_report):
    invalid = deepcopy(SECTION_RESPONSES["at_a_glance_rows"])
    invalid["at_a_glance_rows"][0]["trend_months"] = None
    client = SequenceAiClient([invalid, SECTION_RESPONSES["at_a_glance_rows"]])

    result = await extract_sections(
        db_conn,
        client,
        prepared_report,
        ["at_a_glance_rows"],
        {"at_a_glance_rows": PROMPT_VERSIONS["at_a_glance_rows"]},
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=1,
    )

    assert len(client.prompts) == 2
    assert "failed validation" in client.prompts[1]
    assert "trend_months" in client.prompts[1]
    assert result["call_counts"]["at_a_glance_rows"] == 2
    checkpoint = db_conn.execute(
        "select status, attempt_count, error from ism_ai_section_extractions "
        "where section_name = 'at_a_glance_rows'"
    ).fetchone()
    assert dict(checkpoint) == {
        "status": "ok",
        "attempt_count": 2,
        "error": None,
    }


@pytest.mark.asyncio
async def test_valid_response_uses_one_attempt(db_conn, prepared_report):
    client = SequenceAiClient([SECTION_RESPONSES["at_a_glance_rows"]])

    result = await extract_sections(
        db_conn,
        client,
        prepared_report,
        ["at_a_glance_rows"],
        {"at_a_glance_rows": PROMPT_VERSIONS["at_a_glance_rows"]},
        _fake_build_prompt,
        _fake_model_for_section,
        _fake_validate,
        section_concurrency=1,
    )

    assert len(client.prompts) == 1
    assert result["call_counts"]["at_a_glance_rows"] == 1
    checkpoint = db_conn.execute(
        "select attempt_count from ism_ai_section_extractions "
        "where section_name = 'at_a_glance_rows'"
    ).fetchone()
    assert checkpoint["attempt_count"] == 1


@pytest.mark.asyncio
async def test_provider_failure_is_not_retried_as_validation_repair(
    db_conn, prepared_report
):
    client = SequenceAiClient([RuntimeError("provider unavailable")])

    with pytest.raises(ValueError, match="section report extraction error"):
        await extract_sections(
            db_conn,
            client,
            prepared_report,
            ["report"],
            {"report": PROMPT_VERSIONS["report"]},
            _fake_build_prompt,
            _fake_model_for_section,
            _fake_validate,
            section_concurrency=1,
        )

    assert len(client.prompts) == 1
    checkpoint = db_conn.execute(
        "select status, attempt_count, error from ism_ai_section_extractions "
        "where section_name = 'report'"
    ).fetchone()
    assert checkpoint["status"] == "failed"
    assert checkpoint["attempt_count"] == 1
    assert checkpoint["error"] == "provider unavailable"
