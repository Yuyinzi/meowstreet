import json

import pytest

from app.db import market_assistant as market_assistant_db
from app.services import market_assistant
from app.services.market_assistant import ASSISTANT_POLICY_VERSION
from app.services.market_assistant import PROMPT_VERSION
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_plans import validate_task_plan


def current_question(**overrides):
    question = {
        "question": "Why is the current setup Mild Risk-Off?",
        "mode": "current",
        "previous_context_id": None,
        "deep_research_requested": False,
    }
    question.update(overrides)
    return question


def valid_plan(**overrides):
    plan = {
        "intent": "decision_explanation",
        "context_mode": "current",
        "operations": [
            {"operation_id": "resolve_current_explanation", "parameters": {}}
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    plan.update(overrides)
    return plan


def research_plan(tier="focused", **overrides):
    operation = {
        "focused": "research_focused",
        "standard": "research_standard",
        "deep": "research_deep",
    }[tier]
    plan = {
        "intent": "external_research",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": operation,
                "parameters": {
                    "purpose": "current_events",
                    "queries": ["latest official ism report"],
                    "expected_source_class": "official_publication",
                },
            }
        ],
        "answer_depth": "detailed",
        "research_tier": tier,
    }
    plan.update(overrides)
    return plan


def knowledge_plan(**overrides):
    plan = {
        "intent": "definition",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "get_indicator_definition",
                "parameters": {"indicator_id": "vix"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    plan.update(overrides)
    return plan


def exploration_plan(**overrides):
    plan = {
        "intent": "local_history",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "query_indicator_history",
                "parameters": {
                    "indicator_id": "vix",
                    "start": "2026-01-01",
                    "end": "2026-06-30",
                },
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    plan.update(overrides)
    return plan


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
        "research_enabled": True,
        "supports_web_search": True,
        "api_key": "sk-secret-test-key",
        "base_url": None,
    }
    config.update(overrides)
    return config


def evidence_ref(**overrides):
    ref = {
        "artifact_id": "ctx_123",
        "object_type": "evidence_fact",
        "object_id": "vix_level",
    }
    ref.update(overrides)
    return ref


def valid_claim(**overrides):
    claim = {
        "claim_id": "c1",
        "purpose": "decision_explanation",
        "authority": "decision_fact",
        "refs": [evidence_ref()],
        "template": "The accepted VIX level is {vix_level}.",
        "bindings": {
            "vix_level": {
                "value": 18.4,
                "source": evidence_ref(field="accepted_values.level"),
            }
        },
    }
    claim.update(overrides)
    return claim


def valid_draft():
    return {"sections": [{"kind": "decision", "claims": [valid_claim()]}]}


def invalid_draft():
    return {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "bad1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [evidence_ref()],
                        "template": "The VIX level is 99.9 today.",
                        "bindings": {},
                    }
                ],
            }
        ]
    }


def invalid_repair():
    return {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "bad2",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [evidence_ref()],
                        "template": "The VIX level is 77.7 today.",
                        "bindings": {},
                    }
                ],
            }
        ]
    }


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
        "provider_metadata": {
            "provider_id": "openai_responses_web_search",
            "model": "research-model",
        },
        "searched_at": "2026-08-10T02:00:00Z",
        "search_calls": [{"query": "latest vix"}],
        "sources": [
            {
                "source_id": "src_1",
                "canonical_url": "https://www.cboe.com/vix",
                "title": "CBOE VIX",
                "publisher": "cboe.com",
                "publication_date": "2026-08-10",
                "event_date": "2026-08-10",
                "retrieved_at": "2026-08-10T02:00:00Z",
                "cited_spans": ["The VIX closed at 25.0."],
            }
        ],
        "findings": [
            {
                "finding_id": "fnd_1",
                "statement": "The VIX closed at 25.0.",
                "purpose": "current_events",
                "framing": "reported",
                "source_refs": ["src_1"],
                "cited_spans": ["The VIX closed at 25.0."],
            }
        ],
        "object_index": [
            {
                "object_type": "research_source",
                "object_id": "src_1",
                "authority": "external_research",
                "payload": {
                    "source_id": "src_1",
                    "canonical_url": "https://www.cboe.com/vix",
                    "title": "CBOE VIX",
                    "publisher": "cboe.com",
                    "publication_date": "2026-08-10",
                    "event_date": "2026-08-10",
                    "retrieved_at": "2026-08-10T02:00:00Z",
                    "cited_spans": ["The VIX closed at 25.0."],
                    "reported_level": 25.0,
                },
            },
            {
                "object_type": "research_finding",
                "object_id": "fnd_1",
                "authority": "external_research",
                "payload": {
                    "finding_id": "fnd_1",
                    "statement": "The VIX closed at 25.0.",
                },
            },
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


class FakeDependencies:
    def __init__(
        self,
        plan,
        draft,
        repair=None,
        *,
        resolve=None,
        research=None,
        config=None,
        catalog=None,
        exploration=None,
        knowledge=None,
    ):
        self.llm_calls = []
        self.tool_execution_count = 0
        self.saved_trace = None
        self.saved_artifacts = None
        self.acquired_research_kwargs = None
        self.db_path = ":memory:"
        self.config = config if config is not None else _config()
        self._plan = plan
        self._draft = draft
        self._repair = repair
        self._resolve = resolve if resolve is not None else resolution_envelope()
        self._research = research if research is not None else research_unavailable()
        self._catalog = catalog if catalog is not None else knowledge_catalog()
        self._exploration = exploration
        self._knowledge = knowledge

    async def plan_llm(self, *, question, context_summary):
        self.llm_calls.append("plan")
        if isinstance(self._plan, list):
            response = self._plan.pop(0)
        else:
            response = self._plan
        if isinstance(response, Exception):
            raise response
        return validate_task_plan(response)

    async def synthesize_llm(self, *, question, plan, context_summary, artifacts):
        self.llm_calls.append("draft")
        if isinstance(self._draft, Exception):
            raise self._draft
        return self._draft

    async def repair_llm(
        self, *, question, plan, context_summary, artifacts, draft, validation_report
    ):
        self.llm_calls.append("repair")
        if isinstance(self._repair, Exception):
            raise self._repair
        return self._repair

    def resolve_current_explanation(self, db_path, *, previous_context_id, resolved_at):
        self.tool_execution_count += 1
        return self._resolve

    def load_snapshot(self, con, context_id):
        return self._resolve["snapshot"]

    def connect(self, db_path):
        return _dummy_con()

    def load_knowledge_catalog(self):
        return self._catalog

    def knowledge(self, catalog, indicator_id, object_type):
        if self._knowledge is not None:
            self.tool_execution_count += 1
            return self._knowledge(catalog, indicator_id, object_type)
        for record in catalog.get("records", []):
            if (
                record.get("indicator_id") == indicator_id
                and record.get("object_type") == object_type
            ):
                return record
        raise ValueError(f"knowledge record is not available for {indicator_id}")

    def exploration(self, con, query, *, result_id, created_at):
        self.tool_execution_count += 1
        return self._exploration

    async def acquire_research(self, provider, task, *, result_id, searched_at):
        self.tool_execution_count += 1
        self.acquired_research_kwargs = {
            "result_id": result_id,
            "searched_at": searched_at,
            "task": task,
        }
        return self._research

    def build_research_provider(self, config):
        return object()

    def save_bundle(self, con, *, artifacts, answer_trace):
        self.saved_trace = answer_trace
        self.saved_artifacts = list(artifacts)


def fake_dependencies(plan, draft, repair=None, **kwargs):
    return FakeDependencies(plan, draft, repair=repair, **kwargs)


class RealPersistenceDeps:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.config = _config()

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

    async def plan_llm(self, *, question, context_summary):
        return validate_task_plan(
            {
                "intent": "decision_explanation",
                "context_mode": "current",
                "operations": [
                    {"operation_id": "resolve_current_explanation", "parameters": {}},
                    {
                        "operation_id": "get_indicator_definition",
                        "parameters": {"indicator_id": "vix_level"},
                    },
                ],
                "answer_depth": "standard",
                "research_tier": None,
            }
        )

    async def synthesize_llm(self, *, question, plan, context_summary, artifacts):
        snapshot_artifact = next(
            artifact
            for artifact in artifacts.values()
            if artifact["artifact_kind"] == "explanation_snapshot"
        )
        context_id = snapshot_artifact["artifact_id"]
        regime = snapshot_artifact["payload"]["results"]["macro_regime"]
        knowledge_artifact = next(
            artifact
            for artifact in artifacts.values()
            if artifact["artifact_kind"] == "knowledge_record"
        )
        return {
            "sections": [
                {
                    "kind": "decision",
                    "claims": [
                        {
                            "claim_id": "c1",
                            "purpose": "decision_explanation",
                            "authority": "decision_fact",
                            "refs": [
                                {
                                    "artifact_id": context_id,
                                    "object_type": "market_setup_result",
                                    "object_id": "macro_regime",
                                }
                            ],
                            "template": "The macro regime is {regime}.",
                            "bindings": {
                                "regime": {
                                    "value": regime["code"],
                                    "source": {
                                        "artifact_id": context_id,
                                        "object_type": "market_setup_result",
                                        "object_id": "macro_regime",
                                        "field": "code",
                                    },
                                }
                            },
                        }
                    ],
                },
                {
                    "kind": "knowledge",
                    "claims": [
                        {
                            "claim_id": "k1",
                            "purpose": "method_explanation",
                            "authority": "method_knowledge",
                            "refs": [
                                {
                                    "artifact_id": knowledge_artifact["artifact_id"],
                                    "object_type": "indicator_definition",
                                    "object_id": knowledge_artifact["artifact_id"],
                                }
                            ],
                            "template": "The approved instrument is {title}.",
                            "bindings": {
                                "title": {
                                    "value": "CBOE Volatility Index",
                                    "source": {
                                        "artifact_id": knowledge_artifact[
                                            "artifact_id"
                                        ],
                                        "object_type": "indicator_definition",
                                        "object_id": knowledge_artifact["artifact_id"],
                                        "field": "title",
                                    },
                                }
                            },
                        }
                    ],
                },
            ]
        }

    async def repair_llm(
        self, *, question, plan, context_summary, artifacts, draft, validation_report
    ):
        raise AssertionError("repair must not run")


@pytest.mark.asyncio
async def test_answer_uses_one_structured_synthesis_and_persists_trace():
    deps = fake_dependencies(valid_plan(), valid_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.llm_calls == ["plan", "draft"]
    assert deps.saved_trace["answer_text"] == response["answer_text"]


@pytest.mark.asyncio
async def test_failed_repair_uses_deterministic_fallback_without_new_tools():
    deps = fake_dependencies(valid_plan(), invalid_draft(), invalid_repair())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert deps.tool_execution_count == 1
    assert deps.llm_calls == ["plan", "draft", "repair"]


@pytest.mark.asyncio
async def test_validated_after_repair_returns_repaired_answer():
    deps = fake_dependencies(valid_plan(), invalid_draft(), valid_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_after_repair"
    assert deps.llm_calls == ["plan", "draft", "repair"]
    assert deps.saved_trace["attempts"] == {"plan": 1, "draft": 2, "repair": 1}


@pytest.mark.asyncio
async def test_invalid_plan_repairs_then_synthesizes():
    invalid = valid_plan(intent="decision_explanation", context_mode="historical")
    deps = fake_dependencies([invalid, valid_plan()], valid_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.llm_calls == ["plan", "plan", "draft"]


@pytest.mark.asyncio
async def test_plan_unavailable_uses_deterministic_decision_plan():
    deps = fake_dependencies(RuntimeError("llm down"), valid_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_trace["plan"]["operations"][0]["operation_id"] == (
        "resolve_current_explanation"
    )
    assert deps.tool_execution_count == 1


@pytest.mark.asyncio
async def test_research_operation_calls_acquire_research_with_ids():
    deps = fake_dependencies(
        research_plan(),
        _research_draft(),
        research=research_result(),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert deps.acquired_research_kwargs is not None
    assert deps.acquired_research_kwargs["result_id"].startswith("res_")
    assert deps.acquired_research_kwargs["searched_at"]
    assert deps.acquired_research_kwargs["task"]["depth_tier"] == "focused"
    assert response["generation_status"] == "validated_first_pass"


@pytest.mark.asyncio
async def test_research_unavailable_renders_research_fallback():
    deps = fake_dependencies(
        research_plan(),
        invalid_draft(),
        invalid_repair(),
        research=research_unavailable(),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert "External research is currently unavailable." in response["answer_text"]


@pytest.mark.asyncio
async def test_context_change_notice_precedes_claims():
    deps = fake_dependencies(
        valid_plan(),
        valid_draft(),
        resolve=resolution_envelope(previous_context_id="ctx_A"),
    )
    request = current_question(previous_context_id="ctx_A")
    response = await market_assistant.answer_question(request, dependencies=deps)

    notice = "Market Setup context changed since the previous message."
    assert notice in response["answer_text"]
    assert response["answer_text"].index(notice) < response["answer_text"].index(
        "The accepted VIX level"
    )


@pytest.mark.asyncio
async def test_external_and_local_claims_keep_separate_authorities():
    local_claim = {
        "claim_id": "local1",
        "purpose": "decision_explanation",
        "authority": "decision_fact",
        "refs": [
            {
                "artifact_id": "ctx_123",
                "object_type": "market_setup_result",
                "object_id": "macro_regime",
            },
            evidence_ref(),
        ],
        "template": (
            "The macro regime is {regime} and the accepted VIX level is {vix_level}."
        ),
        "bindings": {
            "regime": {
                "value": "growth_decelerating",
                "source": {
                    "artifact_id": "ctx_123",
                    "object_type": "market_setup_result",
                    "object_id": "macro_regime",
                    "field": "code",
                },
            },
            "vix_level": {
                "value": 18.4,
                "source": evidence_ref(field="accepted_values.level"),
            },
        },
    }
    external_claim = {
        "claim_id": "ext1",
        "purpose": "source_explanation",
        "authority": "external_research",
        "refs": [
            {
                "artifact_id": "res_1",
                "object_type": "research_source",
                "object_id": "src_1",
            }
        ],
        "template": "An external source reports the VIX at {ext_level}.",
        "bindings": {
            "ext_level": {
                "value": 25.0,
                "source": {
                    "artifact_id": "res_1",
                    "object_type": "research_source",
                    "object_id": "src_1",
                    "field": "reported_level",
                },
            }
        },
    }
    plan = valid_plan(
        operations=[
            {"operation_id": "resolve_current_explanation", "parameters": {}},
            {
                "operation_id": "research_focused",
                "parameters": {
                    "purpose": "current_events",
                    "queries": ["latest vix"],
                    "expected_source_class": "official_publication",
                },
            },
        ],
        research_tier="focused",
    )
    draft = {
        "sections": [
            {"kind": "decision", "claims": [local_claim]},
            {"kind": "research", "claims": [external_claim]},
        ]
    }
    deps = fake_dependencies(plan, draft, research=research_result())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert "growth_decelerating" in response["answer_text"]
    assert "18.4" in response["answer_text"]
    assert "25.0" in response["answer_text"]
    authorities = {
        claim["authority"]
        for section in deps.saved_trace["structured_claims"]
        for claim in section["claims"]
    }
    assert authorities == {"decision_fact", "external_research"}
    assert not any(
        artifact["artifact_kind"] == "explanation_snapshot"
        for artifact in deps.saved_artifacts
    )
    research_artifact = next(
        artifact
        for artifact in deps.saved_artifacts
        if artifact["artifact_kind"] == "research_result"
    )
    assert research_artifact["market_setup_relation"] == "non_decision"


@pytest.mark.asyncio
async def test_persistence_failure_raises_stable_error():
    deps = fake_dependencies(valid_plan(), valid_draft())

    def fail_save(con, *, artifacts, answer_trace):
        raise RuntimeError("disk full")

    deps.save_bundle = fail_save

    with pytest.raises(ValueError, match="answer trace persistence failed"):
        await market_assistant.answer_question(current_question(), dependencies=deps)
    assert deps.saved_trace is None


@pytest.mark.asyncio
async def test_every_llm_call_unavailable_renders_market_setup_fallback():
    deps = fake_dependencies(
        RuntimeError("llm down"),
        RuntimeError("llm down"),
        RuntimeError("llm down"),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert "Market Setup decision result:" in response["answer_text"]
    assert deps.saved_trace["generation_status"] == "fallback"


@pytest.mark.asyncio
async def test_answer_trace_has_design_19_fields_and_no_secrets():
    deps = fake_dependencies(valid_plan(), valid_draft())
    await market_assistant.answer_question(current_question(), dependencies=deps)
    trace = deps.saved_trace

    expected_fields = {
        "answer_trace_id",
        "message_id",
        "resolution",
        "explanation_context_id",
        "knowledge_references",
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
        "generated_time",
    }
    assert expected_fields.issubset(trace)
    assert trace["answer_trace_id"].startswith("trc_")
    assert trace["message_id"].startswith("msg_")
    assert trace["generation_status"] == "validated_first_pass"
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
async def test_only_referenced_persistable_artifacts_are_saved():
    plan = valid_plan(
        operations=[
            {"operation_id": "resolve_current_explanation", "parameters": {}},
            {
                "operation_id": "research_focused",
                "parameters": {
                    "purpose": "current_events",
                    "queries": ["latest vix"],
                    "expected_source_class": "official_publication",
                },
            },
        ],
        research_tier="focused",
    )
    draft = {
        "sections": [
            {"kind": "decision", "claims": [valid_claim()]},
            {"kind": "research", "claims": [_research_claim()]},
        ]
    }
    deps = fake_dependencies(plan, draft, research=research_result())
    await market_assistant.answer_question(current_question(), dependencies=deps)

    persisted_ids = [artifact["artifact_id"] for artifact in deps.saved_artifacts]
    assert persisted_ids == ["res_1"]


@pytest.mark.asyncio
async def test_persistence_excludes_pre_durable_snapshot_artifact():
    deps = fake_dependencies(valid_plan(), valid_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_artifacts == []
    assert deps.saved_trace["generation_status"] == "validated_first_pass"


@pytest.mark.asyncio
async def test_unimplemented_operation_returns_deterministic_fallback():
    plan = {
        "intent": "counterfactual",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "get_counterfactuals",
                "parameters": {"context_id": "ctx_123"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    deps = fake_dependencies(plan, valid_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert deps.llm_calls == ["plan"]
    assert deps.saved_trace["generation_status"] == "fallback"


@pytest.mark.asyncio
async def test_answer_question_persists_real_bundle_with_durable_snapshot(tmp_path):
    db_path = tmp_path / "assistant.sqlite"
    deps = RealPersistenceDeps(db_path)
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    con = market_assistant_db.connect(db_path)
    try:
        trace = market_assistant_db.load_answer_trace(con, response["answer_trace_id"])
        assert trace is not None
        snapshot = market_assistant_db.load_snapshot(
            con, trace["explanation_context_id"]
        )
        assert snapshot is not None
        assert trace["knowledge_references"] == ["vix_definition"]
        for table in ("knowledge_records", "exploration_results", "research_results"):
            row = con.execute(f"select count(*) from {table}").fetchone()
            assert row[0] == (1 if table == "knowledge_records" else 0)
    finally:
        con.close()


@pytest.mark.asyncio
async def test_knowledge_operation_acquires_knowledge_record_artifact():
    deps = fake_dependencies(knowledge_plan(), _knowledge_draft())
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_trace["knowledge_references"] == ["vix_definition"]


@pytest.mark.asyncio
async def test_exploration_operation_acquires_exploration_result_artifact():
    deps = fake_dependencies(
        exploration_plan(),
        _exploration_draft(),
        exploration=exploration_result(),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_trace["exploration_result_ids"] == ["expl_1"]


def _knowledge_draft():
    claim = {
        "claim_id": "k1",
        "purpose": "method_explanation",
        "authority": "method_knowledge",
        "refs": [
            {
                "artifact_id": "vix_definition",
                "object_type": "indicator_definition",
                "object_id": "vix_definition",
            }
        ],
        "template": "The VIX measures expected volatility.",
        "bindings": {},
    }
    return {"sections": [{"kind": "knowledge", "claims": [claim]}]}


def _research_claim():
    return {
        "claim_id": "r1",
        "purpose": "source_explanation",
        "authority": "external_research",
        "refs": [
            {
                "artifact_id": "res_1",
                "object_type": "research_source",
                "object_id": "src_1",
            }
        ],
        "template": "The external source reports a VIX level of {reported_level}.",
        "bindings": {
            "reported_level": {
                "value": 25.0,
                "source": {
                    "artifact_id": "res_1",
                    "object_type": "research_source",
                    "object_id": "src_1",
                    "field": "reported_level",
                },
            }
        },
    }


def _research_draft():
    return {"sections": [{"kind": "research", "claims": [_research_claim()]}]}


def _exploration_draft():
    claim = {
        "claim_id": "e1",
        "purpose": "observation",
        "authority": "local_observation",
        "refs": [
            {
                "artifact_id": "expl_1",
                "object_type": "indicator_history",
                "object_id": "vix_history",
            }
        ],
        "template": "The final VIX value in the window is {last_value}.",
        "bindings": {
            "last_value": {
                "value": 18.4,
                "source": {
                    "artifact_id": "expl_1",
                    "object_type": "indicator_history",
                    "object_id": "vix_history",
                    "field": "last_value",
                },
            }
        },
    }
    return {"sections": [{"kind": "observation", "claims": [claim]}]}
