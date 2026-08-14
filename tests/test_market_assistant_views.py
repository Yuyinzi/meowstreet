import re
from copy import deepcopy

from app.services.market_assistant_tool_runtime import (
    _approved_counterfactuals_artifact,
)
from app.services.market_assistant_tool_runtime import _confirmation_test_artifact
from app.services.market_assistant_tool_runtime import _confirmation_tests_artifact
from app.services.market_assistant_tool_runtime import _macro_regime_artifact
from app.services.market_assistant_tool_runtime import _posture_artifact
from app.services.market_assistant_tool_runtime import _setup_overview_artifact
from app.services.market_assistant_tool_runtime import snapshot_artifact
from app.tools import market_setup_evidence_facts
from app.tools import market_setup_explanation_snapshot
from app.tools import market_setup_v2
from app.tools.market_assistant_artifacts import resolve_artifact_ref
from app.tools.market_assistant_routes import route_question
from app.tools.market_assistant_views import build_explanation_view
from app.tools.market_setup_explanation_snapshot import canonical_json

_SNAKE_CODE_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

_DISPLAY_SKIP_KEYS = frozenset(
    {
        "audit_objects",
        "view_version",
        "question_language",
        "as_of",
        "evidence_through",
        "context_id",
        "budget",
        "fact_id",
        "test_id",
        "counterfactual_id",
        "object_id",
        "record_id",
        "indicator_id",
        "artifact_id",
        "object_type",
    }
)


def current_setup_route():
    return route_question("现在市场怎么样？", deep_analysis=False)


def _monthly_period(effective_date="2026-06-30", reference_period="2026-06"):
    return {
        "effective_date": effective_date,
        "reference_period": reference_period,
        "release_date": "2026-07-01",
    }


def _daily_period(effective_date="2026-07-01", observation_date="2026-07-01"):
    return {
        "effective_date": effective_date,
        "observation_date": observation_date,
    }


def _expected_growth(direction="rising"):
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


def _financial_conditions():
    return {
        "source_module": "us_rates_liquidity",
        "method_version": "us_rates_liquidity_v1",
        "facts": {
            "macro_financial_conditions": {
                "relationship_to_growth_direction": "supports",
                "source_period": _monthly_period(
                    effective_date="2026-07-01", reference_period="2026-06"
                ),
            },
            "credit_conditions": {
                "status": "risk_rising",
                "source_period": _monthly_period(
                    effective_date="2026-07-01", reference_period="2026-06"
                ),
            },
            "vix_level": {
                "level": 15.0,
                "source_period": _daily_period(),
            },
        },
    }


def _policy_response(m2_status="expanding"):
    return {
        "source_module": "fomc_policy_tone",
        "method_version": "fomc_policy_tone_v1",
        "facts": {
            "macro_policy_response": {
                "relationship_to_growth_direction": "conflicts",
                "source_period": _monthly_period(
                    effective_date="2026-07-01", reference_period="2026-06"
                ),
            },
            "m2_liquidity": {
                "status": m2_status,
                "source_period": _monthly_period(
                    effective_date="2026-07-01", reference_period="2026-06"
                ),
            },
        },
    }


def _market_environment(state="bull_market"):
    return {
        "source_module": "market_phase",
        "method_version": "market_phase_v1",
        "facts": {
            "sp500_market_phase": {
                "phase": state,
                "source_period": _daily_period(),
            }
        },
    }


def _representative_snapshot():
    inputs = {
        "expected_growth": _expected_growth("rising"),
        "market_environment": _market_environment("bull_market"),
        "financial_conditions": _financial_conditions(),
        "policy_response": _policy_response(),
    }
    setup_result = market_setup_v2.build_market_setup_v2(**inputs)
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup_result,
        inputs=inputs,
        evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )
    for fact in evidence:
        if fact["fact_id"] == "sp500_market_phase":
            fact["indicator_id"] = "sp500_close"
    method_contracts = market_setup_v2.build_explanation_method_contracts()
    state = market_setup_explanation_snapshot.build_snapshot_state(
        setup_result=setup_result,
        evidence=evidence,
        method_contracts=method_contracts,
        as_of="2026-08-13",
        evidence_through="2026-08-12",
        input_registry_version="market_setup_input_registry_v1",
        explanation_surface_version="market_assistant_surface_v1",
    )
    return market_setup_explanation_snapshot.finalize_snapshot(
        state, context_id="ctx_setup", created_at="2026-08-13T00:00:00Z"
    )


def full_setup_artifacts():
    snapshot = _representative_snapshot()
    envelopes = [
        snapshot_artifact(snapshot),
        _setup_overview_artifact(snapshot),
        _macro_regime_artifact(snapshot),
        _confirmation_tests_artifact(
            {"test_ids": ["equity", "credit", "vix"]}, snapshot
        ),
        _posture_artifact(snapshot),
        _approved_counterfactuals_artifact(snapshot),
    ]
    return {envelope["artifact_id"]: envelope for envelope in envelopes}


def setup_artifacts():
    snapshot = _representative_snapshot()
    envelopes = [
        _setup_overview_artifact(snapshot),
        _macro_regime_artifact(snapshot),
        _confirmation_tests_artifact(
            {"test_ids": ["equity", "credit", "vix"]}, snapshot
        ),
        _posture_artifact(snapshot),
        _approved_counterfactuals_artifact(snapshot),
    ]
    return {envelope["artifact_id"]: envelope for envelope in envelopes}


def _display_strings(view):
    strings = []

    def walk(value):
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in _DISPLAY_SKIP_KEYS:
                    continue
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(view)
    return strings


def test_setup_view_keeps_required_semantics_and_drops_snapshot_bulk():
    artifacts = full_setup_artifacts()
    original = deepcopy(artifacts)
    view = build_explanation_view(
        current_setup_route(),
        artifacts,
        question="现在市场怎么样？",
    )
    assert view["view_version"] == "setup_explanation_v1"
    assert set(view["results"]) == {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    }
    assert {item["test_id"] for item in view["confirmation_tests"]} == {
        "equity",
        "credit",
        "vix",
    }
    serialized = canonical_json(view)
    assert b"snapshot_hash" not in serialized
    assert b"explanation_fingerprint" not in serialized
    assert b"method_manifest" not in serialized
    assert artifacts == original


def test_setup_view_is_compact_relative_to_full_artifact_projection():
    artifacts = full_setup_artifacts()
    view = build_explanation_view(
        current_setup_route(),
        artifacts,
        question="现在市场怎么样？",
    )
    view_size = len(canonical_json(view))
    full_size = len(canonical_json(artifacts["ctx_setup"]))
    assert view_size < 32 * 1024
    assert view_size < full_size // 4


def test_setup_view_never_exposes_internal_codes_as_display_strings():
    view = build_explanation_view(
        current_setup_route(),
        full_setup_artifacts(),
        question="现在市场怎么样？",
    )
    for value in _display_strings(view):
        assert not _SNAKE_CODE_RE.match(value)
    for code in ("bull_market", "risk_rising", "modest_long", "selective_positions"):
        assert code not in _display_strings(view)


def test_setup_view_audit_refs_resolve_and_keep_authority():
    artifacts = full_setup_artifacts()
    view = build_explanation_view(
        current_setup_route(),
        artifacts,
        question="现在市场怎么样？",
    )
    assert view["audit_objects"]
    for ref in view["audit_objects"]:
        resolved = resolve_artifact_ref(artifacts, ref)
        assert resolved["authority"] in {"decision_fact", "method_knowledge"}
        if resolved["object_type"] == "method_contract":
            assert resolved["authority"] == "method_knowledge"
        else:
            assert resolved["authority"] == "decision_fact"


def vix_route():
    return route_question("VIX 为什么没有确认？", deep_analysis=False)


def _knowledge_envelope(record):
    return {
        "artifact_id": record["record_id"],
        "artifact_kind": "knowledge_record",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "method_knowledge",
        "market_setup_relation": "non_decision",
        "payload": record,
        "object_index": [
            {
                "object_type": record["object_type"],
                "object_id": record["record_id"],
                "authority": "method_knowledge",
                "payload": record,
            }
        ],
        "integrity_hash": "x" * 64,
    }


def vix_knowledge_envelope():
    from app.tools.market_assistant_knowledge import load_knowledge_catalog

    catalog = load_knowledge_catalog()
    record = next(
        item for item in catalog["records"] if item["record_id"] == "vix_definition"
    )
    return _knowledge_envelope(record)


def _vix_exploration_envelope():
    result = {
        "exploration_result_id": "expl_vix",
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
    return {
        "artifact_id": result["exploration_result_id"],
        "artifact_kind": "exploration_result",
        "schema_version": result["artifact_schema_version"],
        "primary_authority": result["authority"],
        "market_setup_relation": result["market_setup_relation"],
        "payload": result,
        "object_index": result["object_index"],
        "integrity_hash": result["result_hash"],
    }


def vix_artifacts():
    snapshot = _representative_snapshot()
    envelopes = [
        snapshot_artifact(snapshot),
        _confirmation_test_artifact({"test_id": "vix"}, snapshot),
        vix_knowledge_envelope(),
        _vix_exploration_envelope(),
    ]
    return {envelope["artifact_id"]: envelope for envelope in envelopes}


def test_vix_indicator_view_keeps_test_and_relevant_objects():
    artifacts = vix_artifacts()
    view = build_explanation_view(
        vix_route(),
        artifacts,
        question="VIX 为什么没有确认？",
    )
    assert view["view_version"] == "indicator_explanation_v1"
    assert view["indicator_id"] == "vix"
    assert {item["test_id"] for item in view["confirmation_tests"]} == {"vix"}
    assert any(ref["object_id"] == "vix_definition" for ref in view["audit_objects"])
    assert any(ref["object_id"] == "vix_history" for ref in view["audit_objects"])
    serialized = canonical_json(view)
    assert b"ism_manufacturing_pmi" not in serialized
    assert b"m2_money_stock" not in serialized
    assert b"m2_liquidity" not in serialized
    assert all(
        ref["object_id"] not in {"survey_growth_direction", "m2_liquidity"}
        for ref in view["audit_objects"]
    )


def method_route():
    return route_question("VIX 怎么计算？", deep_analysis=False)


def method_artifacts():
    from app.tools.market_assistant_knowledge import load_knowledge_catalog

    catalog = load_knowledge_catalog()
    record = next(
        item for item in catalog["records"] if item["record_id"] == "vix_method"
    )
    return {record["record_id"]: _knowledge_envelope(record)}


def test_method_view_contains_approved_knowledge_without_setup_results():
    artifacts = method_artifacts()
    view = build_explanation_view(
        method_route(),
        artifacts,
        question="VIX 怎么计算？",
    )
    assert view["view_version"] == "method_explanation_v1"
    assert view["indicator_id"] == "vix"
    assert view["method_objects"]
    assert view["method_objects"][0]["record_id"] == "vix_method"
    assert all(
        ref["object_type"] != "market_setup_result" for ref in view["audit_objects"]
    )


def react_route():
    return route_question(
        "VIX、信贷和ISM最近的变化彼此有什么关系？",
        deep_analysis=True,
    )


def react_artifacts():
    return full_setup_artifacts()


def test_react_anchor_contains_only_labels_dates_identity_and_budget():
    artifacts = react_artifacts()
    route = react_route()
    view = build_explanation_view(
        route, artifacts, question="VIX、信贷和ISM最近的变化彼此有什么关系？"
    )
    assert view["view_version"] == "react_anchor_v1"
    assert set(view["results"]) == {
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    }
    assert view["context_id"] == "ctx_setup"
    assert view["as_of"] == "2026-08-13"
    assert view["evidence_through"] == "2026-08-12"
    assert view["budget"] == route["budget"]
    assert "results" in view
    for label in view["results"].values():
        assert isinstance(label, str)


def exploration_route():
    return react_route()


def exploration_artifacts():
    return {"expl_vix": _vix_exploration_envelope()}


def test_exploration_view_uses_exploration_artifact_kind():
    view = build_explanation_view(
        exploration_route(),
        exploration_artifacts(),
        question="VIX 最近六个月的走势如何？",
    )
    assert view["view_version"] == "exploration_explanation_v1"
    assert view["indicator_id"] == "vix"
    assert view["rows"] == [{"date": "2026-06-30", "value": 18.4}]


def _comparison_envelope():
    artifact_id = "cmp_ctx_a_ctx_b"
    delta = {
        "results_changed": True,
        "changes": [
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "field_id": "accepted_value",
                "before": 15.0,
                "after": 18.4,
            }
        ],
    }
    return {
        "artifact_id": artifact_id,
        "artifact_kind": "explanation_snapshot",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": {
            "context_a_id": "ctx_a",
            "context_b_id": "ctx_b",
            "delta": delta,
        },
        "object_index": [
            {
                "object_type": "snapshot_delta",
                "object_id": artifact_id,
                "authority": "decision_fact",
                "payload": delta,
            }
        ],
        "integrity_hash": "x" * 64,
    }


def comparison_artifacts():
    envelope = _comparison_envelope()
    return {envelope["artifact_id"]: envelope}


def test_comparison_view_uses_snapshot_delta_object():
    view = build_explanation_view(
        react_route(),
        comparison_artifacts(),
        question="两个快照有什么不同？",
    )
    assert view["view_version"] == "snapshot_comparison_v1"
    assert view["context_a_id"] == "ctx_a"
    assert view["context_b_id"] == "ctx_b"
    assert view["results_changed"] is True
    assert len(view["changes"]) == 1
