import re
from copy import deepcopy

import pytest

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


@pytest.mark.parametrize("view_type", ["setup_explanation", "react_anchor"])
def test_mixed_macro_preserves_available_surveys_and_unevaluated_equity_trend(view_type):
    inputs = {
        "expected_growth": _expected_growth("mixed"),
        "market_environment": _market_environment("bull_market"),
        "financial_conditions": _financial_conditions(),
        "policy_response": _policy_response(),
    }
    survey = inputs["expected_growth"]["facts"]["survey_growth_direction"]
    survey["status"] = "available"
    survey["explanation"] = {
        "economic_direction": "aligned_expansion",
        "growth_momentum": "mixed",
        "reasons": ["Demand momentum differs between surveys"],
    }
    inputs["market_environment"]["facts"]["sp500_market_phase"]["explanation"] = {
        "state": "bull_market"
    }
    inputs["financial_conditions"]["facts"]["vix_level"]["explanation"] = {
        "state": "normal"
    }
    setup = market_setup_v2.build_market_setup_v2(**inputs)
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup, inputs=inputs, evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )
    snapshot = _representative_snapshot()
    snapshot["results"] = {key: setup[key] for key in snapshot["results"]}
    snapshot["evidence"] = evidence
    artifacts = {
        item["artifact_id"]: item
        for item in [snapshot_artifact(snapshot)]
    }
    route = {**current_setup_route(), "view_type": view_type}
    view = build_explanation_view(route, artifacts, question="当前市场如何？")
    if view_type == "react_anchor":
        view = view["decision_evidence"]

    assert view["macro_selector"]["data_status"] == "可用"
    assert view["macro_selector"]["survey_evidence"]["economic_direction"] == "制造业与服务业均扩张"
    assert view["macro_selector"]["survey_evidence"]["reasons"] == ["Demand momentum differs between surveys"]
    assert view["results"]["market_confirmation"]["meaning"] == "未选定上行或下行宏观方向，方向性市场确认尚未执行"
    tests = {item["test_id"]: item for item in view["confirmation_tests"]}
    assert tests["equity"]["value"] == "未达到熊市回撤阈值"
    assert tests["equity"]["data_status"] == "可用"
    assert tests["equity"]["evaluation_state"] == "尚未执行"
    assert tests["equity"]["confirms"] is None
    assert tests["vix"]["value"] == 15.0
    assert tests["vix"]["current_state"] == "正常"
    for relationship in view["relevant_relationships"]:
        if relationship["fact_id"] == "consumer_demand_outlook":
            assert relationship["data_status"] == "数据缺失"
            continue
        assert relationship["data_status"] == "可用"
        assert relationship["participation"] == "未参与"
        assert relationship["relationship"] == "尚未建立与宏观方向的关系"
    assert setup["market_setup"]["code"] == "insufficient_data"


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


@pytest.mark.parametrize(
    ("phase", "label", "drawdown"),
    [("bull_market", "未达到熊市回撤阈值", -4.91), ("bear_market", "已达到熊市回撤阈值", -20.0)],
)
def test_equity_phase_is_presented_as_drawdown_classification(phase, label, drawdown):
    snapshot = _representative_snapshot()
    equity = next(fact for fact in snapshot["evidence"] if fact["fact_id"] == "sp500_market_phase")
    equity["accepted_values"]["phase"] = phase
    equity["explanation"] = {"state": phase, "price_observation": {"drawdown_pct": drawdown}}
    artifact = _confirmation_tests_artifact({"test_ids": ["equity"]}, snapshot)
    view = build_explanation_view(
        current_setup_route(), {artifact["artifact_id"]: artifact}, question="当前市场如何？"
    )
    observation = view["confirmation_tests"][0]

    assert observation["value"] == label
    assert observation["current_state"] == label
    assert observation["price_observation"] == {"drawdown_pct": drawdown}


def mixed_overview_snapshot(vix=19.42):
    inputs = {
        "expected_growth": _expected_growth("mixed"),
        "market_environment": _market_environment(),
        "financial_conditions": _financial_conditions(),
        "policy_response": _policy_response(),
        "consumer_demand": {
            "facts": {"consumer_demand_outlook": {
                "relationship_to_growth_direction": "neutral",
                "source_period": _monthly_period(),
                "explanation": {
                    "state": "transition", "momentum": "improving",
                    "percentile_label": "6th percentile",
                    "reason": "Consumer expectations do not show a clear directional signal",
                },
            }},
        },
    }
    inputs["expected_growth"]["facts"]["survey_growth_direction"]["status"] = "available"
    financial = inputs["financial_conditions"]["facts"]
    financial["vix_level"]["level"] = vix
    financial["macro_financial_conditions"]["explanation"] = {
        "state": "confirms_contraction_risk",
        "reasons": ["Flat curve and widening credit signal contraction risk"],
        "details": {"curve_status": "flat", "ten_year_real_rate": 2.6},
    }
    inputs["policy_response"]["facts"]["macro_policy_response"]["explanation"] = {
        "state": "restrictive_confirmed", "reasons": ["Inflation constrains policy flexibility"],
    }
    setup = market_setup_v2.build_market_setup_v2(**inputs)
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup, inputs=inputs, evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )
    state = market_setup_explanation_snapshot.build_snapshot_state(
        setup_result=setup, evidence=evidence,
        method_contracts=market_setup_v2.build_explanation_method_contracts(),
        as_of="2026-11-09", evidence_through=setup.get("evidence_through"),
        input_registry_version="market_setup_input_registry_v1",
        explanation_surface_version="market_assistant_surface_v1",
    )
    return market_setup_explanation_snapshot.finalize_snapshot(
        state, context_id="ctx_mixed_overview", created_at="2026-11-09T00:00:00Z"
    )


@pytest.mark.parametrize("view_type", ["setup_explanation", "react_anchor"])
@pytest.mark.parametrize("focused", [False, True])
def test_mixed_overview_carries_methods_context_and_triggers(view_type, focused):
    snapshot = mixed_overview_snapshot()
    if focused:
        envelopes = [
            _setup_overview_artifact(snapshot), _macro_regime_artifact(snapshot),
            _confirmation_tests_artifact({"test_ids": ["equity", "credit", "vix"]}, snapshot),
            _approved_counterfactuals_artifact(snapshot),
        ]
    else:
        envelopes = [snapshot_artifact(snapshot)]
    artifacts = {item["artifact_id"]: item for item in envelopes}
    original = deepcopy(snapshot)
    view = build_explanation_view(
        {**current_setup_route(), "view_type": view_type}, artifacts, question="当前市场如何？"
    )
    if view_type == "react_anchor":
        view = view["decision_evidence"]
    vix = next(item for item in view["confirmation_tests"] if item["test_id"] == "vix")

    assert vix["method_conditions"] == [
        {"direction": "上行", "comparison": "低于", "boundary": 20.0, "current_reading_matches": True},
        {"direction": "下行", "comparison": "大于或等于", "boundary": 20.0, "current_reading_matches": False},
    ]
    assert vix["confirms"] is None
    assert vix["evaluation_state"] == "尚未执行"
    contexts = {item["fact_id"]: item for item in view["relevant_relationships"]}
    assert contexts["macro_financial_conditions"]["current_state"] == "金融条件指向收缩风险"
    assert contexts["macro_financial_conditions"]["details"]["curve_status"] == "平坦"
    assert contexts["macro_financial_conditions"]["details"]["ten_year_real_rate"] == 2.6
    assert contexts["macro_policy_response"]["current_state"] == "限制性政策立场"
    assert contexts["consumer_demand_outlook"]["current_state"] == "需求方向尚不明确"
    assert contexts["consumer_demand_outlook"]["details"]["momentum"] == "改善"
    assert contexts["consumer_demand_outlook"]["details"]["percentile_label"] == "6th percentile"
    assert view["counterfactual_status"]["state"] == "暂无适用情景"
    assert view["counterfactuals"] == []
    assert view["next_triggers"] == [{
        "label": "ISM survey direction resolves from mixed", "effect": "recompute Macro Regime"
    }]
    assert snapshot == original


@pytest.mark.parametrize("level", [19.42, 20.0, 20.01, None])
def test_vix_method_is_visible_without_executing_a_directional_confirmation(level):
    snapshot = mixed_overview_snapshot(level)
    artifact = _confirmation_tests_artifact({"test_ids": ["vix"]}, snapshot)
    view = build_explanation_view(current_setup_route(), {artifact["artifact_id"]: artifact}, question="当前市场如何？")
    vix = view["confirmation_tests"][0]

    assert vix["value"] == level
    assert vix["method_conditions"][0]["boundary"] == 20.0
    assert vix["confirms"] is None
    expected_state = "数据无效" if level is None else "可用"
    assert vix["data_status"] == expected_state
    expected_matches = {
        19.42: [True, False], 20.0: [False, True],
        20.01: [False, True], None: [None, None],
    }
    assert [item["current_reading_matches"] for item in vix["method_conditions"]] == expected_matches[level]


def test_vix_method_uses_the_snapshot_boundary_without_a_default_threshold():
    snapshot = mixed_overview_snapshot()
    predicates = snapshot["method_contracts"]["methods"]["vix_confirmation_v2"]["decision_contract"]["predicates"]
    for predicate in predicates.values():
        predicate["predicate"]["operand"] = 27.0
    artifact = _confirmation_tests_artifact({"test_ids": ["vix"]}, snapshot)
    view = build_explanation_view(current_setup_route(), {artifact["artifact_id"]: artifact}, question="当前市场如何？")

    assert [item["boundary"] for item in view["confirmation_tests"][0]["method_conditions"]] == [27.0, 27.0]
    snapshot["method_contracts"]["methods"].pop("vix_confirmation_v2")
    artifact = _confirmation_tests_artifact({"test_ids": ["vix"]}, snapshot)
    view = build_explanation_view(current_setup_route(), {artifact["artifact_id"]: artifact}, question="当前市场如何？")
    assert view["confirmation_tests"][0]["method_conditions"] == []


def test_evaluated_nonconfirming_credit_remains_available_evidence():
    view = build_explanation_view(
        current_setup_route(), full_setup_artifacts(), question="现在市场怎么样？"
    )
    credit = next(item for item in view["confirmation_tests"] if item["test_id"] == "credit")

    assert credit["value"] == "信贷风险正在上升"
    assert credit["data_status"] == "可用"
    assert credit["evaluation_state"] == "已执行"
    assert credit["confirms"] is False
    assert credit["participation"] == "已参与"


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
    assert view["view_version"] == "indicator_explanation_v1"
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


def test_default_setup_view_isolates_detail_only_explanation_values():
    snapshot = _representative_snapshot()
    for fact in snapshot["evidence"]:
        if fact["fact_id"] == "macro_policy_response":
            explanation = fact.setdefault("explanation", {})
            policy_read = explanation.setdefault("policy_read", {})
            policy_read["reason"] = "detail_only_policy_reason_7f21"
            policy_read["policy_action"] = "hold"
            policy_read["overall_bias"] = "mild_hawkish"
        if fact["fact_id"] == "macro_financial_conditions":
            fact.setdefault("explanation", {}).setdefault("details", {})[
                "curve_status"
            ] = "inverted"
        if fact["fact_id"] == "consumer_demand_outlook":
            fact.setdefault("explanation", {})["percentile_zone"] = "elevated"
    artifacts = {
        envelope["artifact_id"]: envelope
        for envelope in [
            snapshot_artifact(snapshot),
            _setup_overview_artifact(snapshot),
            _macro_regime_artifact(snapshot),
            _confirmation_tests_artifact(
                {"test_ids": ["equity", "credit", "vix"]}, snapshot
            ),
            _posture_artifact(snapshot),
            _approved_counterfactuals_artifact(snapshot),
        ]
    }
    view = build_explanation_view(
        current_setup_route(),
        artifacts,
        question="现在市场怎么样？",
    )
    assert view["view_version"] == "setup_explanation_v1"
    serialized = canonical_json(view)
    for forbidden in (
        b"detail_only_policy_reason_7f21",
        b"policy_action",
        b"overall_bias",
        b"percentile_zone",
    ):
        assert forbidden not in serialized
