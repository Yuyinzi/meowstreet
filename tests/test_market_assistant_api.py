import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.db import market_assistant as market_assistant_db
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
