import json
import re

from app.tools import market_setup_evidence_layers


def _market_setup_result():
    return {
        "version": "market_setup_v2",
        "macro_regime": {
            "code": "growth_decelerating",
            "label": "Growth Decelerating",
        },
        "market_confirmation": {
            "code": "partially_confirming_downside",
            "label": "Downside Partially Confirmed",
            "confirmation_test_count": 1,
            "evidence": {
                "equity_trend": {
                    "state": "bull_market",
                    "confirms": False,
                    "finding": "S&P 500 market phase does not confirm the directional regime",
                },
                "credit": {
                    "state": "risk_rising",
                    "confirms": True,
                    "finding": "credit conditions confirm the directional regime",
                },
                "volatility": {
                    "state": "normal",
                    "confirms": False,
                    "finding": "volatility does not confirm the directional regime",
                },
                "liquidity": {
                    "state": "expanding",
                    "confirms": True,
                    "finding": "M2 money supply is supportive of liquidity",
                },
            },
            "offsets": [
                {
                    "id": "m2_liquidity_support",
                    "finding": "M2 money supply is expanding or in shock, providing liquidity support",
                    "evidence_links": ["m2_money_supply"],
                }
            ],
        },
        "market_setup": {
            "code": "macro_weakening_partially_confirmed",
            "label": "Macro Weakening, Partially Confirmed",
            "agreement": "mixed",
        },
        "portfolio_posture": {
            "code": "mild_risk_off",
            "label": "Mild Risk-Off",
            "net_exposure": "modest_defensive",
            "gross_exposure": "moderate",
            "implementation": "selective_defensive_positions",
            "broad_beta": "reduce_large_directional_exposure",
            "positioning": [
                {
                    "code": "maintain_modest_defensive_exposure",
                    "label": "Maintain modest defensive exposure",
                },
                {
                    "code": "use_moderate_position_sizing",
                    "label": "Use moderate position sizing",
                },
            ],
            "avoid": [
                {
                    "code": "large_directional_long_exposure",
                    "label": "Large directional long exposure",
                },
            ],
        },
        "next_triggers": [
            {
                "id": "vix_stress_threshold",
                "label": "VIX crosses the approved confirmation threshold from normal",
            },
        ],
        "watch_items": [
            {"id": "jobless_claims", "label": "Jobless claims"},
        ],
        "excluded_inputs": ["consumer_demand_outlook"],
        "method_versions": {
            "macro_regime": "market_setup_v2_macro_regime_v1",
            "market_confirmation": "market_setup_v2_market_confirmation_v1",
            "market_setup": "market_setup_v2",
            "portfolio_posture": "market_setup_v2_portfolio_posture_v1",
        },
    }


def _survey_synthesis():
    return {
        "version": "ism_survey_synthesis_v1",
        "status": "available",
        "period": "2026-06",
        "economic_direction": "aligned_expansion",
        "growth_momentum": "falling",
        "survey_alignment": "aligned",
        "expected_gdp_direction": "slowing",
        "components": {
            "manufacturing": {"status": "available", "level": "expanding"},
            "services": {"status": "available", "level": "expanding"},
        },
        "reasons": ["Business surveys indicate broad expansion"],
    }


def _expected_growth():
    return {
        "source_module": "ism_survey_synthesis",
        "method_version": "ism_survey_synthesis_v1",
        "facts": {
            "survey_growth_direction": {
                "direction": "slowing",
                "status": "available",
                "source_period": {
                    "effective_date": "2026-06-30",
                    "reference_period": "2026-06",
                },
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
                "source_period": {"effective_date": "2026-07-26"},
            },
            "credit_conditions": {
                "status": "risk_rising",
                "source_period": {"effective_date": "2026-07-26"},
            },
            "vix_level": {
                "level": 16.5,
                "source_period": {"effective_date": "2026-07-26"},
            },
        },
    }


def _policy_response():
    return {
        "source_module": "fomc_policy_tone",
        "method_version": "fomc_policy_tone_v1",
        "facts": {
            "macro_policy_response": {
                "relationship_to_growth_direction": "conflicts",
                "source_period": {"reference_period": "2026-06"},
            },
            "m2_liquidity": {
                "status": "expanding",
                "source_period": {"reference_period": "2026-06"},
            },
        },
    }


def _consumer_demand():
    return {
        "source_module": "consumer_sentiment",
        "method_version": "market_setup_v2_consumer_demand_v1",
        "facts": {
            "consumer_demand_outlook": {
                "relationship_to_growth_direction": "neutral",
                "source_period": {"reference_period": "2026-06"},
            }
        },
    }


def _claims_trend(classification="stable"):
    return {
        "classification": classification,
        "observation_period": "2026-07-25",
        "latest_4w_mean": 240000.0,
        "comparison_4w_mean": 238000.0,
        "change_pct": 0.008,
    }


def _snapshot(series_id, value, reference_period="2026-06"):
    return {
        "series_id": series_id,
        "reference_period": reference_period,
        "value": value,
        "value_at_release": value,
        "latest_revised_value": value,
        "revision_number": 0,
        "release_date": "2026-07-02",
        "source_url": "https://example.test/source",
    }


def _economic_confirmation_overview():
    return {
        "claims_confirmation": {
            "initial_claims": _claims_trend(),
            "continuing_claims": _claims_trend(),
            "claims_direction": "stable",
            "confirmation_status": "not_confirming",
            "explanation": (
                "Claims are stable, neither supporting nor conflicting with "
                "the decelerating growth thesis"
            ),
            "method_version": "claims_confirmation_v1.0",
        },
        "labor_context": {
            "role": "context_only",
            "method_status": "pending_approval",
            "unavailable_reason": "method_not_approved",
            "data_status": "available",
            "metrics": {
                "nonfarm_payrolls_change": _snapshot("nonfarm_payrolls_change", 147.0),
                "unemployment_rate": _snapshot("unemployment_rate", 4.1),
            },
        },
        "real_activity": {
            "data_status": "available",
            "method_status": "pending_approval",
            "metrics": {
                "manufacturing_production": _snapshot("manufacturing_production", 97.9),
                "total_industrial_production": _snapshot(
                    "total_industrial_production", 103.2
                ),
                "capacity_utilization": _snapshot("capacity_utilization", 77.4),
            },
        },
    }


def _gdp_rows():
    return [
        {
            "date": "2026-03-31",
            "period_label": "2026 Q1",
            "gdp_level": 23500.0,
            "gdp_direction": 1,
            "quad_case": "gdp_rising",
        },
        {
            "date": "2026-06-30",
            "period_label": "2026 Q2",
            "gdp_level": 23400.0,
            "gdp_direction": -1,
            "quad_case": "gdp_falling",
        },
    ]


def _full_kwargs():
    return {
        "market_setup_result": _market_setup_result(),
        "survey_synthesis": _survey_synthesis(),
        "expected_growth": _expected_growth(),
        "financial_conditions": _financial_conditions(),
        "policy_response": _policy_response(),
        "consumer_demand": _consumer_demand(),
        "economic_confirmation_overview": _economic_confirmation_overview(),
        "gdp_rows": _gdp_rows(),
    }


def _groups(layer):
    return {group["id"]: group for group in layer["groups"]}


def _downside_case_kwargs():
    return {
        "market_setup_result": _market_setup_result(),
        "survey_synthesis": _survey_synthesis(),
        "expected_growth": _expected_growth(),
        "financial_conditions": _financial_conditions(),
        "policy_response": _policy_response(),
        "consumer_demand": _consumer_demand(),
        "economic_confirmation_overview": _economic_confirmation_overview(),
        "gdp_rows": _gdp_rows(),
    }


def leading_expectations_layer_for_downside_case():
    layers = market_setup_evidence_layers.build_evidence_layers(
        **_downside_case_kwargs()
    )
    return layers["leading_expectations"]


def market_pricing_layer_for_downside_case():
    layers = market_setup_evidence_layers.build_evidence_layers(
        **_downside_case_kwargs()
    )
    return layers["market_pricing"]


def evidence_layers_for_downside_case():
    return market_setup_evidence_layers.build_evidence_layers(**_downside_case_kwargs())


def group_by_id(groups, group_id):
    return next(group for group in groups if group["id"] == group_id)


def economic_reality_layer_with_available_activity_data():
    layers = market_setup_evidence_layers.build_evidence_layers(
        **_downside_case_kwargs()
    )
    return layers["economic_reality"]


def labor_group_with_claims_and_esr_data():
    layers = market_setup_evidence_layers.build_evidence_layers(
        **_downside_case_kwargs()
    )
    return _groups(layers["economic_reality"])["labor"]


# Keys whose values are internal codes/coloring fields, not user-facing copy.
_CODE_KEYS = {
    "version",
    "role",
    "group_role",
    "sentiment",
    "posture_code",
    "method_versions",
    "excluded_inputs",
    "kind",
}

_RAW_CODE_PATTERN = re.compile(r"[a-z]+_[a-z_]+")


def _iter_strings(node, key=None):
    if isinstance(node, dict):
        for child_key, value in node.items():
            if _is_code_key(child_key):
                continue
            yield from _iter_strings(value, key=child_key)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_strings(value, key=key)
    elif isinstance(node, str):
        yield key, node


def _is_code_key(key):
    if key is None:
        return False
    return key in _CODE_KEYS or key == "id" or key.endswith("_id")


def test_evidence_layers_separate_decision_path_from_supplementary_context():
    layers = market_setup_evidence_layers.build_evidence_layers(
        market_setup_result=_market_setup_result(),
        survey_synthesis=_survey_synthesis(),
        expected_growth=_expected_growth(),
        financial_conditions=_financial_conditions(),
        policy_response=_policy_response(),
        consumer_demand=_consumer_demand(),
    )

    assert [step["kind"] for step in layers["decision_path"]["steps"]] == [
        "macro_thesis",
        "market_test",
        "relationship",
        "action",
    ]
    assert layers["economic_reality"]["role"] == "supplementary"
    assert layers["final_confirmation"]["role"] == "review_only"


def test_full_inputs_build_the_v2_contract():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())

    assert layers["version"] == "market_setup_evidence_layers_v2"
    assert "do not participate" in layers["boundary_note"]
    assert set(layers) == {
        "version",
        "boundary_note",
        "decision_path",
        "leading_expectations",
        "market_pricing",
        "portfolio_conclusion",
        "economic_reality",
        "final_confirmation",
    }

    leading = layers["leading_expectations"]
    assert leading["layer_id"] == "leading_expectations"
    assert leading["title"] == "Leading Expectations"
    assert leading["role"] == "decision_input"
    assert [group["id"] for group in leading["groups"]] == [
        "growth_surveys",
        "financial_conditions",
        "monetary_policy",
        "consumer_demand",
    ]

    reality = layers["economic_reality"]
    assert reality["title"] == "Economic Reality Check"
    assert reality["role"] == "supplementary"
    assert [group["id"] for group in reality["groups"]] == ["labor", "real_activity"]

    final = layers["final_confirmation"]
    assert final["role"] == "review_only"
    assert [group["id"] for group in final["groups"]] == ["economic_output"]


def test_decision_path_maps_the_four_steps():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    steps = layers["decision_path"]["steps"]
    assert [step["n"] for step in steps] == [1, 2, 3, 4]
    assert [step["kind"] for step in steps] == [
        "macro_thesis",
        "market_test",
        "relationship",
        "action",
    ]

    step1 = steps[0]
    assert step1["input"] == {"label": "ISM survey direction", "value": "Slowing"}
    assert step1["output"] == {
        "label": "Growth Decelerating",
        "sentiment": "growth_decelerating",
    }

    step2 = steps[1]
    assert [test["id"] for test in step2["tests"]] == [
        "equity_trend",
        "credit",
        "volatility",
    ]
    credit = step2["tests"][1]
    assert credit["label"] == "Credit Conditions"
    assert credit["state_label"] == "Risk Rising"
    assert credit["sentiment"] == "risk_rising"
    assert credit["passed"] is True
    assert credit["verdict_label"] == "Confirms downside"
    assert credit["finding"] == "credit conditions confirm the directional regime"
    equity = step2["tests"][0]
    assert equity["label"] == "S&P 500 Trend"
    assert equity["state_label"] == "Bull Market"
    assert equity["passed"] is False
    assert equity["verdict_label"] == "Does not confirm"
    volatility = step2["tests"][2]
    assert volatility["state_label"] == "Normal"
    assert volatility["verdict_label"] == "Does not confirm"
    assert step2["passed_count"] == 1
    assert step2["total"] == 3
    assert step2["output"] == {
        "label": "Downside Partially Confirmed",
        "sentiment": "partially_confirming_downside",
    }

    step3 = steps[2]
    assert step3["inputs"] == ["Growth Decelerating", "Downside Partially Confirmed"]
    assert step3["output"] == {
        "label": "Macro Weakening, Partially Confirmed",
        "sentiment": "macro_weakening_partially_confirmed",
        "agreement": "Mixed",
    }

    step4 = steps[3]
    assert step4["output"]["label"] == "Mild Risk-Off"
    assert step4["output"]["sentiment"] == "mild_risk_off"
    assert step4["output"]["fields"] == [
        {"label": "Net exposure", "value": "Modest defensive"},
        {"label": "Gross exposure", "value": "Moderate"},
        {"label": "Implementation", "value": "Selective defensive positions"},
        {"label": "Broad beta", "value": "Reduce large directional exposure"},
    ]


def test_decision_path_degrades_when_test_count_is_none():
    result = _market_setup_result()
    result["market_confirmation"] = {
        "code": "not_applicable",
        "label": "Confirmation Pending a Directional Regime",
        "confirmation_test_count": None,
        "evidence": {},
        "offsets": [],
    }
    layers = market_setup_evidence_layers.build_evidence_layers(
        market_setup_result=result
    )
    step2 = layers["decision_path"]["steps"][1]
    assert step2["passed_count"] is None
    assert step2["total"] is None
    assert step2["tests"] == []
    assert step2["missing_inputs"] == []
    assert step2["output"]["label"] == "Confirmation Pending a Directional Regime"

    pricing = layers["market_pricing"]
    assert pricing["tests_passed"] is None
    assert pricing["tests_total"] is None
    assert pricing["tests_summary"] is None
    assert pricing["tests"] == []
    assert pricing["status_label"] == "Confirmation Pending a Directional Regime"
    assert pricing["missing_inputs"] == []


def test_insufficient_confirmation_does_not_render_fake_test_votes():
    result = _market_setup_result()
    result["market_confirmation"] = {
        "code": "insufficient_data",
        "label": "Insufficient Market Confirmation Evidence",
        "confirmation_test_count": None,
        "evidence": {},
        "offsets": [],
        "missing_inputs": ["S&P 500 market phase", "credit conditions"],
    }
    layers = market_setup_evidence_layers.build_evidence_layers(
        market_setup_result=result
    )
    step2 = layers["decision_path"]["steps"][1]
    assert step2["tests"] == []
    assert step2["passed_count"] is None
    assert step2["total"] is None
    assert step2["missing_inputs"] == ["S&P 500 market phase", "credit conditions"]
    assert step2["output"]["label"] == "Insufficient Market Confirmation Evidence"

    pricing = layers["market_pricing"]
    assert pricing["tests"] == []
    assert pricing["tests_passed"] is None
    assert pricing["tests_total"] is None
    assert pricing["tests_summary"] is None
    assert pricing["status_label"] == "Insufficient Market Confirmation Evidence"
    assert pricing["missing_inputs"] == ["S&P 500 market phase", "credit conditions"]


def test_directional_confirmation_still_exposes_three_tests():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    step2 = layers["decision_path"]["steps"][1]
    assert [test["id"] for test in step2["tests"]] == [
        "equity_trend",
        "credit",
        "volatility",
    ]
    assert step2["passed_count"] == 1
    assert step2["missing_inputs"] == []
    assert layers["market_pricing"]["tests_passed"] == 1
    assert layers["market_pricing"]["tests_total"] == 3
    assert layers["market_pricing"]["status_label"] is None


def test_confirmation_test_verdicts_follow_thesis_direction():
    result = _market_setup_result()
    result["market_confirmation"] = {
        "code": "partially_confirming_upside",
        "label": "Upside Partially Confirmed",
        "confirmation_test_count": 2,
        "evidence": {
            "equity_trend": {"state": "bull_market", "confirms": True},
            "credit": {"state": "stable", "confirms": True},
            "volatility": {"state": "normal", "confirms": False},
        },
        "offsets": [],
    }
    layers = market_setup_evidence_layers.build_evidence_layers(
        market_setup_result=result
    )
    step2 = layers["decision_path"]["steps"][1]
    assert [test["verdict_label"] for test in step2["tests"]] == [
        "Confirms upside",
        "Confirms upside",
        "Does not confirm",
    ]


def test_excluded_inputs_use_display_labels_not_fact_ids():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())

    assert layers["portfolio_conclusion"]["excluded_inputs"] == [
        "Consumer Demand Outlook"
    ]
    assert all(
        "_" not in label for label in layers["portfolio_conclusion"]["excluded_inputs"]
    )


def test_leading_expectations_group_roles_and_fields():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    groups = _groups(layers["leading_expectations"])

    surveys = groups["growth_surveys"]
    assert surveys["group_role"] == "regime_selector"
    assert surveys["group_role_label"] == "Regime Selector"
    assert surveys["current_state"] == "Expansion slowing"
    assert surveys["sentiment"] == "slowing"
    assert surveys["relationship"] is None
    assert surveys["decision_effect"] == "Selects Growth Decelerating"
    assert surveys["period"] == "2026-06"
    assert surveys["interpretation"] == (
        "Surveys still show expansion, but the expected growth rate is decelerating."
    )
    assert surveys["data_status"] == "available"
    metrics = {
        metric["label"]: metric["value"] for metric in surveys["details_metrics"]
    }
    assert metrics == {
        "Current Level": "Broad expansion",
        "Direction": "Slowing",
        "Momentum": "Falling",
    }

    financial = groups["financial_conditions"]
    assert financial["group_role"] == "supporting_evidence"
    assert financial["group_role_label"] == "Supporting Evidence"
    assert financial["current_state"] == "Supports the survey growth direction"
    assert financial["relationship"] == "supports"
    assert financial["decision_effect"] == "Supporting evidence only"
    assert financial["period"] == "2026-07-26"

    policy = groups["monetary_policy"]
    assert policy["title"] == "Monetary Policy"
    assert policy["current_state"] == "Conflicts with the survey growth direction"
    assert policy["decision_effect"] == "Supporting evidence only"

    consumer = groups["consumer_demand"]
    assert consumer["current_state"] == "Neutral"
    assert consumer["decision_effect"] == "None"


def test_leading_expectations_assigns_one_selector_and_three_non_voting_roles():
    layer = leading_expectations_layer_for_downside_case()

    roles = {group["id"]: group["group_role"] for group in layer["groups"]}
    assert roles == {
        "growth_surveys": "regime_selector",
        "financial_conditions": "supporting_evidence",
        "monetary_policy": "supporting_evidence",
        "consumer_demand": "supporting_evidence",
    }
    assert "credit_conditions" not in layer
    assert "vix_level" not in layer


def test_market_pricing_exposes_exactly_three_confirmation_tests_and_one_non_voting_m2_offset():
    layer = market_pricing_layer_for_downside_case()

    assert [test["id"] for test in layer["tests"]] == [
        "equity_trend",
        "credit",
        "volatility",
    ]
    assert layer["tests_passed"] == 1
    assert layer["tests_total"] == 3
    assert layer["liquidity_offset"]["test_contribution"] == "None"


def test_evidence_layer_display_values_do_not_expose_internal_codes():
    layers = evidence_layers_for_downside_case()
    financial = group_by_id(
        layers["leading_expectations"]["groups"], "financial_conditions"
    )

    assert financial["title"] == "Financial Conditions"
    assert "macro_financial_conditions" not in financial["interpretation"]
    assert layers["market_pricing"]["tests"][0]["state_label"] == "Bull Market"


def test_financial_conditions_group_has_no_credit_or_vix():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    groups = _groups(layers["leading_expectations"])
    financial_blob = json.dumps(groups["financial_conditions"])
    assert "VIX" not in financial_blob
    assert "vix" not in financial_blob
    assert "Credit Conditions" not in financial_blob
    assert "credit_conditions" not in financial_blob
    assert "risk_rising" not in financial_blob


def test_monetary_policy_group_has_no_m2():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    groups = _groups(layers["leading_expectations"])
    policy_blob = json.dumps(groups["monetary_policy"])
    assert "M2" not in policy_blob
    assert "m2" not in policy_blob
    assert "expanding" not in policy_blob


def test_market_pricing_exposes_tests_and_liquidity_offset():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    pricing = layers["market_pricing"]
    assert pricing["tests_summary"] == "Approved confirmation tests: 1 / 3"
    assert pricing["tests_passed"] == 1
    assert pricing["tests_total"] == 3
    assert [test["id"] for test in pricing["tests"]] == [
        "equity_trend",
        "credit",
        "volatility",
    ]

    offset = pricing["liquidity_offset"]
    assert offset["label"] == "Liquidity Offset"
    assert offset["state_label"] == "Expanding"
    assert offset["sentiment"] == "expanding"
    assert offset["decision_effect"] == "Offset only"
    assert offset["test_contribution"] == "None"
    assert offset["finding"] == "M2 money supply is supportive of liquidity"
    assert (
        offset["note"] == "Offset only — not included in the confirmation test count."
    )

    assert pricing["offsets"] == [
        {
            "id": "m2_liquidity_support",
            "finding": "M2 money supply is expanding or in shock, providing liquidity support",
        }
    ]
    assert pricing["context"] == []


def test_portfolio_conclusion_maps_exposure_fields():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    conclusion = layers["portfolio_conclusion"]
    assert conclusion["role"] == "decision_output"
    assert conclusion["posture_label"] == "Mild Risk-Off"
    assert conclusion["posture_code"] == "mild_risk_off"
    assert conclusion["net_exposure"] == "Modest defensive"
    assert conclusion["gross_exposure"] == "Moderate"
    assert conclusion["implementation"] == "Selective defensive positions"
    assert conclusion["broad_beta"] == "Reduce large directional exposure"
    assert conclusion["positioning"] == [
        "Maintain modest defensive exposure",
        "Use moderate position sizing",
    ]
    assert conclusion["avoid"] == ["Large directional long exposure"]
    assert conclusion["next_triggers"] == [
        "VIX crosses the approved confirmation threshold from normal"
    ]
    assert conclusion["watch_items"] == ["Jobless claims"]
    assert conclusion["excluded_inputs"] == ["Consumer Demand Outlook"]
    assert conclusion["method_versions"]["market_setup"] == "market_setup_v2"


def test_economic_reality_groups_carry_explanation_fields():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    reality = layers["economic_reality"]
    assert reality["scope_note"] == "Supplementary — does not affect Market Setup v2."
    assert reality["coverage_summary"] == [
        "Labor: partial",
        "Real Activity: data available, method pending",
        "Demand: not implemented",
    ]

    groups = _groups(reality)
    labor = groups["labor"]
    assert labor["formal_signal"] == "Claims trend: Stable"
    assert labor["relation_to_thesis"] == "Not confirming, not conflicting"
    assert labor["decision_effect"] == "No effect on Market Setup v2"
    assert labor["coverage"] == "Claims classified; Employment Situation context only"
    assert labor["sentiment"] == "stable"
    assert labor["data_status"] == "available"
    labels = [metric["label"] for metric in labor["details_metrics"]]
    assert labels[:2] == ["Initial Claims (4w avg)", "Continuing Claims (4w avg)"]
    assert "Nonfarm Payrolls Change" in labels
    initial = labor["details_metrics"][0]
    assert initial["value"] == 240000.0
    assert initial["period"] == "2026-07-25"

    real_activity = groups["real_activity"]
    assert real_activity["formal_signal"] == "Classification unavailable"
    assert real_activity["reason"] == (
        "Trend window and classification method are pending approval."
    )
    assert real_activity["decision_effect"] == "No effect on Market Setup v2"
    assert real_activity["coverage"] == (
        "Manufacturing Production: available · "
        "Total Industrial Production: available · "
        "Capacity Utilization: available"
    )
    assert real_activity["data_status"] == "available"
    metrics = {metric["label"]: metric for metric in real_activity["details_metrics"]}
    assert metrics["Manufacturing Production"]["value"] == "97.9"
    assert metrics["Capacity Utilization"]["value"] == "77.4%"


def test_economic_reality_keeps_unapproved_real_activity_values_in_details():
    layer = economic_reality_layer_with_available_activity_data()
    activity = group_by_id(layer["groups"], "real_activity")

    assert activity["formal_signal"] == "Classification unavailable"
    assert activity["reason"] == (
        "Trend window and classification method are pending approval."
    )
    assert activity["decision_effect"] == "No effect on Market Setup v2"
    assert activity["details_metrics"]


def test_labor_separates_claims_signal_from_context_only_labor_metrics():
    labor = labor_group_with_claims_and_esr_data()

    assert labor["formal_signal"] == "Claims trend: Stable"
    assert labor["relation_to_thesis"] == "Not confirming, not conflicting"
    assert labor["coverage"] == "Claims classified; Employment Situation context only"


def test_final_confirmation_keeps_only_gdp_group():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    final = layers["final_confirmation"]
    assert final["coverage_summary"] == [
        "GDP: available",
        "Corporate results: not implemented",
    ]

    output = final["groups"][0]
    assert output["id"] == "economic_output"
    assert output["formal_signal"] == "GDP: Falling"
    assert output["sentiment"] == "falling"
    assert output["decision_effect"] == "No effect on Market Setup v2"
    assert output["period"] == "2026 Q2"
    assert output["data_status"] == "available"
    metrics = {metric["label"]: metric for metric in output["details_metrics"]}
    assert metrics["GDP Level"]["value"] == 23400.0
    assert metrics["GDP Direction"]["value"] == "Falling"


def test_no_raw_underscore_codes_in_user_facing_strings():
    layers = market_setup_evidence_layers.build_evidence_layers(**_full_kwargs())
    offenders = []
    for key, value in _iter_strings(layers):
        if _is_code_key(key):
            continue
        if _RAW_CODE_PATTERN.search(value):
            offenders.append((key, value))
    assert offenders == []


def test_none_inputs_degrade_without_errors():
    layers = market_setup_evidence_layers.build_evidence_layers()

    assert layers["version"] == "market_setup_evidence_layers_v2"
    steps = layers["decision_path"]["steps"]
    assert len(steps) == 4
    assert steps[0]["input"]["value"] is None
    assert steps[0]["output"]["label"] is None
    assert steps[1]["passed_count"] is None
    assert steps[1]["total"] is None
    assert steps[1]["tests"] == []
    assert steps[1]["missing_inputs"] == []
    assert steps[2]["output"]["label"] is None
    assert steps[3]["output"]["label"] is None

    for group in layers["leading_expectations"]["groups"]:
        assert group["data_status"] == "missing"
        assert group["current_state"] is None

    pricing = layers["market_pricing"]
    assert pricing["tests_passed"] is None
    assert pricing["tests_total"] is None
    assert pricing["tests"] == []
    assert pricing["status_label"] is None
    assert pricing["missing_inputs"] == []
    assert pricing["liquidity_offset"] is None
    assert pricing["offsets"] == []
    assert pricing["context"] == []

    conclusion = layers["portfolio_conclusion"]
    assert conclusion["posture_code"] is None
    assert conclusion["net_exposure"] is None
    assert conclusion["positioning"] == []
    assert conclusion["excluded_inputs"] == []
    assert conclusion["method_versions"] == {}

    reality = _groups(layers["economic_reality"])
    assert reality["labor"]["data_status"] == "missing"
    assert reality["labor"]["formal_signal"] is None
    assert reality["labor"]["details_metrics"] == []
    assert reality["real_activity"]["data_status"] == "missing"
    assert layers["economic_reality"]["coverage_summary"] == [
        "Labor: data missing",
        "Real Activity: data missing",
        "Demand: not implemented",
    ]

    final = layers["final_confirmation"]
    assert final["groups"][0]["data_status"] == "missing"
    assert final["coverage_summary"] == [
        "GDP: missing",
        "Corporate results: not implemented",
    ]


def test_insufficient_data_result_uses_actual_labels():
    result = {
        "version": "market_setup_v2",
        "macro_regime": {
            "code": "insufficient_data",
            "label": "Insufficient Macro Evidence",
        },
        "market_confirmation": {
            "code": "insufficient_data",
            "label": "Insufficient Market Confirmation Evidence",
            "confirmation_test_count": None,
            "evidence": {},
            "offsets": [],
        },
        "market_setup": {
            "code": "insufficient_data",
            "label": "Insufficient Data",
            "agreement": "incomplete",
        },
        "portfolio_posture": {
            "code": "insufficient_data",
            "label": "Insufficient Data",
            "net_exposure": "neutral",
            "gross_exposure": "reduced",
            "implementation": "no_new_directional_exposure",
            "broad_beta": "avoid_large_directional_exposure",
            "positioning": [],
            "avoid": [],
        },
    }
    layers = market_setup_evidence_layers.build_evidence_layers(
        market_setup_result=result
    )
    steps = layers["decision_path"]["steps"]
    assert steps[0]["output"]["label"] == "Insufficient Macro Evidence"
    assert steps[2]["output"]["label"] == "Insufficient Data"
    assert steps[2]["output"]["agreement"] == "Incomplete"
    assert steps[3]["output"]["label"] == "Insufficient Data"

    conclusion = layers["portfolio_conclusion"]
    assert conclusion["net_exposure"] == "Neutral"
    assert conclusion["implementation"] == "No new directional exposure"
    assert conclusion["broad_beta"] == "Avoid large directional exposure"
