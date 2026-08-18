import pytest

from app.tools import market_assistant_evidence_detail_registry
from app.tools.market_assistant_evidence_details import project_evidence_detail

DETAIL_TOPICS = market_assistant_evidence_detail_registry.DETAIL_TOPICS


def method_contracts():
    return {
        "version": "market_setup_explanation_methods_v1",
        "methods": {
            "equity_confirmation_v2": _predicate_method(
                "equity_confirmation_v2", "sp500_market_phase", "phase"
            ),
            "credit_confirmation_v2": _predicate_method(
                "credit_confirmation_v2", "credit_conditions", "status"
            ),
            "vix_confirmation_v2": _predicate_method(
                "vix_confirmation_v2", "vix_level", "level"
            ),
            "macro_regime_selector": {
                "method_version": "market_setup_v2_macro_regime_v1",
                "kind": "selector_mapping",
                "decision_contract": {
                    "selector_fact_id": "survey_growth_direction",
                    "direction_to_regime": [],
                },
                "explanation_contract": {},
            },
            "confirmation_aggregation": {
                "method_version": "market_setup_v2_confirmation_v1",
                "kind": "confirmation_aggregation",
                "decision_contract": {"test_count_to_code": {}},
                "explanation_contract": {},
            },
            "setup_matrix": {
                "method_version": "market_setup_v2",
                "kind": "setup_matrix",
                "decision_contract": {"cells": []},
                "explanation_contract": {},
            },
            "posture_matrix": {
                "method_version": "market_setup_v2_posture_v1",
                "kind": "posture_matrix",
                "decision_contract": {"postures": {}},
                "explanation_contract": {},
            },
            "relationship_adapter": {
                "method_version": "market_setup_v2_relationship_v1",
                "kind": "relationship_adapter",
                "decision_contract": {"relationship_values": []},
                "explanation_contract": {},
            },
        },
    }


def _predicate_method(method_id, fact_id, field_id):
    return {
        "method_version": method_id,
        "kind": "predicate_method",
        "decision_contract": {
            "input_contract": {
                "fact_id": fact_id,
                "field_id": field_id,
                "type": "string",
                "unit": None,
            },
            "predicates": {
                "upside": {
                    "predicate_id": "upside",
                    "field_id": field_id,
                    "operator": "in",
                    "operand": [],
                },
                "downside": {
                    "predicate_id": "downside",
                    "field_id": field_id,
                    "operator": "in",
                    "operand": [],
                },
            },
        },
        "explanation_contract": {},
    }


def _fact(
    fact_id,
    label,
    accepted_values,
    explanation,
    *,
    provenance=None,
    status="available",
):
    return {
        "fact_id": fact_id,
        "indicator_id": fact_id,
        "label": label,
        "accepted_values": dict(accepted_values),
        "classifications": {},
        "role": {
            "decision_scope": "decision_input",
            "function": "contextual_relationship",
            "target_layer": "macro_regime",
            "allowed_effects": ["supports", "conflicts"],
        },
        "data_status": {"state": status},
        "participation": {"state": "applied"},
        "decision_result": {"kind": "relationship", "relationship": "conflicts"},
        "provenance": provenance
        or {
            "source_module": "source",
            "source_id": fact_id,
            "method_references": [],
        },
        "finding": {"state": "applied"},
        "explanation": dict(explanation),
    }


def _record(fact_id, scope, detail_kind, topics, source_module, projection_version):
    return {
        "fact_id": fact_id,
        "scope": scope,
        "detail_kind": detail_kind,
        "supported_topics": list(topics),
        "default_topics": list(topics),
        "aliases": [fact_id],
        "source_module": source_module,
        "projection_version": projection_version,
    }


def policy_fact():
    return _fact(
        "macro_policy_response",
        "Monetary Policy",
        {"relationship_to_growth_direction": "conflicts"},
        {
            "state": "restrictive_confirmed",
            "reasons": ["Fed policy remains restrictive with inflation above target"],
            "details": {
                "fomc_tone": "hawkish",
                "fomc_action": "hold",
                "m2_status": "expanding",
                "inflation_above_target": True,
                "fed_balance_sheet_available": True,
            },
            "policy_read": {
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "tone_change": "more_hawkish",
                "confidence": "high",
                "reason": "Hold decision with hawkish inflation language.",
            },
        },
        provenance={
            "source_module": "fomc_policy_tone",
            "source_id": "macro_policy_response",
            "source_period": {
                "effective_date": "2026-07-28",
                "reference_period": "2026-07",
                "release_date": None,
            },
            "method_references": ["fomc_policy_tone_v1"],
        },
    )


def policy_record():
    return _record(
        "macro_policy_response",
        "decision_input",
        "policy_response",
        ("current", "drivers", "source"),
        "fomc_policy_tone",
        "market_assistant_policy_response_detail_v1",
    )


def survey_fact():
    return _fact(
        "survey_growth_direction",
        "ISM Survey Synthesis Direction",
        {"direction": "rising", "status": "available"},
        {
            "economic_direction": "aligned_expansion",
            "growth_momentum": "rising",
            "survey_alignment": "aligned",
            "demand_alignment": "aligned_rising",
            "leading_side": "manufacturing",
            "cross_sector_comparison": "both_expanding",
            "bias_confirmation": "confirmed",
            "backlog_confirmation": "growing",
            "agreements": ["Manufacturing and Services are both expanding"],
            "conflicts": [],
            "missing_inputs": [],
            "reasons": ["Business surveys indicate broad expansion"],
        },
        provenance={
            "source_module": "ism_survey_synthesis",
            "source_id": "survey_growth_direction",
            "source_period": {
                "effective_date": "2026-06-01",
                "reference_period": "2026-06",
                "release_date": None,
            },
            "method_references": ["ism_survey_synthesis_v1"],
        },
    )


def survey_record():
    return _record(
        "survey_growth_direction",
        "decision_input",
        "survey_synthesis",
        ("current", "drivers", "source"),
        "ism_survey_synthesis",
        "market_assistant_survey_synthesis_detail_v1",
    )


def financial_fact():
    return _fact(
        "macro_financial_conditions",
        "Financial Conditions",
        {"relationship_to_growth_direction": "conflicts"},
        {
            "state": "confirms_contraction_risk",
            "growth_confirmation": "not_confirmed",
            "reasons": ["Yield curve is inverted (10Y-2Y spread is negative)"],
            "details": {
                "curve_status": "inverted",
                "credit_conditions_status": "stress",
                "vix": 30.0,
                "ten_year_real_rate": 1.2,
            },
        },
        provenance={
            "source_module": "us_rates_liquidity",
            "source_id": "macro_financial_conditions",
            "source_period": {
                "effective_date": "2026-06-01",
                "observation_date": "2026-06-01",
            },
            "method_references": ["us_rates_liquidity_v1"],
        },
    )


def financial_record():
    return _record(
        "macro_financial_conditions",
        "decision_input",
        "financial_conditions",
        ("current", "drivers", "source"),
        "us_rates_liquidity",
        "market_assistant_financial_conditions_detail_v1",
    )


def consumer_fact():
    return _fact(
        "consumer_demand_outlook",
        "Consumer Demand Outlook",
        {"relationship_to_growth_direction": "supports"},
        {
            "state": "confirms_expansion",
            "direction": "expansion",
            "reason": "Expectations percentile remains elevated and improving",
            "percentile_zone": "elevated",
            "momentum": "improving",
            "percentile_label": "91st percentile",
            "confirmation_state": "broadly_confirmed",
        },
        provenance={
            "source_module": "consumer_sentiment",
            "source_id": "consumer_demand_outlook",
            "source_period": {
                "effective_date": "2026-06-01",
                "reference_period": "2026-06",
                "release_date": None,
            },
            "method_references": ["market_setup_v2_consumer_demand_v1"],
        },
    )


def consumer_record():
    return _record(
        "consumer_demand_outlook",
        "confirmation_input",
        "consumer_demand",
        ("current", "drivers", "source"),
        "consumer_sentiment",
        "market_assistant_consumer_demand_detail_v1",
    )


def market_phase_fact():
    return _fact(
        "sp500_market_phase",
        "S&P 500 Market Phase",
        {"phase": "bull_market"},
        {
            "state": "bull_market",
            "starting_posture": "long",
            "reason": "S&P 500 is in a bull market phase; starting posture is long-biased",
        },
        provenance={
            "source_module": "market_phase",
            "source_id": "sp500_market_phase",
            "source_period": {
                "effective_date": "2026-06-01",
                "observation_date": "2026-06-01",
            },
            "method_references": ["market_phase_v1"],
        },
    )


def market_phase_record():
    return _record(
        "sp500_market_phase",
        "confirmation_input",
        "market_phase",
        ("current", "method", "source"),
        "market_phase",
        "market_assistant_market_phase_detail_v1",
    )


def credit_fact():
    return _fact(
        "credit_conditions",
        "Credit Conditions",
        {"status": "stress"},
        {"status": "stress"},
        provenance={
            "source_module": "us_rates_liquidity",
            "source_id": "credit_conditions",
            "source_period": {
                "effective_date": "2026-06-01",
                "observation_date": "2026-06-01",
            },
            "method_references": ["us_rates_liquidity_v1"],
        },
    )


def credit_record():
    return _record(
        "credit_conditions",
        "confirmation_input",
        "credit_conditions",
        ("current", "method", "source"),
        "us_rates_liquidity",
        "market_assistant_credit_conditions_detail_v1",
    )


def vix_fact():
    return _fact(
        "vix_level",
        "VIX",
        {"level": 30.0},
        {"level": 30.0},
        provenance={
            "source_module": "us_rates_liquidity",
            "source_id": "vix_level",
            "source_period": {
                "effective_date": "2026-06-01",
                "observation_date": "2026-06-01",
            },
            "method_references": ["us_rates_liquidity_v1"],
        },
    )


def vix_record():
    return _record(
        "vix_level",
        "confirmation_input",
        "vix",
        ("current", "method", "source"),
        "us_rates_liquidity",
        "market_assistant_vix_detail_v1",
    )


def m2_fact():
    return _fact(
        "m2_liquidity",
        "M2 Liquidity",
        {"status": "expanding"},
        {"status": "expanding", "status_label": "Expanding"},
        provenance={
            "source_module": "m2_money_supply",
            "source_id": "m2_liquidity",
            "source_period": {
                "effective_date": "2026-06-01",
                "reference_period": "2026-06",
                "release_date": None,
            },
            "method_references": ["m2_money_supply_v1"],
        },
    )


def m2_record():
    return _record(
        "m2_liquidity",
        "context_only",
        "m2_liquidity",
        ("current", "method", "source"),
        "m2_money_supply",
        "market_assistant_m2_liquidity_detail_v1",
    )


def equity_breadth_fact():
    return {
        "fact_id": "equity_breadth",
        "indicator_id": "equity_breadth",
        "label": "Equity Breadth",
        "accepted_values": {},
        "classifications": {},
        "role": {
            "decision_scope": "observation_only",
            "function": "watch_only",
            "target_layer": None,
            "allowed_effects": [],
        },
        "data_status": {"state": "missing"},
        "participation": {"state": "not_applied", "reason_code": "data_missing"},
        "decision_result": {"kind": "none"},
        "provenance": {
            "source_module": "observation_only",
            "source_id": "equity_breadth",
            "method_references": [],
        },
        "finding": {"state": "not_applied", "reason_code": "watch_only"},
        "explanation": {},
    }


def unsupported_record():
    return _record(
        "equity_breadth",
        "observation_only",
        "unsupported",
        (),
        "observation_only",
        "market_assistant_evidence_detail_unsupported_v1",
    )


def _stale_fact():
    fact = policy_fact()
    fact["data_status"] = {"state": "stale"}
    fact["participation"] = {"state": "not_applied", "reason_code": "data_stale"}
    fact["finding"] = {"state": "not_applied", "reason_code": "data_stale"}
    return fact


def _invalid_fact():
    fact = policy_fact()
    fact["data_status"] = {"state": "invalid"}
    fact["participation"] = {"state": "not_applied", "reason_code": "data_invalid"}
    fact["finding"] = {"state": "not_applied", "reason_code": "data_invalid"}
    return fact


def test_policy_projection_returns_only_requested_topics():
    result = project_evidence_detail(
        policy_fact(), policy_record(), ["current", "drivers"], method_contracts()
    )
    assert result["status"] == "available"
    assert result["current"]["policy_action"] == "hold"
    assert result["current"]["overall_bias"] == "mild_hawkish"
    assert result["current"]["relationship_to_growth_direction"] == "conflicts"
    assert result["drivers"]["policy_reason"]
    assert "source" not in result
    assert "method" not in result


def test_disabled_fact_returns_governed_unsupported_result():
    result = project_evidence_detail(
        equity_breadth_fact(), unsupported_record(), ["current"], method_contracts()
    )
    assert result["fact_id"] == "equity_breadth"
    assert result["status"] == "unsupported"
    assert result["supported_topics"] == []


_ENABLED_CASES = (
    (
        "survey_growth_direction",
        "survey_synthesis",
        survey_fact,
        survey_record,
        ("current", "drivers", "source"),
    ),
    (
        "macro_financial_conditions",
        "financial_conditions",
        financial_fact,
        financial_record,
        ("current", "drivers", "source"),
    ),
    (
        "macro_policy_response",
        "policy_response",
        policy_fact,
        policy_record,
        ("current", "drivers", "source"),
    ),
    (
        "consumer_demand_outlook",
        "consumer_demand",
        consumer_fact,
        consumer_record,
        ("current", "drivers", "source"),
    ),
    (
        "sp500_market_phase",
        "market_phase",
        market_phase_fact,
        market_phase_record,
        ("current", "method", "source"),
    ),
    (
        "credit_conditions",
        "credit_conditions",
        credit_fact,
        credit_record,
        ("current", "method", "source"),
    ),
    (
        "vix_level",
        "vix",
        vix_fact,
        vix_record,
        ("current", "method", "source"),
    ),
    (
        "m2_liquidity",
        "m2_liquidity",
        m2_fact,
        m2_record,
        ("current", "method", "source"),
    ),
)


@pytest.mark.parametrize(
    ("fact_id", "detail_kind", "fact", "record", "supported_topics"),
    [
        (fact_id, detail_kind, fact_builder(), record_builder(), list(topics))
        for fact_id, detail_kind, fact_builder, record_builder, topics in _ENABLED_CASES
    ],
)
def test_enabled_fact_projects_requested_supported_topics(
    fact_id, detail_kind, fact, record, supported_topics
):
    result = project_evidence_detail(fact, record, supported_topics, method_contracts())
    assert result["fact_id"] == fact_id
    assert result["label"] == fact["label"]
    assert result["detail_kind"] == detail_kind
    assert result["topics"] == supported_topics
    assert result["status"] == "available"
    for topic in supported_topics:
        assert topic in result
        assert isinstance(result[topic], dict)
    for topic in DETAIL_TOPICS:
        if topic not in supported_topics:
            assert topic not in result


@pytest.mark.parametrize(
    ("fact", "expected_status"),
    [
        (None, "missing"),
        (_stale_fact(), "stale"),
        (_invalid_fact(), "invalid"),
    ],
)
def test_non_available_fact_returns_governed_status(fact, expected_status):
    result = project_evidence_detail(
        fact, policy_record(), ["current", "source"], method_contracts()
    )
    assert result["status"] == expected_status
    assert result["detail_kind"] == "policy_response"
    assert result["topics"] == ["current", "source"]
    assert "current" not in result
    if fact is None:
        assert "source" not in result
    else:
        assert set(result["source"].keys()) <= {
            "source_module",
            "source_id",
            "source_period",
            "method_references",
        }


def test_stale_fact_retains_snapshot_source_period_and_reason():
    fact = _stale_fact()
    result = project_evidence_detail(
        fact, policy_record(), ["source"], method_contracts()
    )
    assert result["status"] == "stale"
    assert result["reason"] == "data_stale"
    assert result["source"]["source_period"] == fact["provenance"]["source_period"]


def test_invalid_fact_returns_invalid_without_replacement_value():
    result = project_evidence_detail(
        _invalid_fact(), policy_record(), ["current"], method_contracts()
    )
    assert result["status"] == "invalid"
    assert "current" not in result
    assert result["reason"] == "data_invalid"


def test_policy_current_is_bounded_not_full_explanation():
    result = project_evidence_detail(
        policy_fact(), policy_record(), ["current", "drivers"], method_contracts()
    )
    assert set(result["current"].keys()) == {
        "policy_action",
        "overall_bias",
        "guidance_bias",
        "language_tone",
        "tone_change",
        "confidence",
        "state",
        "relationship_to_growth_direction",
        "details",
    }
    assert set(result["drivers"].keys()) == {"policy_reason", "reasons"}
    assert result["current"]["details"] == policy_fact()["explanation"]["details"]


def test_source_contains_only_snapshot_provenance():
    result = project_evidence_detail(
        market_phase_fact(), market_phase_record(), ["source"], method_contracts()
    )
    source = result["source"]
    assert set(source.keys()) == {
        "source_module",
        "source_id",
        "source_period",
        "method_references",
    }
    assert source["source_module"] == "market_phase"
    assert source["method_references"] == ["market_phase_v1"]
    assert source["source_period"] == market_phase_fact()["provenance"]["source_period"]


def test_method_contains_only_matching_approved_contract():
    result = project_evidence_detail(
        credit_fact(), credit_record(), ["method"], method_contracts()
    )
    method = result["method"]
    assert method["method_references"] == ["us_rates_liquidity_v1"]
    contracts = method["method_contracts"]
    assert [contract["method_id"] for contract in contracts] == [
        "credit_confirmation_v2"
    ]
    for contract in contracts:
        assert (
            contract["decision_contract"]["input_contract"]["fact_id"]
            == "credit_conditions"
        )


def test_m2_method_returns_references_without_invented_contract():
    result = project_evidence_detail(
        m2_fact(), m2_record(), ["method"], method_contracts()
    )
    assert result["status"] == "available"
    assert result["method"]["method_references"] == ["m2_money_supply_v1"]
    assert "method_contracts" not in result["method"]


def test_project_evidence_detail_rejects_unknown_topic():
    with pytest.raises(ValueError, match="topic is unknown"):
        project_evidence_detail(
            policy_fact(), policy_record(), ["bogus"], method_contracts()
        )


def test_project_evidence_detail_rejects_duplicate_topics():
    with pytest.raises(ValueError, match="topics are duplicated"):
        project_evidence_detail(
            policy_fact(), policy_record(), ["current", "current"], method_contracts()
        )


def test_project_evidence_detail_rejects_empty_topics():
    with pytest.raises(ValueError, match="topics are required"):
        project_evidence_detail(policy_fact(), policy_record(), [], method_contracts())


def test_project_evidence_detail_rejects_invalid_record():
    with pytest.raises(ValueError, match="record is required"):
        project_evidence_detail(policy_fact(), None, ["current"], method_contracts())


def test_project_evidence_detail_rejects_record_without_detail_kind():
    record = dict(policy_record())
    del record["detail_kind"]
    with pytest.raises(ValueError, match="detail kind is required"):
        project_evidence_detail(policy_fact(), record, ["current"], method_contracts())


def test_enabled_fact_with_unsupported_topic_returns_unsupported():
    result = project_evidence_detail(
        policy_fact(), policy_record(), ["method"], method_contracts()
    )
    assert result["status"] == "unsupported"
    assert result["supported_topics"] == ["current", "drivers", "source"]
    assert "current" not in result


def test_enabled_fact_with_partially_supported_topics_returns_unsupported():
    result = project_evidence_detail(
        policy_fact(), policy_record(), ["current", "method"], method_contracts()
    )
    assert result["status"] == "unsupported"
    assert result["supported_topics"] == ["current", "drivers", "source"]
    assert "current" not in result
