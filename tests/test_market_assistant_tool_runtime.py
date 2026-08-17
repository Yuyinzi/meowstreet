import asyncio
import json
from datetime import date, timedelta

import pytest

from app.db import macro_indicators
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.services.market_assistant_exploration import execute_exploration
from app.services.market_assistant_tool_runtime import TOOL_RUNTIME_POLICIES
from app.services.market_assistant_tool_runtime import execute_tool_batch
from app.services.market_assistant_tool_runtime import execute_tool_call
from app.tools.market_assistant_tools import ALL_TOOL_IDS


def _confirmation_evidence(fact_id, indicator_id, label):
    return {
        "fact_id": fact_id,
        "indicator_id": indicator_id,
        "label": label,
        "role": {
            "decision_scope": "confirmation_input",
            "function": "confirmation_test",
            "target_layer": "market_confirmation",
            "allowed_effects": [],
        },
        "accepted_values": {"level": 18.4},
        "data_status": {"state": "available"},
        "participation": {"state": "applied"},
        "decision_result": {"evaluation": {"state": "evaluated"}},
    }


def _policy_evidence():
    return {
        "fact_id": "macro_policy_response",
        "label": "Monetary Policy Response",
        "role": {
            "decision_scope": "decision_input",
            "function": "selector",
            "target_layer": "macro_regime",
            "allowed_effects": [],
        },
        "accepted_values": {"relationship_to_growth_direction": "conflicts"},
        "data_status": {"state": "available"},
        "participation": {"state": "applied"},
        "provenance": {
            "source_module": "fomc_policy_tone",
            "source_id": "policy_2026-07-28",
            "source_period": "2026-07-28",
            "method_references": ["fomc_policy_tone_method_v1"],
        },
        "explanation": {
            "state": "restrictive_confirmed",
            "policy_read": {
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "tone_change": "more_hawkish",
                "confidence": "high",
                "reason": "Hold decision with hawkish inflation language.",
            },
            "details": {
                "fomc_tone": "hawkish",
                "fomc_action": "hold",
                "m2_status": "available",
                "inflation_above_target": True,
                "fed_balance_sheet_available": True,
            },
            "reasons": ["Hold decision with hawkish inflation language."],
        },
    }


def _vix_predicate_method():
    return {
        "method_id": "vix_predicate_v1",
        "method_version": "market_setup_v2_vix_predicate_v1",
        "kind": "predicate_method",
        "decision_contract": {
            "input_contract": {"fact_id": "vix_level"},
            "predicate": {"kind": "threshold"},
        },
        "explanation_contract": {"summary": "vix level predicate"},
    }


def fake_snapshot(context_id="ctx_current"):
    return {
        "context_id": context_id,
        "as_of": "2026-08-13",
        "evidence_through": "2026-08-12",
        "results": {
            "macro_regime": {
                "code": "growth_decelerating",
                "label": "Growth Decelerating",
            },
            "market_confirmation": {
                "code": "downside_confirmation",
                "label": "Downside Confirmation",
            },
            "market_setup": {"code": "downside_setup", "label": "Downside Setup"},
            "portfolio_posture": {"code": "defensive", "label": "Defensive Posture"},
        },
        "decision_path": [
            {
                "step_id": "macro_thesis",
                "object_type": "market_setup_result",
                "object_id": "macro_regime",
                "label": "Macro Thesis",
                "code": "growth_decelerating",
            },
            {
                "step_id": "market_test",
                "object_type": "market_setup_result",
                "object_id": "market_confirmation",
                "label": "Market Test",
                "code": "downside_confirmation",
            },
            {
                "step_id": "setup_relationship",
                "object_type": "market_setup_result",
                "object_id": "market_setup",
                "label": "Setup Relationship",
                "code": "downside_setup",
            },
            {
                "step_id": "portfolio_action",
                "object_type": "market_setup_result",
                "object_id": "portfolio_posture",
                "label": "Portfolio Action",
                "code": "defensive",
            },
        ],
        "evidence": [
            _confirmation_evidence("sp500_market_phase", "sp500_close", "Equity"),
            _confirmation_evidence("credit_conditions", "credit_conditions", "Credit"),
            _confirmation_evidence("vix_level", "vix", "VIX"),
        ],
        "method_contracts": {
            "version": "market_setup_explanation_methods_v1",
            "methods": {
                "posture_matrix": {
                    "method_version": "market_setup_v2_posture_matrix_v1",
                    "kind": "matrix_method",
                    "decision_contract": {"postures": {}},
                    "explanation_contract": {"summary": "posture matrix"},
                }
            },
        },
        "counterfactuals": [
            {
                "counterfactual_id": "setup_growth_decelerating_confirming_downside",
                "object_type": "market_setup",
                "object_id": "setup_growth_decelerating_confirming_downside",
                "from_code": "downside_setup",
                "to_code": "upside_setup",
                "confirmation_change": {
                    "from": "downside_confirmation",
                    "to": "upside_confirmation",
                },
                "posture_change": {"from": "defensive", "to": "aggressive"},
                "decision_effect": "market_setup_and_posture_change",
            }
        ],
    }


def resolved_context(context_id="ctx_current"):
    return {
        "resolution": {
            "mode": "current",
            "resolved_at": "2026-08-13T00:00:00Z",
            "previous_context_id": None,
            "current_context_id": context_id,
            "context_changed": False,
        },
        "delta": {"results_changed": False, "changes": []},
        "snapshot": fake_snapshot(context_id),
    }


def knowledge_catalog():
    return {
        "version": "market_assistant_knowledge_v1",
        "records": [
            {
                "record_id": "vix_definition",
                "version": "v1",
                "object_type": "indicator_definition",
                "authority": "method_knowledge",
                "indicator_id": "vix",
                "title": "VIX Definition",
                "explanation": "The VIX measures expected 30-day volatility.",
            }
        ],
    }


def exploration_result():
    return {
        "exploration_result_id": "expl_1",
        "artifact_schema_version": "market_assistant_exploration_result_v1",
        "authority": "local_observation",
        "market_setup_relation": "non_decision",
        "query_contract": {
            "query_kind": "indicator_history",
            "indicator_id": "vix",
            "start": "2026-01-01",
            "end": "2026-06-30",
        },
        "observed_window": {"start": "2026-01-01", "end": "2026-06-30"},
        "data_through": "2026-06-30",
        "rows": [{"date": "2026-06-30", "value": 18.4}],
        "deterministic_statistics": {"last_value": 18.4},
        "gaps": {"policy": "not_applicable", "missing_periods": None},
        "object_index": [
            {
                "object_type": "indicator_history",
                "object_id": "vix_history",
                "authority": "local_observation",
                "payload": {
                    "rows": [{"date": "2026-06-30", "value": 18.4}],
                    "last_value": 18.4,
                },
            }
        ],
        "result_hash": "a" * 64,
    }


def research_result():
    return {
        "research_result_id": "res_1",
        "artifact_schema_version": "market_assistant_research_result_v1",
        "authority": "external_research",
        "market_setup_relation": "non_decision",
        "task": {
            "purpose": "current_events",
            "depth_tier": "focused",
            "queries": ["latest vix"],
            "expected_source_class": "official_publication",
        },
        "searched_at": "2026-08-13T00:00:00Z",
        "sources": [],
        "findings": [],
        "object_index": [
            {
                "object_type": "research_finding",
                "object_id": "fnd_1",
                "authority": "external_research",
                "payload": {"finding_id": "fnd_1", "statement": "latest vix"},
            }
        ],
        "result_hash": "a" * 64,
    }


class _DummyCon:
    def close(self):
        pass


class _FakeDependencies:
    def __init__(self):
        self.requested = []
        self.db_path = ":memory:"
        self.config = {
            "model": "assistant-model",
            "research_model": "research-model",
            "provider": "openai_responses",
            "structured_output_mode": "json_object",
            "research_enabled": True,
            "supports_web_search": True,
            "api_key": "sk-secret-test-key",
            "base_url": None,
        }
        self._catalog = knowledge_catalog()
        self._exploration = exploration_result()
        self._research = research_result()

    def connect(self, db_path):
        self.requested.append("connect")
        return _DummyCon()

    def load_snapshot(self, con, context_id):
        self.requested.append("load_snapshot")
        return None

    def load_knowledge_catalog(self):
        self.requested.append("load_knowledge_catalog")
        return self._catalog

    def exploration(self, con, query, *, result_id, created_at):
        self.requested.append("exploration")
        return self._exploration

    async def acquire_research(
        self, provider, task, *, result_id, searched_at, explicit_deep=False
    ):
        self.requested.append("acquire_research")
        return self._research

    def build_research_provider(self, config):
        self.requested.append("build_research_provider")
        return object()


def fake_dependencies():
    return _FakeDependencies()


def confirmation_calls():
    return [
        {
            "call_id": "call_equity",
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": "equity"},
        },
        {
            "call_id": "call_credit",
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": "credit"},
        },
        {
            "call_id": "call_vix",
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": "vix"},
        },
    ]


def concurrent_fake_dependencies(gate):
    dependencies = fake_dependencies()
    started = {"count": 0}
    all_started = asyncio.Event()

    async def load_frozen_context(resolution):
        started["count"] += 1
        if started["count"] == 3:
            all_started.set()
        await gate.wait()
        return resolution["snapshot"]

    dependencies.load_frozen_context = load_frozen_context
    dependencies.all_started = all_started
    return dependencies


@pytest.mark.asyncio
async def test_snapshot_calls_use_resolution_context_not_model_arguments():
    results = await execute_tool_batch(
        [
            {
                "call_id": "call_1",
                "tool_name": "get_confirmation_test",
                "arguments": {"test_id": "vix"},
            }
        ],
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    assert results[0]["artifact"]["payload"]["context_id"] == "ctx_current"


@pytest.mark.asyncio
async def test_independent_calls_execute_concurrently():
    gate = asyncio.Event()
    dependencies = concurrent_fake_dependencies(gate)
    task = asyncio.create_task(
        execute_tool_batch(
            confirmation_calls(),
            request={"external_search_requested": False},
            resolution=resolved_context("ctx_current"),
            dependencies=dependencies,
            created_at="2026-08-13T00:00:00Z",
        )
    )
    await asyncio.wait_for(dependencies.all_started.wait(), timeout=0.5)
    gate.set()
    assert len(await task) == 3


@pytest.mark.asyncio
async def test_confirmation_test_returns_selected_evidence_object():
    record = await execute_tool_call(
        {
            "call_id": "call_vix",
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": "vix"},
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    object_ids = {obj["object_id"] for obj in record["artifact"]["object_index"]}
    assert "vix_level" in object_ids
    assert "sp500_market_phase" not in object_ids


@pytest.mark.asyncio
async def test_focused_artifacts_carry_context_dates_and_stable_object_ids():
    results = await execute_tool_batch(
        [
            {"call_id": "c1", "tool_name": "get_setup_overview", "arguments": {}},
            {"call_id": "c2", "tool_name": "get_posture_explanation", "arguments": {}},
        ],
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    overview = results[0]["artifact"]
    assert overview["payload"] == {
        "context_id": "ctx_current",
        "as_of": "2026-08-13",
        "evidence_through": "2026-08-12",
    }
    object_ids = [obj["object_id"] for obj in overview["object_index"]]
    assert {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    } <= set(object_ids)
    assert {
        "macro_thesis",
        "market_test",
        "setup_relationship",
        "portfolio_action",
    } <= set(object_ids)
    posture = results[1]["artifact"]
    posture_types = {
        (obj["object_type"], obj["object_id"]) for obj in posture["object_index"]
    }
    assert ("market_setup_result", "portfolio_posture") in posture_types
    assert ("method_contract", "posture_matrix") in posture_types
    assert posture["payload"]["context_id"] == "ctx_current"


@pytest.mark.asyncio
async def test_approved_counterfactuals_keep_setup_level_objects():
    record = await execute_tool_call(
        {
            "call_id": "c1",
            "tool_name": "get_approved_counterfactuals",
            "arguments": {},
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    objects = record["artifact"]["object_index"]
    assert {obj["object_type"] for obj in objects} == {"market_setup"}
    assert all(obj["object_id"].startswith("setup_") for obj in objects)


@pytest.mark.asyncio
async def test_missing_confirmation_test_returns_none_artifact():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    snapshot["evidence"] = snapshot["evidence"][:1]
    resolution["snapshot"] = snapshot
    record = await execute_tool_call(
        {
            "call_id": "c1",
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": "credit"},
        },
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    assert record["artifact"] is None


@pytest.mark.asyncio
async def test_snapshot_tools_return_only_frozen_authorities():
    results = await execute_tool_batch(
        [
            {"call_id": "c1", "tool_name": "get_setup_overview", "arguments": {}},
            {
                "call_id": "c2",
                "tool_name": "get_confirmation_test",
                "arguments": {"test_id": "vix"},
            },
            {"call_id": "c3", "tool_name": "get_posture_explanation", "arguments": {}},
            {
                "call_id": "c4",
                "tool_name": "get_approved_counterfactuals",
                "arguments": {},
            },
        ],
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    for record in results:
        artifact = record["artifact"]
        assert artifact["artifact_kind"] == "explanation_snapshot"
        assert {obj["authority"] for obj in artifact["object_index"]} <= {
            "decision_fact",
            "method_knowledge",
        }


@pytest.mark.asyncio
async def test_knowledge_returns_method_knowledge_objects():
    record = await execute_tool_call(
        {
            "call_id": "c1",
            "tool_name": "get_indicator_knowledge",
            "arguments": {"indicator_id": "vix", "topic": "definition"},
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["artifact_kind"] == "knowledge_record"
    assert {obj["authority"] for obj in artifact["object_index"]} == {
        "method_knowledge"
    }


@pytest.mark.asyncio
async def test_exploration_returns_local_observation_objects():
    record = await execute_tool_call(
        {
            "call_id": "c1",
            "tool_name": "query_indicator_history",
            "arguments": {
                "indicator_id": "vix",
                "start": "2026-01-01",
                "end": "2026-06-30",
            },
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["artifact_kind"] == "exploration_result"
    assert {obj["authority"] for obj in artifact["object_index"]} == {
        "local_observation"
    }


@pytest.mark.asyncio
async def test_research_disabled_without_external_search_request():
    record = await execute_tool_call(
        {
            "call_id": "c1",
            "tool_name": "research_focused",
            "arguments": {
                "purpose": "current_events",
                "queries": ["latest vix"],
                "expected_source_class": "official_publication",
            },
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["artifact_kind"] == "research_result"
    assert artifact["payload"]["status"] == "research_unavailable"
    assert artifact["payload"]["reason_code"] == "external_search_not_requested"
    assert "acquire_research" not in record["artifact"]


@pytest.mark.asyncio
async def test_research_executes_when_external_search_requested():
    record = await execute_tool_call(
        {
            "call_id": "c1",
            "tool_name": "research_focused",
            "arguments": {
                "purpose": "current_events",
                "queries": ["latest vix"],
                "expected_source_class": "official_publication",
            },
        },
        request={"external_search_requested": True},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["artifact_kind"] == "research_result"
    assert artifact["payload"]["research_result_id"] == "res_1"
    assert {obj["authority"] for obj in artifact["object_index"]} == {
        "external_research"
    }


@pytest.mark.asyncio
async def test_local_tools_request_no_forbidden_dependencies():
    dependencies = fake_dependencies()
    await execute_tool_batch(
        [
            {"call_id": "c1", "tool_name": "get_setup_overview", "arguments": {}},
            {
                "call_id": "c2",
                "tool_name": "get_indicator_knowledge",
                "arguments": {"indicator_id": "vix", "topic": "definition"},
            },
            {
                "call_id": "c3",
                "tool_name": "query_indicator_history",
                "arguments": {
                    "indicator_id": "vix",
                    "start": "2026-01-01",
                    "end": "2026-06-30",
                },
            },
        ],
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=dependencies,
        created_at="2026-08-13T00:00:00Z",
    )
    requested = set(dependencies.requested)
    assert not (requested & {"refresh", "ingest", "http_client", "provider_client"})


@pytest.mark.asyncio
async def test_call_records_expose_only_safe_fields():
    results = await execute_tool_batch(
        [
            {
                "call_id": "call_vix",
                "tool_name": "get_confirmation_test",
                "arguments": {"test_id": "vix"},
            }
        ],
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    record = results[0]
    assert set(record) == {
        "call_id",
        "tool_name",
        "arguments",
        "artifact",
        "progress_label",
    }
    assert record["call_id"] == "call_vix"
    assert record["tool_name"] == "get_confirmation_test"
    assert record["arguments"] == {"test_id": "vix"}
    assert record["progress_label"]
    serialized = json.dumps(record)
    assert "api_key" not in serialized
    assert "sk-secret-test-key" not in serialized


def _credit_series_dates():
    start = date(2026, 3, 2)
    current = start
    dates = []
    while current <= date(2026, 8, 10):
        dates.append(current)
        current = current + timedelta(days=7)
    return dates


@pytest.mark.asyncio
async def test_evidence_detail_returns_focused_policy_projection():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    snapshot["evidence"].append(_policy_evidence())
    snapshot["method_contracts"]["methods"]["vix_predicate_v1"] = (
        _vix_predicate_method()
    )
    resolution["snapshot"] = snapshot
    record = await execute_tool_call(
        {
            "call_id": "call_detail",
            "tool_name": "get_evidence_detail",
            "arguments": {
                "fact_id": "macro_policy_response",
                "topics": ["current", "drivers", "source"],
            },
        },
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["artifact_kind"] == "explanation_snapshot"
    assert artifact["artifact_id"] == (
        "ctx_current_evidence_detail_macro_policy_response_current_drivers_source"
    )
    payload = artifact["payload"]
    assert payload["context_id"] == "ctx_current"
    assert payload["as_of"] == "2026-08-13"
    assert payload["evidence_through"] == "2026-08-12"
    assert payload["fact_id"] == "macro_policy_response"
    assert payload["detail_kind"] == "policy_response"
    assert payload["topics"] == ["current", "drivers", "source"]
    assert payload["status"] == "available"
    assert payload["detail"]["current"]["policy_action"] == "hold"
    assert payload["detail"]["current"]["overall_bias"] == "mild_hawkish"
    assert (
        payload["detail"]["current"]["relationship_to_growth_direction"] == "conflicts"
    )
    assert payload["detail"]["drivers"]["policy_reason"]
    assert payload["detail"]["source"]["source_module"] == "fomc_policy_tone"
    assert payload["detail"]["source"]["source_period"] == "2026-07-28"
    assert "evidence" not in payload
    assert "results" not in payload
    object_ids = {obj["object_id"] for obj in artifact["object_index"]}
    assert object_ids == {
        "ctx_current_evidence_detail_macro_policy_response_current_drivers_source",
        "ctx_current_evidence_detail_macro_policy_response_current_drivers_source_source",
    }
    assert {obj["object_type"] for obj in artifact["object_index"]} == {
        "evidence_detail",
        "evidence_detail_source",
    }
    authorities_by_type = {
        obj["object_type"]: obj["authority"] for obj in artifact["object_index"]
    }
    assert authorities_by_type["evidence_detail"] == "decision_fact"
    assert authorities_by_type["evidence_detail_source"] == "method_knowledge"
    source_obj = next(
        obj
        for obj in artifact["object_index"]
        if obj["object_type"] == "evidence_detail_source"
    )
    assert source_obj["payload"]["source"]["source_module"] == "fomc_policy_tone"
    decision_obj = next(
        obj
        for obj in artifact["object_index"]
        if obj["object_type"] == "evidence_detail"
    )
    assert "source" not in decision_obj["payload"]


@pytest.mark.asyncio
async def test_evidence_detail_excludes_unrelated_facts_from_object_index():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    snapshot["evidence"].append(_policy_evidence())
    resolution["snapshot"] = snapshot
    record = await execute_tool_call(
        {
            "call_id": "call_detail",
            "tool_name": "get_evidence_detail",
            "arguments": {
                "fact_id": "macro_policy_response",
                "topics": ["current"],
            },
        },
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    object_ids = {obj["object_id"] for obj in record["artifact"]["object_index"]}
    assert object_ids == {"ctx_current_evidence_detail_macro_policy_response_current"}
    assert "sp500_market_phase" not in object_ids
    assert "credit_conditions" not in object_ids
    assert "vix_level" not in object_ids


@pytest.mark.asyncio
async def test_evidence_detail_adds_method_object_when_matched():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    snapshot["method_contracts"]["methods"]["vix_predicate_v1"] = (
        _vix_predicate_method()
    )
    resolution["snapshot"] = snapshot
    record = await execute_tool_call(
        {
            "call_id": "call_detail",
            "tool_name": "get_evidence_detail",
            "arguments": {
                "fact_id": "vix_level",
                "topics": ["current", "method"],
            },
        },
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    objects_by_type = {obj["object_type"]: obj for obj in artifact["object_index"]}
    assert set(objects_by_type) == {"evidence_detail", "evidence_detail_method"}
    detail_obj = objects_by_type["evidence_detail"]
    assert detail_obj["authority"] == "decision_fact"
    assert detail_obj["payload"]["status"] == "available"
    method_obj = objects_by_type["evidence_detail_method"]
    assert method_obj["authority"] == "method_knowledge"
    assert method_obj["payload"]["method_references"] == []
    assert (
        method_obj["payload"]["method_contracts"][0]["method_id"] == "vix_predicate_v1"
    )


@pytest.mark.asyncio
async def test_evidence_detail_returns_stale_projection():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    stale = _policy_evidence()
    stale["data_status"] = {"state": "stale"}
    stale["participation"] = {"state": "stale", "reason_code": "data_stale"}
    snapshot["evidence"].append(stale)
    resolution["snapshot"] = snapshot
    record = await execute_tool_call(
        {
            "call_id": "call_detail",
            "tool_name": "get_evidence_detail",
            "arguments": {
                "fact_id": "macro_policy_response",
                "topics": ["current", "source"],
            },
        },
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["payload"]["status"] == "stale"
    assert artifact["payload"]["detail"]["status"] == "stale"
    assert artifact["payload"]["detail"]["reason"] == "data_stale"
    assert artifact["payload"]["detail"]["source"]["source_period"] == "2026-07-28"
    assert "current" not in artifact["payload"]["detail"]


@pytest.mark.asyncio
async def test_evidence_detail_returns_unsupported_projection():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    snapshot["evidence"].append(
        {
            "fact_id": "equity_breadth",
            "label": "Equity Breadth",
            "data_status": {"state": "available"},
        }
    )
    resolution["snapshot"] = snapshot
    record = await execute_tool_call(
        {
            "call_id": "call_detail",
            "tool_name": "get_evidence_detail",
            "arguments": {
                "fact_id": "equity_breadth",
                "topics": ["current"],
            },
        },
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["payload"]["status"] == "unsupported"
    assert artifact["payload"]["detail"]["status"] == "unsupported"
    assert artifact["payload"]["detail"]["supported_topics"] == []
    assert artifact["payload"]["detail"]["detail_kind"] == "unsupported"


@pytest.mark.asyncio
async def test_evidence_detail_returns_missing_projection():
    record = await execute_tool_call(
        {
            "call_id": "call_detail",
            "tool_name": "get_evidence_detail",
            "arguments": {
                "fact_id": "jobless_claims",
                "topics": ["current", "source"],
            },
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    artifact = record["artifact"]
    assert artifact["payload"]["status"] == "missing"
    assert artifact["payload"]["detail"]["status"] == "missing"
    assert artifact["payload"]["detail"]["fact_id"] == "jobless_claims"
    assert "current" not in artifact["payload"]["detail"]
    assert "source" not in artifact["payload"]["detail"]
    object_ids = {obj["object_id"] for obj in artifact["object_index"]}
    assert object_ids == {"ctx_current_evidence_detail_jobless_claims_current_source"}
    assert {obj["object_type"] for obj in artifact["object_index"]} == {
        "evidence_detail"
    }
    assert all(obj["authority"] == "decision_fact" for obj in artifact["object_index"])


@pytest.mark.asyncio
async def test_evidence_detail_artifact_id_is_order_independent():
    resolution = resolved_context("ctx_current")
    snapshot = fake_snapshot("ctx_current")
    snapshot["evidence"].append(_policy_evidence())
    resolution["snapshot"] = snapshot
    results = await execute_tool_batch(
        [
            {
                "call_id": "call_a",
                "tool_name": "get_evidence_detail",
                "arguments": {
                    "fact_id": "macro_policy_response",
                    "topics": ["current", "source"],
                },
            },
            {
                "call_id": "call_b",
                "tool_name": "get_evidence_detail",
                "arguments": {
                    "fact_id": "macro_policy_response",
                    "topics": ["source", "current"],
                },
            },
        ],
        request={"external_search_requested": False},
        resolution=resolution,
        dependencies=fake_dependencies(),
        created_at="2026-08-13T00:00:00Z",
    )
    assert (
        results[0]["artifact"]["artifact_id"] == (results[1]["artifact"]["artifact_id"])
    )
    assert results[0]["artifact"]["artifact_id"] == (
        "ctx_current_evidence_detail_macro_policy_response_current_source"
    )


def _credit_series_points(value, *, high_value=None):
    return [
        {
            "date": current.isoformat(),
            "value": (
                high_value
                if high_value is not None and current >= date(2026, 7, 6)
                else value
            ),
            "source": "fred_ice_bofa",
        }
        for current in _credit_series_dates()
    ]


def credit_dependencies(tmp_path):
    db_path = tmp_path / "runtime_credit.sqlite"
    con = us_rates_liquidity_db.connect(db_path)
    macro_indicators.connect(db_path)
    us_rates_liquidity_db.replace_rate_series_points(
        con,
        {
            "series_id": "treasury_10y",
            "title": "10-Year Treasury",
            "instrument_type": "nominal_treasury",
            "maturity_months": 120,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        [
            {
                "date": current.isoformat(),
                "value": 4.00,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            }
            for current in _credit_series_dates()
        ],
    )
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "bbb_corporate_yield",
            "title": "BBB Corporate Yield",
            "units": "percent",
            "source": "BAMLC0A4CBBBEY.csv",
        },
        _credit_series_points(5.00),
    )
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "ccc_corporate_yield",
            "title": "CCC Corporate Yield",
            "units": "percent",
            "source": "BAMLH0A3HYC.csv",
        },
        _credit_series_points(8.00, high_value=10.00),
    )
    return {
        "db_path": str(db_path),
        "connect": us_rates_liquidity_db.connect,
        "exploration": execute_exploration,
    }


@pytest.mark.asyncio
async def test_credit_history_tool_call_returns_bounded_categorical_artifact(tmp_path):
    dependencies = credit_dependencies(tmp_path)
    artifact = await execute_tool_call(
        {
            "call_id": "call_credit_history",
            "tool_name": "query_indicator_history",
            "arguments": {
                "indicator_id": "credit_conditions",
                "window": "6m",
            },
        },
        request={"external_search_requested": False},
        resolution=resolved_context("ctx_current"),
        dependencies=dependencies,
        created_at="2026-08-13T00:00:00Z",
    )

    artifact_payload = artifact["artifact"]
    assert artifact_payload["artifact_kind"] == "exploration_result"
    assert artifact_payload["primary_authority"] == "local_observation"
    assert artifact_payload["market_setup_relation"] == "non_decision"
    assert (
        artifact_payload["payload"]["query_contract"]["indicator_id"]
        == "credit_conditions"
    )
    assert (
        artifact_payload["payload"]["deterministic_statistics"]["lifecycle_summary"][
            "current_run_start"
        ]
        is not None
    )


def test_tool_runtime_policies_cover_every_registered_tool():
    assert set(TOOL_RUNTIME_POLICIES) == set(ALL_TOOL_IDS)


def test_tool_runtime_policies_use_only_registered_capability_classes():
    known_capabilities = {
        "frozen_local",
        "local_read",
        "external_read",
        "side_effecting",
    }
    for tool_id, (capability, controls) in TOOL_RUNTIME_POLICIES.items():
        assert capability in known_capabilities
        assert isinstance(controls, tuple)
        assert all(isinstance(control, str) for control in controls)


def test_every_external_or_side_effecting_tool_names_request_controls():
    for tool_id, (capability, controls) in TOOL_RUNTIME_POLICIES.items():
        if capability in {"external_read", "side_effecting"}:
            assert controls, f"{tool_id} requires a request-control guard"
        if tool_id.startswith("research_"):
            assert "external_search_requested" in controls


def test_evidence_detail_is_frozen_local_without_controls():
    capability, controls = TOOL_RUNTIME_POLICIES["get_evidence_detail"]
    assert capability == "frozen_local"
    assert controls == ()
