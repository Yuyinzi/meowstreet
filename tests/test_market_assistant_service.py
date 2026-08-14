import asyncio
import inspect
import json
import logging
from copy import deepcopy

import pytest

from app.db import market_assistant as market_assistant_db
from app.services import market_assistant
from app.services import market_assistant_react
from app.services.market_assistant import ASSISTANT_POLICY_VERSION
from app.services.market_assistant import PROMPT_VERSION
from app.services.market_assistant_react import run_hybrid_narration
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_artifacts import resolve_artifact_ref
from app.tools.market_assistant_knowledge import load_knowledge_catalog
from app.tools.market_assistant_routes import route_question
from app.tools.market_setup_explanation_snapshot import canonical_json


def current_question(question="Why is the current setup Mild Risk-Off?", **overrides):
    payload = {
        "question": question,
        "mode": "current",
        "previous_context_id": None,
        "deep_research_requested": False,
    }
    payload.update(overrides)
    return payload


def fake_snapshot():
    return {
        "context_id": "ctx_123",
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
            {
                "fact_id": "vix_level",
                "indicator_id": "vix",
                "label": "VIX",
                "accepted_values": {"level": 18.4},
                "data_status": {"state": "available"},
                "participation": {"state": "applied"},
                "decision_result": {"evaluation": {"state": "evaluated"}},
            }
        ],
        "method_contracts": {
            "version": "market_setup_explanation_methods_v1",
            "methods": {},
        },
        "counterfactuals": [],
    }


def resolution_envelope(previous_context_id=None, context_id="ctx_123"):
    return {
        "resolution": {
            "mode": "current",
            "resolved_at": "2026-08-10T02:00:00Z",
            "previous_context_id": previous_context_id,
            "current_context_id": context_id,
            "context_changed": previous_context_id != context_id,
        },
        "delta": {"results_changed": False, "changes": []},
        "snapshot": fake_snapshot(),
    }


def _config(**overrides):
    config = {
        "model": "assistant-model",
        "research_model": "research-model",
        "provider": "openai_responses",
        "structured_output_mode": "json_object",
        "research_enabled": True,
        "supports_web_search": True,
        "api_key": "sk-secret-test-key",
        "base_url": None,
    }
    config.update(overrides)
    return config


def _dummy_con():
    return _DummyCon()


class _DummyCon:
    def close(self):
        pass


def knowledge_catalog():
    return {
        "version": "market_assistant_knowledge_v1",
        "records": [
            {
                "record_id": "vix_definition",
                "version": "vix_confirmation_v2",
                "object_type": "indicator_definition",
                "authority": "method_knowledge",
                "indicator_id": "vix",
                "title": "VIX Definition",
                "explanation": "The VIX measures expected 30-day volatility.",
                "source": {
                    "source_module": "market_setup_evidence_facts",
                    "method_version": "vix_confirmation_v2",
                },
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


def research_unavailable():
    return {
        "authority": "external_research",
        "market_setup_relation": "non_decision",
        "research_result_id": "res_1",
        "status": "research_unavailable",
        "reason_code": "provider_error",
        "searched_at": "2026-08-10T02:00:00Z",
    }


def narration_step(text="现在的市场偏积极，但仍需保持谨慎。", deltas=None, error=None):
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


def tool_step(calls):
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


class _ScriptedStream:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

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
                "observer": observer,
            }
        )
        for event in step.get("observer_events") or []:
            result = observer(event)
            if inspect.isawaitable(result):
                await result
        if step.get("error") is not None:
            raise step["error"]
        return step["result"]


class RecordingSink:
    def __init__(self):
        self.events = []

    async def send(self, event):
        self.events.append(event)


def _default_narration_stream():
    text = "现在的市场偏积极，但仍需保持谨慎。"
    return _ScriptedStream([narration_step(text, deltas=[text])])


def _setup_result_artifact_id(artifact_projection):
    for artifact_id, artifact in artifact_projection.items():
        for obj in artifact.get("object_index") or []:
            if (
                obj.get("object_type") == "market_setup_result"
                and obj.get("object_id") == "macro_regime"
            ):
                return artifact_id
    return None


def _valid_audit_payload(answer_text, artifact_projection=None, **kwargs):
    artifact_id = _setup_result_artifact_id(artifact_projection or {})
    if artifact_id is None:
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
            "refs": [
                {
                    "artifact_id": artifact_id,
                    "object_type": "market_setup_result",
                    "object_id": "macro_regime",
                }
            ],
            "values": [],
        }
    return {"claims": [claim]}


def _invalid_audit_payload(answer_text, artifact_projection=None, **kwargs):
    return {
        "claims": [
            {
                "claim_id": "claim_bad",
                "start": 0,
                "end": len(answer_text),
                "exact_text": answer_text + " unapproved claim",
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [
                    {
                        "artifact_id": "ctx_123_overview",
                        "object_type": "market_setup_result",
                        "object_id": "macro_regime",
                    }
                ],
                "values": [],
            }
        ]
    }


class HybridDependencies:
    def __init__(
        self,
        *,
        stream=None,
        audit=None,
        resolve=None,
        config=None,
        research=None,
        exploration=None,
        catalog=None,
        route=None,
    ):
        self.db_path = ":memory:"
        self.config = config if config is not None else _config()
        self.client = object()
        self.model = self.config["model"]
        self.reasoning_effort = self.config.get("reasoning_effort", "low")
        self.stream_turn = stream if stream is not None else _default_narration_stream()
        self.audit_timeout_seconds = self.config.get("audit_timeout_seconds")
        self._audit = audit
        self._resolve = resolve if resolve is not None else resolution_envelope()
        self._research = research if research is not None else research_unavailable()
        self._exploration = (
            exploration if exploration is not None else exploration_result()
        )
        self._catalog = catalog if catalog is not None else knowledge_catalog()
        self._route = route
        self.saved_trace = None
        self.saved_artifacts = None
        self.tool_execution_count = 0
        self.llm_calls = []
        self.audit_kwargs = None

    def route_question(self, question, *, deep_analysis):
        if self._route is not None:
            return deepcopy(self._route)
        return route_question(question, deep_analysis=deep_analysis)

    async def claim_audit_llm(
        self, *, answer_text, explanation_view, artifact_projection
    ):
        self.llm_calls.append("audit")
        self.audit_kwargs = {
            "answer_text": answer_text,
            "explanation_view": explanation_view,
            "artifact_projection": artifact_projection,
        }
        if isinstance(self._audit, Exception):
            raise self._audit
        if callable(self._audit):
            result = self._audit(
                answer_text=answer_text, artifact_projection=artifact_projection
            )
            if inspect.isawaitable(result):
                return await result
            return result
        if self._audit is not None:
            return self._audit
        return _valid_audit_payload(answer_text, artifact_projection)

    def resolve_current_explanation(self, db_path, *, previous_context_id, resolved_at):
        self.tool_execution_count += 1
        return self._resolve

    def load_snapshot(self, con, context_id):
        return self._resolve["snapshot"]

    def connect(self, db_path):
        return _dummy_con()

    def load_knowledge_catalog(self):
        return self._catalog

    def exploration(self, con, query, *, result_id, created_at):
        self.tool_execution_count += 1
        return self._exploration

    async def acquire_research(
        self, provider, task, *, result_id, searched_at, explicit_deep=False
    ):
        self.tool_execution_count += 1
        return self._research

    def build_research_provider(self, config):
        return object()

    def save_bundle(self, con, *, artifacts, answer_trace):
        self.saved_trace = answer_trace
        self.saved_artifacts = list(artifacts)


def hybrid_dependencies(**kwargs):
    return HybridDependencies(**kwargs)


class HybridRealPersistenceDeps:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.config = _config()
        self.client = object()
        self.model = self.config["model"]
        self.reasoning_effort = self.config.get("reasoning_effort", "low")
        self.stream_turn = _default_narration_stream()
        self.audit_timeout_seconds = None
        self.llm_calls = []

    async def claim_audit_llm(
        self, *, answer_text, explanation_view, artifact_projection
    ):
        self.llm_calls.append("audit")
        return _valid_audit_payload(answer_text, artifact_projection)

    def connect(self, db_path):
        return market_assistant_db.connect(db_path)

    def save_bundle(self, con, *, artifacts, answer_trace):
        market_assistant_db.save_answer_bundle(
            con, artifacts=artifacts, answer_trace=answer_trace
        )

    def resolve_current_explanation(self, db_path, *, previous_context_id, resolved_at):
        return resolve_current_explanation(
            db_path, previous_context_id=previous_context_id, resolved_at=resolved_at
        )


@pytest.mark.asyncio
async def test_answer_streams_before_claim_audit():
    sink = RecordingSink()
    await market_assistant.answer_question(
        current_question("现在市场怎么样？"),
        dependencies=hybrid_dependencies(),
        event_sink=sink,
    )
    types = [event["type"] for event in sink.events]
    answer_index = types.index("answer_delta")
    validating_index = next(
        index
        for index, event in enumerate(sink.events)
        if event == {"type": "status", "status": "validating"}
    )
    validation_index = types.index("validation")
    assert answer_index < validating_index < validation_index


@pytest.mark.asyncio
async def test_audit_failure_visibility():
    deps = hybrid_dependencies(audit=_invalid_audit_payload)
    sink = RecordingSink()

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"),
        dependencies=deps,
        event_sink=sink,
    )

    assert response["generation_status"] == "narration_validation_failed"
    assert response["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"
    assert not any(event["type"] == "answer_replace" for event in sink.events)
    assert deps.saved_trace["answer_text"] == response["answer_text"]
    assert deps.saved_trace["generation_status"] == "narration_validation_failed"
    report = deps.saved_trace["claim_audit"]["validation"]
    assert report["valid"] is False
    assert [error["code"] for error in report["errors"]] == ["ANSWER_TEXT_MISMATCH"]
    assert deps.saved_trace["validation_error_codes"] == ["ANSWER_TEXT_MISMATCH"]


@pytest.mark.asyncio
async def test_disabled_claim_validation_persists_narration_validation_disabled(caplog):
    deps = hybrid_dependencies(config=_config(claim_validation_enabled=False))
    sink = RecordingSink()

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = await market_assistant.answer_question(
            current_question("现在市场怎么样？"),
            dependencies=deps,
            event_sink=sink,
        )

    assert response["generation_status"] == "narration_validation_disabled"
    assert response["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"
    assert "audit" not in deps.llm_calls
    validations = [event for event in sink.events if event["type"] == "validation"]
    assert validations == [
        {"type": "validation", "status": "disabled", "error_codes": []}
    ]
    assert not any(event["type"] == "answer_replace" for event in sink.events)
    assert deps.saved_trace["generation_status"] == "narration_validation_disabled"
    assert deps.saved_trace["claim_audit"]["audit"] is None
    assert deps.saved_trace["attempts"] == {"narration": 1, "audit": 0}
    assert "audit_completed" not in _observed_stages(caplog)


@pytest.mark.asyncio
async def test_claim_validation_remains_enabled_when_config_key_is_absent():
    config = _config()
    config.pop("claim_validation_enabled", None)
    deps = hybrid_dependencies(config=config)

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"), dependencies=deps
    )

    assert response["generation_status"] == "narration_validated"
    assert "audit" in deps.llm_calls


@pytest.mark.asyncio
async def test_audit_timeout_emits_validation_unavailable_without_repair():
    async def hang_forever(**kwargs):
        await asyncio.Event().wait()

    deps = hybrid_dependencies(
        audit=hang_forever,
        config=_config(audit_timeout_seconds=0.01),
    )
    sink = RecordingSink()

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"),
        dependencies=deps,
        event_sink=sink,
    )

    assert response["generation_status"] == "narration_validation_unavailable"
    assert response["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"
    assert deps.saved_trace["generation_status"] == "narration_validation_unavailable"
    assert deps.saved_trace["claim_audit"]["audit"] is None
    validations = [event for event in sink.events if event["type"] == "validation"]
    assert validations == [
        {"type": "validation", "status": "unavailable", "error_codes": []}
    ]
    assert len(deps.stream_turn.calls) == 1


@pytest.mark.asyncio
async def test_narration_failure_before_text_renders_deterministic_fallback(caplog):
    stream = _ScriptedStream([narration_step(error=RuntimeError("llm down"))])
    deps = hybrid_dependencies(stream=stream)
    sink = RecordingSink()

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"),
        dependencies=deps,
        event_sink=sink,
    )

    assert response["generation_status"] == "deterministic_fallback"
    assert response["answer_text"].startswith("Market Setup decision result:")
    assert deps.saved_trace["generation_status"] == "deterministic_fallback"
    assert deps.saved_trace["narration_status"] == "narration_unavailable"
    assert any(event["type"] == "answer_replace" for event in sink.events)
    validations = [event for event in sink.events if event["type"] == "validation"]
    assert validations == [
        {"type": "validation", "status": "fallback", "error_codes": []}
    ]


@pytest.mark.asyncio
async def test_narration_interrupted_keeps_partial_text_and_emits_notice():
    stream = _ScriptedStream(
        [narration_step(deltas=["部分文本"], error=RuntimeError("cut off"))]
    )
    deps = hybrid_dependencies(stream=stream)
    sink = RecordingSink()

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"),
        dependencies=deps,
        event_sink=sink,
    )

    assert response["generation_status"] == "narration_interrupted"
    assert response["answer_text"] == "部分文本"
    assert deps.saved_trace["generation_status"] == "narration_interrupted"
    assert "audit" not in deps.llm_calls
    validations = [event for event in sink.events if event["type"] == "validation"]
    assert validations == [
        {"type": "validation", "status": "interrupted", "error_codes": []}
    ]


@pytest.mark.asyncio
async def test_hybrid_answer_uses_one_narration_turn_and_persists_trace():
    deps = hybrid_dependencies()

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"), dependencies=deps
    )

    assert response["generation_status"] == "narration_validated"
    assert response["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"
    assert deps.llm_calls == ["audit"]
    assert deps.saved_trace["answer_text"] == response["answer_text"]


@pytest.mark.asyncio
async def test_hybrid_answer_trace_has_required_fields_and_no_secrets():
    deps = hybrid_dependencies()
    await market_assistant.answer_question(
        current_question("现在市场怎么样？"), dependencies=deps
    )
    trace = deps.saved_trace

    expected_fields = {
        "answer_trace_id",
        "message_id",
        "resolution",
        "explanation_context_id",
        "request_controls",
        "route",
        "tool_trace",
        "budget",
        "explanation_view",
        "knowledge_references",
        "snapshot_artifact_ids",
        "exploration_result_ids",
        "research_result_ids",
        "plan",
        "structured_claims",
        "generation_status",
        "attempts",
        "validation_error_codes",
        "prompt",
        "model_configuration_fingerprint",
        "tool_schema_versions",
        "answer_text",
        "answer_text_hash",
        "claim_audit",
        "timings",
        "generated_time",
    }
    assert expected_fields.issubset(trace)
    assert trace["answer_trace_id"].startswith("trc_")
    assert trace["message_id"].startswith("msg_")
    assert trace["generation_status"] == "narration_validated"
    assert trace["route"]["route_id"] == "current_setup_overview"
    assert trace["route"]["routing_source"] == "deterministic"
    assert trace["request_controls"]["mode"] == "current"
    assert trace["request_controls"]["deep_analysis_requested"] is False
    assert trace["explanation_view"]["view_version"] == "setup_explanation_v1"
    assert len(trace["explanation_view"]["view_hash"]) == 64
    assert isinstance(trace["tool_trace"], list)
    assert trace["claim_audit"]["validation"]["valid"] is True
    assert trace["claim_audit"]["audit"]["claims"]
    assert trace["timings"]["narration"]["executed_calls"] == 0
    assert trace["attempts"] == {"narration": 1, "audit": 1}
    assert trace["plan"] is None
    assert trace["structured_claims"] is None
    assert trace["prompt"]["version"] == PROMPT_VERSION
    assert len(trace["prompt"]["hash"]) == 64
    assert trace["model_configuration_fingerprint"]["prompt_version"] == PROMPT_VERSION
    assert (
        trace["model_configuration_fingerprint"]["assistant_policy_version"]
        == ASSISTANT_POLICY_VERSION
    )
    assert trace["model_configuration_fingerprint"]["model"] == "assistant-model"
    assert len(trace["answer_text_hash"]) == 64
    assert "api_key" not in json.dumps(trace)
    assert "sk-secret-test-key" not in json.dumps(trace)
    assert "api_key" not in json.dumps(trace["model_configuration_fingerprint"])


@pytest.mark.asyncio
async def test_deep_analysis_selects_deep_budget_route():
    deps = hybrid_dependencies()
    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？", deep_analysis_requested=True),
        dependencies=deps,
    )

    assert response["generation_status"] == "narration_validated"
    assert deps.saved_trace["route"]["budget"]["max_rounds"] == 4
    assert deps.saved_trace["route"]["budget"]["max_tool_calls"] == 12
    assert deps.saved_trace["route"]["budget"]["deadline_seconds"] == 300.0


@pytest.mark.asyncio
async def test_knowledge_operation_acquires_knowledge_record_artifact():
    deps = hybrid_dependencies()

    response = await market_assistant.answer_question(
        current_question("VIX 是什么？"), dependencies=deps
    )

    assert response["generation_status"] == "narration_validated"
    assert deps.saved_trace["knowledge_references"] == ["vix_definition"]


@pytest.mark.asyncio
async def test_knowledge_definition_through_real_catalog_aliases_vix():
    deps = hybrid_dependencies(catalog=load_knowledge_catalog())

    response = await market_assistant.answer_question(
        current_question("VIX 是什么？"), dependencies=deps
    )

    assert response["generation_status"] == "narration_validated"
    assert deps.saved_trace["knowledge_references"] == ["vix_definition"]


@pytest.mark.asyncio
async def test_unknown_knowledge_indicator_routes_to_fallback():
    catalog = {"version": "market_assistant_knowledge_v1", "records": []}
    stream = _ScriptedStream([narration_step(error=RuntimeError("llm down"))])
    deps = hybrid_dependencies(stream=stream, catalog=catalog)

    response = await market_assistant.answer_question(
        current_question("VIX 是什么？"), dependencies=deps
    )

    assert response["generation_status"] == "deterministic_fallback"
    assert (
        "The approved knowledge record is currently unavailable."
        in response["answer_text"]
    )


@pytest.mark.asyncio
async def test_exploration_operation_acquires_exploration_result_artifact():
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_1",
                        "tool_name": "query_indicator_history",
                        "arguments": {
                            "indicator_id": "vix",
                            "window": "6m",
                        },
                    }
                ]
            ),
            narration_step(),
        ]
    )
    deps = hybrid_dependencies(stream=stream)

    response = await market_assistant.answer_question(
        current_question("VIX 确认了吗？"), dependencies=deps
    )

    assert response["generation_status"] == "narration_validated"
    assert deps.saved_trace["exploration_result_ids"] == ["expl_1"]
    assert deps.tool_execution_count == 2


@pytest.mark.asyncio
async def test_external_search_disabled_never_executes_research():
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_1",
                        "tool_name": "research_focused",
                        "arguments": {
                            "purpose": "current_events",
                            "queries": ["latest vix"],
                            "expected_source_class": "official_publication",
                        },
                    }
                ]
            ),
            narration_step(),
        ]
    )
    deps = hybrid_dependencies(stream=stream)

    response = await market_assistant.answer_question(
        current_question("讲个笑话", external_search_requested=False),
        dependencies=deps,
    )

    assert response["generation_status"] == "narration_validated"
    assert deps.tool_execution_count == 1
    assert any(
        item["tool_name"] == "research_focused" and item["status"] == "rejected"
        for item in deps.saved_trace["tool_trace"]
    )
    assert deps.saved_trace["research_result_ids"] == []


@pytest.mark.asyncio
async def test_context_change_surfaces_in_resolution_not_answer_text():
    deps = hybrid_dependencies(resolve=resolution_envelope(previous_context_id="ctx_A"))
    request = current_question("现在市场怎么样？", previous_context_id="ctx_A")
    response = await market_assistant.answer_question(request, dependencies=deps)

    assert response["resolution"]["context_changed"] is True
    assert response["resolution"]["previous_context_id"] == "ctx_A"
    assert response["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"


@pytest.mark.asyncio
async def test_hybrid_persists_narration_artifacts_not_the_full_snapshot():
    deps = hybrid_dependencies()
    await market_assistant.answer_question(
        current_question("现在市场怎么样？"), dependencies=deps
    )

    persisted_ids = [artifact["artifact_id"] for artifact in deps.saved_artifacts]
    assert "ctx_123" not in persisted_ids
    assert "ctx_123_overview" in persisted_ids
    assert "ctx_123_macro_regime" in persisted_ids


@pytest.mark.asyncio
async def test_persistence_failure_raises_stable_error():
    deps = hybrid_dependencies()

    def fail_save(con, *, artifacts, answer_trace):
        raise RuntimeError("disk full")

    deps.save_bundle = fail_save

    with pytest.raises(ValueError, match="answer trace persistence failed"):
        await market_assistant.answer_question(
            current_question("现在市场怎么样？"), dependencies=deps
        )
    assert deps.saved_trace is None


@pytest.mark.asyncio
async def test_hybrid_answer_persists_real_bundle_with_durable_snapshot(tmp_path):
    db_path = tmp_path / "assistant.sqlite"
    deps = HybridRealPersistenceDeps(db_path)
    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"), dependencies=deps
    )

    assert response["generation_status"] == "narration_validated"
    con = market_assistant_db.connect(db_path)
    try:
        trace = market_assistant_db.load_answer_trace(con, response["answer_trace_id"])
        assert trace is not None
        assert trace["route"]["route_id"] == "current_setup_overview"
        snapshot = market_assistant_db.load_snapshot(
            con, trace["explanation_context_id"]
        )
        assert snapshot is not None
    finally:
        con.close()


@pytest.mark.asyncio
async def test_market_setup_results_byte_identical_across_assistant_modes():
    baseline = canonical_json(fake_snapshot()["results"])
    cases = [
        (
            hybrid_dependencies(),
            current_question("现在市场怎么样？"),
        ),
        (
            hybrid_dependencies(config=_config(claim_validation_enabled=False)),
            current_question("现在市场怎么样？"),
        ),
        (
            hybrid_dependencies(),
            current_question("现在市场怎么样？", deep_analysis_requested=True),
        ),
        (
            hybrid_dependencies(),
            current_question("讲个笑话", external_search_requested=False),
        ),
        (
            hybrid_dependencies(audit=_invalid_audit_payload),
            current_question("现在市场怎么样？"),
        ),
    ]
    observed = []
    for deps, request in cases:
        await market_assistant.answer_question(request, dependencies=deps)
        observed.append(canonical_json(deps._resolve["snapshot"]["results"]))
    assert observed == [baseline] * len(cases)


@pytest.mark.asyncio
async def test_stream_answer_question_yields_events_and_stops_at_complete():
    deps = hybrid_dependencies()

    events = [
        event
        async for event in market_assistant.stream_answer_question(
            current_question("现在市场怎么样？"), dependencies=deps
        )
    ]

    assert events[-1]["type"] == "complete"
    assert events[-1]["generation_status"] == "narration_validated"
    assert events[-1]["answer_trace_id"]
    assert events[-1]["citations"] == []
    assert deps.saved_trace is not None


@pytest.mark.asyncio
async def test_stream_events_carry_stable_request_id_without_fingerprint_leak():
    deps = hybrid_dependencies()

    events = [
        event
        async for event in market_assistant.stream_answer_question(
            current_question("现在市场怎么样？"), dependencies=deps
        )
    ]

    resolution_event = next(event for event in events if event["type"] == "resolution")
    complete_event = events[-1]
    assert complete_event["type"] == "complete"
    assert resolution_event["request_id"].startswith("req_")
    assert resolution_event["request_id"] == complete_event["request_id"]
    assert deps.saved_trace is not None
    assert "request_id" not in json.dumps(deps.saved_trace)


@pytest.mark.asyncio
async def test_stage_logs_include_request_id_and_exclude_privacy(caplog):
    text = "现在的市场偏积极，但仍需保持谨慎。"
    stream = _ScriptedStream(
        [
            {
                "result": {
                    "output_text": text,
                    "tool_calls": [],
                    "response_items": [],
                    "usage": None,
                    "timings": {},
                },
                "observer_events": [
                    {"type": "reasoning_started"},
                    {"type": "output_delta", "delta": "  "},
                    {"type": "output_delta", "delta": text},
                ],
            }
        ]
    )
    deps = hybrid_dependencies(stream=stream)

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await market_assistant.answer_question(
            current_question("现在市场怎么样？"), dependencies=deps
        )

    stage_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "uvicorn.error"
        and "market assistant stage" in record.getMessage()
    ]
    expected_stages = {
        "resolution_completed",
        "route_selected",
        "initial_tools_completed",
        "react_round_started",
        "narration_request_started",
        "first_reasoning_delta",
        "first_output_text_delta",
        "first_user_visible_delta",
        "narration_completed",
        "audit_completed",
        "request_completed",
    }
    observed = [line.split("stage=")[1].split()[0] for line in stage_lines]
    assert len(observed) == len(set(observed))
    assert expected_stages.issubset(set(observed))
    for line in stage_lines:
        assert "request_id=req_" in line
        assert "elapsed_seconds=" in line

    combined = " ".join(stage_lines)
    for forbidden in (
        "现在市场怎么样",
        "偏积极",
        "sk-secret-test-key",
        "ctx_123",
        "expl_1",
        "test_ids",
        "reasoning_text",
        "prompt",
    ):
        assert forbidden not in combined


def _observed_stages(caplog):
    stage_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "uvicorn.error"
        and "market assistant stage" in record.getMessage()
    ]
    return {line.split("stage=")[1].split()[0] for line in stage_lines}


@pytest.mark.asyncio
async def test_react_round_completed_stage_recorded_when_optional_round_runs(caplog):
    stream = _ScriptedStream(
        [
            tool_step([_confirmation_call("call_vix", "vix")]),
            narration_step(),
        ]
    )
    deps = hybrid_dependencies(stream=stream)

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await market_assistant.answer_question(
            current_question("讲个笑话"), dependencies=deps
        )

    assert "react_round_completed" in _observed_stages(caplog)
    assert deps.saved_trace["timings"]["narration"]["optional_rounds"] == 1


@pytest.mark.asyncio
async def test_react_round_completed_stage_not_recorded_without_optional_round(caplog):
    deps = hybrid_dependencies()

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await market_assistant.answer_question(
            current_question("现在市场怎么样？"), dependencies=deps
        )

    assert "react_round_completed" not in _observed_stages(caplog)
    assert deps.saved_trace["timings"]["narration"]["optional_rounds"] == 0


@pytest.mark.asyncio
async def test_stream_answer_question_sends_error_and_stops_without_trace():
    deps = hybrid_dependencies()

    def fail_save(con, *, artifacts, answer_trace):
        raise RuntimeError("disk full")

    deps.save_bundle = fail_save

    events = [
        event
        async for event in market_assistant.stream_answer_question(
            current_question("现在市场怎么样？"), dependencies=deps
        )
    ]

    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "market assistant service is unavailable"
    assert not any(event["type"] == "complete" for event in events)
    assert deps.saved_trace is None


@pytest.mark.asyncio
async def test_stream_answer_question_aclose_cancels_worker_and_narration_task():
    deps = hybrid_dependencies()
    cancelled = []
    started = asyncio.Event()

    async def hanging_stream(
        client,
        *,
        model,
        input_items,
        instructions,
        tools,
        reasoning_effort,
        observer=None,
    ):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    deps.stream_turn = hanging_stream

    generator = market_assistant.stream_answer_question(
        current_question("现在市场怎么样？"), dependencies=deps
    )
    assert (await anext(generator))["type"] == "resolution"
    await asyncio.wait_for(started.wait(), timeout=0.5)
    await generator.aclose()

    assert cancelled == [True]
    assert deps.saved_trace is None


def test_audit_artifact_projection_keeps_objects_without_snapshot_bulk():
    artifacts = _projection_artifacts()

    projection = market_assistant._audit_artifact_projection(artifacts)

    artifact = projection["ctx_123"]
    assert "payload" not in artifact
    assert artifact["primary_authority"] == "decision_fact"
    assert artifact["market_setup_relation"] == "authoritative_snapshot"
    assert any(
        obj["object_type"] == "market_setup_result"
        and obj["object_id"] == "macro_regime"
        for obj in artifact["object_index"]
    )


def test_decision_explanation_projection_excludes_non_decision_display_objects():
    artifact = {
        "artifact_id": "ctx_123",
        "artifact_kind": "explanation_snapshot",
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "object_index": [
            {
                "object_type": "evidence_fact",
                "object_id": "survey_growth_direction",
                "authority": "decision_fact",
                "payload": {
                    "role": {"function": "selector"},
                    "participation": {"state": "applied"},
                },
            },
            {
                "object_type": "evidence_fact",
                "object_id": "cyclical_commodities",
                "authority": "decision_fact",
                "payload": {
                    "role": {"function": "display_only"},
                    "participation": {"state": "not_applied"},
                    "large_unused_payload": "x" * 1000,
                },
            },
            {
                "object_type": "method_contract",
                "object_id": "vix_confirmation_v2",
                "authority": "method_knowledge",
                "payload": {"description": "Not needed for a general setup answer."},
            },
        ],
    }

    projected = market_assistant._llm_artifact_projection(
        {"ctx_123": artifact}, _decision_plan()
    )

    assert [item["object_id"] for item in projected["ctx_123"]["object_index"]] == [
        "survey_growth_direction"
    ]


def _decision_plan(intent="decision_explanation", **overrides):
    plan = {
        "intent": intent,
        "context_mode": "current",
        "operations": [
            {"operation_id": "resolve_current_explanation", "parameters": {}}
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    plan.update(overrides)
    return plan


def _projection_evidence_fact(fact_id, role_function, source_period):
    return {
        "fact_id": fact_id,
        "indicator_id": "vix" if fact_id == "vix_level" else fact_id,
        "label": "VIX" if fact_id == "vix_level" else fact_id,
        "accepted_values": (
            {"level": 18.4} if fact_id == "vix_level" else {"direction": "slowing"}
        ),
        "classifications": {"level": "elevated"},
        "role": {
            "decision_scope": "confirmation_input",
            "function": role_function,
            "target_layer": "market_confirmation",
            "allowed_effects": [],
        },
        "data_status": {"state": "available"},
        "participation": {"state": "applied"},
        "decision_result": {"kind": "evaluated", "evaluation": {"state": "evaluated"}},
        "provenance": {
            "source_module": "market_setup_evidence_facts",
            "source_id": fact_id,
            "method_references": ["vix_confirmation_v2"],
            "source_period": source_period,
        },
        "finding": {"state": "evaluated", "confirms": True},
    }


def _projection_snapshot():
    return {
        "context_id": "ctx_123",
        "results": {
            "macro_regime": {
                "code": "growth_decelerating",
                "label": "Growth Decelerating",
                "primary_source": "ism_survey_synthesis",
                "supports": [{"fact_id": "survey_growth_direction"}],
                "conflicts": [{"fact_id": "macro_policy_response"}],
                "missing_inputs": [],
                "excluded_inputs": ["housing_starts"],
                "method_version": "market_setup_v2_macro_regime_v1",
                "source_periods": {
                    "survey_growth_direction": {"reference_period": "2026-06"}
                },
            },
            "market_confirmation": {
                "code": "downside_confirmation",
                "label": "Downside Confirmation",
                "confirmation_test_count": 2,
                "evidence": {"volatility": "confirmed", "liquidity": "confirmed"},
                "offsets": [{"fact_id": "m2_liquidity", "effect": "delays"}],
                "missing_inputs": [],
                "method_version": "market_setup_v2_market_confirmation_v1",
                "source_periods": {"vix_level": {"observation_date": "2026-07-01"}},
            },
            "market_setup": {
                "code": "downside_setup",
                "label": "Downside Setup",
                "agreement": "aligned",
            },
            "portfolio_posture": {
                "code": "defensive",
                "label": "Defensive Posture",
                "net_exposure": "underweight",
                "gross_exposure": "low",
                "implementation": "reduce_equity",
                "broad_beta": "risk_off",
                "positioning": [{"instrument": "equities", "action": "reduce"}],
                "avoid": [{"instrument": "high_beta"}],
                "method_version": "market_setup_v2_posture_v1",
            },
        },
        "evidence": [
            _projection_evidence_fact(
                "vix_level",
                "confirmation_test",
                {"effective_date": "2026-07-01"},
            ),
            _projection_evidence_fact(
                "survey_growth_direction",
                "selector",
                {"reference_period": "2026-06"},
            ),
            _projection_evidence_fact("cyclical_commodities", "display_only", None),
            _projection_evidence_fact("equity_breadth", "watch_only", None),
        ],
        "method_contracts": {
            "version": "market_setup_explanation_methods_v1",
            "methods": {
                "vix_confirmation_v2": {
                    "method_version": "vix_confirmation_v2",
                    "kind": "predicate_method",
                    "decision_contract": {"input_contract": {"fact_id": "vix_level"}},
                    "explanation_contract": {"summary": "predicate method"},
                }
            },
        },
        "counterfactuals": [
            {
                "counterfactual_id": "vix_downside_crossing",
                "object_type": "confirmation_test",
                "object_id": "vix_level",
                "predicate_ref": {"method_id": "vix_confirmation_v2"},
                "transition": "accepted_value_crosses_boundary",
                "decision_effect": "confirmation_test_result_change",
            },
            {
                "counterfactual_id": "setup_growth_decelerating_confirming_downside",
                "object_type": "market_setup",
                "object_id": "setup_growth_decelerating_confirming_downside",
                "from_code": "neutral_setup",
                "to_code": "downside_setup",
                "confirmation_change": {
                    "from": "neutral_confirmation",
                    "to": "downside_confirmation",
                },
                "posture_change": {"from": "balanced", "to": "defensive"},
                "decision_effect": "market_setup_and_posture_change",
            },
            {
                "counterfactual_id": "setup_growth_decelerating_not_confirming_downside",
                "object_type": "market_setup",
                "object_id": "setup_growth_decelerating_not_confirming_downside",
                "from_code": "neutral_setup",
                "to_code": "upside_setup",
                "confirmation_change": {
                    "from": "neutral_confirmation",
                    "to": "upside_confirmation",
                },
                "posture_change": {"from": "balanced", "to": "aggressive"},
                "decision_effect": "market_setup_and_posture_change",
            },
            {
                "counterfactual_id": "sp500_downside_crossing",
                "object_type": "confirmation_test",
                "object_id": "sp500_market_phase",
                "predicate_ref": {"method_id": "equity_confirmation_v2"},
                "transition": "accepted_value_crosses_boundary",
                "decision_effect": "confirmation_test_result_change",
            },
            {
                "counterfactual_id": "setup_growth_decelerating_third",
                "object_type": "market_setup",
                "object_id": "setup_growth_decelerating_third",
                "from_code": "neutral_setup",
                "to_code": "downside_setup",
                "confirmation_change": {
                    "from": "neutral_confirmation",
                    "to": "downside_confirmation",
                },
                "posture_change": {"from": "balanced", "to": "defensive"},
                "decision_effect": "market_setup_and_posture_change",
            },
        ],
    }


def _projection_artifacts():
    artifact = market_assistant.snapshot_artifact(_projection_snapshot())
    return {artifact["artifact_id"]: artifact}


def _projected(plan):
    return market_assistant._llm_artifact_projection(_projection_artifacts(), plan)


def _projected_objects():
    return _projected(_decision_plan())["ctx_123"]["object_index"]


def _previous_style_object_index(object_index):
    return [
        item
        for item in object_index
        if item.get("object_type") != "method_contract"
        and (
            item.get("object_type") != "evidence_fact"
            or (item.get("payload") or {}).get("role", {}).get("function")
            not in {"display_only", "watch_only"}
        )
    ]


def _dotted_paths(payload, prefix=""):
    paths = []
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.extend(_dotted_paths(value, path))
        else:
            paths.append(path)
    return paths


def _path_exists(payload, path):
    current = payload
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    return True


def test_llm_artifact_projection_does_not_mutate_full_artifacts():
    artifacts = _projection_artifacts()
    frozen = deepcopy(artifacts)
    projected = market_assistant._llm_artifact_projection(artifacts, _decision_plan())

    assert artifacts == frozen
    assert len(canonical_json(projected)) < len(canonical_json(artifacts))


def test_llm_artifact_projection_keeps_layer_results_and_applied_evidence():
    by_id = {item["object_id"]: item for item in _projected_objects()}

    assert {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    } <= set(by_id)
    assert by_id["macro_regime"]["payload"] == {
        "code": "growth_decelerating",
        "label": "Growth Decelerating",
        "primary_source": "ism_survey_synthesis",
        "supports": [{"fact_id": "survey_growth_direction"}],
        "conflicts": [{"fact_id": "macro_policy_response"}],
        "missing_inputs": [],
        "excluded_inputs": ["housing_starts"],
        "method_version": "market_setup_v2_macro_regime_v1",
    }
    assert by_id["market_confirmation"]["payload"] == {
        "code": "downside_confirmation",
        "label": "Downside Confirmation",
        "confirmation_test_count": 2,
        "offsets": [{"fact_id": "m2_liquidity", "effect": "delays"}],
        "missing_inputs": [],
        "method_version": "market_setup_v2_market_confirmation_v1",
    }
    assert by_id["market_setup"]["payload"] == {
        "code": "downside_setup",
        "label": "Downside Setup",
        "agreement": "aligned",
    }
    assert by_id["portfolio_posture"]["payload"] == {
        "code": "defensive",
        "label": "Defensive Posture",
        "net_exposure": "underweight",
        "gross_exposure": "low",
        "implementation": "reduce_equity",
        "broad_beta": "risk_off",
        "positioning": [{"instrument": "equities", "action": "reduce"}],
        "avoid": [{"instrument": "high_beta"}],
        "method_version": "market_setup_v2_posture_v1",
    }

    evidence = [
        item for item in _projected_objects() if item["object_type"] == "evidence_fact"
    ]
    assert [item["object_id"] for item in evidence] == [
        "vix_level",
        "survey_growth_direction",
    ]
    assert evidence[0]["payload"] == {
        "fact_id": "vix_level",
        "label": "VIX",
        "accepted_values": {"level": 18.4},
        "classifications": {"level": "elevated"},
        "data_status": {"state": "available"},
        "participation": {"state": "applied"},
        "decision_result": {"kind": "evaluated", "evaluation": {"state": "evaluated"}},
        "finding": {"state": "evaluated", "confirms": True},
        "role": {
            "decision_scope": "confirmation_input",
            "function": "confirmation_test",
            "target_layer": "market_confirmation",
            "allowed_effects": [],
        },
        "provenance": {"source_period": {"effective_date": "2026-07-01"}},
    }
    assert evidence[1]["payload"]["provenance"] == {
        "source_period": {"reference_period": "2026-06"}
    }


def test_llm_artifact_projection_drops_redundant_objects_and_fields():
    object_index = _projected_objects()
    object_ids = {item["object_id"] for item in object_index}

    assert "vix_confirmation_v2" not in object_ids
    assert "cyclical_commodities" not in object_ids
    assert "equity_breadth" not in object_ids
    assert "vix_downside_crossing" not in object_ids
    assert "sp500_downside_crossing" not in object_ids
    assert "setup_growth_decelerating_third" not in object_ids

    for item in object_index:
        if item["object_type"] == "market_setup_result":
            assert "source_periods" not in item["payload"]
            if item["object_id"] == "market_confirmation":
                assert "evidence" not in item["payload"]
        if item["object_type"] == "evidence_fact":
            assert "indicator_id" not in item["payload"]
            assert set(item["payload"]["provenance"]) == {"source_period"}


def test_llm_artifact_projection_keeps_only_first_two_setup_counterfactuals():
    object_index = _projected_objects()

    setup_counterfactuals = [
        item
        for item in object_index
        if item["object_type"] == "market_setup" and item["object_id"] != "market_setup"
    ]
    assert [item["object_id"] for item in setup_counterfactuals] == [
        "setup_growth_decelerating_confirming_downside",
        "setup_growth_decelerating_not_confirming_downside",
    ]
    assert setup_counterfactuals[0]["payload"]["from_code"] == "neutral_setup"
    assert setup_counterfactuals[0]["payload"]["decision_effect"] == (
        "market_setup_and_posture_change"
    )
    assert not any(item["object_type"] == "confirmation_test" for item in object_index)


def test_llm_artifact_projection_refs_resolve_in_full_artifacts():
    artifacts = _projection_artifacts()
    object_index = _projected(_decision_plan())["ctx_123"]["object_index"]

    for item in object_index:
        resolved = resolve_artifact_ref(
            artifacts,
            {
                "artifact_id": "ctx_123",
                "object_type": item["object_type"],
                "object_id": item["object_id"],
            },
        )
        for path in _dotted_paths(item["payload"]):
            assert _path_exists(resolved["payload"], path)


def test_evidence_projection_omits_provenance_without_source_period():
    snapshot = _projection_snapshot()
    snapshot["evidence"] = [
        _projection_evidence_fact(
            "vix_level",
            "confirmation_test",
            {"effective_date": "2026-07-01"},
        ),
        _projection_evidence_fact("survey_growth_direction", "selector", None),
        {
            "fact_id": "credit_conditions",
            "indicator_id": "credit_conditions",
            "label": "Credit Conditions",
            "accepted_values": {"state": "tightening"},
            "role": {"function": "selector"},
            "data_status": {"state": "available"},
            "participation": {"state": "applied"},
            "decision_result": {
                "kind": "evaluated",
                "evaluation": {"state": "evaluated"},
            },
            "finding": {"state": "evaluated", "confirms": True},
        },
    ]
    artifact = market_assistant.snapshot_artifact(snapshot)
    artifacts = {artifact["artifact_id"]: artifact}

    projected = market_assistant._llm_artifact_projection(artifacts, _decision_plan())

    by_id = {item["object_id"]: item for item in projected["ctx_123"]["object_index"]}
    assert by_id["vix_level"]["payload"]["provenance"] == {
        "source_period": {"effective_date": "2026-07-01"}
    }
    assert "provenance" not in by_id["survey_growth_direction"]["payload"]
    assert "provenance" not in by_id["credit_conditions"]["payload"]
    for item in projected["ctx_123"]["object_index"]:
        resolved = resolve_artifact_ref(
            artifacts,
            {
                "artifact_id": "ctx_123",
                "object_type": item["object_type"],
                "object_id": item["object_id"],
            },
        )
        for path in _dotted_paths(item["payload"]):
            assert _path_exists(resolved["payload"], path)


def test_keeps_artifact_object_tolerates_missing_object_id():
    malformed = {"object_type": "market_setup"}

    kept = market_assistant._keeps_artifact_object(malformed, ["market_setup"])

    assert kept is False


def test_llm_artifact_projection_smaller_than_previous_full_payload_projection():
    artifacts = _projection_artifacts()
    compact = market_assistant._llm_artifact_projection(artifacts, _decision_plan())
    previous = {
        artifact_id: {
            "artifact_id": artifact["artifact_id"],
            "artifact_kind": artifact["artifact_kind"],
            "primary_authority": artifact["primary_authority"],
            "market_setup_relation": artifact["market_setup_relation"],
            "object_index": _previous_style_object_index(artifact["object_index"]),
        }
        for artifact_id, artifact in artifacts.items()
    }

    assert len(canonical_json(compact)) < len(canonical_json(previous))


def test_non_decision_projection_returns_objects_unchanged():
    artifacts = _projection_artifacts()
    frozen = deepcopy(artifacts)
    projected = market_assistant._llm_artifact_projection(
        artifacts, _decision_plan(intent="counterfactual")
    )

    assert projected["ctx_123"]["object_index"] == frozen["ctx_123"]["object_index"]


def test_model_configuration_fingerprint_includes_reasoning_effort():
    fingerprint = market_assistant._model_configuration_fingerprint(
        _config(reasoning_effort="medium")
    )

    assert fingerprint["reasoning_effort"] == "medium"


def test_model_configuration_fingerprint_defaults_reasoning_effort_to_low():
    config = _config()
    config.pop("reasoning_effort", None)

    fingerprint = market_assistant._model_configuration_fingerprint(config)

    assert fingerprint["reasoning_effort"] == "low"


class _ReactDeps:
    def __init__(self, stream, *, huge_exploration=False):
        self.client = object()
        self.model = "assistant-model"
        self.reasoning_effort = "medium"
        self.stream_turn = stream
        self.db_path = ":memory:"
        self.executed = []
        self._huge = huge_exploration
        self.config = _config()

    def connect(self, db_path):
        return _dummy_con()

    def load_snapshot(self, con, context_id):
        return None

    def load_knowledge_catalog(self):
        return knowledge_catalog()

    def exploration(self, con, query, *, result_id, created_at):
        self.executed.append(deepcopy(query))
        rows = [{"date": "2026-08-13", "value": 18.4, "note": "x" * 800}] * (
            120 if self._huge else 1
        )
        return {
            "exploration_result_id": result_id,
            "artifact_schema_version": "market_assistant_exploration_result_v1",
            "authority": "local_observation",
            "market_setup_relation": "non_decision",
            "query_contract": deepcopy(query),
            "observed_window": {"start": query.get("start"), "end": query.get("end")},
            "data_through": query.get("end"),
            "rows": rows,
            "deterministic_statistics": {"last_value": 18.4},
            "gaps": {"policy": "not_applicable", "missing_periods": None},
            "object_index": [
                {
                    "object_type": "indicator_history",
                    "object_id": "history",
                    "authority": "local_observation",
                    "payload": {"rows": rows},
                }
            ],
            "result_hash": "a" * 64,
        }

    async def acquire_research(
        self, provider, task, *, result_id, searched_at, explicit_deep=False
    ):
        self.executed.append(deepcopy(task))
        return {
            "research_result_id": result_id,
            "status": "research_unavailable",
            "reason_code": "provider_error",
        }

    def build_research_provider(self, config):
        return object()


def _react_resolution():
    return {
        "resolution": {
            "mode": "current",
            "resolved_at": "2026-08-13T00:00:00Z",
            "previous_context_id": None,
            "current_context_id": "ctx_react",
            "context_changed": False,
        },
        "delta": {"results_changed": False, "changes": []},
        "snapshot": {"context_id": "ctx_react"},
    }


def _react_request(**overrides):
    request = {"question": "讲个笑话"}
    request.update(overrides)
    return request


def _history_call(call_id, *, indicator_id="vix", window="6m", statistics=None):
    arguments = {"indicator_id": indicator_id, "window": window}
    if statistics is not None:
        arguments["statistics"] = statistics
    return {
        "call_id": call_id,
        "tool_name": "query_indicator_history",
        "arguments": arguments,
    }


def _confirmation_call(call_id, test_id):
    return {
        "call_id": call_id,
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": test_id},
    }


def _empty_call(call_id, tool_name):
    return {"call_id": call_id, "tool_name": tool_name, "arguments": {}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "research_focused",
            {
                "purpose": "current_events",
                "queries": ["latest vix"],
                "expected_source_class": "official_publication",
            },
        ),
        ("refresh_benchmarks", {}),
        ("ingest_snapshot", {}),
        ("import_ism_report", {}),
        (
            "query_indicator_history",
            {"indicator_id": "https://evil.example/x", "window": "6m"},
        ),
        (
            "query_indicator_history",
            {
                "indicator_id": "vix",
                "window": "6m",
                "statistics": ["'; DROP TABLE answer_traces;--"],
            },
        ),
        ("get_confirmation_test", {"test_id": "vix", "context_id": "ctx_hack"}),
    ],
)
async def test_hostile_tool_calls_are_rejected_without_execution(tool_name, arguments):
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_hostile",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    }
                ]
            ),
            narration_step(),
        ]
    )
    deps = _ReactDeps(stream)

    result = await run_hybrid_narration(
        _react_request(external_search_requested=False),
        route=route_question("讲个笑话", deep_analysis=False),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "answered"
    assert deps.executed == []
    rejected = [
        entry for entry in result["tool_trace"] if entry["status"] == "rejected"
    ]
    assert rejected == [
        {
            "phase": "optional",
            "call_id": "call_hostile",
            "tool_name": tool_name,
            "arguments": arguments,
            "status": "rejected",
            "reason": "tool_call_invalid",
            "artifact_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_repeated_tool_call_stops_loop_before_any_execution():
    call = _confirmation_call("call_dup", "vix")
    stream = _ScriptedStream([tool_step([dict(call), dict(call)]), narration_step()])
    deps = _ReactDeps(stream)

    result = await run_hybrid_narration(
        _react_request(),
        route=route_question("讲个笑话", deep_analysis=False),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "duplicate_tool_call"
    assert deps.executed == []
    assert len(stream.calls) == 1
    assert not any(entry["status"] == "executed" for entry in result["tool_trace"])


@pytest.mark.asyncio
async def test_fifth_parallel_call_is_rejected_without_execution():
    calls = [
        _confirmation_call("call_1", "vix"),
        _confirmation_call("call_2", "credit"),
        _confirmation_call("call_3", "equity"),
        _history_call("call_4", indicator_id="vix"),
        _empty_call("call_5", "get_posture_explanation"),
    ]
    stream = _ScriptedStream([tool_step(calls), narration_step()])
    deps = _ReactDeps(stream)

    result = await run_hybrid_narration(
        _react_request(),
        route=route_question("讲个笑话", deep_analysis=False),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "answered"
    rejected = [
        entry for entry in result["tool_trace"] if entry["status"] == "rejected"
    ]
    assert len(rejected) == 1
    assert rejected[0]["call_id"] == "call_5"
    assert rejected[0]["tool_name"] == "get_posture_explanation"
    assert rejected[0]["reason"] == "parallel_call_limit"
    handled = [entry for entry in result["tool_trace"] if entry["status"] != "rejected"]
    assert len(handled) == 4
    assert all(entry["status"] in {"executed", "unavailable"} for entry in handled)
    assert not any(
        entry["tool_name"] == "get_posture_explanation"
        for entry in result["tool_trace"]
        if entry["status"] == "executed"
    )


@pytest.mark.asyncio
async def test_thirteenth_deep_analysis_call_is_rejected_without_execution():
    calls = [
        _empty_call("c1", "get_setup_overview"),
        _empty_call("c2", "get_macro_regime_explanation"),
        _confirmation_call("c3", "vix"),
        _confirmation_call("c4", "credit"),
        _confirmation_call("c5", "equity"),
        _empty_call("c6", "get_posture_explanation"),
        _empty_call("c7", "get_approved_counterfactuals"),
        {
            "call_id": "c8",
            "tool_name": "get_confirmation_tests",
            "arguments": {"test_ids": ["equity", "credit", "vix"]},
        },
        {
            "call_id": "c9",
            "tool_name": "get_indicator_knowledge",
            "arguments": {"indicator_id": "vix", "topic": "definition"},
        },
        _history_call("c10", indicator_id="vix", window="1m"),
        _history_call("c11", indicator_id="credit_conditions", window="3m"),
        _history_call("c12", indicator_id="sp500_close", window="6m"),
        _history_call("c13", indicator_id="vix", window="1y"),
        _history_call("c14", indicator_id="vix", window="2y"),
    ]
    rounds = [calls[0:4], calls[4:8], calls[8:11], calls[11:13], calls[13:14]]
    stream = _ScriptedStream([tool_step(round_calls) for round_calls in rounds])
    deps = _ReactDeps(stream)

    result = await run_hybrid_narration(
        _react_request(deep_analysis_requested=True),
        route=route_question("讲个笑话", deep_analysis=True),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "budget_exhausted"
    rejected = [
        entry for entry in result["tool_trace"] if entry["status"] == "rejected"
    ]
    assert rejected == [
        {
            "phase": "optional",
            "call_id": "c13",
            "tool_name": "query_indicator_history",
            "arguments": {
                "indicator_id": "vix",
                "window": "1y",
                "start": None,
                "end": None,
                "statistics": [],
            },
            "status": "rejected",
            "reason": "tool_call_budget",
            "artifact_id": None,
        }
    ]
    handled = [entry for entry in result["tool_trace"] if entry["status"] != "rejected"]
    assert len(handled) == 12
    assert not any(
        entry["call_id"] == "c13" and entry["status"] == "executed"
        for entry in result["tool_trace"]
    )


@pytest.mark.asyncio
async def test_tool_result_context_overflow_stops_loop_without_more_execution():
    stream = _ScriptedStream(
        [
            tool_step([_history_call("call_history", indicator_id="vix")]),
            narration_step(),
        ]
    )
    deps = _ReactDeps(stream, huge_exploration=True)

    result = await run_hybrid_narration(
        _react_request(),
        route=route_question("讲个笑话", deep_analysis=False),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "budget_exhausted"
    executed = [
        entry for entry in result["tool_trace"] if entry["status"] == "executed"
    ]
    assert len(executed) == 1
    assert executed[0]["tool_name"] == "query_indicator_history"
    assert len(stream.calls) == 1


@pytest.mark.asyncio
async def test_rejected_invalid_calls_consume_call_budget():
    invalid_calls = [
        {
            "call_id": f"call_hostile_{index}",
            "tool_name": "refresh_benchmarks",
            "arguments": {},
        }
        for index in range(12)
    ]
    stream = _ScriptedStream(
        [
            tool_step(invalid_calls[0:4]),
            tool_step(invalid_calls[4:8]),
            tool_step(invalid_calls[8:12]),
            narration_step(),
        ]
    )
    deps = _ReactDeps(stream)

    result = await run_hybrid_narration(
        _react_request(deep_analysis_requested=True),
        route=route_question("讲个笑话", deep_analysis=True),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "answered"
    assert result["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"
    assert deps.executed == []
    assert len(stream.calls) == 4
    rejected = [
        entry for entry in result["tool_trace"] if entry["status"] == "rejected"
    ]
    assert len(rejected) == 12
    assert all(entry["reason"] == "tool_call_invalid" for entry in rejected)
    assert not any(entry["status"] == "executed" for entry in result["tool_trace"])


@pytest.mark.asyncio
async def test_deadline_expiry_stops_loop_before_first_model_turn(monkeypatch):
    class _DeadlineClock:
        def __init__(self):
            self.count = 0

        def __call__(self):
            self.count += 1
            return 0.0 if self.count <= 2 else 10000.0

    monkeypatch.setattr(market_assistant_react, "monotonic", _DeadlineClock())
    stream = _ScriptedStream([narration_step()])
    deps = _ReactDeps(stream)

    result = await run_hybrid_narration(
        _react_request(),
        route=route_question("讲个笑话", deep_analysis=False),
        resolution=_react_resolution(),
        dependencies=deps,
    )

    assert result["generation_status"] == "deadline_exceeded"
    assert stream.calls == []
    assert deps.executed == []


@pytest.mark.asyncio
async def test_deadline_exhaustion_freezes_deadline_exceeded_in_trace():
    class _SlowNarrationStream:
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
            await asyncio.sleep(0.10)
            return {
                "output_text": "现在的市场偏积极，但仍需保持谨慎。",
                "tool_calls": [],
                "response_items": [],
                "usage": None,
                "timings": {},
            }

    route = route_question("现在市场怎么样？", deep_analysis=False)
    route["budget"] = {**route["budget"], "deadline_seconds": 0.02}
    deps = hybrid_dependencies(stream=_SlowNarrationStream(), route=route)
    sink = RecordingSink()

    response = await market_assistant.answer_question(
        current_question("现在市场怎么样？"),
        dependencies=deps,
        event_sink=sink,
    )

    assert response["generation_status"] == "deterministic_fallback"
    assert deps.saved_trace["generation_status"] == "deterministic_fallback"
    assert deps.saved_trace["narration_status"] == "deadline_exceeded"
