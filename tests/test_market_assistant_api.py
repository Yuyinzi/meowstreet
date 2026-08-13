import json

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.db import market_assistant as market_assistant_db
from app.routers import market_assistant as market_assistant_router
from app.services import market_assistant as market_assistant_service

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
