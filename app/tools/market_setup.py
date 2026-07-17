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


def build_expected_growth(ism_macro_signal, growth_cycle_bias_evidence):
    cycle_state = _ism_cycle_state(ism_macro_signal)
    if cycle_state is None or cycle_state == "unavailable":
        return {
            "state": "unavailable",
            "expected_gdp_direction": None,
            "initial_bias": "neutral",
            "reason": "ISM macro signal is not available",
            "evidence_links": ["ism_manufacturing"],
            "source_module": "ism_macro_signal",
            "observation_period": _ism_period(ism_macro_signal),
            "data_status": "missing",
        }
    mapping = _ISM_EXPECTED_GDP_MAP.get(cycle_state)
    if mapping is None:
        return {
            "state": "unresolved",
            "expected_gdp_direction": "mixed",
            "initial_bias": "neutral",
            "reason": f"ISM cycle state '{cycle_state}' does not map to a clear GDP direction",
            "evidence_links": ["ism_manufacturing"],
            "source_module": "ism_macro_signal",
            "observation_period": _ism_period(ism_macro_signal),
            "data_status": "partial",
        }
    direction, initial_bias, base_reason = mapping
    growth_impulse = (
        ism_macro_signal.get("growth_impulse", "unavailable")
        if ism_macro_signal
        else "unavailable"
    )
    return {
        "state": cycle_state,
        "expected_gdp_direction": direction,
        "initial_bias": initial_bias,
        "growth_impulse": growth_impulse,
        "reason": base_reason,
        "evidence_links": ["ism_manufacturing"],
        "source_module": "ism_macro_signal",
        "observation_period": _ism_period(ism_macro_signal),
        "data_status": "available",
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

    if market_state == "bull_market" and base_posture in ("short_or_neutral",):
        conflicts.append(
            "Bull market phase conflicts with contraction setup — reconciled to neutral posture"
        )
        return "neutral", conflicts, agreements

    if market_state == "bear_market" and base_posture in ("long", "neutral_to_long"):
        conflicts.append(
            "Bear market phase conflicts with expansion setup — reconciled to neutral posture"
        )
        return "neutral", conflicts, agreements

    return base_posture, conflicts, agreements


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
    ism_macro_signal=None,
    growth_cycle_bias_evidence=None,
    rates_liquidity_payload=None,
    fomc_tone=None,
    m2_headline=None,
    inflation_context=None,
    fed_balance_sheet=None,
    ism_industry_analysis=None,
):
    market_env = build_market_environment(market_phase_payload)
    expected_growth = build_expected_growth(
        ism_macro_signal, growth_cycle_bias_evidence
    )
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

    missing_inputs = []
    if market_env.get("data_status") == "missing":
        missing_inputs.append("Market phase (S&P 500)")
    if expected_growth.get("data_status") == "missing":
        missing_inputs.append("ISM manufacturing signal")
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
        "missing_inputs": missing_inputs,
        "pending_confirmations": ["ISM Services", "Labor trend", "Consumer indicators"],
        "limitations": [
            "This is a deterministic connection layer over Methods P2-P7. It does not calculate a numeric confidence score.",
            "Later-method indicators (ISM Services, labor, consumer) may change the outlook when implemented.",
        ],
    }
