import asyncio
import json
from copy import deepcopy

import pytest

from app.db import market_assistant as market_assistant_db
from app.services import market_assistant
from app.services.market_assistant import ASSISTANT_POLICY_VERSION
from app.services.market_assistant import PROMPT_VERSION
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_answers import validate_answer_draft_schema
from app.tools.market_assistant_artifacts import resolve_artifact_ref
from app.tools.market_assistant_knowledge import load_knowledge_catalog
from app.tools.market_assistant_plans import validate_task_plan
from app.tools.market_setup_explanation_snapshot import canonical_json


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


def beginner_debug_draft():
    return {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "beginner_summary",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [evidence_ref()],
                        "template": "现在的市场可以理解为：经济增长正在{direction}，但市场只确认了{confirmation}风险。",
                        "bindings": {
                            "direction": "放慢",
                            "confirmation": "一部分",
                        },
                    }
                ],
            }
        ]
    }


def _chinese_observation_debug_draft():
    return {
        "sections": [
            {
                "kind": "observation",
                "claims": [
                    {
                        "claim_id": "obs_debug",
                        "purpose": "observation",
                        "authority": "local_observation",
                        "refs": [],
                        "template": "当前波动率为{vix}。",
                        "bindings": {
                            "vix": {
                                "artifact_id": "ctx_1",
                                "object_type": "evidence_fact",
                                "object_id": "vix_level",
                                "field": "observed.value",
                            }
                        },
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
        self.context_summaries = []
        self.tool_execution_count = 0
        self.saved_trace = None
        self.saved_artifacts = None
        self.acquired_research_kwargs = None
        self.acquired_artifacts = None
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
        self.context_summaries.append(context_summary)
        if isinstance(self._plan, list):
            response = self._plan.pop(0)
        else:
            response = self._plan
        if isinstance(response, Exception):
            raise response
        return validate_task_plan(response)

    async def synthesize_llm(self, *, question, plan, context_summary, artifacts):
        self.llm_calls.append("draft")
        self.acquired_artifacts = artifacts
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

    async def acquire_research(
        self, provider, task, *, result_id, searched_at, explicit_deep=False
    ):
        self.tool_execution_count += 1
        self.acquired_research_kwargs = {
            "result_id": result_id,
            "searched_at": searched_at,
            "task": task,
            "explicit_deep": explicit_deep,
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
        regime = next(
            item["payload"]
            for item in snapshot_artifact["object_index"]
            if item["object_type"] == "market_setup_result"
            and item["object_id"] == "macro_regime"
        )
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
                                    "value": regime["label"],
                                    "source": {
                                        "artifact_id": context_id,
                                        "object_type": "market_setup_result",
                                        "object_id": "macro_regime",
                                        "field": "label",
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
async def test_llm_receives_bounded_object_projection_not_duplicated_payload():
    deps = fake_dependencies(valid_plan(), valid_draft())

    await market_assistant.answer_question(current_question(), dependencies=deps)

    assert deps.acquired_artifacts
    for artifact in deps.acquired_artifacts.values():
        assert "payload" not in artifact
        assert isinstance(artifact["object_index"], list)


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
        {"ctx_123": artifact}, valid_plan()
    )

    assert [item["object_id"] for item in projected["ctx_123"]["object_index"]] == [
        "survey_growth_direction"
    ]


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
    artifact = market_assistant._snapshot_artifact(_projection_snapshot())
    return {artifact["artifact_id"]: artifact}


def _projected(plan):
    return market_assistant._llm_artifact_projection(_projection_artifacts(), plan)


def _projected_objects():
    return _projected(valid_plan())["ctx_123"]["object_index"]


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
    projected = market_assistant._llm_artifact_projection(artifacts, valid_plan())

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
    object_index = _projected(valid_plan())["ctx_123"]["object_index"]

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


def test_llm_artifact_projection_smaller_than_previous_full_payload_projection():
    artifacts = _projection_artifacts()
    compact = market_assistant._llm_artifact_projection(artifacts, valid_plan())
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
        artifacts, valid_plan(intent="counterfactual")
    )

    assert projected["ctx_123"]["object_index"] == frozen["ctx_123"]["object_index"]


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
async def test_disabled_claim_validation_returns_unvalidated_debug_draft():
    deps = fake_dependencies(
        valid_plan(),
        beginner_debug_draft(),
        invalid_repair(),
        config=_config(claim_validation_enabled=False),
    )

    response = await market_assistant.answer_question(
        current_question(question="现在市场怎么样？为什么？"),
        dependencies=deps,
    )

    assert response["generation_status"] == "unvalidated_debug"
    assert response["answer_text"] == (
        "现在的市场可以理解为：经济增长正在放慢，但市场只确认了一部分风险。"
    )
    assert "sections" not in response["answer_text"]
    assert response["citations"] == []
    assert deps.llm_calls == ["plan", "draft"]
    assert deps.saved_trace["generation_status"] == "unvalidated_debug"
    expected_claims = validate_answer_draft_schema(beginner_debug_draft())["sections"]
    assert deps.saved_trace["structured_claims"] == expected_claims
    assert deps.saved_trace["validation_error_codes"] == []
    assert deps.saved_trace["attempts"] == {
        "plan": 1,
        "draft": 1,
        "repair": 0,
    }


@pytest.mark.asyncio
async def test_disabled_claim_validation_debug_render_uses_detected_language():
    deps = fake_dependencies(
        valid_plan(),
        _chinese_observation_debug_draft(),
        config=_config(claim_validation_enabled=False),
    )

    response = await market_assistant.answer_question(
        current_question(question="现在市场怎么样？"),
        dependencies=deps,
    )

    assert response["generation_status"] == "unvalidated_debug"
    assert response["answer_text"].startswith("本地数据观察\n")
    assert "当前波动率为暂不可用。" in response["answer_text"]
    assert deps.llm_calls == ["plan", "draft"]


@pytest.mark.asyncio
async def test_fully_filtered_debug_draft_falls_back_deterministically():
    draft = {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "d1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [evidence_ref()],
                        "template": "当前市场状态是{state}，因此应该买入。",
                        "bindings": {"state": "增长放缓"},
                    }
                ],
            }
        ]
    }
    deps = fake_dependencies(
        valid_plan(),
        draft,
        invalid_repair(),
        config=_config(claim_validation_enabled=False),
    )

    response = await market_assistant.answer_question(
        current_question(question="现在市场怎么样？"),
        dependencies=deps,
    )

    assert response["generation_status"] == "fallback"
    assert response["answer_text"].strip()
    assert "买入" not in response["answer_text"]
    assert deps.llm_calls == ["plan", "draft"]
    assert deps.saved_trace["generation_status"] == "fallback"
    assert "DISPLAY_FILTERED" in deps.saved_trace["validation_error_codes"]
    assert deps.saved_trace["structured_claims"] is not None


@pytest.mark.asyncio
async def test_validated_chinese_question_uses_chinese_heading():
    deps = fake_dependencies(knowledge_plan(), _knowledge_draft())

    response = await market_assistant.answer_question(
        current_question(question="VIX 是什么？"),
        dependencies=deps,
    )

    assert response["generation_status"] == "validated_first_pass"
    assert response["answer_text"].startswith("指标与方法\n")
    assert "Method & Knowledge" not in response["answer_text"]


@pytest.mark.asyncio
async def test_disabled_claim_validation_still_falls_back_for_invalid_schema():
    deps = fake_dependencies(
        valid_plan(),
        {"sections": []},
        invalid_repair(),
        config=_config(claim_validation_enabled=False),
    )

    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert deps.llm_calls == ["plan", "draft"]
    assert deps.saved_trace["structured_claims"] is None
    assert deps.saved_trace["validation_error_codes"] == ["SCHEMA_INVALID"]


@pytest.mark.asyncio
async def test_claim_validation_remains_enabled_when_config_key_is_absent():
    config = _config()
    config.pop("claim_validation_enabled", None)
    deps = fake_dependencies(
        valid_plan(),
        invalid_draft(),
        invalid_repair(),
        config=config,
    )

    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
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
async def test_context_change_surfaces_in_resolution_not_answer_text():
    deps = fake_dependencies(
        valid_plan(),
        valid_draft(),
        resolve=resolution_envelope(previous_context_id="ctx_A"),
    )
    request = current_question(previous_context_id="ctx_A")
    response = await market_assistant.answer_question(request, dependencies=deps)

    notice = "Market Setup context changed since the previous message."
    assert response["resolution"]["context_changed"] is True
    assert response["resolution"]["previous_context_id"] == "ctx_A"
    assert notice not in response["answer_text"]


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
                "value": "Growth Decelerating",
                "source": {
                    "artifact_id": "ctx_123",
                    "object_type": "market_setup_result",
                    "object_id": "macro_regime",
                    "field": "label",
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
    assert "Growth Decelerating" in response["answer_text"]
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
async def test_every_llm_call_unavailable_renders_market_setup_fallback(caplog):
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
    assert "market assistant plan generation failed" in caplog.text
    assert "market assistant synthesis failed" in caplog.text


@pytest.mark.asyncio
async def test_hanging_synthesis_returns_deterministic_fallback_within_budget():
    deps = fake_dependencies(valid_plan(), valid_draft())
    deps.llm_attempt_timeout = 0.01

    async def hang_forever(**kwargs):
        await asyncio.Event().wait()

    deps.synthesize_llm = hang_forever

    response = await asyncio.wait_for(
        market_assistant.answer_question(current_question(), dependencies=deps),
        timeout=0.5,
    )

    assert response["generation_status"] == "fallback"
    assert "Market Setup decision result:" in response["answer_text"]


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
    assert (
        trace["model_configuration_fingerprint"]["structured_output_mode"]
        == "json_object"
    )
    assert trace["model_configuration_fingerprint"]["reasoning_effort"] == "low"
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
async def test_counterfactuals_mismatched_context_falls_back():
    plan = {
        "intent": "counterfactual",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "get_counterfactuals",
                "parameters": {"context_id": "ctx_old"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    snapshot = fake_snapshot()
    snapshot["counterfactuals"] = [
        {
            "counterfactual_id": "cf_1",
            "object_type": "confirmation_test",
            "object_id": "vix_downside_confirmation",
            "transition": "accepted_value_crosses_boundary",
            "decision_effect": "confirmation_test_result_change",
        }
    ]
    resolve = resolution_envelope()
    resolve["snapshot"] = snapshot
    deps = fake_dependencies(plan, valid_draft(), resolve=resolve)
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert deps.saved_trace["generation_status"] == "fallback"


@pytest.mark.asyncio
async def test_historical_snapshot_mismatched_context_falls_back():
    plan = {
        "intent": "historical_snapshot",
        "context_mode": "historical",
        "operations": [
            {
                "operation_id": "get_historical_snapshot",
                "parameters": {"context_id": "ctx_old"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    deps = fake_dependencies(plan, valid_draft())
    response = await market_assistant.answer_question(
        current_question(mode="historical", context_id="ctx_123"),
        dependencies=deps,
    )

    assert response["generation_status"] == "fallback"
    assert deps.saved_trace["generation_status"] == "fallback"


@pytest.mark.asyncio
async def test_compare_snapshots_requires_resolution_context():
    plan = {
        "intent": "snapshot_comparison",
        "context_mode": "historical",
        "operations": [
            {
                "operation_id": "compare_snapshots",
                "parameters": {
                    "context_a_id": "ctx_A",
                    "context_b_id": "ctx_B",
                },
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    deps = fake_dependencies(plan, valid_draft())
    response = await market_assistant.answer_question(
        current_question(mode="historical", context_id="ctx_123"),
        dependencies=deps,
    )

    assert response["generation_status"] == "fallback"
    assert deps.saved_trace["generation_status"] == "fallback"


@pytest.mark.asyncio
async def test_missing_counterfactuals_returns_deterministic_fallback():
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
async def test_historical_snapshot_operation_acquires_snapshot_artifact():
    plan = {
        "intent": "historical_snapshot",
        "context_mode": "historical",
        "operations": [
            {
                "operation_id": "get_historical_snapshot",
                "parameters": {"context_id": "ctx_123"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    draft = {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "h1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [
                            {
                                "artifact_id": "ctx_123",
                                "object_type": "market_setup_result",
                                "object_id": "macro_regime",
                            }
                        ],
                        "template": "The macro regime was {regime}.",
                        "bindings": {
                            "regime": {
                                "value": "Growth Decelerating",
                                "source": {
                                    "artifact_id": "ctx_123",
                                    "object_type": "market_setup_result",
                                    "object_id": "macro_regime",
                                    "field": "label",
                                },
                            }
                        },
                    }
                ],
            }
        ]
    }
    deps = fake_dependencies(plan, draft)
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert any(
        artifact["artifact_kind"] == "explanation_snapshot"
        for artifact in deps.acquired_artifacts.values()
    )


@pytest.mark.asyncio
async def test_snapshot_object_operation_acquires_focused_artifact():
    plan = {
        "intent": "decision_explanation",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "get_snapshot_object",
                "parameters": {
                    "object_type": "market_setup_result",
                    "object_id": "macro_regime",
                },
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    draft = {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "s1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [
                            {
                                "artifact_id": "ctx_123_market_setup_result_macro_regime",
                                "object_type": "market_setup_result",
                                "object_id": "macro_regime",
                            }
                        ],
                        "template": "The macro regime is {regime}.",
                        "bindings": {
                            "regime": {
                                "value": "Growth Decelerating",
                                "source": {
                                    "artifact_id": "ctx_123_market_setup_result_macro_regime",
                                    "object_type": "market_setup_result",
                                    "object_id": "macro_regime",
                                    "field": "label",
                                },
                            }
                        },
                    }
                ],
            }
        ]
    }
    deps = fake_dependencies(plan, draft)
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"


@pytest.mark.asyncio
async def test_counterfactuals_operation_acquires_artifact_when_present():
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
    snapshot = fake_snapshot()
    snapshot["counterfactuals"] = [
        {
            "counterfactual_id": "cf_1",
            "object_type": "confirmation_test",
            "object_id": "vix_downside_confirmation",
            "transition": "accepted_value_crosses_boundary",
            "decision_effect": "confirmation_test_result_change",
        }
    ]
    resolve = resolution_envelope()
    resolve["snapshot"] = snapshot
    draft = {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "cf1",
                        "purpose": "counterfactual_explanation",
                        "authority": "decision_fact",
                        "refs": [
                            {
                                "artifact_id": "ctx_123_counterfactuals",
                                "object_type": "confirmation_test",
                                "object_id": "vix_downside_confirmation",
                            }
                        ],
                        "template": "The approved test would flip.",
                        "bindings": {},
                    }
                ],
            }
        ]
    }
    deps = fake_dependencies(plan, draft, resolve=resolve)
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert "ctx_123_counterfactuals" in deps.saved_trace["snapshot_artifact_ids"]
    assert "ctx_123_counterfactuals" in [
        artifact["artifact_id"] for artifact in deps.saved_artifacts
    ]


@pytest.mark.asyncio
async def test_compare_snapshots_operation_acquires_delta_artifact():
    plan = {
        "intent": "snapshot_comparison",
        "context_mode": "historical",
        "operations": [
            {
                "operation_id": "compare_snapshots",
                "parameters": {
                    "context_a_id": "ctx_A",
                    "context_b_id": "ctx_123",
                },
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    draft = {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "cmp1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [
                            {
                                "artifact_id": "cmp_ctx_A_ctx_123",
                                "object_type": "snapshot_delta",
                                "object_id": "cmp_ctx_A_ctx_123",
                            }
                        ],
                        "template": "The snapshots are compared.",
                        "bindings": {},
                    }
                ],
            }
        ]
    }
    deps = fake_dependencies(plan, draft)
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert any(
        artifact["artifact_id"] == "cmp_ctx_A_ctx_123"
        for artifact in deps.acquired_artifacts.values()
    )
    assert "cmp_ctx_A_ctx_123" in deps.saved_trace["snapshot_artifact_ids"]
    assert "cmp_ctx_A_ctx_123" in [
        artifact["artifact_id"] for artifact in deps.saved_artifacts
    ]


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


def _knowledge_draft_with_answer_text(answer_text):
    draft = _knowledge_draft()
    draft["answer_text"] = answer_text
    return draft


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


def _knowledge_method_draft(record_id="vix_method"):
    claim = {
        "claim_id": "m1",
        "purpose": "method_explanation",
        "authority": "method_knowledge",
        "refs": [
            {
                "artifact_id": record_id,
                "object_type": "indicator_method",
                "object_id": record_id,
            }
        ],
        "template": "The VIX confirmation method is the approved market confirmation method.",
        "bindings": {},
    }
    return {"sections": [{"kind": "knowledge", "claims": [claim]}]}


def _knowledge_source_draft(record_id="vix_source"):
    claim = {
        "claim_id": "s1",
        "purpose": "source_explanation",
        "authority": "method_knowledge",
        "refs": [
            {
                "artifact_id": record_id,
                "object_type": "indicator_source",
                "object_id": record_id,
            }
        ],
        "template": "The VIX level is sourced from the accepted daily series.",
        "bindings": {},
    }
    return {"sections": [{"kind": "research", "claims": [claim]}]}


@pytest.mark.asyncio
async def test_deep_research_with_explicit_intent_executes():
    deps = fake_dependencies(
        research_plan("deep"), _research_draft(), research=research_result()
    )
    request = current_question(deep_research_requested=True)
    response = await market_assistant.answer_question(request, dependencies=deps)

    assert deps.acquired_research_kwargs is not None
    assert deps.acquired_research_kwargs["task"]["depth_tier"] == "deep"
    assert deps.acquired_research_kwargs["explicit_deep"] is True
    assert response["generation_status"] == "validated_first_pass"


@pytest.mark.asyncio
async def test_deep_research_without_explicit_intent_never_executes():
    deps = fake_dependencies(research_plan("deep"), invalid_draft(), invalid_repair())
    request = current_question(deep_research_requested=False)
    response = await market_assistant.answer_question(request, dependencies=deps)

    assert deps.acquired_research_kwargs is None
    assert response["generation_status"] == "fallback"
    assert "External research is currently unavailable." in response["answer_text"]


@pytest.mark.asyncio
async def test_external_search_requested_flows_to_planner_context():
    deps = fake_dependencies(valid_plan(), valid_draft())
    request = current_question(external_search_requested=True)
    response = await market_assistant.answer_question(request, dependencies=deps)

    assert response["generation_status"] == "validated_first_pass"
    assert deps.context_summaries[0]["external_search_requested"] is True


@pytest.mark.asyncio
async def test_knowledge_definition_through_real_catalog_aliases_vix():
    deps = fake_dependencies(
        knowledge_plan(), _knowledge_draft(), catalog=load_knowledge_catalog()
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_trace["knowledge_references"] == ["vix_definition"]


@pytest.mark.asyncio
async def test_knowledge_method_through_real_catalog_aliases_vix():
    deps = fake_dependencies(
        knowledge_plan(
            operations=[
                {
                    "operation_id": "get_indicator_method",
                    "parameters": {"indicator_id": "vix"},
                }
            ],
            intent="method",
        ),
        _knowledge_method_draft(),
        catalog=load_knowledge_catalog(),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_trace["knowledge_references"] == ["vix_method"]


@pytest.mark.asyncio
async def test_knowledge_source_through_real_catalog_aliases_vix():
    deps = fake_dependencies(
        knowledge_plan(
            operations=[
                {
                    "operation_id": "get_indicator_source",
                    "parameters": {"indicator_id": "vix"},
                }
            ],
            intent="source",
        ),
        _knowledge_source_draft(),
        catalog=load_knowledge_catalog(),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.saved_trace["knowledge_references"] == ["vix_source"]


@pytest.mark.asyncio
async def test_unknown_knowledge_indicator_routes_to_fallback():
    deps = fake_dependencies(
        knowledge_plan(
            operations=[
                {
                    "operation_id": "get_indicator_definition",
                    "parameters": {"indicator_id": "unknown_series"},
                }
            ]
        ),
        valid_draft(),
    )
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert (
        "The approved knowledge record is currently unavailable."
        in response["answer_text"]
    )


@pytest.mark.asyncio
async def test_unregistered_exploration_indicator_routes_to_fallback():
    plan = {
        "intent": "local_history",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "query_indicator_history",
                "parameters": {
                    "indicator_id": "not_registered",
                    "start": "2026-01-01",
                    "end": "2026-06-30",
                },
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    deps = fake_dependencies(plan, valid_draft())

    def raise_unregistered(con, query, *, result_id, created_at):
        raise ValueError(f"indicator is not registered: {query['indicator_id']}")

    deps.exploration = raise_unregistered
    response = await market_assistant.answer_question(
        current_question(), dependencies=deps
    )

    assert response["generation_status"] == "fallback"
    assert "Local exploration data is currently unavailable." in response["answer_text"]


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


@pytest.mark.asyncio
async def test_matching_chinese_answer_text_passes_validation():
    deps = fake_dependencies(
        knowledge_plan(),
        _knowledge_draft_with_answer_text(
            "指标与方法\nThe VIX measures expected volatility."
        ),
    )

    response = await market_assistant.answer_question(
        current_question(question="VIX 是什么？"), dependencies=deps
    )

    assert response["generation_status"] == "validated_first_pass"
    assert deps.llm_calls == ["plan", "draft"]


@pytest.mark.asyncio
async def test_mismatched_chinese_answer_text_repairs_then_passes():
    deps = fake_dependencies(
        knowledge_plan(),
        _knowledge_draft_with_answer_text("指标与方法\nThe VIX is highly volatile."),
        _knowledge_draft_with_answer_text(
            "指标与方法\nThe VIX measures expected volatility."
        ),
    )

    response = await market_assistant.answer_question(
        current_question(question="VIX 是什么？"), dependencies=deps
    )

    assert response["generation_status"] == "validated_after_repair"
    assert deps.llm_calls == ["plan", "draft", "repair"]
    assert deps.saved_trace["validation_error_codes"] == ["ANSWER_TEXT_MISMATCH"]


@pytest.mark.asyncio
async def test_debug_mode_prefers_draft_answer_text():
    draft = beginner_debug_draft()
    draft["answer_text"] = "市场处于轻度避险状态。"
    deps = fake_dependencies(
        valid_plan(),
        draft,
        invalid_repair(),
        config=_config(claim_validation_enabled=False),
    )

    response = await market_assistant.answer_question(
        current_question(question="现在市场怎么样？为什么？"),
        dependencies=deps,
    )

    assert response["generation_status"] == "unvalidated_debug"
    assert response["answer_text"] == "市场处于轻度避险状态。"
    assert deps.llm_calls == ["plan", "draft"]
