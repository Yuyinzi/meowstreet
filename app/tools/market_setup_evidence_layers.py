EVIDENCE_LAYERS_VERSION = "market_setup_evidence_layers_v2"

_BOUNDARY_NOTE = (
    "Economic Reality and Final Confirmation are supplementary evidence and "
    "do not participate in Market Setup v2 classification."
)

_ECONOMIC_REALITY_SCOPE_NOTE = (
    "Supplementary economic evidence — modules may be context-only, "
    "method-pending, or not implemented. None affects Market Setup v2."
)

_FINAL_CONFIRMATION_SCOPE_NOTE = (
    "Lagging outcomes are used for cycle positioning and retrospective "
    "review. They are intentionally excluded from Market Setup v2."
)

_LIQUIDITY_OFFSET_NOTE = "Offset only — not included in the confirmation test count."

_LIQUIDITY_OFFSET_LABEL = "Liquidity Offset"

_LIQUIDITY_OFFSET_ID = "m2_liquidity_support"

_OFFSET_DECISION_EFFECT = "Offset only"

_OFFSET_TEST_CONTRIBUTION = "None"

_REAL_ACTIVITY_REASON = (
    "Data are available, but no directional classification method has been "
    "approved. No current decision effect."
)

_DECISION_EFFECT_NONE = "No effect on Market Setup v2"

_SUPPORTING_EVIDENCE_EFFECT = "Supporting evidence only"

# Display labels for internal state codes (Presentation Contract: the
# dashboard must never render raw underscore-delimited codes as copy).
_STATE_LABELS = {
    # S&P 500 market phase
    "bull_market": "Bull Market",
    "bear_market": "Bear Market",
    "transition": "Transition",
    # Credit Conditions status (approved ten-state vocabulary)
    "healthy": "Healthy",
    "supportive": "Supportive",
    "weak_credit_warning": "Weak Credit Warning",
    "mixed": "Mixed",
    "selective": "Selective",
    "risk_rising": "Risk Rising",
    "crisis_stress": "Crisis Stress",
    "stress": "Stress",
    "risk_off": "Risk-Off",
    "serious_deterioration": "Serious Deterioration",
    # VIX zone
    "normal": "Normal",
    "elevated": "Elevated",
    # M2 liquidity
    "expanding": "Expanding",
    "shock": "Shock",
}

_DIRECTION_LABELS = {
    "rising": "Rising",
    "slowing": "Slowing",
    "falling": "Falling",
    "improving": "Improving",
    "rebound_risk": "Rebound Risk",
    "stable": "Stable",
}

_AGREEMENT_LABELS = {
    "aligned": "Aligned",
    "mixed": "Mixed",
    "conflicting": "Conflicting",
    "incomplete": "Incomplete",
}

_RELATIONSHIP_STATE_LABELS = {
    "supports": "Supports the survey growth direction",
    "conflicts": "Conflicts with the survey growth direction",
    "neutral": "Neutral",
    "unavailable": "Unavailable",
}

_RELATIONSHIP_LABELS = {
    "supports": "Supports",
    "conflicts": "Conflicts",
    "neutral": "Neutral",
    "unavailable": "Unavailable",
}

_SURVEY_LEVEL_LABELS = {
    "aligned_expansion": "Broad expansion",
    "aligned_contraction": "Broad contraction",
    "aligned_neutral": "Neutral",
    "divergent": "Mixed",
}

_SURVEY_LEVEL_WORDS = {
    "aligned_expansion": "Expansion",
    "aligned_contraction": "Contraction",
    "aligned_neutral": "Neutral",
    "divergent": "Mixed",
}

_SURVEY_LEVEL_NOUNS = {
    "aligned_expansion": "expansion",
    "aligned_contraction": "contraction",
    "aligned_neutral": "neutral conditions",
    "divergent": "mixed conditions",
}

_SURVEY_INTERPRETATIONS = {
    ("aligned_expansion", "rising"): (
        "Surveys show expansion, and the expected growth rate is accelerating."
    ),
    ("aligned_expansion", "slowing"): (
        "Surveys still show expansion, but the expected growth rate is decelerating."
    ),
    ("aligned_expansion", "stable"): (
        "Surveys show expansion with a steady expected growth rate."
    ),
    ("aligned_contraction", "falling"): (
        "Surveys show contraction, and the expected growth rate is still falling."
    ),
    ("aligned_contraction", "improving"): (
        "Surveys still show contraction, but conditions are improving."
    ),
    ("aligned_contraction", "rebound_risk"): (
        "Surveys still show contraction, but conditions are improving."
    ),
    ("aligned_neutral", "stable"): (
        "Surveys indicate neutral conditions with a stable growth outlook."
    ),
}

_CLAIMS_DIRECTION_LABELS = {
    "deteriorating": "Deteriorating",
    "improving": "Improving",
    "stable": "Stable",
    "partially_deteriorating": "Partially Deteriorating",
    "partially_improving": "Partially Improving",
    "conflicting": "Conflicting",
    "unavailable": "Unavailable",
}

_CLAIMS_RELATION_LABELS = {
    "confirming": "Confirming the macro thesis",
    "partial": "Partially confirming the macro thesis",
    "not_confirming": "Not confirming, not conflicting",
    "conflicting": "Conflicting with the macro thesis",
    "unavailable": "Unavailable",
}

_NET_EXPOSURE_LABELS = {
    "long": "Long",
    "modest_long": "Modest long",
    "neutral": "Neutral",
    "reduced": "Reduced",
    "modest_defensive": "Modest defensive",
}

_GROSS_EXPOSURE_LABELS = {
    "normal": "Normal",
    "moderate": "Moderate",
    "reduced": "Reduced",
}

_IMPLEMENTATION_LABELS = {
    "broad_and_selective_positions": "Broad and selective positions",
    "selective_positions": "Selective positions",
    "defensive_or_hedged_positions": "Defensive or hedged positions",
    "selective_defensive_positions": "Selective defensive positions",
    "no_new_directional_exposure": "No new directional exposure",
}

_BROAD_BETA_LABELS = {
    "permitted_with_risk_controls": "Permitted with risk controls",
    "avoid_large_directional_exposure": "Avoid large directional exposure",
    "avoid_long_broad_beta": "Avoid long broad beta",
    "reduce_large_directional_exposure": "Reduce large directional exposure",
}

_GDP_DIRECTION_LABELS = {
    1: ("rising", "Rising"),
    -1: ("falling", "Falling"),
    0: ("flat", "Flat"),
}

_MARKET_PRICING_TEST_LABELS = {
    "equity_trend": "S&P 500 Trend",
    "credit": "Credit Conditions",
    "volatility": "Volatility (VIX)",
}

_TEST_ORDER = ("equity_trend", "credit", "volatility")

_GROUP_ROLE_LABELS = {
    "regime_selector": "Regime Selector",
    "supporting_evidence": "Supporting Evidence",
}

_GOVERNANCE_STATUS_LABELS = {
    "context_only": "Context Only",
    "method_pending": "Method Pending",
    "review_only": "Review Only",
    "not_implemented": "Not Implemented",
}

_GOVERNANCE_LEGEND = [
    {
        "status": "context_only",
        "label": "Context Only",
        "description": "Approved contextual role; no classification effect.",
    },
    {
        "status": "method_pending",
        "label": "Method Pending",
        "description": "Data available; classification method not approved.",
    },
    {
        "status": "review_only",
        "label": "Review Only",
        "description": "Used for cycle review; intentionally non-decision.",
    },
    {
        "status": "not_implemented",
        "label": "Not Implemented",
        "description": "Data or module not yet available.",
    },
]

_GOVERNANCE_DESCRIPTIONS = {
    entry["status"]: entry["description"] for entry in _GOVERNANCE_LEGEND
}

_EXCLUDED_FACT_LABELS = {
    "macro_financial_conditions": "Financial Conditions",
    "macro_policy_response": "Monetary Policy",
    "consumer_demand_outlook": "Consumer Demand Outlook",
    "economic_confirmation": "Economic Confirmation",
    "cyclical_commodities": " Cyclical Commodities",
    "nfib_regional_evidence": "NFIB Regional Evidence",
    "sp500_market_phase": "S&P 500 Market Phase",
    "credit_conditions": "Credit Conditions",
    "vix_level": "VIX",
    "m2_liquidity": "M2 Liquidity",
    "survey_growth_direction": "Survey Growth Direction",
}

_LABOR_CONTEXT_METRICS = {
    "nonfarm_payrolls_change": ("Nonfarm Payrolls Change", "K"),
    "payrolls_3m_average_change": ("Nonfarm Payrolls 3M Avg Change", "K"),
    "unemployment_rate": ("Unemployment Rate", "%"),
    "average_weekly_hours": ("Average Weekly Hours", " hours"),
    "average_hourly_earnings": ("Average Hourly Earnings", "$"),
}

_REAL_ACTIVITY_METRICS = {
    "manufacturing_production": ("Manufacturing Production", ""),
    "total_industrial_production": ("Total Industrial Production", ""),
    "capacity_utilization": ("Capacity Utilization", "%"),
}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _fact(bundle, fact_id):
    facts = _dict(bundle).get("facts")
    fact = _dict(facts).get(fact_id)
    return fact if isinstance(fact, dict) else None


def _period_label(source_period):
    period = _dict(source_period)
    for key in ("reference_period", "effective_date", "observation_date"):
        if period.get(key):
            return str(period[key])
    return None


def _display(code, labels):
    if code is None:
        return None
    return labels.get(str(code), str(code).replace("_", " ").title())


def _metric(label, value, period=None, sentiment=None):
    record = {"label": label, "value": value}
    if period is not None:
        record["period"] = period
    if sentiment is not None:
        record["sentiment"] = sentiment
    return record


# ---------------------------------------------------------------------------
# Decision path
# ---------------------------------------------------------------------------


def _survey_direction(expected_growth, survey_synthesis):
    fact = _fact(expected_growth, "survey_growth_direction") or {}
    return fact.get("direction") or _dict(survey_synthesis).get(
        "expected_gdp_direction"
    )


def _test_contribution(confirms, state):
    if state is None:
        return None
    return "1 of 3" if confirms else "0 of 3"


def _test_verdict(confirms, direction):
    if confirms:
        return f"Confirms {direction}" if direction else "Confirms"
    return "Does not confirm"


def _thesis_direction(confirmation):
    code = str(confirmation.get("code") or "")
    if code.endswith("_downside"):
        return "downside"
    if code.endswith("_upside"):
        return "upside"
    return None


def _confirmation_tests(confirmation):
    test_count = confirmation.get("confirmation_test_count")
    has_count = isinstance(test_count, int) and not isinstance(test_count, bool)
    if not has_count:
        return []
    direction = _thesis_direction(confirmation)
    evidence = _dict(confirmation.get("evidence"))
    tests = []
    for test_id in _TEST_ORDER:
        record = _dict(evidence.get(test_id))
        state = record.get("state")
        confirms = bool(record.get("confirms"))
        tests.append(
            {
                "id": test_id,
                "label": _MARKET_PRICING_TEST_LABELS[test_id],
                "state_label": _display(state, _STATE_LABELS),
                "sentiment": state,
                "passed": confirms,
                "verdict_label": _test_verdict(confirms, direction),
                "test_contribution": _test_contribution(confirms, state),
                "finding": record.get("finding"),
            }
        )
    return tests


def _decision_path(market_setup_result, expected_growth, survey_synthesis):
    result = _dict(market_setup_result)
    regime = _dict(result.get("macro_regime"))
    confirmation = _dict(result.get("market_confirmation"))
    setup = _dict(result.get("market_setup"))
    posture = _dict(result.get("portfolio_posture"))

    direction = _survey_direction(expected_growth, survey_synthesis)
    test_count = confirmation.get("confirmation_test_count")
    has_count = isinstance(test_count, int) and not isinstance(test_count, bool)

    steps = [
        {
            "n": 1,
            "kind": "macro_thesis",
            "title": "Macro Thesis",
            "input": {
                "label": "ISM survey direction",
                "value": _display(direction, _DIRECTION_LABELS),
            },
            "output": {
                "label": regime.get("label"),
                "sentiment": regime.get("code"),
            },
        },
        {
            "n": 2,
            "kind": "market_test",
            "title": "Market Test",
            "tests": _confirmation_tests(confirmation),
            "passed_count": test_count if has_count else None,
            "total": 3 if has_count else None,
            "missing_inputs": confirmation.get("missing_inputs") or [],
            "output": {
                "label": confirmation.get("label"),
                "sentiment": confirmation.get("code"),
            },
        },
        {
            "n": 3,
            "kind": "relationship",
            "title": "Relationship",
            "inputs": [regime.get("label"), confirmation.get("label")],
            "output": {
                "label": setup.get("label"),
                "sentiment": setup.get("code"),
                "agreement": _display(setup.get("agreement"), _AGREEMENT_LABELS),
            },
        },
        {
            "n": 4,
            "kind": "action",
            "title": "Action",
            "output": {
                "label": posture.get("label"),
                "sentiment": posture.get("code"),
                "fields": [
                    {
                        "label": "Net exposure",
                        "value": _display(
                            posture.get("net_exposure"), _NET_EXPOSURE_LABELS
                        ),
                    },
                    {
                        "label": "Gross exposure",
                        "value": _display(
                            posture.get("gross_exposure"), _GROSS_EXPOSURE_LABELS
                        ),
                    },
                    {
                        "label": "Implementation",
                        "value": _display(
                            posture.get("implementation"), _IMPLEMENTATION_LABELS
                        ),
                    },
                    {
                        "label": "Broad beta",
                        "value": _display(
                            posture.get("broad_beta"), _BROAD_BETA_LABELS
                        ),
                    },
                ],
            },
        },
    ]
    return {"steps": steps}


# ---------------------------------------------------------------------------
# Leading Expectations
# ---------------------------------------------------------------------------


def _survey_level_key(synthesis):
    economic_direction = synthesis.get("economic_direction")
    if economic_direction in _SURVEY_LEVEL_LABELS:
        return economic_direction
    components = _dict(synthesis.get("components"))
    manufacturing = _dict(components.get("manufacturing")).get("level")
    services = _dict(components.get("services")).get("level")
    if manufacturing is None or services is None:
        return None
    if manufacturing == services == "expanding":
        return "aligned_expansion"
    if manufacturing == services == "contracting":
        return "aligned_contraction"
    if manufacturing == services == "neutral":
        return "aligned_neutral"
    return "divergent"


def _survey_interpretation(level_key, direction):
    if level_key is None or direction is None:
        return None
    template = _SURVEY_INTERPRETATIONS.get((level_key, direction))
    if template is not None:
        return template
    noun = _SURVEY_LEVEL_NOUNS[level_key]
    direction_text = str(_display(direction, _DIRECTION_LABELS)).lower()
    return (
        f"Surveys indicate {noun}, with the expected growth direction {direction_text}."
    )


def _growth_surveys_group(survey_synthesis, expected_growth, macro_regime):
    synthesis = _dict(survey_synthesis)
    fact = _fact(expected_growth, "survey_growth_direction") or {}
    direction = fact.get("direction") or synthesis.get("expected_gdp_direction")
    momentum = synthesis.get("growth_momentum")
    period = _period_label(fact.get("source_period")) or synthesis.get("period")
    level_key = _survey_level_key(synthesis)

    direction_label = _display(direction, _DIRECTION_LABELS)
    level_word = _SURVEY_LEVEL_WORDS.get(level_key)
    if level_word and direction_label:
        current_state = f"{level_word} {direction_label.lower()}"
    else:
        current_state = direction_label or level_word

    regime_label = _dict(macro_regime).get("label")
    decision_effect = f"Selects {regime_label}" if regime_label else None

    details_metrics = []
    level_label = _SURVEY_LEVEL_LABELS.get(level_key)
    if level_label:
        details_metrics.append(_metric("Current Level", level_label, period=period))
    if direction_label:
        details_metrics.append(
            _metric("Direction", direction_label, period=period, sentiment=direction)
        )
    if momentum:
        details_metrics.append(
            _metric(
                "Momentum",
                _display(momentum, {}),
                period=period,
                sentiment=momentum,
            )
        )

    return {
        "id": "growth_surveys",
        "title": "Growth Surveys (ISM)",
        "group_role": "regime_selector",
        "group_role_label": _GROUP_ROLE_LABELS["regime_selector"],
        "current_state": current_state,
        "sentiment": direction,
        "relationship": None,
        "decision_effect": decision_effect,
        "period": period,
        "interpretation": _survey_interpretation(level_key, direction),
        "data_status": "available" if direction else "missing",
        "details_metrics": details_metrics,
    }


def _relationship_interpretation(title, relationship):
    if relationship == "supports":
        return f"{title} supports the survey growth direction."
    if relationship == "conflicts":
        return f"{title} conflicts with the survey growth direction."
    if relationship == "neutral":
        return f"{title} is neutral relative to the survey growth direction."
    return None


def _relationship_group(group_id, title, bundle, fact_id):
    bundle = _dict(bundle)
    fact = _fact(bundle, fact_id) or {}
    relationship = fact.get("relationship_to_growth_direction")
    if relationship in ("supports", "conflicts"):
        decision_effect = _SUPPORTING_EVIDENCE_EFFECT
    elif relationship is not None:
        decision_effect = "None"
    else:
        decision_effect = None
    return {
        "id": group_id,
        "title": title,
        "group_role": "supporting_evidence",
        "group_role_label": _GROUP_ROLE_LABELS["supporting_evidence"],
        "current_state": _RELATIONSHIP_STATE_LABELS.get(relationship),
        "sentiment": relationship,
        "relationship": relationship,
        "relationship_label": _RELATIONSHIP_LABELS.get(relationship),
        "decision_effect": decision_effect,
        "period": _period_label(fact.get("source_period")),
        "data_status": "available" if fact else "missing",
        "interpretation": _relationship_interpretation(title, relationship),
    }


def _leading_expectations_layer(
    survey_synthesis,
    expected_growth,
    financial_conditions,
    policy_response,
    consumer_demand,
    market_setup_result,
):
    macro_regime = _dict(_dict(market_setup_result).get("macro_regime"))
    return {
        "layer_id": "leading_expectations",
        "title": "Leading Expectations",
        "role": "decision_input",
        "groups": [
            _growth_surveys_group(survey_synthesis, expected_growth, macro_regime),
            _relationship_group(
                "financial_conditions",
                "Financial Conditions",
                financial_conditions,
                "macro_financial_conditions",
            ),
            _relationship_group(
                "monetary_policy",
                "Monetary Policy",
                policy_response,
                "macro_policy_response",
            ),
            _relationship_group(
                "consumer_demand",
                "Consumer Demand",
                consumer_demand,
                "consumer_demand_outlook",
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Market Pricing
# ---------------------------------------------------------------------------


def _market_pricing_layer(market_setup_result):
    confirmation = _dict(_dict(market_setup_result).get("market_confirmation"))
    test_count = confirmation.get("confirmation_test_count")
    has_count = isinstance(test_count, int) and not isinstance(test_count, bool)

    liquidity = _dict(_dict(confirmation.get("evidence")).get("liquidity"))
    liquidity_offset = None
    if liquidity:
        state = liquidity.get("state")
        liquidity_offset = {
            "label": _LIQUIDITY_OFFSET_LABEL,
            "state_label": _display(state, _STATE_LABELS),
            "sentiment": state,
            "decision_effect": _OFFSET_DECISION_EFFECT,
            "test_contribution": _OFFSET_TEST_CONTRIBUTION,
            "finding": liquidity.get("finding"),
            "note": _LIQUIDITY_OFFSET_NOTE,
        }

    offsets = [
        {"id": _dict(offset).get("id"), "finding": _dict(offset).get("finding")}
        for offset in confirmation.get("offsets") or []
        if _dict(offset).get("id") != _LIQUIDITY_OFFSET_ID
    ]

    return {
        "layer_id": "market_pricing",
        "title": "Market Pricing",
        "role": "decision_input",
        "tests_summary": (
            f"Approved confirmation tests: {test_count} / 3" if has_count else None
        ),
        "status_label": confirmation.get("label") if not has_count else None,
        "missing_inputs": confirmation.get("missing_inputs") or [],
        "tests_passed": test_count if has_count else None,
        "tests_total": 3 if has_count else None,
        "tests": _confirmation_tests(confirmation),
        "liquidity_offset": liquidity_offset,
        "offsets": offsets,
        "context": [],
    }


# ---------------------------------------------------------------------------
# Portfolio Conclusion
# ---------------------------------------------------------------------------


def _action_labels(items):
    labels = []
    for item in items or []:
        if isinstance(item, dict):
            label = item.get("label") or item.get("code")
        else:
            label = item
        if label:
            labels.append(label)
    return labels


def _excluded_input_labels(fact_ids):
    return [
        _EXCLUDED_FACT_LABELS.get(fact_id, fact_id.replace("_", " ").title())
        for fact_id in (fact_ids or [])
    ]


def _portfolio_conclusion_layer(market_setup_result):
    result = _dict(market_setup_result)
    posture = _dict(result.get("portfolio_posture"))
    return {
        "layer_id": "portfolio_conclusion",
        "title": "Portfolio Conclusion",
        "role": "decision_output",
        "posture_label": posture.get("label"),
        "posture_code": posture.get("code"),
        "net_exposure": _display(posture.get("net_exposure"), _NET_EXPOSURE_LABELS),
        "gross_exposure": _display(
            posture.get("gross_exposure"), _GROSS_EXPOSURE_LABELS
        ),
        "implementation": _display(
            posture.get("implementation"), _IMPLEMENTATION_LABELS
        ),
        "broad_beta": _display(posture.get("broad_beta"), _BROAD_BETA_LABELS),
        "positioning": _action_labels(posture.get("positioning")),
        "avoid": _action_labels(posture.get("avoid")),
        "next_triggers": _action_labels(result.get("next_triggers")),
        "watch_items": _action_labels(result.get("watch_items")),
        "excluded_inputs": _excluded_input_labels(result.get("excluded_inputs")),
        "method_versions": dict(_dict(result.get("method_versions"))),
    }


# ---------------------------------------------------------------------------
# Economic Reality (supplementary)
# ---------------------------------------------------------------------------


def _format_snapshot_value(value, suffix):
    if value is None:
        return None
    if suffix == "$":
        return f"${value}"
    return f"{value}{suffix}"


def _snapshot_metrics(snapshots, label_map):
    metrics = []
    for series_id, (label, suffix) in label_map.items():
        snapshot = _dict(snapshots).get(series_id)
        if not isinstance(snapshot, dict):
            continue
        metrics.append(
            _metric(
                label,
                _format_snapshot_value(snapshot.get("value"), suffix),
                period=snapshot.get("reference_period"),
            )
        )
    return metrics


def _claims_metric(label, trend):
    trend = _dict(trend)
    if not trend or trend.get("latest_4w_mean") is None:
        return None
    return _metric(
        label,
        trend.get("latest_4w_mean"),
        period=trend.get("observation_period"),
        sentiment=trend.get("classification"),
    )


def _governance(status):
    return {
        "governance_status": status,
        "governance_status_label": _GOVERNANCE_STATUS_LABELS[status],
    }


def _labor_group(overview):
    claims = _dict(_dict(overview).get("claims_confirmation"))
    labor_context = _dict(_dict(overview).get("labor_context"))

    details_metrics = []
    initial = _claims_metric("Initial Claims (4w avg)", claims.get("initial_claims"))
    if initial:
        details_metrics.append(initial)
    continuing = _claims_metric(
        "Continuing Claims (4w avg)", claims.get("continuing_claims")
    )
    if continuing:
        details_metrics.append(continuing)
    context_metrics = _snapshot_metrics(
        labor_context.get("metrics"), _LABOR_CONTEXT_METRICS
    )
    details_metrics.extend(context_metrics)

    claims_direction = claims.get("claims_direction")
    confirmation_status = claims.get("confirmation_status")
    formal_signal = None
    if claims_direction:
        formal_signal = (
            f"Claims trend: {_display(claims_direction, _CLAIMS_DIRECTION_LABELS)}"
        )

    if claims_direction and claims_direction != "unavailable":
        coverage = "Claims classified"
    elif claims:
        coverage = "Claims unavailable"
    else:
        coverage = None
    if coverage and context_metrics:
        coverage = f"{coverage}; Employment Situation context only"

    return {
        "id": "labor",
        "title": "Labor Reality Check",
        "formal_signal": formal_signal,
        "relation_to_thesis": _CLAIMS_RELATION_LABELS.get(confirmation_status),
        "decision_effect": _DECISION_EFFECT_NONE,
        "coverage": coverage,
        "sentiment": claims_direction,
        "data_status": "available" if details_metrics else "missing",
        "details_metrics": details_metrics,
        **_governance("context_only"),
    }


def _real_activity_group(overview):
    real_activity = _dict(_dict(overview).get("real_activity"))
    snapshots = _dict(real_activity.get("metrics"))
    details_metrics = _snapshot_metrics(snapshots, _REAL_ACTIVITY_METRICS)

    coverage_parts = []
    for series_id, (label, _suffix) in _REAL_ACTIVITY_METRICS.items():
        status = (
            "available" if isinstance(snapshots.get(series_id), dict) else "missing"
        )
        coverage_parts.append(f"{label}: {status}")
    coverage = " · ".join(coverage_parts) if real_activity else None

    data_status = real_activity.get("data_status")
    if data_status not in ("available", "missing"):
        data_status = "available" if details_metrics else "missing"

    return {
        "id": "real_activity",
        "title": "Real Activity",
        "formal_signal": "Classification unavailable",
        "reason": _REAL_ACTIVITY_REASON,
        "decision_effect": _DECISION_EFFECT_NONE,
        "coverage": coverage,
        "data_status": data_status,
        "details_metrics": details_metrics,
        **_governance("method_pending"),
    }


def _economic_reality_layer(economic_confirmation_overview):
    labor = _labor_group(economic_confirmation_overview)
    real_activity = _real_activity_group(economic_confirmation_overview)
    labor_coverage = (
        "Labor: partial"
        if labor["data_status"] == "available"
        else "Labor: data missing"
    )
    real_activity_coverage = (
        "Real Activity: data available, method pending"
        if real_activity["details_metrics"]
        else "Real Activity: data missing"
    )
    return {
        "layer_id": "economic_reality",
        "title": "Economic Reality Check",
        "role": "supplementary",
        "scope_note": _ECONOMIC_REALITY_SCOPE_NOTE,
        "coverage_summary": [
            labor_coverage,
            real_activity_coverage,
            "Demand: not implemented",
        ],
        "groups": [labor, real_activity],
    }


# ---------------------------------------------------------------------------
# Final / Lagging Confirmation (review only)
# ---------------------------------------------------------------------------


def _economic_output_group(gdp_rows):
    rows = [row for row in (gdp_rows or []) if isinstance(row, dict)]
    if not rows:
        return {
            "id": "economic_output",
            "title": "Economic Output (GDP)",
            "formal_signal": None,
            "sentiment": None,
            "decision_effect": _DECISION_EFFECT_NONE,
            "period": None,
            "data_status": "missing",
            "details_metrics": [],
            **_governance("review_only"),
        }
    latest = rows[-1]
    _, direction_label = _GDP_DIRECTION_LABELS.get(
        latest.get("gdp_direction"), (None, None)
    )
    period = latest.get("period_label") or latest.get("date")
    details_metrics = [
        _metric("GDP Level", latest.get("gdp_level"), period=period),
    ]
    if direction_label:
        details_metrics.append(_metric("GDP Direction", direction_label, period=period))
    return {
        "id": "economic_output",
        "title": "Economic Output (GDP)",
        "formal_signal": f"GDP: {direction_label}" if direction_label else None,
        "sentiment": None,
        "decision_effect": _DECISION_EFFECT_NONE,
        "period": period,
        "data_status": "available",
        "details_metrics": details_metrics,
        **_governance("review_only"),
    }


def _final_confirmation_layer(gdp_rows):
    economic_output = _economic_output_group(gdp_rows)
    gdp_coverage = (
        "GDP: available"
        if economic_output["data_status"] == "available"
        else "GDP: missing"
    )
    return {
        "layer_id": "final_confirmation",
        "title": "Lagging Outcomes & Cycle Review",
        "role": "review_only",
        "scope_note": _FINAL_CONFIRMATION_SCOPE_NOTE,
        "coverage_summary": [gdp_coverage, "Corporate results: not implemented"],
        "groups": [economic_output],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_evidence_layers(
    market_setup_result=None,
    survey_synthesis=None,
    expected_growth=None,
    financial_conditions=None,
    policy_response=None,
    consumer_demand=None,
    economic_confirmation_overview=None,
    gdp_rows=None,
):
    return {
        "version": EVIDENCE_LAYERS_VERSION,
        "boundary_note": _BOUNDARY_NOTE,
        "governance_legend": list(_GOVERNANCE_LEGEND),
        "decision_path": _decision_path(
            market_setup_result, expected_growth, survey_synthesis
        ),
        "leading_expectations": _leading_expectations_layer(
            survey_synthesis,
            expected_growth,
            financial_conditions,
            policy_response,
            consumer_demand,
            market_setup_result,
        ),
        "market_pricing": _market_pricing_layer(market_setup_result),
        "portfolio_conclusion": _portfolio_conclusion_layer(market_setup_result),
        "economic_reality": _economic_reality_layer(economic_confirmation_overview),
        "final_confirmation": _final_confirmation_layer(gdp_rows),
    }
