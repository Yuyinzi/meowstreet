import asyncio
import inspect
import json
from copy import deepcopy

import pytest

from app.services.market_assistant_react import _DeadlineExceeded
from app.services.market_assistant_react import _translate_initial_operation
from app.services.market_assistant_react import run_hybrid_narration
from app.tools.market_assistant_artifacts import resolve_artifact_ref
from app.tools.market_assistant_routes import budget_for_mode
from app.tools.market_assistant_routes import route_question

_FALLBACK_ZH = "当前市场证据已收集，但回答生成暂不可用。"


def current_setup_route():
    return route_question("现在市场怎么样？", deep_analysis=False)


def react_route():
    return route_question("讲个笑话", deep_analysis=False)


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
            }
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


def huge_exploration_result():
    result = exploration_result()
    result["rows"] = [{"date": "2026-06-30", "value": 18.4, "note": "x" * 800}] * 120
    return result


def research_result():
    return {
        "research_result_id": "res_1",
        "artifact_schema_version": "market_assistant_research_result_v1",
        "authority": "external_research",
        "market_setup_relation": "non_decision",
        "task": {
            "purpose": "current_events",
            "depth_tier": "deep",
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
    def __init__(self, stream=None):
        self.client = object()
        self.model = "assistant-model"
        self.reasoning_effort = "medium"
        self.stream_turn = stream or _ScriptedStream([])
        self.event_sink = None
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


def fake_dependencies(stream=None):
    return _FakeDependencies(stream)


def recording_dependencies(events, stream=None):
    deps = fake_dependencies(stream)
    deps.event_sink = lambda event: events.append(event["type"])
    return deps


def vix_confirmation_call():
    return {
        "call_id": "call_vix",
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": "vix"},
    }


@pytest.mark.asyncio
async def test_fast_path_executes_initial_tools_before_first_model_turn():
    events = []
    stream = _ScriptedStream([narration_step()])
    dependencies = recording_dependencies(events, stream=stream)
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？", "deep_analysis_requested": False},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=dependencies,
    )
    assert events[:2] == ["initial_tools_started", "initial_tools_completed"]
    assert events[2] == "model_turn_started"
    assert result["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"


@pytest.mark.asyncio
async def test_result_contract_keys():
    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert set(result) == {
        "answer_text",
        "artifacts",
        "view",
        "tool_trace",
        "route",
        "timings",
        "generation_status",
    }
    assert result["generation_status"] == "answered"


@pytest.mark.asyncio
async def test_optional_round_executes_parallel_tools_then_final_narration():
    events = []
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    vix_confirmation_call(),
                    {
                        "call_id": "call_credit_history",
                        "tool_name": "query_indicator_history",
                        "arguments": {
                            "indicator_id": "credit_conditions",
                            "window": "6m",
                        },
                    },
                ]
            ),
            narration_step(),
        ]
    )
    deps = recording_dependencies(events, stream=stream)
    request = {"question": "VIX和信贷最近的变化有什么关系？"}
    result = await run_hybrid_narration(
        request,
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "answered"
    assert result["answer_text"] == "现在的市场偏积极，但仍需保持谨慎。"
    optional = [item for item in result["tool_trace"] if item["phase"] == "optional"]
    assert len(optional) == 2
    assert all(item["status"] == "executed" for item in optional)
    assert {item["tool_name"] for item in optional} == {
        "get_confirmation_test",
        "query_indicator_history",
    }
    assert events.count("model_turn_started") == 2


@pytest.mark.asyncio
async def test_standard_budget_allows_two_optional_rounds_then_final_narration():
    events = []
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_current",
                        "tool_name": "get_indicator_current",
                        "arguments": {"indicator_id": "vix"},
                    }
                ]
            ),
            tool_step(
                [
                    {
                        "call_id": "call_definition",
                        "tool_name": "get_indicator_definition",
                        "arguments": {"indicator_id": "vix"},
                    }
                ]
            ),
            narration_step(),
        ]
    )
    deps = recording_dependencies(events, stream=stream)
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "answered"
    assert result["timings"]["optional_rounds"] == 2
    assert len(stream.calls) == 3
    assert events.count("model_turn_started") == 3
    optional = [item for item in result["tool_trace"] if item["phase"] == "optional"]
    assert {item["tool_name"] for item in optional} == {
        "get_indicator_current",
        "get_indicator_definition",
    }
    assert all(item["status"] in {"executed", "unavailable"} for item in optional)


@pytest.mark.asyncio
async def test_third_optional_round_in_standard_is_refused_after_budget():
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_current",
                        "tool_name": "get_indicator_current",
                        "arguments": {"indicator_id": "vix"},
                    }
                ]
            ),
            tool_step(
                [
                    {
                        "call_id": "call_definition",
                        "tool_name": "get_indicator_definition",
                        "arguments": {"indicator_id": "vix"},
                    }
                ]
            ),
            tool_step(
                [
                    {
                        "call_id": "call_method",
                        "tool_name": "get_indicator_method",
                        "arguments": {"indicator_id": "vix"},
                    }
                ]
            ),
        ]
    )
    deps = recording_dependencies([], stream=stream)
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "budget_exhausted"
    assert result["timings"]["optional_rounds"] == 2
    assert len(stream.calls) == 3
    assert result["answer_text"] == _FALLBACK_ZH


@pytest.mark.asyncio
async def test_first_turn_input_contains_only_question_and_compact_view():
    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    items = deps.stream_turn.calls[0]["input_items"]
    assert len(items) == 1
    assert items[0]["type"] == "message"
    assert items[0]["role"] == "user"
    assert [part["type"] for part in items[0]["content"]] == [
        "input_text",
        "input_text",
    ]
    assert items[0]["content"][0]["text"] == "现在市场怎么样？"
    assert "explanation_view" in items[0]["content"][1]["text"]
    assert not any(item["type"] == "function_call_output" for item in items)
    assert not any(item["type"] == "function_call" for item in items)
    assert len(result["artifacts"]) >= 5


@pytest.mark.asyncio
async def test_duplicate_normalized_call_stops_loop_without_more_budget():
    events = []
    repeated = vix_confirmation_call()
    stream = _ScriptedStream(
        [
            tool_step([dict(repeated)]),
            tool_step([dict(repeated)]),
        ]
    )
    deps = recording_dependencies(events, stream=stream)
    result = await run_hybrid_narration(
        {"question": "VIX和信贷最近的变化有什么关系？"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "duplicate_tool_call"
    assert len(stream.calls) == 2
    optional = [item for item in result["tool_trace"] if item["phase"] == "optional"]
    assert len(optional) == 1
    assert optional[0]["status"] == "executed"
    assert result["answer_text"] == _FALLBACK_ZH


@pytest.mark.asyncio
async def test_progress_events_use_deterministic_chinese_copy():
    events = []
    stream = _ScriptedStream(
        [
            tool_step([vix_confirmation_call()]),
            narration_step(),
        ]
    )
    deps = fake_dependencies(stream)
    deps.event_sink = lambda event: events.append(event)
    request = {"question": "VIX和信贷最近的变化有什么关系？"}
    await run_hybrid_narration(
        request,
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    progress = [event for event in events if event["type"] == "progress"]
    assert progress == [
        {
            "type": "progress",
            "stage": "checking_confirmation",
            "message": "正在检查股票、信贷与波动率信号…",
        },
        {"type": "progress", "stage": "writing_answer", "message": "正在整理回答…"},
    ]


@pytest.mark.asyncio
async def test_progress_events_use_deterministic_english_copy():
    events = []
    stream = _ScriptedStream(
        [
            tool_step([vix_confirmation_call()]),
            narration_step(text="The market is risk-on but cautious."),
        ]
    )
    deps = fake_dependencies(stream)
    deps.event_sink = lambda event: events.append(event)
    request = {"question": "how are the vix and credit conditions related?"}
    await run_hybrid_narration(
        request,
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    progress = [event for event in events if event["type"] == "progress"]
    assert progress == [
        {
            "type": "progress",
            "stage": "checking_confirmation",
            "message": "Checking equity, credit, and volatility signals…",
        },
        {
            "type": "progress",
            "stage": "writing_answer",
            "message": "Writing the answer…",
        },
    ]


@pytest.mark.asyncio
async def test_deep_analysis_alone_never_adds_research_tools():
    deps = recording_dependencies([], stream=_ScriptedStream([narration_step()]))
    request = {"question": "讲个笑话", "deep_analysis_requested": True}
    result = await run_hybrid_narration(
        request,
        route=route_question(request["question"], deep_analysis=True),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    tool_names = [tool["name"] for tool in deps.stream_turn.calls[0]["tools"]]
    assert not any(name.startswith("research_") for name in tool_names)
    assert "acquire_research" not in deps.requested
    assert result["generation_status"] == "answered"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_overrides", "expected_research"),
    [
        ({"research_tier": "focused"}, ["research_focused"]),
        (
            {"research_tier": "standard"},
            ["research_focused", "research_standard"],
        ),
        (
            {"deep_research_requested": True},
            ["research_focused", "research_standard", "research_deep"],
        ),
    ],
)
async def test_external_search_adds_only_permitted_research_tier(
    request_overrides, expected_research
):
    deps = recording_dependencies([], stream=_ScriptedStream([narration_step()]))
    request = {
        "question": "讲个笑话",
        "external_search_requested": True,
        **request_overrides,
    }
    await run_hybrid_narration(
        request,
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    tool_names = [tool["name"] for tool in deps.stream_turn.calls[0]["tools"]]
    research = [name for name in tool_names if name.startswith("research_")]
    assert research == expected_research


@pytest.mark.asyncio
async def test_combined_controls_preserve_research_artifacts_as_non_decision():
    deps = recording_dependencies(
        [],
        stream=_ScriptedStream(
            [
                tool_step(
                    [
                        {
                            "call_id": "call_research",
                            "tool_name": "research_deep",
                            "arguments": {
                                "purpose": "current_events",
                                "queries": ["latest vix"],
                                "expected_source_class": "official_publication",
                            },
                        },
                        {
                            "call_id": "call_overview",
                            "tool_name": "get_setup_overview",
                            "arguments": {},
                        },
                    ]
                ),
                narration_step(),
            ],
        ),
    )
    request = {
        "question": "讲个笑话",
        "external_search_requested": True,
        "deep_research_requested": True,
    }
    result = await run_hybrid_narration(
        request,
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    research = result["artifacts"]["res_1"]
    assert research["primary_authority"] == "external_research"
    assert research["market_setup_relation"] == "non_decision"
    assert result["generation_status"] == "answered"
    for ref in result["view"]["audit_objects"]:
        resolved = resolve_artifact_ref(result["artifacts"], ref)
        assert resolved["authority"] in {"decision_fact", "method_knowledge"}


@pytest.mark.asyncio
async def test_tool_loop_never_mutates_resolution_snapshot_results():
    resolution = resolved_context("ctx_1")
    before = deepcopy(resolution["snapshot"]["results"])
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_overview",
                        "tool_name": "get_setup_overview",
                        "arguments": {},
                    }
                ]
            ),
            narration_step(),
        ]
    )
    deps = recording_dependencies([], stream=stream)
    await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolution,
        dependencies=deps,
    )
    assert resolution["snapshot"]["results"] == before


@pytest.mark.asyncio
async def test_provider_failure_before_text_returns_narration_unavailable():
    deps = recording_dependencies(
        [], stream=_ScriptedStream([narration_step(error=ValueError("provider down"))])
    )
    result = await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "narration_unavailable"
    assert result["answer_text"] == _FALLBACK_ZH


@pytest.mark.asyncio
async def test_provider_failure_after_deltas_retains_partial_text():
    partial = "现在的市场偏积极"
    deps = recording_dependencies(
        [],
        stream=_ScriptedStream(
            [narration_step(deltas=[partial], error=ValueError("provider died"))]
        ),
    )
    result = await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "narration_interrupted"
    assert result["answer_text"] == partial


@pytest.mark.asyncio
async def test_budget_exhaustion_selects_deterministic_fallback():
    deps = recording_dependencies(
        [],
        stream=_ScriptedStream(
            [
                tool_step(
                    [
                        {
                            "call_id": "call_overview",
                            "tool_name": "get_setup_overview",
                            "arguments": {},
                        }
                    ]
                ),
                tool_step(
                    [
                        {
                            "call_id": "call_posture",
                            "tool_name": "get_posture_explanation",
                            "arguments": {},
                        }
                    ]
                ),
                tool_step(
                    [
                        {
                            "call_id": "call_counterfactuals",
                            "tool_name": "get_approved_counterfactuals",
                            "arguments": {},
                        }
                    ]
                ),
            ]
        ),
    )
    result = await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "budget_exhausted"
    assert result["answer_text"] == _FALLBACK_ZH


@pytest.mark.asyncio
async def test_result_byte_budget_stops_optional_loop():
    deps = fake_dependencies(
        stream=_ScriptedStream(
            [
                tool_step(
                    [
                        {
                            "call_id": "call_history",
                            "tool_name": "query_indicator_history",
                            "arguments": {"indicator_id": "vix", "window": "6m"},
                        }
                    ]
                )
            ]
        )
    )
    deps._exploration = huge_exploration_result()
    deps.event_sink = lambda event: None
    result = await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "budget_exhausted"
    assert result["answer_text"] == _FALLBACK_ZH


class _SlowStream:
    def __init__(self, delay, output_text="现在的市场偏积极，但仍需保持谨慎。"):
        self.delay = delay
        self.output_text = output_text
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
        self.calls.append(1)
        await asyncio.sleep(self.delay)
        return {
            "output_text": self.output_text,
            "tool_calls": [],
            "response_items": [],
            "usage": None,
            "timings": {},
        }


def _budget_route(deadline_seconds, route=None):
    route = route or current_setup_route()
    route["budget"] = budget_for_mode(False)
    route["budget"]["deadline_seconds"] = deadline_seconds
    return route


@pytest.mark.asyncio
async def test_deadline_bounds_slow_model_turn_before_answer():
    stream = _SlowStream(delay=0.10)
    deps = recording_dependencies([], stream=stream)
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=_budget_route(0.02),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "deadline_exceeded"
    assert result["answer_text"] == _FALLBACK_ZH
    assert len(stream.calls) == 1


@pytest.mark.asyncio
async def test_deadline_bounds_slow_optional_tool_batch():
    stream = _ScriptedStream(
        [
            tool_step(
                [
                    {
                        "call_id": "call_overview",
                        "tool_name": "get_setup_overview",
                        "arguments": {},
                    }
                ]
            ),
            narration_step(),
        ]
    )
    deps = recording_dependencies([], stream=stream)

    from app.services.market_assistant_tool_runtime import execute_tool_batch

    async def slow_execute_batch(calls, **kwargs):
        await asyncio.sleep(0.10)
        return await execute_tool_batch(calls, **kwargs)

    deps.execute_tool_batch = slow_execute_batch
    result = await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=_budget_route(0.02, route=react_route()),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "deadline_exceeded"
    assert result["answer_text"] == _FALLBACK_ZH


@pytest.mark.asyncio
async def test_deadline_bounds_slow_initial_tools_batch():
    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)

    from app.services.market_assistant_tool_runtime import execute_tool_batch

    async def slow_execute_batch(calls, **kwargs):
        await asyncio.sleep(0.10)
        return await execute_tool_batch(calls, **kwargs)

    deps.execute_tool_batch = slow_execute_batch
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=_budget_route(0.02),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "deadline_exceeded"
    assert result["answer_text"] == ""
    assert result["view"]["view_version"] == "setup_explanation_v1"


@pytest.mark.asyncio
async def test_provider_timeout_is_not_misclassified_as_deadline():
    from app.services.market_assistant_react import _await_within_budget

    async def provider_timeout():
        raise asyncio.TimeoutError("provider slow")

    with pytest.raises(asyncio.TimeoutError) as exc_info:
        await _await_within_budget(lambda: provider_timeout(), 1e9)
    assert not isinstance(exc_info.value, _DeadlineExceeded)


@pytest.mark.asyncio
async def test_model_timeout_under_remaining_budget_is_narration_unavailable():
    async def provider_timeout_stream(client, **kwargs):
        raise asyncio.TimeoutError("provider slow")

    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)
    deps.stream_turn = provider_timeout_stream
    route = current_setup_route()
    route["budget"] = budget_for_mode(False)
    route["budget"]["deadline_seconds"] = 30.0
    result = await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=route,
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert result["generation_status"] == "narration_unavailable"
    assert result["answer_text"] == _FALLBACK_ZH


def test_translate_initial_operation_maps_indicator_operations():
    assert _translate_initial_operation(
        {"operation_id": "get_indicator_confirmation", "indicator_id": "vix"}
    ) == {"tool_name": "get_confirmation_test", "arguments": {"test_id": "vix"}}
    assert _translate_initial_operation(
        {"operation_id": "get_indicator_confirmation", "indicator_id": "sp500_close"}
    ) == {"tool_name": "get_confirmation_test", "arguments": {"test_id": "equity"}}
    assert _translate_initial_operation(
        {
            "operation_id": "get_indicator_confirmation",
            "indicator_id": "credit_conditions",
        }
    ) == {"tool_name": "get_confirmation_test", "arguments": {"test_id": "credit"}}
    assert _translate_initial_operation(
        {
            "operation_id": "get_indicator_confirmation",
            "indicator_id": "ism_manufacturing_pmi",
        }
    ) == {
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": "ism_manufacturing_pmi"},
    }
    assert _translate_initial_operation(
        {"operation_id": "get_indicator_definition", "indicator_id": "vix"}
    ) == {
        "tool_name": "get_indicator_knowledge",
        "arguments": {"indicator_id": "vix", "topic": "definition"},
    }
    assert _translate_initial_operation(
        {"operation_id": "get_indicator_method", "indicator_id": "vix"}
    ) == {
        "tool_name": "get_indicator_knowledge",
        "arguments": {"indicator_id": "vix", "topic": "method"},
    }
    assert _translate_initial_operation({"operation_id": "get_setup_overview"}) == {
        "tool_name": "get_setup_overview",
        "arguments": {},
    }


@pytest.mark.asyncio
async def test_indicator_confirmation_missing_test_is_unavailable_evidence():
    request = {"question": "ISM的确认信号怎么样？"}
    route = route_question(request["question"], deep_analysis=False)
    deps = recording_dependencies([], stream=_ScriptedStream([narration_step()]))
    result = await run_hybrid_narration(
        request,
        route=route,
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert any(
        item["tool_name"] == "get_confirmation_test" and item["status"] == "unavailable"
        for item in result["tool_trace"]
    )
    assert result["generation_status"] == "answered"


@pytest.mark.asyncio
async def test_run_hybrid_narration_uses_injected_narration_instructions():
    stream = _ScriptedStream([narration_step()])
    dependencies = {
        "client": object(),
        "config": {"model": "assistant-model", "reasoning_effort": "medium"},
        "stream_turn": stream,
        "narration_instructions": "beginner narration instructions",
        "event_sink": None,
    }
    await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=dependencies,
    )
    assert stream.calls[0]["instructions"] == "beginner narration instructions"


@pytest.mark.asyncio
async def test_run_hybrid_narration_invokes_callable_narration_instructions():
    stream = _ScriptedStream([narration_step()])
    dependencies = {
        "client": object(),
        "config": {"model": "assistant-model", "reasoning_effort": "medium"},
        "stream_turn": stream,
        "narration_instructions": lambda: "callable narration instructions",
        "event_sink": None,
    }
    await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=dependencies,
    )
    assert stream.calls[0]["instructions"] == "callable narration instructions"


@pytest.mark.asyncio
async def test_initial_tool_outputs_are_bounded_not_full_snapshots():
    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)
    await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    serialized = json.dumps(deps.stream_turn.calls[0]["input_items"])
    assert "snapshot_hash" not in serialized
    assert "decision_fingerprint" not in serialized


def _first_turn_view(stream):
    first_message = stream.calls[0]["input_items"][0]
    view_text = first_message["content"][1]["text"]
    return json.loads(view_text)["explanation_view"]


@pytest.mark.asyncio
async def test_first_turn_input_carries_compact_explanation_view():
    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)
    await run_hybrid_narration(
        {"question": "现在市场怎么样？"},
        route=current_setup_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    view = _first_turn_view(deps.stream_turn)
    assert view["view_version"] == "setup_explanation_v1"
    assert view["question_language"] == "zh"
    assert set(view["results"]) == {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    }
    assert view["posture_meaning"]


@pytest.mark.asyncio
async def test_react_route_first_turn_carries_minimal_anchor_with_result_labels():
    stream = _ScriptedStream([narration_step()])
    deps = recording_dependencies([], stream=stream)
    await run_hybrid_narration(
        {"question": "讲个笑话"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    view = _first_turn_view(deps.stream_turn)
    assert view["view_version"] == "react_anchor_v1"
    assert view["context_id"] == "ctx_1"
    assert set(view["results"]) == {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    }
    assert all(isinstance(label, str) for label in view["results"].values())


@pytest.mark.asyncio
async def test_final_narration_turn_input_carries_current_view():
    stream = _ScriptedStream(
        [
            tool_step([vix_confirmation_call()]),
            narration_step(),
        ]
    )
    deps = recording_dependencies([], stream=stream)
    await run_hybrid_narration(
        {"question": "VIX和信贷最近的变化有什么关系？"},
        route=react_route(),
        resolution=resolved_context("ctx_1"),
        dependencies=deps,
    )
    assert len(stream.calls) == 2
    final_message = stream.calls[1]["input_items"][0]
    final_view = json.loads(final_message["content"][1]["text"])["explanation_view"]
    assert final_view["view_version"] == "react_anchor_v1"
    assert "results" in final_view
