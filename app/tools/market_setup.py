from datetime import date

_MARKET_STATE_MAP = {
    "bull_market": {"state": "bull_market", "starting_posture": "long"},
    "bear_market": {"state": "bear_market", "starting_posture": "short_or_neutral"},
}

_ISM_EXPECTED_GDP_MAP = {
    "expansion_rising": ("rising", "long", "ISM is above 50 and rising"),
    "expansion_slowing": ("slowing", "neutral", "ISM is above 50 but slowing"),
    "peaking": ("slowing", "neutral", "ISM is near 60 and peaking"),
    "contraction_deepening": ("falling", "short", "ISM is below 50 and falling"),
    "contraction_improving": ("improving", "short", "ISM is below 50 but improving"),
    "troughing": ("rebound_risk", "neutral_to_long", "ISM is troughing near 40-45"),
    "stable": ("stable", "neutral", "ISM momentum is flat"),
}

_EXPANSION_CURVE_OK = {"steep"}
_EXPANSION_CREDIT_OK = {
    "healthy",
    "supportive",
    "low_risk_low_dispersion",
    "low_risk_high_dispersion",
    "weak_credit_warning",
}
_CONTRACTION_CURVE_SIGNAL = {"inverted", "flat"}
_CONTRACTION_CREDIT_SIGNAL = {
    "risk_rising",
    "crisis_stress",
    "stress",
    "risk_off",
    "serious_deterioration",
}

_FINANCIAL_CONDITIONS_RESULTS = {
    "confirms_expansion",
    "confirms_contraction_risk",
    "transition_warning",
    "mixed",
    "unavailable",
}

_POLICY_RESPONSE_RESULTS = {
    "support_confirmed",
    "support_possible",
    "support_constrained",
    "restrictive_confirmed",
    "policy_liquidity_conflict",
    "no_clear_response",
    "unavailable",
}

_DOVISH_TONES = {"dovish", "easing", "accommodative"}
_HAWKISH_TONES = {"hawkish", "tightening", "restrictive"}


def _us_market_phase(payload):
    markets = (payload or {}).get("markets", [])
    sp500 = None
    for market in markets:
        if market.get("benchmark_id") == "us_sp500":
            sp500 = market
            break
    if sp500 is None:
        for market in markets:
            if str(market.get("region", "")).upper() == "US":
                sp500 = market
                break
    return sp500


def build_market_environment(market_phase_payload):
    market = _us_market_phase(market_phase_payload)
    if market is None:
        return {
            "state": "unavailable",
            "starting_posture": "neutral",
            "reason": "Market phase data is not loaded",
            "evidence_links": ["market_phase"],
            "source_module": "market_phase",
            "observation_period": None,
            "data_status": "missing",
        }
    status = market.get("latest", {}).get("market_phase_status")
    entry = _MARKET_STATE_MAP.get(
        status, {"state": "transition", "starting_posture": "neutral"}
    )
    reason = {
        "bull_market": "S&P 500 is in a bull market phase; starting posture is long-biased",
        "bear_market": "S&P 500 is in a bear market phase; starting posture is short-biased or neutral",
        "transition": "Market phase is uncertain or transitional; starting posture is neutral",
    }.get(entry["state"], "Market phase could not be determined")
    return {
        "state": entry["state"],
        "starting_posture": entry["starting_posture"],
        "reason": reason,
        "evidence_links": ["market_phase"],
        "source_module": "market_phase",
        "observation_period": market.get("data_through"),
        "data_status": "available",
    }


def _ism_cycle_state(ism_macro_signal):
    if ism_macro_signal is None:
        return None
    return ism_macro_signal.get("cycle_state")


def _ism_period(ism_macro_signal):
    if ism_macro_signal is None:
        return None
    return ism_macro_signal.get("period")


def build_expected_growth(survey_synthesis, consumer_demand_outlook=None):
    if consumer_demand_outlook is None:
        consumer_demand_outlook = {
            "state": "unavailable",
            "direction": None,
            "reason": "Consumer Demand Outlook is awaiting complete, aligned percentile data.",
            "observation_period": None,
            "data_status": "missing",
            "percentile_zone": None,
            "momentum": None,
            "percentile_label": None,
            "confirmation_state": None,
            "evidence_links": ["consumer_sentiment"],
        }

    expansion_directions = {"rising", "rebound_risk"}
    downside_directions = {"slowing", "falling"}

    consumer_agreement = False
    consumer_conflict = False

    if survey_synthesis is None:
        return {
            "state": "unavailable",
            "expected_gdp_direction": None,
            "initial_bias": "neutral",
            "reason": "Survey synthesis data is not available",
            "evidence_links": ["ism_manufacturing", "ism_services"],
            "source_module": "ism_survey_synthesis",
            "observation_period": None,
            "data_status": "missing",
            "missing_inputs": ["ISM Manufacturing", "ISM Services"],
            "consumer_demand": consumer_demand_outlook,
            "consumer_demand_agreement": False,
            "consumer_demand_conflict": False,
        }
    status = survey_synthesis.get("status")
    if status in ("partial", "mixed_periods"):
        return {
            "state": "unavailable",
            "expected_gdp_direction": None,
            "initial_bias": "neutral",
            "reason": "Survey synthesis is incomplete",
            "evidence_links": ["ism_manufacturing", "ism_services"],
            "source_module": "ism_survey_synthesis",
            "observation_period": survey_synthesis.get("period"),
            "data_status": "missing",
            "missing_inputs": survey_synthesis.get("missing_inputs", []),
            "consumer_demand": consumer_demand_outlook,
            "consumer_demand_agreement": False,
            "consumer_demand_conflict": False,
        }

    ism_dir = survey_synthesis.get("expected_gdp_direction")
    agreements = list(survey_synthesis.get("agreements", []))
    conflicts = list(survey_synthesis.get("conflicts", []))
    evidence_links = ["ism_manufacturing", "ism_services"]

    consumer_state = consumer_demand_outlook.get("state")
    if consumer_state == "confirms_expansion" and ism_dir in expansion_directions:
        consumer_agreement = True
        agreements.append(
            "Business surveys and consumer expectations both support expansion"
        )
    elif consumer_state == "confirms_downside_risk" and ism_dir in downside_directions:
        consumer_agreement = True
        agreements.append(
            "Business surveys and consumer expectations both signal downside risk"
        )
    elif consumer_state == "confirms_expansion" and ism_dir in downside_directions:
        consumer_conflict = True
        conflicts.append(
            "Business surveys indicate slowing or contraction while consumer expectations signal strength"
        )
    elif consumer_state == "confirms_downside_risk" and ism_dir in expansion_directions:
        consumer_conflict = True
        conflicts.append(
            "Business surveys indicate expansion while consumer expectations signal downside risk"
        )

    if consumer_demand_outlook.get("data_status") == "available":
        if "consumer_sentiment" not in evidence_links:
            evidence_links.append("consumer_sentiment")

    return {
        "state": survey_synthesis["economic_direction"],
        "expected_gdp_direction": survey_synthesis["expected_gdp_direction"],
        "initial_bias": survey_synthesis["survey_portfolio_implication"],
        "growth_momentum": survey_synthesis.get("growth_momentum"),
        "survey_alignment": survey_synthesis.get("survey_alignment"),
        "demand_alignment": survey_synthesis.get("demand_alignment"),
        "components": survey_synthesis.get("components", {}),
        "reason": "; ".join(survey_synthesis.get("reasons", [])),
        "agreements": agreements,
        "conflicts": conflicts,
        "evidence_links": evidence_links,
        "source_module": "ism_survey_synthesis",
        "observation_period": survey_synthesis.get("period"),
        "data_status": "available",
        "consumer_demand": consumer_demand_outlook,
        "consumer_demand_agreement": consumer_agreement,
        "consumer_demand_conflict": consumer_conflict,
    }


def _curve_is_expansionary(curve_status):
    return curve_status in _EXPANSION_CURVE_OK


def _curve_is_contractionary(curve_status):
    if curve_status == "inverted":
        return True
    return False


def _curve_is_transition(curve_status):
    return curve_status == "flat"


def _credit_is_stable(credit_status):
    return credit_status in _EXPANSION_CREDIT_OK


def _credit_is_widening(credit_status):
    return credit_status in _CONTRACTION_CREDIT_SIGNAL


def build_financial_conditions(rates_liquidity_payload):
    if rates_liquidity_payload is None:
        return {
            "state": "unavailable",
            "growth_confirmation": "unavailable",
            "reasons": ["US rates and credit data is not available"],
            "evidence_links": [
                "yield_curve",
                "real_rate_risk",
                "credit_conditions",
                "vix",
            ],
            "source_module": "us_rates_liquidity",
            "observation_period": None,
            "data_status": "missing",
        }
    derived = rates_liquidity_payload.get("derived", {})
    curve_status = derived.get("curve_status", "missing")
    credit_conditions = derived.get("credit_conditions_status", "missing")
    vix = derived.get("vix")
    real_rate = derived.get("ten_year_real_rate")
    cpi_real_rate = derived.get("cpi_based_real_rate")
    as_of = rates_liquidity_payload.get("as_of")

    reasons = []
    curve_is_inverted = _curve_is_contractionary(curve_status)
    curve_is_flat = _curve_is_transition(curve_status)
    curve_is_steep = _curve_is_expansionary(curve_status)
    credit_stable = _credit_is_stable(credit_conditions)
    credit_widening = _credit_is_widening(credit_conditions)

    if curve_is_inverted:
        reasons.append(f"Yield curve is inverted (10Y-2Y spread is negative)")
    elif curve_is_flat:
        reasons.append("Yield curve is flat — a transition warning")
    elif curve_is_steep:
        reasons.append("Yield curve is steep — consistent with expansion expectations")
    else:
        reasons.append("Yield curve status is not available")

    if credit_widening:
        reasons.append(
            f"Credit conditions signal widening stress ({credit_conditions})"
        )
    elif credit_stable:
        reasons.append(f"Credit conditions are stable ({credit_conditions})")
    else:
        reasons.append(f"Credit conditions are ambiguous or missing")

    if vix is not None:
        if vix > 25:
            reasons.append(f"VIX is elevated at {vix:.1f}")
        elif vix > 20:
            reasons.append(f"VIX is moderately elevated at {vix:.1f}")
        else:
            reasons.append(f"VIX is low at {vix:.1f}")

    if real_rate is not None:
        if real_rate > 2:
            reasons.append(f"Real rates are high ({real_rate:.2f}%)")
        elif real_rate < 0:
            reasons.append(
                f"Real rates are negative ({real_rate:.2f}%) — supportive for liquidity"
            )

    if curve_is_steep and credit_stable:
        result_state = "confirms_expansion"
        confirmation = "confirmed"
        reasons.append(
            "Yield curve and credit conditions both support an expansion view"
        )
    elif curve_is_inverted and credit_widening:
        result_state = "confirms_contraction_risk"
        confirmation = "not_confirmed"
        reasons.append("Inverted curve and widening credit confirm contraction risk")
    elif curve_is_flat and not credit_widening:
        result_state = "transition_warning"
        confirmation = "not_confirmed"
    elif curve_is_flat and credit_widening:
        result_state = "confirms_contraction_risk"
        confirmation = "not_confirmed"
        reasons.append(
            "Flat curve together with widening credit signals contraction risk"
        )
    elif curve_is_inverted and credit_stable:
        result_state = "mixed"
        confirmation = "not_confirmed"
        reasons.append("Curve is inverted but credit is not yet confirming stress")
    elif curve_is_steep and credit_widening:
        result_state = "mixed"
        confirmation = "not_confirmed"
        reasons.append(
            "Curve is steep but credit is showing stress — conditions are mixed"
        )
    else:
        result_state = "mixed"
        confirmation = "not_confirmed"
        reasons.append("Financial conditions are mixed or unclear")

    return {
        "state": result_state,
        "growth_confirmation": confirmation,
        "reasons": reasons,
        "evidence_links": ["yield_curve", "credit_conditions", "real_rate_risk", "vix"],
        "source_module": "us_rates_liquidity",
        "observation_period": as_of,
        "data_status": "available",
        "details": {
            "curve_status": curve_status,
            "credit_conditions_status": credit_conditions,
            "vix": vix,
            "ten_year_real_rate": real_rate,
        },
    }


def _fomc_is_dovish(fomc_tone):
    if not fomc_tone:
        return False
    latest = fomc_tone.get("latest_tone") or {}
    marker_tone = latest.get("marker_tone", "")
    if marker_tone is None:
        return False
    return marker_tone.lower() in _DOVISH_TONES


def _fomc_is_hawkish(fomc_tone):
    if not fomc_tone:
        return False
    latest = fomc_tone.get("latest_tone") or {}
    marker_tone = latest.get("marker_tone", "")
    if marker_tone is None:
        return False
    return marker_tone.lower() in _HAWKISH_TONES


def _inflation_above_target(inflation_context):
    if not inflation_context:
        return None
    return inflation_context.get("status") == "above_target"


def build_policy_response(fomc_tone, m2_headline, inflation_context, fed_balance_sheet):
    is_dovish = _fomc_is_dovish(fomc_tone)
    is_hawkish = _fomc_is_hawkish(fomc_tone)
    inflation_above = _inflation_above_target(inflation_context)
    m2_status = (m2_headline or {}).get("status", "missing")
    m2_is_contracting = m2_status == "contracting"
    m2_is_expanding = m2_status == "expanding"
    m2_is_shock = m2_status == "shock"

    fomc_period = None
    if fomc_tone:
        fomc_period = fomc_tone.get("period")

    m2_period = (m2_headline or {}).get("period")
    inflation_period = (inflation_context or {}).get("period")

    if fomc_tone is None and m2_headline is None and inflation_context is None:
        return {
            "state": "unavailable",
            "changes_growth_outcome": False,
            "reasons": ["Policy and liquidity data is not available"],
            "evidence_links": ["fomc_policy", "m2_money_supply"],
            "source_module": "fomc_policy_tone + m2_money_supply + inflation_context",
            "observation_period": None,
            "data_status": "missing",
            "details": {
                "fomc_tone": None,
                "fomc_action": None,
                "m2_status": "missing",
                "inflation_above_target": None,
                "fed_balance_sheet_available": False,
            },
        }

    reasons = []

    if is_dovish and inflation_above:
        result_state = "support_constrained"
        reasons.append("Dovish intent is constrained by above-target inflation")
    elif is_dovish and m2_is_expanding:
        result_state = "support_confirmed"
        reasons.append("Dovish FOMC tone with expanding M2 confirms liquidity support")
    elif is_dovish and m2_is_contracting:
        result_state = "policy_liquidity_conflict"
        reasons.append(
            "Dovish FOMC tone contrasts with contracting M2 — policy/liquidity conflict"
        )
    elif is_dovish and not m2_is_contracting:
        result_state = "support_possible"
        reasons.append(
            "Dovish FOMC tone suggests possible support, awaiting M2 confirmation"
        )
    elif is_hawkish and m2_is_contracting:
        result_state = "restrictive_confirmed"
        reasons.append(
            "Hawkish FOMC tone with contracting M2 confirms restrictive conditions"
        )
    elif is_hawkish:
        result_state = "restrictive_confirmed"
        reasons.append("Hawkish FOMC tone indicates restrictive policy stance")
    elif m2_is_shock:
        result_state = "no_clear_response"
        reasons.append(
            "Abnormal M2 movement suggests a stress response — requires investigation"
        )
    elif m2_is_expanding:
        result_state = "support_possible"
        reasons.append("M2 is expanding but FOMC signal is not clearly dovish")
    elif m2_is_contracting:
        result_state = "restrictive_confirmed"
        reasons.append(
            "M2 is contracting, consistent with restrictive liquidity conditions"
        )
    else:
        result_state = "no_clear_response"
        reasons.append("No clear policy or liquidity signal")

    if inflation_above:
        reasons.append(
            "Inflation is above the Fed target, constraining policy flexibility"
        )

    fomc_action = None
    if fomc_tone:
        latest = fomc_tone.get("latest_tone") or {}
        fomc_action = latest.get("policy_action")

    fed_sheet_available = (
        fed_balance_sheet is not None and fed_balance_sheet.get("status") != "missing"
    )

    return {
        "state": result_state,
        "changes_growth_outcome": result_state
        in (
            "support_confirmed",
            "support_possible",
            "support_constrained",
            "policy_liquidity_conflict",
        ),
        "reasons": reasons,
        "evidence_links": ["fomc_policy", "m2_money_supply"],
        "source_module": "fomc_policy_tone + m2_money_supply + inflation_context",
        "observation_period": fomc_period or m2_period or inflation_period,
        "data_status": "available",
        "details": {
            "fomc_tone": fomc_tone.get("latest_tone", {}).get("marker_tone")
            if fomc_tone
            else None,
            "fomc_action": fomc_action,
            "m2_status": m2_status,
            "inflation_above_target": inflation_above,
            "fed_balance_sheet_available": fed_sheet_available,
        },
    }


_POLICY_ANY_NON_RESTRICTIVE = {
    "support_confirmed",
    "support_possible",
    "support_constrained",
    "no_clear_response",
    "policy_liquidity_conflict",
}

_POLICY_ACTIVE_SUPPORT = {
    "support_confirmed",
    "support_possible",
    "support_constrained",
}

_POLICY_ACTIVE_RESTRICTIVE = {
    "restrictive_confirmed",
    "policy_liquidity_conflict",
}

_POLICY_ANY_NON_SUPPORTIVE = {
    "restrictive_confirmed",
    "no_clear_response",
    "policy_liquidity_conflict",
    "unavailable",
}


_SETUP_SCENARIOS = [
    {
        "growth_direction_pattern": {"rising", "rebound_risk"},
        "financial_state": "confirms_expansion",
        "policy_states": _POLICY_ANY_NON_RESTRICTIVE,
        "setup_type": "growth_and_conditions_aligned",
        "portfolio_posture": "long",
        "trade_implications": [
            "Broad long posture is supported by aligned growth and financial conditions"
        ],
    },
    {
        "growth_direction_pattern": {"falling", "slowing"},
        "financial_state": "confirms_contraction_risk",
        "policy_states": _POLICY_ANY_NON_SUPPORTIVE,
        "setup_type": "contraction_risk_aligned",
        "portfolio_posture": "short_or_neutral",
        "trade_implications": [
            "Short or market-neutral posture is supported by contraction signals"
        ],
    },
    {
        "growth_direction_pattern": {"falling", "improving"},
        "financial_state": "transition_warning",
        "policy_states": _POLICY_ACTIVE_SUPPORT,
        "setup_type": "weak_growth_with_policy_support",
        "portfolio_posture": "neutral_to_long",
        "trade_implications": [
            "Reduce broad short conviction; inspect relative industry weakness",
            "Policy support may challenge a pure short thesis",
        ],
    },
    {
        "growth_direction_pattern": {"falling", "improving"},
        "financial_state": "mixed",
        "policy_states": _POLICY_ACTIVE_SUPPORT,
        "setup_type": "weak_growth_with_policy_support",
        "portfolio_posture": "neutral_to_long",
        "trade_implications": [
            "Reduce broad short conviction; inspect relative industry weakness",
            "Curve warns but credit is not confirming crisis stress",
            "Policy support may challenge a pure short thesis — the 2019 pattern",
        ],
    },
    {
        "growth_direction_pattern": {"rising", "rebound_risk"},
        "financial_state": "mixed",
        "policy_states": _POLICY_ACTIVE_RESTRICTIVE,
        "setup_type": "growth_liquidity_conflict",
        "portfolio_posture": "neutral",
        "trade_implications": [
            "Avoid aggressive broad long; favor selectivity or neutral posture",
            "Growth improving but liquidity/conditions are restrictive",
        ],
    },
]


def _growth_direction_set(growth):
    direction = (growth or {}).get("expected_gdp_direction")
    if direction == "rising":
        return {"rising"}
    if direction == "falling":
        return {"falling"}
    if direction == "slowing":
        return {"slowing"}
    if direction == "improving":
        return {"improving"}
    if direction == "rebound_risk":
        return {"rebound_risk"}
    if direction == "stable":
        return {"stable"}
    return set()


def classify_setup_type(
    market_environment, expected_growth, financial_conditions, policy_response
):
    growth_state = expected_growth.get("state", "unavailable")
    growth_direction_set = _growth_direction_set(expected_growth)
    fc_state = financial_conditions.get("state", "unavailable")
    policy_state = policy_response.get("state", "unavailable")

    if growth_state == "unavailable" or fc_state == "unavailable":
        return {
            "setup_type": "insufficient_data",
            "portfolio_posture": market_environment.get("starting_posture", "neutral"),
            "trade_implications": ["Insufficient data to classify the market setup"],
            "agreements": [],
            "conflicts": [],
        }

    for scenario in _SETUP_SCENARIOS:
        growth_match = bool(growth_direction_set & scenario["growth_direction_pattern"])
        fc_match = fc_state == scenario["financial_state"]
        policy_match = policy_state in scenario["policy_states"]

        if growth_match and fc_match and policy_match:
            return {
                "setup_type": scenario["setup_type"],
                "portfolio_posture": scenario["portfolio_posture"],
                "trade_implications": scenario["trade_implications"],
                "agreements": _derive_agreements(
                    expected_growth, financial_conditions, policy_response
                ),
                "conflicts": _derive_conflicts(
                    expected_growth, financial_conditions, policy_response
                ),
            }

    return {
        "setup_type": "unresolved_macro_conflict",
        "portfolio_posture": "cautious",
        "trade_implications": [
            "Keep posture cautious and inspect conflicting evidence"
        ],
        "agreements": _derive_agreements(
            expected_growth, financial_conditions, policy_response
        ),
        "conflicts": _derive_conflicts(
            expected_growth, financial_conditions, policy_response
        ),
    }


def _derive_agreements(expected_growth, financial_conditions, policy_response):
    agreements = []
    growth_dir = expected_growth.get("expected_gdp_direction")
    fc_state = financial_conditions.get("state")
    if growth_dir in ("rising",) and fc_state == "confirms_expansion":
        agreements.append(
            "Growth direction and financial conditions both support expansion"
        )
    if growth_dir in ("falling",) and fc_state == "confirms_contraction_risk":
        agreements.append(
            "Growth weakening and financial conditions both signal contraction risk"
        )
    return agreements


def _derive_conflicts(expected_growth, financial_conditions, policy_response):
    conflicts = []
    growth_dir = expected_growth.get("expected_gdp_direction")
    fc_state = financial_conditions.get("state")
    policy_state = policy_response.get("state")
    if growth_dir in ("rising",) and fc_state in ("mixed", "confirms_contraction_risk"):
        conflicts.append(
            "Growth direction suggests improvement but financial conditions disagree"
        )
    if growth_dir in ("falling", "improving") and policy_state in (
        "support_confirmed",
        "support_possible",
    ):
        conflicts.append("Growth weakening but policy response may support markets")
    if fc_state == "mixed":
        conflicts.append("Financial conditions are mixed — curve and credit disagree")
    return conflicts


def reconcile_portfolio_posture(market_environment, setup_type_result, expected_growth):
    base_posture = setup_type_result.get("portfolio_posture", "neutral")
    market_state = market_environment.get("state")
    starting_posture = market_environment.get("starting_posture", "neutral")
    conflicts = list(setup_type_result.get("conflicts", []))
    agreements = list(setup_type_result.get("agreements", []))

    if market_state == "unavailable":
        return base_posture, conflicts, agreements

    posture = base_posture

    if market_state == "bull_market" and posture in ("short_or_neutral",):
        conflicts.append(
            "Bull market phase conflicts with contraction setup — reconciled to neutral posture"
        )
        posture = "neutral"

    if market_state == "bear_market" and posture in ("long", "neutral_to_long"):
        conflicts.append(
            "Bear market phase conflicts with expansion setup — reconciled to neutral posture"
        )
        posture = "neutral"

    if expected_growth.get("consumer_demand_conflict") and posture in (
        "long",
        "short_or_neutral",
    ):
        conflicts.append(
            "Consumer expectations conflict with the growth path, limiting conviction."
        )
        if posture == "long":
            posture = "neutral_to_long"
        elif posture == "short_or_neutral":
            posture = "cautious"
    elif expected_growth.get("consumer_demand_conflict"):
        conflicts.append(
            "Consumer expectations conflict with the growth path, limiting conviction."
        )

    return posture, conflicts, agreements


def _industry_signal_direction(industry):
    signal = industry.get("overall_signal") or {}
    direction = signal.get("direction") or industry.get("direction")
    return direction


def _growing_clues(industries_data):
    if not industries_data:
        return []
    result = []
    for ind in industries_data:
        direction = _industry_signal_direction(ind)
        if direction not in ("growth", "higher", "increase"):
            continue
        trend = ind.get("trend_summary") or {}
        streak = trend.get("positive_month_streak", 0)
        if streak >= 2:
            result.append(ind["industry"])
        elif streak == 1 or not trend:
            result.append(ind["industry"])
    return result


def _contracting_clues(industries_data):
    if not industries_data:
        return []
    result = []
    for ind in industries_data:
        direction = _industry_signal_direction(ind)
        if direction not in ("contraction", "decrease", "lower"):
            continue
        trend = ind.get("trend_summary") or {}
        neg_streak = trend.get("negative_month_streak", 0)
        eligible = trend.get("eligible_month_count", 0)
        if neg_streak >= 2:
            result.append(ind["industry"])
        elif not eligible:
            result.append(ind["industry"])
    return result


def build_idea_generation_clues(ism_industry_analysis):
    if not ism_industry_analysis:
        return {
            "broad_market": "No industry analysis data available for research clues",
            "industry_long_clues": [],
            "industry_short_clues": [],
            "warning": "Research clues only; ticker validation is still required",
            "source_module": "ism_industry_analysis",
            "data_status": "missing",
        }
    industries = ism_industry_analysis.get("industries", [])
    comments = ism_industry_analysis.get("comments", [])
    long_clues = _growing_clues(industries)
    short_clues = _contracting_clues(industries)
    return {
        "broad_market": "Use ISM industry rankings and comments to seed long/short research candidates",
        "industry_long_clues": long_clues,
        "industry_short_clues": short_clues,
        "extreme_comments_count": len(comments),
        "warning": "Research clues only; ticker validation is still required",
        "source_module": "ism_industry_analysis",
        "data_status": "available" if industries else "partial",
    }


_CONCLUSION_MAP = [
    {
        "setup_types": {"growth_and_conditions_aligned"},
        "market_phase": "bull_market",
        "code": "growth_and_trend_aligned",
        "title": "Growth and market trend aligned",
        "summary": "Manufacturing and Services expansion, supportive financial conditions, and a bullish market trend support broad-market long exposure.",
    },
    {
        "setup_types": {"growth_and_conditions_aligned"},
        "market_phase": "bear_market",
        "code": "macro_improving_trend_not_reversed",
        "title": "Macro improvement; bear market not reversed",
        "summary": "Growth and conditions are improving, but the S&P 500 bear market has not yet reversed. Posture is neutral until the price trend confirms the macro improvement.",
    },
    {
        "setup_types": {"contraction_risk_aligned"},
        "market_phase": "bear_market",
        "code": "contraction_risk_market_confirmed",
        "title": "Contraction risk confirmed by market trend",
        "summary": "Weakening growth, deteriorating financial conditions, and a bear market phase all confirm elevated downside risk.",
    },
    {
        "setup_types": {"contraction_risk_aligned"},
        "market_phase": "bull_market",
        "code": "macro_risk_rising_bull_intact",
        "title": "Macro Risk Rising; Bull Market Intact",
        "summary": "Growth and financial conditions are deteriorating, but the S&P 500 bull phase and liquidity offsets do not confirm a broad-market short setup.",
    },
    {
        "setup_types": {"weak_growth_with_policy_support"},
        "market_phase": "bull_market",
        "code": "weak_growth_policy_offset",
        "title": "Weak growth offset by policy and liquidity support",
        "summary": "Growth is weak but active policy support and liquidity offset the downside.",
    },
    {
        "setup_types": {"weak_growth_with_policy_support"},
        "market_phase": "bear_market",
        "code": "policy_support_bear_trend",
        "title": "Policy support present; bear trend not reversed",
        "summary": "Policy and liquidity are supportive, but the bear market prevents a long-biased posture.",
    },
    {
        "setup_types": {"growth_liquidity_conflict"},
        "code": "growth_liquidity_mismatch",
        "title": "Growth improving but liquidity remains restrictive",
        "summary": "Growth direction is improving, but restrictive financial conditions and policy constrain the outlook.",
    },
    {
        "setup_types": {"unresolved_macro_conflict"},
        "code": "evidence_unresolved",
        "title": "Evidence remains unresolved",
        "summary": "Growth, financial conditions, and policy are sending conflicting signals.",
    },
    {
        "setup_types": {"insufficient_data"},
        "code": "insufficient_evidence",
        "title": "Insufficient evidence for a directional posture",
        "summary": "Key inputs are missing or unavailable. Posture is neutral until sufficient data is loaded.",
    },
]


_GUIDANCE_TEMPLATES = {
    "long": {
        "actions": [
            "Deploy broad-market long exposure with trend confirmation",
            "Favor industries with persistent ISM growth across Manufacturing or Services",
            "Monitor ISM, credit conditions, and market phase for deterioration",
        ],
        "avoid": [
            "Aggressive short positioning while growth and conditions support expansion",
        ],
    },
    "neutral": {
        "actions": [
            "Maintain balanced exposure with no net directional bias",
            "Inspect individual positions for standalone merit",
        ],
        "avoid": [
            "Building large directional positions without clearer alignment",
        ],
    },
    "neutral_to_long": {
        "actions": [
            "Maintain a modest long bias while waiting for macro confirmation",
            "Inspect growth-aligned industries for selective long candidates",
        ],
        "avoid": [
            "Aggressive broad-market short positions",
        ],
    },
    "short_or_neutral": {
        "actions": [
            "Favor short or market-neutral positioning",
            "Research contracting manufacturing industries for short candidates",
        ],
        "avoid": [
            "Aggressive broad-market long additions without clear macro improvement",
        ],
    },
    "cautious": {
        "actions": [
            "Keep broad-market exposure selective and well-hedged",
            "Balance long positions with relative shorts or hedges",
            "Wait for clearer macro alignment before committing material capital",
        ],
        "avoid": [
            "Aggressive directional bets while evidence is unresolved",
        ],
    },
}

_CONSUMER_DEMAND_OUTLOOK_DIRECTIONS = {
    ("elevated", "improving"): ("confirms_expansion", "expansion"),
    ("depressed", "weakening"): ("confirms_downside_risk", "downside_risk"),
}

_CONSUMER_DEMAND_OUTLOOK_REASONS = {
    "confirms_expansion": "Consumer Expectations are elevated and improving, confirming expansion-oriented demand evidence.",
    "confirms_downside_risk": "Consumer Expectations are depressed and weakening, confirming consumer-demand downside risk.",
    "transition": "Consumer Expectations do not show a clear directional signal.",
}


def build_consumer_demand_outlook(consumer_sentiment_summary):
    unavailable = {
        "state": "unavailable",
        "direction": None,
        "reason": "Consumer Demand Outlook is awaiting complete, aligned percentile data.",
        "observation_period": None,
        "data_status": "missing",
        "percentile_zone": None,
        "momentum": None,
        "percentile_label": None,
        "confirmation_state": None,
        "evidence_links": ["consumer_sentiment"],
    }
    if consumer_sentiment_summary is None:
        return unavailable
    if consumer_sentiment_summary.get("method_version") != 2:
        return unavailable
    if consumer_sentiment_summary.get("data_status") != "aligned_period":
        return unavailable
    primary = consumer_sentiment_summary.get("primary_signal") or {}
    if primary.get("series_id") != "umcsi_expectations":
        return unavailable
    zone = primary.get("percentile_zone")
    momentum = primary.get("momentum")
    expectations = consumer_sentiment_summary.get("expectations") or {}
    percentile_rank = expectations.get("percentile_rank")
    if zone is None or momentum is None or percentile_rank is None:
        return unavailable
    if zone == "percentile_unavailable":
        return unavailable
    outlook = _CONSUMER_DEMAND_OUTLOOK_DIRECTIONS.get((zone, momentum))
    if outlook is None:
        return {
            "state": "transition",
            "direction": None,
            "reason": _CONSUMER_DEMAND_OUTLOOK_REASONS["transition"],
            "observation_period": consumer_sentiment_summary.get("aligned_month"),
            "data_status": "available",
            "percentile_zone": zone,
            "momentum": momentum,
            "percentile_label": expectations.get("percentile_label"),
            "confirmation_state": (
                consumer_sentiment_summary.get("confirmation") or {}
            ).get("state"),
            "evidence_links": ["consumer_sentiment"],
        }
    state, direction = outlook
    return {
        "state": state,
        "direction": direction,
        "reason": _CONSUMER_DEMAND_OUTLOOK_REASONS[state],
        "observation_period": consumer_sentiment_summary.get("aligned_month"),
        "data_status": "available",
        "percentile_zone": zone,
        "momentum": momentum,
        "percentile_label": expectations.get("percentile_label"),
        "confirmation_state": (
            consumer_sentiment_summary.get("confirmation") or {}
        ).get("state"),
        "evidence_links": ["consumer_sentiment"],
    }


_CONFIRMATION_MORE_DEFENSIVE = [
    "S&P 500 enters a bear-market phase",
    "ISM falls below 50 with weakening New Orders",
    "Credit stress broadens or deteriorates further",
    "VIX rises and confirms risk repricing",
    "M2 or the Fed balance sheet turns restrictive",
]

_CONFIRMATION_MORE_CONSTRUCTIVE = [
    "ISM and New Orders improve",
    "Credit spreads stabilize or narrow",
    "Real rates fall",
    "Policy becomes less restrictive",
]


def _growth_path_evidence(expected_growth):
    direction = expected_growth.get("expected_gdp_direction")
    state = expected_growth.get("state", "unavailable")
    if state == "unavailable" or expected_growth.get("data_status") == "missing":
        return None
    if direction == "rising":
        finding = "Business surveys indicate expansion is strengthening"
        implication = "GDP and earnings growth are likely to accelerate"
        tone = "constructive"
    elif direction == "slowing":
        finding = "Business survey expansion is slowing"
        implication = "GDP and earnings growth are more likely to slow than accelerate"
        tone = "caution"
    elif direction == "falling":
        finding = "Business surveys indicate contraction"
        implication = "GDP and earnings are at risk of declining"
        tone = "defensive"
    elif direction == "improving":
        finding = "Business survey contraction is showing early improvement"
        implication = "The worst of the macro deterioration may be passing"
        tone = "caution"
    elif direction == "rebound_risk":
        finding = "Business surveys may be near a cyclical trough"
        implication = "A rebound would challenge bearish positioning"
        tone = "caution"
    elif direction == "stable":
        finding = "Business survey momentum is flat"
        implication = "Growth path lacks a clear near-term catalyst"
        tone = "caution"
    else:
        finding = "Business survey direction is unclear"
        implication = "Growth path requires more data to assess"
        tone = "caution"
    evidence = [expected_growth.get("reason", "")]
    agreements = expected_growth.get("agreements", [])
    if agreements:
        evidence.extend(agreements)
    conflicts = expected_growth.get("conflicts", [])
    if conflicts:
        evidence.extend(conflicts)
    return {
        "id": "growth_path",
        "title": "Growth path",
        "finding": finding,
        "implication": implication,
        "tone": tone,
        "evidence": [e for e in evidence if e],
        "evidence_links": expected_growth.get("evidence_links", []),
    }


def _financial_evidence(financial_conditions):
    state = financial_conditions.get("state", "unavailable")
    if state == "unavailable":
        return None
    if state == "confirms_expansion":
        finding = "Financial conditions support an expansion view"
        implication = "Curve and credit are aligned with constructive risk-taking"
        tone = "constructive"
    elif state == "confirms_contraction_risk":
        finding = "Financial conditions confirm rising downside risk"
        implication = "The macro environment warrants defensive positioning"
        tone = "defensive"
    elif state == "transition_warning":
        finding = "Financial conditions are flashing a transition warning"
        implication = "The expansion cycle may be losing momentum"
        tone = "caution"
    elif state == "mixed":
        finding = "Financial conditions are sending mixed signals"
        implication = "Curve and credit disagree — selectivity is warranted"
        tone = "caution"
    else:
        return None
    return {
        "id": "financial_confirmation",
        "title": "Financial confirmation",
        "finding": finding,
        "implication": implication,
        "tone": tone,
        "evidence": list(financial_conditions.get("reasons", [])),
        "evidence_links": financial_conditions.get("evidence_links", []),
    }


def _policy_evidence(policy_response):
    state = policy_response.get("state", "unavailable")
    if state == "unavailable":
        return None
    if state == "restrictive_confirmed":
        finding = "Monetary policy is restrictive"
        implication = "The Fed has less room to offset weaker growth"
        tone = "defensive"
    elif state == "support_constrained":
        finding = "Policy support is constrained by above-target inflation"
        implication = "Policy flexibility is limited while inflation remains elevated"
        tone = "caution"
    elif state in ("support_confirmed", "support_possible"):
        finding = "Monetary policy is supportive"
        implication = "Liquidity conditions are favorable for risk-taking"
        tone = "constructive"
    elif state == "policy_liquidity_conflict":
        finding = "Policy tone and liquidity conditions are diverging"
        implication = "The policy environment lacks clear directional alignment"
        tone = "caution"
    elif state == "no_clear_response":
        finding = "Policy signal is unclear"
        implication = "Policy direction needs more data"
        tone = "caution"
    else:
        return None
    return {
        "id": "policy_constraint",
        "title": "Policy constraint",
        "finding": finding,
        "implication": implication,
        "tone": tone,
        "evidence": list(policy_response.get("reasons", [])),
        "evidence_links": policy_response.get("evidence_links", []),
    }


def build_evidence_chain(expected_growth, financial_conditions, policy_response):
    groups = []
    for fn in (_growth_path_evidence, _financial_evidence, _policy_evidence):
        group = fn(
            expected_growth
            if fn is _growth_path_evidence
            else financial_conditions
            if fn is _financial_evidence
            else policy_response
        )
        if group:
            groups.append(group)
    return groups


def _conviction_limit_market_phase(market_environment, setup_type_result):
    market_state = market_environment.get("state")
    raw_setup = setup_type_result.get("setup_type")
    if market_state == "bull_market" and raw_setup in (
        "contraction_risk_aligned",
        "unresolved_macro_conflict",
    ):
        return {
            "finding": "S&P 500 remains in a bull market",
            "effect": "Prevents an aggressive broad-market short posture",
            "evidence_links": ["market_phase"],
        }
    if market_state == "bear_market" and raw_setup in (
        "growth_and_conditions_aligned",
        "weak_growth_with_policy_support",
    ):
        return {
            "finding": "S&P 500 is in a bear market",
            "effect": "Prevents an aggressive broad-market long posture",
            "evidence_links": ["market_phase"],
        }
    return None


def _conviction_limit_m2(policy_response):
    m2_status = policy_response.get("details", {}).get("m2_status")
    if m2_status in ("expanding", "shock"):
        return {
            "finding": "M2 money supply is expanding",
            "effect": "Provides a liquidity offset to restrictive policy concerns",
            "evidence_links": ["m2_money_supply"],
        }
    return None


def _conviction_limit_vix(financial_conditions):
    details = financial_conditions.get("details", {})
    vix = details.get("vix")
    fc_state = financial_conditions.get("state")
    if (
        vix is not None
        and vix < 20
        and fc_state in ("confirms_contraction_risk", "transition_warning", "mixed")
    ):
        return {
            "finding": "VIX remains low",
            "effect": "Acute market stress is not yet being priced",
            "evidence_links": ["vix"],
        }
    return None


def build_conviction_limits(
    market_environment,
    financial_conditions,
    policy_response,
    setup_type_result,
    expected_growth=None,
):
    offsets = []
    offset = _conviction_limit_market_phase(market_environment, setup_type_result)
    if offset:
        offsets.append(offset)
    offset = _conviction_limit_m2(policy_response)
    if offset:
        offsets.append(offset)
    offset = _conviction_limit_vix(financial_conditions)
    if offset:
        offsets.append(offset)
    if expected_growth and expected_growth.get("consumer_demand_conflict"):
        offsets.append(
            {
                "finding": "Consumer expectations conflict with the business-survey growth path",
                "effect": "Limits conviction in the directional Market Setup posture",
                "evidence_links": ["consumer_sentiment"],
            }
        )
    if not offsets:
        return None
    limit_count = len(offsets)
    if limit_count >= 2:
        summary = "The macro warning is not fully confirmed by price, liquidity, or volatility"
    elif any(o.get("evidence_links") == ["market_phase"] for o in offsets):
        summary = "The market-phase trend does not confirm the macro warning"
    elif any(o.get("evidence_links") == ["m2_money_supply"] for o in offsets):
        summary = "Liquidity conditions do not uniformly confirm the macro view"
    elif any(o.get("evidence_links") == ["consumer_sentiment"] for o in offsets):
        summary = "Consumer demand does not confirm the business-survey growth path"
    else:
        summary = "Volatility conditions do not confirm acute stress"
    return {
        "title": "Why conviction is limited",
        "summary": summary,
        "offsets": offsets,
    }


def build_market_conclusion(
    setup_type_result, market_environment, reconciled_posture, expected_growth=None
):
    setup_type = setup_type_result.get("setup_type", "insufficient_data")
    market_state = market_environment.get("state")
    for entry in _CONCLUSION_MAP:
        if setup_type not in entry["setup_types"]:
            continue
        market_match = entry.get("market_phase")
        if market_match and market_state != market_match:
            continue
        summary = entry["summary"]
        if expected_growth and expected_growth.get("consumer_demand_conflict"):
            summary += " Consumer expectations conflict with the growth path, limiting conviction."
        return {
            "code": entry["code"],
            "title": entry["title"],
            "summary": summary,
        }
    summary = "The combination of inputs does not match a defined scenario. Posture is cautious."
    if expected_growth and expected_growth.get("consumer_demand_conflict"):
        summary += (
            " Consumer expectations conflict with the growth path, limiting conviction."
        )
    return {
        "code": "unresolved",
        "title": "Evidence is unresolved",
        "summary": summary,
    }


def build_portfolio_guidance(reconciled_posture):
    template = _GUIDANCE_TEMPLATES.get(
        reconciled_posture, _GUIDANCE_TEMPLATES["neutral"]
    )
    summary_map = {
        "long": "Broad long exposure is supported by aligned growth, conditions, and price trend",
        "neutral": "Conflicting signals or insufficient evidence support a neutral posture",
        "neutral_to_long": "A mildly long-biased posture is supported by policy and liquidity offsets",
        "short_or_neutral": "A short-biased posture is supported by deteriorating macro conditions",
        "cautious": "Avoid aggressive directional exposure while macro evidence is in conflict",
    }
    return {
        "posture": reconciled_posture,
        "summary": summary_map.get(reconciled_posture, "Maintain a selective posture"),
        "actions": template["actions"],
        "avoid": template["avoid"],
    }


def build_confirmation_conditions(setup_type_result, market_environment):
    more_defensive = list(_CONFIRMATION_MORE_DEFENSIVE)
    more_constructive = list(_CONFIRMATION_MORE_CONSTRUCTIVE)
    return {
        "more_defensive": more_defensive,
        "more_constructive": more_constructive,
    }


def _oldest_period(*periods):
    candidates = [p for p in periods if p is not None]
    if not candidates:
        return None
    return min(candidates)


def _latest_period(*periods):
    candidates = [p for p in periods if p is not None]
    if not candidates:
        return None
    return max(candidates)


def build_market_setup(
    market_phase_payload=None,
    survey_synthesis=None,
    rates_liquidity_payload=None,
    fomc_tone=None,
    m2_headline=None,
    inflation_context=None,
    fed_balance_sheet=None,
    ism_industry_analysis=None,
    consumer_sentiment_summary=None,
    housing_permits_signal=None,
    nfib_sbo_signal=None,
    claims_confirmation_qualifier=None,
):
    market_env = build_market_environment(market_phase_payload)
    consumer_demand_outlook = build_consumer_demand_outlook(consumer_sentiment_summary)
    expected_growth = build_expected_growth(survey_synthesis, consumer_demand_outlook)
    financial_conditions = build_financial_conditions(rates_liquidity_payload)
    policy_response = build_policy_response(
        fomc_tone, m2_headline, inflation_context, fed_balance_sheet
    )
    setup_type_result = classify_setup_type(
        market_env, expected_growth, financial_conditions, policy_response
    )
    reconciled_posture, posture_conflicts, posture_agreements = (
        reconcile_portfolio_posture(market_env, setup_type_result, expected_growth)
    )
    idea_gen = build_idea_generation_clues(ism_industry_analysis)

    all_agreements = list(setup_type_result.get("agreements", [])) + posture_agreements
    all_conflicts = list(setup_type_result.get("conflicts", [])) + posture_conflicts

    evidence_chain = build_evidence_chain(
        expected_growth, financial_conditions, policy_response
    )
    conviction_limits = build_conviction_limits(
        market_env,
        financial_conditions,
        policy_response,
        setup_type_result,
        expected_growth,
    )
    market_conclusion = build_market_conclusion(
        setup_type_result, market_env, reconciled_posture, expected_growth
    )
    portfolio_guidance = build_portfolio_guidance(reconciled_posture)
    confirmation_conditions = build_confirmation_conditions(
        setup_type_result, market_env
    )

    pending_confirmations = ["Labor trend"]
    if housing_permits_signal:
        hp_status = housing_permits_signal.get("status")
        hp_reason = housing_permits_signal.get("reason", "")
        if hp_status == "supports_growth_path":
            all_agreements.append(hp_reason)
        elif hp_status == "challenges_growth_path":
            all_conflicts.append(hp_reason)
        elif hp_status in ("awaiting_confirmation", "unavailable"):
            pending_confirmations.append(
                f"Housing permits — {hp_reason or 'awaiting confirmation'}"
            )
    else:
        pending_confirmations.append("Housing permits")

    if nfib_sbo_signal:
        nfib_status = nfib_sbo_signal.get("status")
        nfib_reason = nfib_sbo_signal.get("reason", "")
        if "nfib_sbo" not in expected_growth.get("evidence_links", []):
            expected_growth["evidence_links"].append("nfib_sbo")
        if nfib_status == "supports_growth_path":
            all_agreements.append(nfib_reason)
        elif nfib_status == "challenges_growth_path":
            all_conflicts.append(nfib_reason)
        elif nfib_status in ("awaiting_confirmation", "unavailable"):
            pending_confirmations.append(
                f"NFIB Small Business — {nfib_reason or 'awaiting confirmation'}"
            )
    else:
        pending_confirmations.append("NFIB Small Business")

    missing_inputs = []
    if market_env.get("data_status") == "missing":
        missing_inputs.append("Market phase (S&P 500)")
    if expected_growth.get("data_status") == "missing":
        missing_inputs.append("Survey synthesis (ISM Manufacturing and Services)")
    if financial_conditions.get("data_status") == "missing":
        missing_inputs.append("US rates and credit conditions")
    if policy_response.get("data_status") == "missing":
        missing_inputs.append("FOMC policy or M2 data")

    as_of = _oldest_period(
        market_env.get("observation_period"),
        expected_growth.get("observation_period"),
        financial_conditions.get("observation_period"),
        policy_response.get("observation_period"),
    )
    version = "market_setup_v1"

    return {
        "version": version,
        "status": "available" if not missing_inputs else "partial",
        "as_of": as_of,
        "market_environment": market_env,
        "expected_growth": expected_growth,
        "financial_conditions": financial_conditions,
        "policy_response": policy_response,
        "setup_type": setup_type_result["setup_type"],
        "portfolio_posture": reconciled_posture,
        "trade_implications": setup_type_result.get("trade_implications", []),
        "idea_generation": idea_gen,
        "agreements": all_agreements,
        "conflicts": all_conflicts,
        "market_conclusion": market_conclusion,
        "portfolio_guidance": portfolio_guidance,
        "evidence_chain": evidence_chain,
        "conviction_limits": conviction_limits,
        "confirmation_conditions": confirmation_conditions,
        "missing_inputs": missing_inputs,
        "pending_confirmations": pending_confirmations,
        "claims_confirmation_qualifier": claims_confirmation_qualifier,
        "limitations": [
            "This is a deterministic connection layer over method sections P2-P9. It does not calculate a numeric confidence score.",
            "Later-method leading-indicator modules may still change the outlook when implemented.",
        ],
    }
