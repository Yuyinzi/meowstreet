import hashlib
import inspect
import json
import logging
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.db import market_assistant as market_assistant_db
from app.routers import market_assistant as market_assistant_router
from app.services import market_assistant as market_assistant_service
from app.tools import market_setup_evidence_facts
from app.tools import market_setup_explanation_snapshot
from app.tools import market_setup_v2
from app.tools.market_assistant_claim_audit import ClaimAuditSchema

client = TestClient(app)


@pytest.fixture
def assistant_env(monkeypatch):
    monkeypatch.setenv("MARKET_ASSISTANT_MODEL", "test-model")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_MODEL", "test-research-model")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_PROVIDER", "openai_responses")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH", "false")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _fake_answer(payload):
    async def fake_answer_question(request, *, dependencies):
        return payload

    return fake_answer_question


def _stored_trace():
    return {
        "answer_trace_id": "trace_123",
        "message_id": "msg_456",
        "resolution": {
            "mode": "current",
            "resolved_at": "2026-08-10T02:00:00Z",
            "previous_context_id": "ctx_A",
            "current_context_id": "ctx_B",
            "context_changed": True,
        },
        "explanation_context_id": "ctx_B",
        "knowledge_references": ["vix_definition"],
        "snapshot_artifact_ids": [],
        "exploration_result_ids": [],
        "research_result_ids": [],
        "plan": {
            "intent": "decision_explanation",
            "context_mode": "current",
            "operations": [
                {"operation_id": "resolve_current_explanation", "parameters": {}}
            ],
            "answer_depth": "standard",
            "research_tier": None,
        },
        "structured_claims": None,
        "generation_status": "validated_first_pass",
        "attempts": {"plan": 1, "draft": 1, "repair": 0},
        "validation_error_codes": [],
        "prompt": {"version": "market_assistant_prompt_v1", "hash": "a" * 64},
        "model_configuration_fingerprint": {
            "provider": "openai_responses",
            "model": "assistant-model",
            "research_model": "research-model",
            "tool_schema_versions": {"artifacts": "market_assistant_artifact_v1"},
            "assistant_policy_version": "market_assistant_policy_v1",
            "prompt_version": "market_assistant_prompt_v1",
        },
        "tool_schema_versions": {"artifacts": "market_assistant_artifact_v1"},
        "answer_text": "Market Setup remains macro_improving.",
        "answer_text_hash": "b" * 64,
        "generated_time": "2026-08-10T02:00:00Z",
    }


class _FakeCon:
    def close(self):
        pass


def test_current_question_returns_resolution_answer_and_trace(
    assistant_env, monkeypatch
):
    payload = {
        "resolution": {"mode": "current"},
        "answer_text": "The current setup is Mild Risk-Off.",
        "citations": [],
        "generation_status": "validated_first_pass",
        "answer_trace_id": "trace_123",
    }
    monkeypatch.setattr(
        market_assistant_service, "answer_question", _fake_answer(payload)
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why Mild Risk-Off?", "mode": "current"},
    )

    assert response.status_code == 200
    assert response.json()["resolution"]["mode"] == "current"
    assert response.json()["answer_trace_id"] == "trace_123"


def test_assistant_runtime_allows_bounded_streaming_request(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "app.routers.market_assistant.load_market_assistant_config",
        lambda: {
            "model": "assistant-model",
            "structured_output_mode": "json_object",
        },
    )

    def fake_build_async_client(config, **kwargs):
        captured["config"] = config
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "app.routers.market_assistant.build_async_client", fake_build_async_client
    )

    (
        _,
        model,
        structured_output_mode,
        reasoning_effort,
    ) = market_assistant_router._assistant_runtime()

    assert model == "assistant-model"
    assert structured_output_mode == "json_object"
    assert reasoning_effort == "low"
    assert captured["kwargs"]["timeout"] == 900.0


@pytest.mark.asyncio
async def test_llm_helpers_thread_reasoning_effort_from_config(monkeypatch):
    captured = {"plan_reasoning": None, "llm_reasoning": []}

    monkeypatch.setattr(
        market_assistant_router,
        "_assistant_runtime",
        lambda: ("client", "assistant-model", "json_schema", "medium"),
    )
    monkeypatch.setattr(
        market_assistant_router,
        "deterministic_plan",
        lambda question: {"intent": "unsupported"},
    )

    async def fake_plan_question(client, **kwargs):
        captured["plan_reasoning"] = kwargs["reasoning_effort"]
        return {"intent": "unsupported"}

    async def fake_complete_structured(client, **kwargs):
        captured["llm_reasoning"].append(kwargs["reasoning_effort"])
        return {"sections": []}

    monkeypatch.setattr(market_assistant_router, "plan_question", fake_plan_question)
    monkeypatch.setattr(
        market_assistant_router, "complete_structured", fake_complete_structured
    )

    await market_assistant_router._plan_llm(
        question="hello world",
        context_summary={"mode": "current"},
    )
    await market_assistant_router._synthesize_llm(
        question="hello world",
        plan={"intent": "decision_explanation"},
        context_summary={"mode": "current"},
        artifacts={},
    )
    await market_assistant_router._repair_llm(
        question="hello world",
        plan={"intent": "decision_explanation"},
        context_summary={"mode": "current"},
        artifacts={},
        draft={"sections": []},
        validation_report={"valid": False},
    )

    assert captured["plan_reasoning"] == "medium"
    assert captured["llm_reasoning"] == ["medium", "medium"]


@pytest.mark.asyncio
async def test_known_setup_question_uses_deterministic_plan_without_llm(monkeypatch):
    monkeypatch.setattr(
        market_assistant_router,
        "_assistant_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("LLM must not run")),
    )

    plan = await market_assistant_router._plan_llm(
        question="explain the market setup",
        context_summary={"mode": "current"},
    )

    assert plan["intent"] == "decision_explanation"
    assert plan["operations"] == [
        {"operation_id": "resolve_current_explanation", "parameters": {}}
    ]


def test_historical_question_without_context_id_returns_400():
    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "historical"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "context id is required"


def test_historical_question_passes_exact_context_to_service(
    assistant_env, monkeypatch
):
    captured = {}

    async def fake_answer_question(request, *, dependencies):
        captured["request"] = request
        return {"resolution": {"mode": "historical"}}

    monkeypatch.setattr(
        market_assistant_service, "answer_question", fake_answer_question
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "historical", "context_id": "ctx_123"},
    )

    assert response.status_code == 200
    assert captured["request"]["context_id"] == "ctx_123"
    assert captured["request"]["mode"] == "historical"


def test_external_search_requested_flows_to_service(assistant_env, monkeypatch):
    captured = {}

    async def fake_answer_question(request, *, dependencies):
        captured["request"] = request
        return {"resolution": {"mode": "current"}}

    monkeypatch.setattr(
        market_assistant_service, "answer_question", fake_answer_question
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={
            "question": "Why?",
            "mode": "current",
            "external_search_requested": True,
        },
    )

    assert response.status_code == 200
    assert captured["request"]["external_search_requested"] is True
    assert captured["request"]["deep_research_requested"] is False


def test_question_accepts_deep_analysis_without_external_search(
    assistant_env, monkeypatch
):
    captured = {}

    async def fake_answer_question(request, *, dependencies):
        captured["request"] = request
        return {"resolution": {"mode": "current"}}

    monkeypatch.setattr(
        market_assistant_service, "answer_question", fake_answer_question
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={
            "question": "现在市场怎么样？",
            "mode": "current",
            "deep_analysis_requested": True,
            "external_search_requested": False,
        },
    )

    assert response.status_code == 200
    assert captured["request"]["deep_analysis_requested"] is True
    assert captured["request"]["external_search_requested"] is False


def test_stream_accepts_deep_analysis_without_external_search(monkeypatch):
    captured = {}

    async def fake_answer(request, dependencies):
        captured.update(request)
        yield {"type": "complete", "answer_trace_id": "ans_1"}

    monkeypatch.setattr(
        market_assistant_service,
        "stream_answer_question",
        fake_answer,
    )
    response = client.post(
        "/api/market-assistant/questions/stream",
        json={
            "question": "现在市场怎么样？",
            "deep_analysis_requested": True,
            "external_search_requested": False,
        },
    )
    assert response.status_code == 200
    assert captured["deep_analysis_requested"] is True
    assert captured["external_search_requested"] is False


def test_stream_deep_analysis_non_boolean_returns_400():
    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json={"question": "Why?", "deep_analysis_requested": "yes"},
    ) as response:
        assert response.status_code == 400
        response.read()
        assert response.json()["detail"] == "question request is invalid"


def test_stream_unknown_request_field_returns_400():
    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json={"question": "Why?", "unknown_field": 1},
    ) as response:
        assert response.status_code == 400
        response.read()
        assert response.json()["detail"] == "question request is invalid"


def test_question_passes_real_dependencies_dict(assistant_env, monkeypatch):
    captured = {}

    async def fake_answer_question(request, *, dependencies):
        captured["dependencies"] = dependencies
        return {"resolution": {"mode": "current"}}

    monkeypatch.setattr(
        market_assistant_service, "answer_question", fake_answer_question
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 200
    deps = captured["dependencies"]
    assert deps["db_path"]
    assert callable(deps["plan_llm"])
    assert callable(deps["synthesize_llm"])
    assert callable(deps["repair_llm"])
    assert callable(deps["react_turn_llm"])
    assert deps["stream_turn"] is deps["react_turn_llm"]
    assert callable(deps["narration_instructions"])
    assert callable(deps["claim_audit_llm"])
    assert callable(deps["build_research_provider"])
    assert callable(deps["exploration"])
    assert callable(deps["load_knowledge_catalog"])
    assert callable(deps["save_bundle"])
    assert callable(deps["resolve_current_explanation"])


def test_get_answer_trace_returns_stored_trace(monkeypatch):
    trace = _stored_trace()
    monkeypatch.setattr(market_assistant_db, "connect", lambda db_path: _FakeCon())
    monkeypatch.setattr(
        market_assistant_db,
        "load_answer_trace",
        lambda con, answer_trace_id: trace if answer_trace_id == "trace_123" else None,
    )

    response = client.get("/api/market-assistant/traces/trace_123")

    assert response.status_code == 200
    assert response.json()["answer_trace_id"] == "trace_123"
    assert response.json()["message_id"] == "msg_456"


def test_get_answer_trace_returns_404_for_unknown(monkeypatch):
    monkeypatch.setattr(market_assistant_db, "connect", lambda db_path: _FakeCon())
    monkeypatch.setattr(
        market_assistant_db, "load_answer_trace", lambda con, answer_trace_id: None
    )

    response = client.get("/api/market-assistant/traces/unknown")

    assert response.status_code == 404


def test_question_value_error_maps_to_400(assistant_env, monkeypatch):
    async def raise_value_error(request, *, dependencies):
        raise ValueError("question is unsupported")

    monkeypatch.setattr(market_assistant_service, "answer_question", raise_value_error)

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "question is unsupported"


def test_question_artifact_corruption_maps_to_409(assistant_env, monkeypatch):
    async def raise_corruption(request, *, dependencies):
        raise ValueError("answer trace is invalid")

    monkeypatch.setattr(market_assistant_service, "answer_question", raise_corruption)

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "answer trace is invalid"


def test_question_artifact_corruption_with_expanded_message_maps_to_409(
    assistant_env, monkeypatch
):
    async def raise_corruption(request, *, dependencies):
        raise ValueError("artifact object is duplicated: evidence_fact.vix_level")

    monkeypatch.setattr(market_assistant_service, "answer_question", raise_corruption)

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "artifact object is duplicated: evidence_fact.vix_level"
    )


def test_question_unexpected_error_maps_to_503_without_stack_trace(
    assistant_env, monkeypatch
):
    async def raise_unexpected(request, *, dependencies):
        raise RuntimeError("boom")

    monkeypatch.setattr(market_assistant_service, "answer_question", raise_unexpected)

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 503
    assert "Traceback" not in response.text
    assert "boom" not in response.text


def test_missing_market_assistant_config_falls_back_not_503(monkeypatch):
    for name in (
        "MARKET_ASSISTANT_MODEL",
        "MARKET_ASSISTANT_RESEARCH_MODEL",
        "MARKET_ASSISTANT_RESEARCH_PROVIDER",
        "MARKET_ASSISTANT_RESEARCH_ENABLED",
        "MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("MARKET_ASSISTANT_MODEL", raising=False)

    async def fake_answer_question(request, *, dependencies):
        return {"resolution": {"mode": "current"}, "generation_status": "fallback"}

    monkeypatch.setattr(
        market_assistant_service, "answer_question", fake_answer_question
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 200
    assert response.json()["generation_status"] == "fallback"


def test_question_endpoint_has_no_refresh_side_effects(assistant_env, monkeypatch):
    from app.data_sources import census_nrc
    from app.tools import benchmark_market_data as benchmark_market_data_tool

    def raise_on_call(*args, **kwargs):
        raise RuntimeError("refresh must not be called")

    monkeypatch.setattr(benchmark_market_data_tool, "refresh_benchmarks", raise_on_call)
    monkeypatch.setattr(census_nrc, "fetch_permits_workbook", raise_on_call)
    monkeypatch.setattr(
        market_assistant_service,
        "answer_question",
        _fake_answer({"resolution": {"mode": "current"}}),
    )

    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )

    assert response.status_code == 200


def test_synthesis_prompt_requests_beginner_chinese_explanation():
    prompt = market_assistant_router._synthesis_prompt(
        "现在市场怎么样？为什么？",
        {"intent": "decision_explanation", "answer_depth": "standard"},
        {"mode": "current"},
        {"ctx_1": {"object_index": []}},
    )
    system = prompt[0]["content"]

    assert "Answer language: Chinese" in system
    assert "financial beginner" in system
    assert "final user-facing prose" in system
    assert "do not display internal codes" in system
    assert "annotated artifact bindings" in system
    assert "conflicting or unconfirmed evidence" in system
    assert "up to three main reasons" in system


def test_synthesis_prompt_selects_english_for_english_question():
    prompt = market_assistant_router._synthesis_prompt(
        "Explain the market setup",
        {"intent": "decision_explanation"},
        {"mode": "current"},
        {"ctx_1": {"object_index": []}},
    )
    assert "Answer language: English" in prompt[0]["content"]


def test_synthesis_prompt_requires_streamable_answer_text():
    prompt = market_assistant_router._synthesis_prompt(
        "Explain the market setup",
        {"intent": "decision_explanation"},
        {"mode": "current"},
        {"ctx_1": {"object_index": []}},
    )
    system = prompt[0]["content"]
    assert "Serialize answer_text as the first top-level property." in system
    assert (
        "answer_text must exactly equal the deterministic rendering of sections "
        "and claims." in system
    )
    assert "Do not place markdown fences around the JSON object." in system


def test_repair_prompt_preserves_beginner_contract():
    prompt = market_assistant_router._repair_prompt(
        "现在市场怎么样？",
        {"intent": "decision_explanation"},
        {"mode": "current"},
        {"ctx_1": {"object_index": []}},
        {"sections": []},
        {"valid": False, "errors": []},
    )
    system = prompt[0]["content"]

    assert "Answer language: Chinese" in system
    assert "financial beginner" in system
    assert "same evidence set" in system
    assert "complete corrected StructuredAnswerDraft" in system


def test_narration_instructions_contain_beginner_prompt_boundaries():
    lower_instructions = market_assistant_router._narration_instructions().lower()

    for phrase in (
        "write for a financial beginner",
        "answer the user's question before naming system labels",
        "use only supplied views and tool results",
        "do not display internal codes or artifact identifiers",
        "when tools are needed, return tool calls only",
        "when answering, return plain text only",
        "do not reinterpret or override Market Setup",
    ):
        assert phrase.lower() in lower_instructions


def test_narration_input_items_exclude_snapshot_and_schema_bulk():
    items = market_assistant_router._narration_input_items(
        "现在市场怎么样？",
        {
            "view_version": "setup_explanation_v1",
            "results": {"market_setup": "improving"},
            "audit_objects": [],
        },
        {"get_setup_overview": {"status": "available"}},
    )
    serialized = json.dumps(items, ensure_ascii=False)

    for forbidden in (
        "snapshot_json",
        "snapshot_hash",
        "method_manifest",
        "StructuredAnswerDraft",
        "object_index",
    ):
        assert forbidden not in serialized
    assert "view_version" in serialized
    assert "get_setup_overview" in serialized
    assert "现在市场怎么样？" in serialized


def test_claim_audit_prompt_receives_exact_answer_and_frozen_refs():
    answer_text = "现在的市场偏积极，但仍没有得到全面确认。"
    explanation_view = {
        "view_version": "setup_explanation_v1",
        "audit_objects": [
            {
                "artifact_id": "ctx_1",
                "object_type": "result",
                "object_id": "market_setup",
            }
        ],
    }
    artifact_projection = {
        "ctx_1": {
            "artifact_id": "ctx_1",
            "payload": {"result": "improving"},
        }
    }
    prompt = market_assistant_router._claim_audit_prompt(
        answer_text, explanation_view, artifact_projection
    )
    system = prompt[0]["content"]
    user_content = prompt[1]["content"]

    assert "exact offsets" in system
    assert "exact text copied verbatim" in system
    assert "ClaimAudit" in system
    assert "Do not alter the supplied answer" in system
    assert answer_text in user_content
    assert '"explanation_view"' in user_content
    assert '"artifact_projection"' in user_content
    assert '"object_id"' in user_content
    assert "market_setup" in user_content


def test_claim_audit_prompt_does_not_ask_to_rewrite_the_answer():
    prompt = market_assistant_router._claim_audit_prompt(
        "现在的市场偏积极。",
        {"view_version": "setup_explanation_v1", "audit_objects": []},
        {"ctx_1": {"artifact_id": "ctx_1"}},
    )
    text = prompt[0]["content"] + " " + prompt[1]["content"]

    for forbidden in (
        "rewrite the answer",
        "improve the answer",
        "repair the answer",
        "replace the answer",
        "return a corrected",
    ):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_narration_llm_adapter_delegates_with_orchestrator_signature(monkeypatch):
    captured = {}

    async def fake_stream_response_turn(client, **kwargs):
        captured["client"] = client
        captured["kwargs"] = kwargs
        return {
            "output_text": "answer",
            "tool_calls": [],
            "response_items": [],
            "usage": None,
            "timings": {},
        }

    monkeypatch.setattr(
        market_assistant_router, "stream_response_turn", fake_stream_response_turn
    )

    result = await market_assistant_router._react_turn_llm(
        "client",
        model="assistant-model",
        input_items=[{"type": "message", "role": "user", "content": []}],
        instructions="narration instructions",
        tools=[{"type": "function", "name": "get_setup_overview"}],
        reasoning_effort="high",
        observer=None,
    )

    assert captured["client"] == "client"
    assert captured["kwargs"]["model"] == "assistant-model"
    assert captured["kwargs"]["reasoning_effort"] == "high"
    assert captured["kwargs"]["instructions"] == "narration instructions"
    assert captured["kwargs"]["tools"] == [
        {"type": "function", "name": "get_setup_overview"}
    ]
    assert captured["kwargs"]["observer"] is None
    assert "text_format" not in captured["kwargs"]
    assert result["output_text"] == "answer"


@pytest.mark.asyncio
async def test_claim_audit_prompt_adapter_uses_claim_audit_schema_without_tools(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        market_assistant_router,
        "_assistant_runtime",
        lambda: ("client", "assistant-model", "json_schema", "medium"),
    )

    async def fake_complete_structured(client, **kwargs):
        captured["client"] = client
        captured["kwargs"] = kwargs
        return {"claims": []}

    monkeypatch.setattr(
        market_assistant_router, "complete_structured", fake_complete_structured
    )

    result = await market_assistant_router._claim_audit_llm(
        answer_text="answer",
        explanation_view={"view_version": "setup_explanation_v1"},
        artifact_projection={"ctx_1": {"artifact_id": "ctx_1"}},
    )

    assert captured["client"] == "client"
    assert captured["kwargs"]["model"] == "assistant-model"
    assert captured["kwargs"]["schema_type"] is ClaimAuditSchema
    assert captured["kwargs"]["reasoning_effort"] == "medium"
    assert "tools" not in captured["kwargs"]
    assert result == {"claims": []}


def _stream_events():
    events = [
        {"type": "status", "status": "thinking"},
        {"type": "answer_delta", "delta": "市场 "},
        {"type": "validation", "status": "passed", "error_codes": []},
        {
            "type": "complete",
            "generation_status": "validated_first_pass",
            "answer_trace_id": "trace_123",
            "citations": [],
        },
    ]

    async def fake_stream(request, *, dependencies):
        for event in events:
            yield event

    return fake_stream


def test_stream_question_returns_ndjson_event_sequence(assistant_env, monkeypatch):
    monkeypatch.setattr(
        market_assistant_service, "stream_answer_question", _stream_events()
    )

    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json={"question": "Why?", "mode": "current"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        raw_lines = list(response.iter_lines())
        parsed = [json.loads(line) for line in raw_lines]
        assert [event["type"] for event in parsed] == [
            "status",
            "answer_delta",
            "validation",
            "complete",
        ]
        assert parsed[0] == {"type": "status", "status": "thinking"}
        assert parsed[1] == {"type": "answer_delta", "delta": "市场 "}
        wire_line = raw_lines[1]
        compact = json.dumps(parsed[1], ensure_ascii=False, separators=(",", ":"))
        assert wire_line == compact
        assert ", " not in wire_line
        assert ": " not in wire_line
        assert "市场" in wire_line
        assert "\\u" not in wire_line


def test_stream_logs_first_ndjson_answer_delta_sent_with_request_id(
    caplog, monkeypatch
):
    monkeypatch.setattr(
        market_assistant_service, "stream_answer_question", _stream_events()
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with client.stream(
            "POST",
            "/api/market-assistant/questions/stream",
            json={"question": "Why?", "mode": "current"},
        ) as response:
            assert response.status_code == 200
            response.read()

    stage_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "uvicorn.error"
        and "stage=first_ndjson_answer_delta_sent" in record.getMessage()
    ]
    assert len(stage_lines) == 1
    assert "request_id=req_" in stage_lines[0]
    assert "elapsed_seconds=" in stage_lines[0]

    combined = " ".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "uvicorn.error"
    )
    assert "Why?" not in combined


def test_stream_question_empty_question_returns_400_before_streaming(assistant_env):
    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json={"question": "  ", "mode": "current"},
    ) as response:
        assert response.status_code == 400
        response.read()
        assert response.json()["detail"] == "question is required"


def test_stream_question_historical_without_context_returns_400_before_streaming(
    assistant_env,
):
    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json={"question": "Why?", "mode": "historical"},
    ) as response:
        assert response.status_code == 400
        response.read()
        assert response.json()["detail"] == "context id is required"


def test_stream_worker_error_emits_error_line_without_stack_trace(
    assistant_env, monkeypatch
):
    async def fake_stream(request, *, dependencies):
        yield {"type": "status", "status": "thinking"}
        raise RuntimeError("boom")

    monkeypatch.setattr(market_assistant_service, "stream_answer_question", fake_stream)

    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json={"question": "Why?", "mode": "current"},
    ) as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())
        parsed = [json.loads(line) for line in lines]
        assert [event["type"] for event in parsed] == ["status", "error"]
        assert parsed[-1] == {
            "type": "error",
            "message": "market assistant service is unavailable",
        }
        assert "boom" not in "".join(lines)
        assert "Traceback" not in "".join(lines)


def _e2e_env(monkeypatch):
    monkeypatch.setenv("MARKET_ASSISTANT_STRUCTURED_OUTPUT_MODE", "json_schema")
    monkeypatch.setenv("MARKET_ASSISTANT_CLAIM_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("MARKET_ASSISTANT_REASONING_EFFORT", "low")
    monkeypatch.setenv("MARKET_ASSISTANT_AUDIT_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("MARKET_ASSISTANT_MODEL", "test-model")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_MODEL", "test-research-model")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_PROVIDER", "openai_responses")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH", "false")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _monthly_period(effective_date="2026-06-30", reference_period="2026-06"):
    return {
        "effective_date": effective_date,
        "reference_period": reference_period,
        "release_date": "2026-07-01",
    }


def _daily_period(effective_date="2026-07-01", observation_date="2026-07-01"):
    return {"effective_date": effective_date, "observation_date": observation_date}


def _expected_growth(direction="slowing"):
    return {
        "source_module": "ism_survey_synthesis",
        "method_version": "ism_survey_synthesis_v1",
        "facts": {
            "survey_growth_direction": {
                "direction": direction,
                "source_period": _monthly_period(),
            }
        },
    }


def _market_environment(state="bear_market"):
    return {
        "source_module": "market_phase",
        "method_version": "market_phase_v1",
        "facts": {
            "sp500_market_phase": {"phase": state, "source_period": _daily_period()}
        },
    }


def _financial_conditions(vix=18.4):
    return {
        "source_module": "us_rates_liquidity",
        "method_version": "us_rates_liquidity_v1",
        "facts": {
            "macro_financial_conditions": {
                "relationship_to_growth_direction": "neutral",
                "source_period": _monthly_period(effective_date="2026-07-01"),
            },
            "credit_conditions": {
                "status": "risk_rising",
                "source_period": _monthly_period(effective_date="2026-07-01"),
            },
            "vix_level": {"level": vix, "source_period": _daily_period()},
        },
    }


def _policy_response(m2_status="expanding"):
    return {
        "source_module": "fomc_policy_tone",
        "method_version": "fomc_policy_tone_v1",
        "facts": {
            "macro_policy_response": {
                "relationship_to_growth_direction": "conflicts",
                "source_period": _monthly_period(effective_date="2026-07-01"),
            },
            "m2_liquidity": {
                "status": m2_status,
                "source_period": _monthly_period(effective_date="2026-07-01"),
            },
        },
    }


def _consumer_demand():
    return {
        "source_module": "consumer_sentiment",
        "method_version": "market_setup_v2_consumer_demand_v1",
        "facts": {
            "consumer_demand_outlook": {
                "relationship_to_growth_direction": "supports",
                "source_period": _monthly_period(),
            }
        },
    }


def _representative_inputs():
    return {
        "expected_growth": _expected_growth(),
        "market_environment": _market_environment(),
        "financial_conditions": _financial_conditions(),
        "policy_response": _policy_response(),
        "consumer_demand": _consumer_demand(),
    }


def _snapshot_state():
    inputs = _representative_inputs()
    setup_result = market_setup_v2.build_market_setup_v2(**inputs)
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup_result,
        inputs=inputs,
        evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )
    method_contracts = market_setup_v2.build_explanation_method_contracts()
    return market_setup_explanation_snapshot.build_snapshot_state(
        setup_result=setup_result,
        evidence=evidence,
        method_contracts=method_contracts,
        as_of="2026-08-13",
        evidence_through=setup_result["evidence_through"],
        input_registry_version="market_setup_input_registry_v1",
        explanation_surface_version="market_assistant_surface_v1",
    )


def _context_id_for(explanation_fingerprint, created_at):
    digest = hashlib.sha1(f"{explanation_fingerprint}{created_at}".encode()).hexdigest()
    return f"ctx_{digest[:12]}"


def _build_resolution(db_path, created_at="2026-08-13T02:00:00Z"):
    state = _snapshot_state()
    context_id = _context_id_for(
        market_setup_explanation_snapshot.compute_explanation_fingerprint(state),
        created_at,
    )
    con = market_assistant_db.connect(db_path)
    try:
        snapshot = market_assistant_db.get_or_create_snapshot(
            con, state, context_id=context_id, created_at=created_at
        )
    finally:
        con.close()
    return {
        "resolution": {
            "mode": "current",
            "resolved_at": created_at,
            "previous_context_id": None,
            "current_context_id": context_id,
            "context_changed": False,
            "evidence_through": snapshot.get("evidence_through"),
        },
        "delta": {"results_changed": False, "changes": []},
        "snapshot": snapshot,
    }


class _ScriptedStreamTurn:
    def __init__(self, steps, order=None):
        self.steps = list(steps)
        self.calls = []
        self._order = order

    async def __call__(
        self,
        client,
        *,
        model,
        input_items,
        instructions,
        tools,
        reasoning_effort,
        observer=None,
    ):
        step = self.steps.pop(0)
        self.calls.append(
            {
                "client": client,
                "model": model,
                "input_items": input_items,
                "instructions": instructions,
                "tools": tools,
                "reasoning_effort": reasoning_effort,
            }
        )
        if self._order is not None:
            self._order.append("narration")
        for event in step.get("observer_events") or []:
            result = observer(event)
            if inspect.isawaitable(result):
                await result
        if step.get("error") is not None:
            raise step["error"]
        return step["result"]


def _narration_step(text, deltas=None, error=None):
    step = {
        "result": {
            "output_text": text,
            "tool_calls": [],
            "response_items": [],
            "usage": None,
            "timings": {},
        }
    }
    if deltas:
        step["observer_events"] = [
            {"type": "output_delta", "delta": delta} for delta in deltas
        ]
    if error is not None:
        step["error"] = error
    return step


def _tool_step(calls):
    response_items = [
        {
            "type": "function_call",
            "call_id": call["call_id"],
            "name": call["tool_name"],
            "arguments": json.dumps(
                call["arguments"], ensure_ascii=False, sort_keys=True
            ),
        }
        for call in calls
    ]
    return {
        "result": {
            "output_text": "",
            "tool_calls": list(calls),
            "response_items": response_items,
            "usage": None,
            "timings": {},
        }
    }


def _first_decision_fact_ref(artifact_projection):
    for artifact_id in sorted(artifact_projection):
        for obj in artifact_projection[artifact_id].get("object_index") or []:
            if obj.get("authority") == "decision_fact":
                return {
                    "artifact_id": artifact_id,
                    "object_type": obj["object_type"],
                    "object_id": obj["object_id"],
                }
    return None


def _claim_audit_factory(recorder, order=None):
    async def fake_complete_structured(client, **kwargs):
        recorder.append(kwargs)
        if order is not None:
            order.append("audit")
        user_payload = json.loads(kwargs["prompt"][1]["content"])
        artifact_projection = user_payload["artifact_projection"]
        ref = _first_decision_fact_ref(artifact_projection)
        answer_text = user_payload["answer_text"]
        if ref is None:
            claim = {
                "claim_id": "claim_1",
                "start": 0,
                "end": len(answer_text),
                "exact_text": answer_text,
                "purpose": "illustration",
                "authority": "hypothetical",
                "refs": [],
                "values": [],
            }
        else:
            claim = {
                "claim_id": "claim_1",
                "start": 0,
                "end": len(answer_text),
                "exact_text": answer_text,
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [ref],
                "values": [],
            }
        return {"claims": [claim]}

    return fake_complete_structured


def _hybrid_e2e(
    monkeypatch,
    tmp_path,
    *,
    steps,
    question="现在市场怎么样？",
    deep_analysis=False,
    request_overrides=None,
    exploration=None,
    audit=None,
    order=None,
):
    _e2e_env(monkeypatch)
    db_path = tmp_path / "assistant.sqlite"
    monkeypatch.setattr(market_assistant_db, "DEFAULT_DB_PATH", db_path)
    resolution = _build_resolution(db_path)
    turn = _ScriptedStreamTurn(steps, order=order)
    audit_recorder = []
    if audit is None:
        audit = _claim_audit_factory(audit_recorder, order=order)
    monkeypatch.setattr(
        market_assistant_router, "build_async_client", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(
        market_assistant_router,
        "_assistant_runtime",
        lambda: (object(), "test-model", "json_schema", "low"),
    )
    monkeypatch.setattr(
        market_assistant_router,
        "resolve_current_explanation",
        lambda db_path, *, previous_context_id, resolved_at: deepcopy(resolution),
    )
    monkeypatch.setattr(market_assistant_router, "complete_structured", audit)
    monkeypatch.setattr(market_assistant_router, "_react_turn_llm", turn)
    if exploration is not None:
        monkeypatch.setattr(market_assistant_router, "execute_exploration", exploration)
    payload = {"question": question, "mode": "current"}
    if deep_analysis:
        payload["deep_analysis_requested"] = True
    if request_overrides:
        payload.update(request_overrides)
    with client.stream(
        "POST",
        "/api/market-assistant/questions/stream",
        json=payload,
    ) as response:
        lines = list(response.iter_lines())
    events = [json.loads(line) for line in lines]
    return {
        "status_code": response.status_code,
        "events": events,
        "turn": turn,
        "audit_calls": audit_recorder,
        "db_path": db_path,
        "resolution": resolution,
    }


def test_hybrid_stream_fast_path_sequence_and_narration_prompt_contract(
    monkeypatch, tmp_path
):
    text = "现在的市场偏积极，但仍需保持谨慎。"
    order = []
    result = _hybrid_e2e(
        monkeypatch,
        tmp_path,
        steps=[_narration_step(text, deltas=[text])],
        question="现在市场怎么样？",
        order=order,
    )

    assert result["status_code"] == 200
    events = result["events"]
    types = [event["type"] for event in events]
    validating_index = next(
        index
        for index, event in enumerate(events)
        if event == {"type": "status", "status": "validating"}
    )
    validation_index = types.index("validation")
    complete_index = types.index("complete")
    assert types[0] == "resolution"
    assert types.index("initial_tools_started") < types.index("initial_tools_completed")
    assert types.index("initial_tools_completed") < types.index("answer_delta")
    assert "progress" in types
    assert types.index("answer_delta") < validating_index
    assert validating_index < validation_index < complete_index
    assert events[validation_index] == {
        "type": "validation",
        "status": "passed",
        "error_codes": [],
    }
    assert events[complete_index]["generation_status"] == "narration_validated"
    assert order == ["narration", "audit"]

    serialized = json.dumps(result["turn"].calls[0]["input_items"], ensure_ascii=False)
    input_bytes = len(serialized.encode("utf-8"))
    for forbidden in (
        "snapshot_hash",
        "method_manifest",
        "decision_fingerprint",
        "snapshot_json",
    ):
        assert forbidden not in serialized
    assert "explanation_view" in serialized
    assert "setup_explanation_v1" in serialized
    first_items = result["turn"].calls[0]["input_items"]
    assert len(first_items) == 1
    assert first_items[0]["type"] == "message"
    assert [part["type"] for part in first_items[0]["content"]] == [
        "input_text",
        "input_text",
        "input_text",
        "input_text",
    ]
    assert not any(item["type"] == "function_call_output" for item in first_items)
    assert not any(item["type"] == "function_call" for item in first_items)
    from app.services.market_assistant_tool_runtime import snapshot_artifact

    envelope_bytes = len(
        json.dumps(
            snapshot_artifact(result["resolution"]["snapshot"]), ensure_ascii=False
        ).encode("utf-8")
    )
    assert input_bytes < envelope_bytes


def _exploration_payload(query, result_id):
    return {
        "exploration_result_id": result_id,
        "artifact_schema_version": "market_assistant_exploration_result_v1",
        "authority": "local_observation",
        "market_setup_relation": "non_decision",
        "query_contract": deepcopy(query),
        "observed_window": {"start": query.get("start"), "end": query.get("end")},
        "data_through": query.get("end"),
        "rows": [{"date": query.get("end"), "value": 18.4}],
        "deterministic_statistics": {"last_value": 18.4},
        "gaps": {"policy": "not_applicable", "missing_periods": None},
        "object_index": [
            {
                "object_type": "indicator_history",
                "object_id": "credit_history",
                "authority": "local_observation",
                "payload": {
                    "rows": [{"date": query.get("end"), "value": 18.4}],
                    "last_value": 18.4,
                },
            }
        ],
        "result_hash": "a" * 64,
    }


def _function_call_output(input_items, call_id):
    return next(
        item["output"]
        for item in input_items
        if item["type"] == "function_call_output" and item["call_id"] == call_id
    )


def test_hybrid_stream_react_two_rounds_immutable_artifacts_and_audit(
    monkeypatch, tmp_path
):
    answer = (
        "现在市场整体偏积极，但仍需谨慎。当前判断主要依据增长放缓但尚未确认下滑。"
        "信贷状况与增长方向不一致，显示一定冲突。整体组合姿态偏向防御，即降低股票敞口。"
        "如果确认信号转弱，结论会改变。"
    )
    exploration_payloads = {}

    def fake_exploration(con, query, *, result_id, created_at):
        payload = _exploration_payload(query, result_id)
        exploration_payloads[result_id] = deepcopy(payload)
        return payload

    steps = [
        _tool_step(
            [
                {
                    "call_id": "call_vix",
                    "tool_name": "get_confirmation_test",
                    "arguments": {"test_id": "vix"},
                },
                {
                    "call_id": "call_credit_history",
                    "tool_name": "query_indicator_history",
                    "arguments": {"indicator_id": "credit_conditions", "window": "6m"},
                },
            ]
        ),
        _tool_step(
            [
                {
                    "call_id": "call_counterfactuals",
                    "tool_name": "get_approved_counterfactuals",
                    "arguments": {},
                }
            ]
        ),
        _narration_step(answer, deltas=[answer]),
    ]
    result = _hybrid_e2e(
        monkeypatch,
        tmp_path,
        steps=steps,
        question="VIX和信贷最近的变化有什么关系？",
        deep_analysis=True,
        exploration=fake_exploration,
    )

    events = result["events"]
    types = [event["type"] for event in events]
    assert result["status_code"] == 200
    assert types.count("model_turn_started") == 3
    assert types.index("answer_delta") < types.index("validation")
    assert events[-1]["type"] == "complete"
    assert any(
        event == {"type": "validation", "status": "passed", "error_codes": []}
        for event in events
    )

    con = market_assistant_db.connect(result["db_path"])
    try:
        trace = market_assistant_db.load_answer_trace(
            con, events[-1]["answer_trace_id"]
        )
    finally:
        con.close()
    assert trace["generation_status"] == "narration_validated"
    assert trace["route"]["route_id"] == "react"
    assert trace["route"]["budget"]["max_tool_calls"] == 12
    assert trace["timings"]["narration"]["optional_rounds"] == 2
    assert trace["timings"]["narration"]["executed_calls"] == 3
    optional = [entry for entry in trace["tool_trace"] if entry["phase"] == "optional"]
    assert len(optional) == 3
    assert all(entry["status"] == "executed" for entry in optional)
    assert {entry["tool_name"] for entry in optional} == {
        "get_confirmation_test",
        "query_indicator_history",
        "get_approved_counterfactuals",
    }
    assert len(trace["exploration_result_ids"]) == 1

    first_message = result["turn"].calls[0]["input_items"][0]
    first_view = json.loads(first_message["content"][1]["text"])["explanation_view"]
    assert first_view["view_version"] == "react_anchor_v1"
    assert set(first_view["results"]) == {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    }
    assert first_view["context_id"] == result["resolution"]["snapshot"]["context_id"]

    final_message = result["turn"].calls[2]["input_items"][0]
    final_view = json.loads(final_message["content"][1]["text"])["explanation_view"]
    assert final_view["view_version"] == "react_anchor_v1"

    second_items = result["turn"].calls[1]["input_items"]
    credit_output = json.loads(
        _function_call_output(second_items, "call_credit_history")
    )
    assert credit_output["status"] == "available"
    assert credit_output["artifact_kind"] == "exploration_result"
    assert credit_output["primary_authority"] == "local_observation"
    exploration_id = credit_output["artifact_id"]
    assert exploration_id in exploration_payloads
    assert credit_output["payload"] == exploration_payloads[exploration_id]
    query_contract = credit_output["payload"]["query_contract"]
    assert query_contract["query_kind"] == "indicator_history"
    assert query_contract["indicator_id"] == "credit_conditions"
    assert (
        query_contract["start"]
        == exploration_payloads[exploration_id]["query_contract"]["start"]
    )
    assert (
        query_contract["end"]
        == exploration_payloads[exploration_id]["query_contract"]["end"]
    )

    vix_output = json.loads(_function_call_output(second_items, "call_vix"))
    assert vix_output["primary_authority"] == "decision_fact"
    assert vix_output["market_setup_relation"] == "authoritative_snapshot"


def _credit_conditions_exploration_payload(query, result_id):
    rows = [
        {
            "date": "2026-05-01",
            "state": "healthy",
            "method_version": "credit_conditions_history_v1",
            "decision_method_version": "credit_conditions_v1",
        },
        {
            "date": "2026-07-06",
            "state": "weak_credit_warning",
            "method_version": "credit_conditions_history_v1",
            "decision_method_version": "credit_conditions_v1",
        },
        {
            "date": "2026-08-10",
            "state": "risk_rising",
            "method_version": "credit_conditions_history_v1",
            "decision_method_version": "credit_conditions_v1",
        },
    ]
    statistics = {
        "first_state": "healthy",
        "last_state": "risk_rising",
        "state_counts": {
            "healthy": 1,
            "weak_credit_warning": 1,
            "risk_rising": 1,
        },
        "transition_count": 2,
        "latest_transition": {
            "date": "2026-08-10",
            "from_state": "weak_credit_warning",
            "to_state": "risk_rising",
        },
        "current_run_start": "2026-08-10",
        "current_run_observations": 1,
    }
    objects = [
        {
            "object_type": "observation_row",
            "object_id": f"credit_conditions:{row['date']}",
            "authority": "local_observation",
            "payload": row,
        }
        for row in rows
    ]
    for statistic_id, statistic_value in statistics.items():
        objects.append(
            {
                "object_type": "deterministic_statistic",
                "object_id": statistic_id,
                "authority": "local_observation",
                "payload": {
                    "statistic_id": statistic_id,
                    "value": statistic_value,
                },
            }
        )
    return {
        "exploration_result_id": result_id,
        "artifact_schema_version": "market_assistant_exploration_result_v1",
        "authority": "local_observation",
        "market_setup_relation": "non_decision",
        "query_contract": deepcopy(query),
        "observed_window": {"start": query.get("start"), "end": query.get("end")},
        "data_through": "2026-08-10",
        "rows": rows,
        "deterministic_statistics": statistics,
        "gaps": {"policy": "not_applicable", "missing_periods": None},
        "object_index": objects,
        "result_hash": "a" * 64,
    }


def test_hybrid_stream_react_consumes_categorical_credit_history_without_new_tool(
    monkeypatch, tmp_path
):
    answer = (
        "本地信贷条件历史显示，5月初为健康状态，7月转为弱信用警告，"
        "截至 2026-08-10 已转为风险上升，这一状态从 2026-08-10 开始延续。"
        "最新一次状态转换发生在 2026-08-10，从弱信用警告转向风险上升。"
        "这是对本地已接受观测的解释，不独立改变市场设置。"
    )
    exploration_payloads = {}

    def fake_exploration(con, query, *, result_id, created_at):
        payload = _credit_conditions_exploration_payload(query, result_id)
        exploration_payloads[result_id] = deepcopy(payload)
        return payload

    steps = [
        _tool_step(
            [
                {
                    "call_id": "call_credit_history",
                    "tool_name": "query_indicator_history",
                    "arguments": {
                        "indicator_id": "credit_conditions",
                        "window": "6m",
                    },
                }
            ]
        ),
        _narration_step(answer, deltas=[answer]),
    ]
    result = _hybrid_e2e(
        monkeypatch,
        tmp_path,
        steps=steps,
        question="信贷条件是最近才恶化，还是已经持续一段时间？",
        exploration=fake_exploration,
    )

    events = result["events"]
    types = [event["type"] for event in events]
    assert result["status_code"] == 200
    assert types.count("model_turn_started") == 2
    assert any(
        event == {"type": "validation", "status": "passed", "error_codes": []}
        for event in events
    )

    con = market_assistant_db.connect(result["db_path"])
    try:
        trace = market_assistant_db.load_answer_trace(
            con, events[-1]["answer_trace_id"]
        )
    finally:
        con.close()
    assert trace["generation_status"] == "narration_validated"
    assert trace["route"]["route_id"] == "react"
    assert len(trace["exploration_result_ids"]) == 1
    executed = [entry for entry in trace["tool_trace"] if entry["status"] == "executed"]
    assert {entry["tool_name"] for entry in executed} == {"query_indicator_history"}

    second_items = result["turn"].calls[1]["input_items"]
    credit_output = json.loads(
        _function_call_output(second_items, "call_credit_history")
    )
    assert credit_output["status"] == "available"
    assert credit_output["artifact_kind"] == "exploration_result"
    assert credit_output["primary_authority"] == "local_observation"
    assert credit_output["market_setup_relation"] == "non_decision"
    exploration_id = credit_output["artifact_id"]
    assert exploration_id in exploration_payloads
    assert credit_output["payload"] == exploration_payloads[exploration_id]
    statistics = credit_output["payload"]["deterministic_statistics"]
    assert statistics["last_state"] == "risk_rising"
    assert statistics["current_run_start"] == "2026-08-10"
    assert statistics["latest_transition"]["to_state"] == "risk_rising"
    assert any(
        obj["object_type"] == "observation_row"
        and obj["object_id"].startswith("credit_conditions:")
        for obj in credit_output["payload"]["object_index"]
    )
