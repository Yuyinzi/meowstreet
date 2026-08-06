import json
from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "data" / "local_system" / "market_setup_input_registry.v1.json"

VALID_SCOPES = {
    "decision_input",
    "confirmation_input",
    "context_only",
    "observation_only",
    "manual_review",
    "experimental",
}

VALID_TARGET_LAYERS = {"macro_regime", "market_confirmation"}

DISPLAY_ONLY_EFFECT = "display_only"

EFFECTS_BY_LAYER = {
    "macro_regime": {"regime_selector", "supports", "conflicts"},
    "market_confirmation": {"confirmation_test", "offset"},
}

REGISTRY_RECORD_KEYS = {
    "fact_id",
    "decision_scope",
    "target_layers",
    "allowed_effects",
    "required_for_layer",
    "source_module",
    "method_version",
    "freshness_required",
}

MACRO_REGIME_VERSION = "market_setup_v2_macro_regime_v1"

_DIRECTION_TO_REGIME = {
    "rising": ("growth_accelerating", "Growth Accelerating"),
    "slowing": ("growth_decelerating", "Growth Decelerating"),
    "falling": ("contraction_risk_rising", "Contraction Risk Rising"),
    "improving": ("early_recovery", "Early Recovery"),
    "rebound_risk": ("early_recovery", "Early Recovery"),
    "stable": ("growth_stable", "Growth Stable"),
}

_SURVEY_MISSING_INPUT_LABEL = "ISM survey synthesis"

_FINDINGS = {
    "supports": "is consistent with the survey growth direction",
    "conflicts": "conflicts with the survey growth direction",
    "neutral": "does not clearly support or conflict with the survey growth direction",
    "unavailable": "is unavailable or stale for this decision",
}

_SOURCE_DISPLAY_NAMES = {
    "macro_financial_conditions": "Financial Conditions",
    "macro_policy_response": "Monetary Policy",
    "consumer_demand_outlook": "Consumer Demand Outlook",
}


def load_input_registry(path=REGISTRY_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_registry_payload(payload)


def validate_registry_payload(payload):
    if not isinstance(payload, dict) or "version" not in payload:
        raise ValueError("registry version is required")
    if "facts" not in payload:
        raise ValueError("registry facts are required")
    facts = payload["facts"]
    if not isinstance(facts, dict):
        raise ValueError("registry facts must be an object")
    seen = set()
    for fact_id, record in facts.items():
        if not isinstance(record, dict):
            raise ValueError(f"registry fact {fact_id} is not an object")
        missing_keys = sorted(REGISTRY_RECORD_KEYS - set(record))
        if missing_keys:
            raise ValueError(
                f"registry fact {fact_id} is missing required record keys: {', '.join(missing_keys)}"
            )
        record_fact_id = record["fact_id"]
        if record_fact_id in seen:
            raise ValueError(f"registry fact {record_fact_id} is duplicated")
        seen.add(record_fact_id)
        if record["decision_scope"] not in VALID_SCOPES:
            raise ValueError(
                f"registry fact {record_fact_id} has unknown decision scope: {record['decision_scope']}"
            )
        for layer in record["target_layers"]:
            if layer not in VALID_TARGET_LAYERS:
                raise ValueError(
                    f"registry fact {record_fact_id} has unknown target layer: {layer}"
                )
        for effect in record["allowed_effects"]:
            if effect == DISPLAY_ONLY_EFFECT:
                if record["target_layers"]:
                    raise ValueError(
                        f"effect {effect} is not allowed for target layers: {', '.join(record['target_layers'])}"
                    )
                continue
            for layer in record["target_layers"]:
                if effect not in EFFECTS_BY_LAYER.get(layer, set()):
                    raise ValueError(
                        f"effect {effect} is not allowed for target layer: {layer}"
                    )
        if record["required_for_layer"] and (
            DISPLAY_ONLY_EFFECT in record["allowed_effects"]
        ):
            raise ValueError(
                f"registry fact {record_fact_id} is display-only and cannot be required"
            )
        if record["required_for_layer"]:
            for layer in record["required_for_layer"]:
                if layer not in record["target_layers"]:
                    raise ValueError(
                        f"registry fact {record_fact_id} is required for a layer it does not target: {layer}"
                    )
    return payload


def _facts(payload):
    if payload is None:
        return {}
    facts = payload.get("facts", {})
    return facts if isinstance(facts, dict) else {}


def _find_fact(registry, payload, fact_id):
    facts = _facts(payload)
    return facts.get(fact_id)


def _fact_for_layer(registry, payload, fact_id, layer, effects):
    record = registry["facts"].get(fact_id)
    if record is None:
        return None
    if layer not in record["target_layers"]:
        return None
    if not (set(record["allowed_effects"]) & set(effects)):
        return None
    return _find_fact(registry, payload, fact_id)


def _is_valid_iso_date(value):
    if value is None:
        return False
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _effective_date(fact):
    if not isinstance(fact, dict):
        return None
    period = fact.get("source_period")
    if not isinstance(period, dict):
        return None
    effective = period.get("effective_date")
    if not _is_valid_iso_date(effective):
        return None
    return str(effective)


def _fact_is_fresh(fact):
    return _effective_date(fact) is not None


def _extract(registry, payload, fact_id, layer, effects):
    fact = _fact_for_layer(registry, payload, fact_id, layer, effects)
    if fact is None:
        return None
    if not _fact_is_fresh(fact):
        return None
    return fact


def _source_periods(*pairs):
    periods = {}
    for fact_id, fact in pairs:
        if isinstance(fact, dict):
            period = fact.get("source_period")
            if isinstance(period, dict):
                periods[fact_id] = period
    return periods


def _source_record(fact_id, finding):
    return {
        "source_id": fact_id,
        "finding": finding,
        "evidence_links": [fact_id],
    }


def _relationship_finding(fact_id, relationship):
    template = _FINDINGS.get(relationship, _FINDINGS["neutral"])
    display_name = _SOURCE_DISPLAY_NAMES.get(fact_id, fact_id.replace("_", " ").title())
    return _source_record(fact_id, f"{display_name} {template}")


def build_macro_regime(
    expected_growth,
    financial_conditions,
    policy_response,
    consumer_demand=None,
):
    registry = load_input_registry(REGISTRY_PATH)
    survey = _extract(
        registry,
        expected_growth,
        "survey_growth_direction",
        "macro_regime",
        ["regime_selector"],
    )
    direction = None
    if survey is not None:
        status = survey.get("status")
        if status not in ("partial", "mixed_periods", "unavailable"):
            candidate = survey.get("direction")
            if candidate in _DIRECTION_TO_REGIME:
                direction = candidate
    if direction is None:
        return {
            "code": "insufficient_data",
            "label": "Insufficient Macro Evidence",
            "primary_source": "ism_survey_synthesis",
            "supports": [],
            "conflicts": [],
            "missing_inputs": [_SURVEY_MISSING_INPUT_LABEL],
            "excluded_inputs": [],
            "method_version": MACRO_REGIME_VERSION,
            "source_periods": _source_periods(
                ("survey_growth_direction", survey),
                (
                    "macro_financial_conditions",
                    _extract(
                        registry,
                        financial_conditions,
                        "macro_financial_conditions",
                        "macro_regime",
                        ["supports", "conflicts"],
                    ),
                ),
                (
                    "macro_policy_response",
                    _extract(
                        registry,
                        policy_response,
                        "macro_policy_response",
                        "macro_regime",
                        ["supports", "conflicts"],
                    ),
                ),
                (
                    "consumer_demand_outlook",
                    _extract(
                        registry,
                        consumer_demand,
                        "consumer_demand_outlook",
                        "macro_regime",
                        ["supports", "conflicts"],
                    ),
                ),
            ),
        }

    code, label = _DIRECTION_TO_REGIME[direction]
    supports = []
    conflicts = []
    excluded_inputs = []
    period_pairs = [("survey_growth_direction", survey)]

    for fact_id, payload in (
        ("macro_financial_conditions", financial_conditions),
        ("macro_policy_response", policy_response),
        ("consumer_demand_outlook", consumer_demand),
    ):
        fact = _extract(
            registry,
            payload,
            fact_id,
            "macro_regime",
            ["supports", "conflicts"],
        )
        period_pairs.append((fact_id, fact))
        if fact is None:
            excluded_inputs.append(fact_id)
            continue
        relationship = fact.get("relationship_to_growth_direction")
        if relationship == "supports":
            supports.append(_relationship_finding(fact_id, relationship))
        elif relationship == "conflicts":
            conflicts.append(_relationship_finding(fact_id, relationship))
        else:
            excluded_inputs.append(fact_id)

    return {
        "code": code,
        "label": label,
        "primary_source": "ism_survey_synthesis",
        "supports": supports,
        "conflicts": conflicts,
        "missing_inputs": [],
        "excluded_inputs": excluded_inputs,
        "method_version": MACRO_REGIME_VERSION,
        "source_periods": _source_periods(*period_pairs),
    }


MARKET_CONFIRMATION_VERSION = "market_setup_v2_market_confirmation_v1"

_DOWNSIDE_REGIMES = {"growth_decelerating", "contraction_risk_rising"}
_UPSIDE_REGIMES = {"growth_accelerating", "early_recovery"}

_RISK_CREDIT_STATES = {
    "risk_rising",
    "crisis_stress",
    "stress",
    "risk_off",
    "serious_deterioration",
}

_SUPPORTIVE_CREDIT_STATES = {"healthy", "supportive"}

_NEUTRAL_CREDIT_STATES = {"weak_credit_warning", "mixed", "selective"}

_KNOWN_CREDIT_STATES = (
    _SUPPORTIVE_CREDIT_STATES | _RISK_CREDIT_STATES | _NEUTRAL_CREDIT_STATES
)

_VIX_STRESS_THRESHOLD = 20

_MARKET_CONFIRMATION_MISSING_LABELS = {
    "sp500_market_phase": "S&P 500 market phase",
    "credit_conditions": "credit conditions",
    "vix_level": "VIX",
}

_M2_OFFSET_STATUSES = {"expanding", "shock"}


def _direction_of_regime(macro_regime):
    code = (macro_regime or {}).get("code")
    if code in _DOWNSIDE_REGIMES:
        return "downside"
    if code in _UPSIDE_REGIMES:
        return "upside"
    if code == "growth_stable":
        return "stable"
    return None


def _credit_is_risk_state(status):
    return status in _RISK_CREDIT_STATES


def _vix_zone(vix):
    if vix is None:
        return None
    if vix >= _VIX_STRESS_THRESHOLD:
        return "stress"
    return "normal"


def _equity_trend_evidence(direction, phase):
    if direction == "downside":
        confirms = phase == "bear_market"
    else:
        confirms = phase == "bull_market"
    return {
        "state": phase,
        "confirms": confirms,
        "finding": (
            "S&P 500 market phase confirms the directional regime"
            if confirms
            else "S&P 500 market phase does not confirm the directional regime"
        ),
    }


def _credit_evidence(direction, status):
    if direction == "downside":
        confirms = _credit_is_risk_state(status)
    else:
        confirms = status in _SUPPORTIVE_CREDIT_STATES
    return {
        "state": status,
        "confirms": confirms,
        "finding": (
            "credit conditions confirm the directional regime"
            if confirms
            else "credit conditions do not confirm the directional regime"
        ),
    }


def _volatility_evidence(direction, vix):
    zone = _vix_zone(vix)
    if direction == "downside":
        confirms = zone == "stress"
    else:
        confirms = zone == "normal"
    return {
        "state": zone,
        "confirms": confirms,
        "finding": (
            "volatility confirms the directional regime"
            if confirms
            else "volatility does not confirm the directional regime"
        ),
    }


def _liquidity_evidence(m2_fact):
    status = m2_fact.get("status") if m2_fact else None
    return {
        "state": status,
        "confirms": status in _M2_OFFSET_STATUSES,
        "finding": (
            "M2 money supply is supportive of liquidity"
            if status in _M2_OFFSET_STATUSES
            else "M2 money supply is not a liquidity offset"
        ),
    }


def build_market_confirmation(
    macro_regime,
    market_environment,
    financial_conditions,
    policy_response,
):
    registry = load_input_registry(REGISTRY_PATH)
    direction = _direction_of_regime(macro_regime)
    if direction is None or direction == "stable":
        return {
            "code": "not_applicable",
            "label": "Confirmation Pending a Directional Regime",
            "confirmation_test_count": None,
            "evidence": {},
            "offsets": [],
            "missing_inputs": [],
            "method_version": MARKET_CONFIRMATION_VERSION,
            "source_periods": {},
        }

    phase_fact = _extract(
        registry,
        market_environment,
        "sp500_market_phase",
        "market_confirmation",
        ["confirmation_test"],
    )
    credit_fact = _extract(
        registry,
        financial_conditions,
        "credit_conditions",
        "market_confirmation",
        ["confirmation_test"],
    )
    vix_fact = _extract(
        registry,
        financial_conditions,
        "vix_level",
        "market_confirmation",
        ["confirmation_test"],
    )
    m2_fact = _extract(
        registry,
        policy_response,
        "m2_liquidity",
        "market_confirmation",
        ["offset"],
    )

    missing = []
    if phase_fact is None:
        missing.append(_MARKET_CONFIRMATION_MISSING_LABELS["sp500_market_phase"])
    if credit_fact is None:
        missing.append(_MARKET_CONFIRMATION_MISSING_LABELS["credit_conditions"])
    if vix_fact is None:
        missing.append(_MARKET_CONFIRMATION_MISSING_LABELS["vix_level"])

    phase = phase_fact.get("phase") if phase_fact else None
    credit_status = credit_fact.get("status") if credit_fact else None
    vix = vix_fact.get("level") if vix_fact else None

    if phase not in ("bull_market", "bear_market"):
        missing.append(_MARKET_CONFIRMATION_MISSING_LABELS["sp500_market_phase"])
    if credit_status not in _KNOWN_CREDIT_STATES:
        missing.append(_MARKET_CONFIRMATION_MISSING_LABELS["credit_conditions"])
    if vix is None:
        missing.append(_MARKET_CONFIRMATION_MISSING_LABELS["vix_level"])

    if missing:
        return {
            "code": "insufficient_data",
            "label": "Insufficient Market Confirmation Evidence",
            "confirmation_test_count": None,
            "evidence": {},
            "offsets": [],
            "missing_inputs": sorted(set(missing), key=_missing_sort_key),
            "method_version": MARKET_CONFIRMATION_VERSION,
            "source_periods": _source_periods(
                ("sp500_market_phase", phase_fact),
                ("credit_conditions", credit_fact),
                ("vix_level", vix_fact),
                ("m2_liquidity", m2_fact),
            ),
        }

    equity = _equity_trend_evidence(direction, phase)
    credit = _credit_evidence(direction, credit_status)
    volatility = _volatility_evidence(direction, vix)
    liquidity = _liquidity_evidence(m2_fact)

    test_count = sum(1 for record in (equity, credit, volatility) if record["confirms"])

    if direction == "downside":
        code = {
            3: "confirming_downside",
            2: "partially_confirming_downside",
            1: "partially_confirming_downside",
            0: "not_confirming_downside",
        }[test_count]
        label = {
            "confirming_downside": "Downside Broadly Confirmed",
            "partially_confirming_downside": "Downside Partially Confirmed",
            "not_confirming_downside": "Downside Not Broadly Confirmed",
        }[code]
    else:
        code = {
            3: "confirming_upside",
            2: "partially_confirming_upside",
            1: "partially_confirming_upside",
            0: "not_confirming_upside",
        }[test_count]
        label = {
            "confirming_upside": "Upside Broadly Confirmed",
            "partially_confirming_upside": "Upside Partially Confirmed",
            "not_confirming_upside": "Upside Not Broadly Confirmed",
        }[code]

    offsets = []
    if liquidity["confirms"]:
        offsets.append(
            {
                "id": "m2_liquidity_support",
                "finding": "M2 money supply is expanding or in shock, providing liquidity support",
                "evidence_links": ["m2_money_supply"],
            }
        )

    return {
        "code": code,
        "label": label,
        "confirmation_test_count": test_count,
        "evidence": {
            "equity_trend": equity,
            "credit": credit,
            "volatility": volatility,
            "liquidity": liquidity,
        },
        "offsets": offsets,
        "missing_inputs": [],
        "method_version": MARKET_CONFIRMATION_VERSION,
        "source_periods": _source_periods(
            ("sp500_market_phase", phase_fact),
            ("credit_conditions", credit_fact),
            ("vix_level", vix_fact),
            ("m2_liquidity", m2_fact),
        ),
    }


def _missing_sort_key(label):
    order = [
        "S&P 500 market phase",
        "credit conditions",
        "VIX",
    ]
    return order.index(label) if label in order else len(order)


MARKET_SETUP_VERSION = "market_setup_v2"
PORTFOLIO_POSTURE_VERSION = "market_setup_v2_portfolio_posture_v1"

_MARKET_SETUP_MATRIX = {
    ("growth_accelerating", "confirming_upside"): (
        "macro_improving_market_confirming",
        "Macro Improving, Market Confirming",
    ),
    ("growth_accelerating", "partially_confirming_upside"): (
        "macro_improving_partially_confirmed",
        "Macro Improving, Partially Confirmed",
    ),
    ("growth_accelerating", "not_confirming_upside"): (
        "macro_improving_price_not_confirming",
        "Macro Improving, Price Not Confirming",
    ),
    ("growth_decelerating", "confirming_downside"): (
        "macro_weakening_market_confirming",
        "Macro Weakening, Market Confirming",
    ),
    ("growth_decelerating", "partially_confirming_downside"): (
        "macro_weakening_partially_confirmed",
        "Macro Weakening, Partially Confirmed",
    ),
    ("growth_decelerating", "not_confirming_downside"): (
        "macro_weakening_price_not_confirming",
        "Macro Weakening, Price Not Confirming",
    ),
    ("contraction_risk_rising", "confirming_downside"): (
        "macro_weakening_market_confirming",
        "Macro Weakening, Market Confirming",
    ),
    ("contraction_risk_rising", "partially_confirming_downside"): (
        "macro_weakening_partially_confirmed",
        "Macro Weakening, Partially Confirmed",
    ),
    ("contraction_risk_rising", "not_confirming_downside"): (
        "macro_weakening_price_not_confirming",
        "Macro Weakening, Price Not Confirming",
    ),
    ("early_recovery", "confirming_upside"): (
        "early_recovery_confirmed",
        "Early Recovery, Market Confirming",
    ),
    ("early_recovery", "partially_confirming_upside"): (
        "early_recovery_partially_confirmed",
        "Early Recovery, Partially Confirmed",
    ),
    ("early_recovery", "not_confirming_upside"): (
        "early_recovery_price_not_confirming",
        "Early Recovery, Price Not Confirming",
    ),
    ("growth_stable", "not_applicable"): (
        "mixed_or_transition",
        "Mixed or Transitioning Environment",
    ),
}

_INTERPRETATIONS = {
    "macro_improving_market_confirming": "Economic expectations are improving and market pricing broadly confirms the upside environment.",
    "macro_improving_partially_confirmed": "Economic expectations are improving, with partial confirmation from market pricing.",
    "macro_improving_price_not_confirming": "Economic expectations are improving, but market pricing does not yet broadly confirm the upside environment.",
    "macro_weakening_market_confirming": "Macro downside risk is rising and market pricing broadly confirms a risk-off environment.",
    "macro_weakening_partially_confirmed": "Macro downside risk is rising, with partial confirmation from market pricing.",
    "macro_weakening_price_not_confirming": "Macro downside risk is rising, but market prices do not yet validate a broad risk-off setup.",
    "early_recovery_confirmed": "Economic expectations indicate an early recovery and market pricing broadly confirms the upside transition.",
    "early_recovery_partially_confirmed": "Economic expectations indicate an early recovery, with partial confirmation from market pricing.",
    "early_recovery_price_not_confirming": "Economic expectations indicate an early recovery, but market pricing does not yet confirm the transition.",
    "mixed_or_transition": "The macro-market relationship does not currently support a clear directional environment.",
    "insufficient_data": "Required evidence is missing or stale, so a complete market setup cannot be determined.",
}

_PORTFOLIO_POSTURE_MATRIX = {
    "macro_improving_market_confirming": {
        "code": "risk_on",
        "label": "Risk-On",
        "net_exposure": "long",
        "gross_exposure": "normal",
        "implementation": "broad_and_selective_positions",
        "broad_beta": "permitted_with_risk_controls",
        "positioning": [
            "maintain_long_net_exposure",
            "use_normal_position_sizing",
            "allow_broad_and_selective_positions",
        ],
        "avoid": [
            "ignoring_risk_controls",
            "adding_leverage_without_position_limits",
        ],
    },
    "macro_improving_partially_confirmed": {
        "code": "mild_risk_on",
        "label": "Mild Risk-On",
        "net_exposure": "modest_long",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_modest_long_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "macro_improving_price_not_confirming": {
        "code": "neutral_selective",
        "label": "Neutral / Selective",
        "net_exposure": "neutral",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_neutral_net_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "macro_weakening_market_confirming": {
        "code": "defensive",
        "label": "Defensive",
        "net_exposure": "reduced",
        "gross_exposure": "reduced",
        "implementation": "defensive_or_hedged_positions",
        "broad_beta": "avoid_long_broad_beta",
        "positioning": [
            "maintain_reduced_net_exposure",
            "use_reduced_position_sizing",
            "prefer_defensive_or_hedged_positions",
        ],
        "avoid": [
            "large_directional_long_exposure",
            "unhedged_broad_beta_exposure",
            "increasing_leverage_during_confirmed_risk_off",
        ],
    },
    "macro_weakening_partially_confirmed": {
        "code": "mild_risk_off",
        "label": "Mild Risk-Off",
        "net_exposure": "modest_defensive",
        "gross_exposure": "moderate",
        "implementation": "selective_defensive_positions",
        "broad_beta": "reduce_large_directional_exposure",
        "positioning": [
            "maintain_modest_defensive_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_defensive_positions",
        ],
        "avoid": [
            "large_directional_long_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "macro_weakening_price_not_confirming": {
        "code": "neutral_selective",
        "label": "Neutral / Selective",
        "net_exposure": "neutral",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_neutral_net_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "early_recovery_partially_confirmed": {
        "code": "mild_risk_on",
        "label": "Mild Risk-On",
        "net_exposure": "modest_long",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_modest_long_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "early_recovery_confirmed": {
        "code": "mild_risk_on",
        "label": "Mild Risk-On",
        "net_exposure": "modest_long",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_modest_long_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "early_recovery_price_not_confirming": {
        "code": "neutral_selective",
        "label": "Neutral / Selective",
        "net_exposure": "neutral",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_neutral_net_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "mixed_or_transition": {
        "code": "neutral_selective",
        "label": "Neutral / Selective",
        "net_exposure": "neutral",
        "gross_exposure": "moderate",
        "implementation": "selective_positions",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_neutral_net_exposure",
            "use_moderate_position_sizing",
            "prefer_selective_positions",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_confirmation",
        ],
    },
    "insufficient_data": {
        "code": "insufficient_data",
        "label": "Insufficient Data",
        "net_exposure": "neutral",
        "gross_exposure": "reduced",
        "implementation": "no_new_directional_exposure",
        "broad_beta": "avoid_large_directional_exposure",
        "positioning": [
            "maintain_neutral_net_exposure",
            "use_reduced_position_sizing",
            "defer_new_directional_exposure",
        ],
        "avoid": [
            "large_broad_beta_directional_exposure",
            "increasing_leverage_without_complete_evidence",
        ],
    },
}


def build_market_setup(macro_regime, market_confirmation):
    regime_code = macro_regime.get("code")
    confirmation_code = market_confirmation.get("code")
    if regime_code == "insufficient_data" or confirmation_code == "insufficient_data":
        return {
            "code": "insufficient_data",
            "label": "Insufficient Data",
            "agreement": "incomplete",
        }
    matrix_key = (regime_code, confirmation_code)
    if matrix_key in _MARKET_SETUP_MATRIX:
        code, label = _MARKET_SETUP_MATRIX[matrix_key]
    else:
        return {
            "code": "insufficient_data",
            "label": "Insufficient Data",
            "agreement": "incomplete",
        }
    return {
        "code": code,
        "label": label,
        "agreement": _market_setup_agreement(macro_regime, market_confirmation),
    }


def _market_setup_agreement(macro_regime, market_confirmation):
    count = market_confirmation.get("confirmation_test_count")
    if count == 3:
        return "aligned"
    if count in (1, 2):
        return "mixed"
    if count == 0:
        return "conflicting"
    return "mixed"


_POSTURE_ACTION_LABELS = {
    "maintain_long_net_exposure": "Maintain long net exposure",
    "use_normal_position_sizing": "Use normal position sizing",
    "allow_broad_and_selective_positions": "Allow broad and selective positions",
    "maintain_modest_long_exposure": "Maintain modest long exposure",
    "use_moderate_position_sizing": "Use moderate position sizing",
    "prefer_selective_positions": "Prefer selective positions",
    "maintain_neutral_net_exposure": "Maintain neutral net exposure",
    "maintain_reduced_net_exposure": "Maintain reduced net exposure",
    "use_reduced_position_sizing": "Use reduced position sizing",
    "prefer_defensive_or_hedged_positions": "Prefer defensive or hedged positions",
    "maintain_modest_defensive_exposure": "Maintain modest defensive exposure",
    "prefer_selective_defensive_positions": "Prefer selective defensive positions",
    "defer_new_directional_exposure": "Defer new directional exposure",
    "ignoring_risk_controls": "Ignoring risk controls",
    "adding_leverage_without_position_limits": "Adding leverage without position limits",
    "large_broad_beta_directional_exposure": "Large broad-beta directional exposure",
    "increasing_leverage_without_confirmation": "Increasing leverage without confirmation",
    "large_directional_long_exposure": "Large directional long exposure",
    "unhedged_broad_beta_exposure": "Unhedged broad-beta exposure",
    "increasing_leverage_during_confirmed_risk_off": "Increasing leverage during a confirmed risk-off",
    "increasing_leverage_without_complete_evidence": "Increasing leverage without complete evidence",
}


def _posture_actions(codes):
    return [
        {
            "code": code,
            "label": _POSTURE_ACTION_LABELS.get(code, code.replace("_", " ").title()),
        }
        for code in codes
    ]


def build_portfolio_posture(market_setup):
    config = _PORTFOLIO_POSTURE_MATRIX.get(
        market_setup.get("code"), _PORTFOLIO_POSTURE_MATRIX["insufficient_data"]
    )
    posture = dict(config, method_version=PORTFOLIO_POSTURE_VERSION)
    posture["positioning"] = _posture_actions(config["positioning"])
    posture["avoid"] = _posture_actions(config["avoid"])
    return posture


_TRIGGER_DEFS = {
    "sp500_market_phase_change": {
        "condition_ref": "market_phase_v1",
        "effect": "recompute Market Confirmation",
    },
    "credit_conditions_risk_state": {
        "condition_ref": "credit_conditions_v1",
        "effect": "recompute Market Confirmation",
    },
    "vix_stress_threshold": {
        "condition_ref": "vix_confirmation_v2",
        "effect": "recompute Market Confirmation",
    },
    "ism_survey_direction_change": {
        "condition_ref": "ism_survey_synthesis_v1",
        "effect": "recompute Macro Regime",
    },
}

_CONFIRMATION_MARKET_TRIGGERS = (
    "sp500_market_phase_change",
    "credit_conditions_risk_state",
    "vix_stress_threshold",
)

_TRIGGER_FACT_IDS = {
    "sp500_market_phase_change": "sp500_market_phase",
    "credit_conditions_risk_state": "credit_conditions",
    "vix_stress_threshold": "vix_level",
    "ism_survey_direction_change": "survey_growth_direction",
}

_OBSERVATION_WATCH_ITEMS = {
    "equity_breadth": "Equity breadth",
    "jobless_claims": "Jobless claims",
}

_TRIGGER_STATE_LABELS = {
    "bull_market": "bull market",
    "bear_market": "bear market",
    "healthy": "healthy",
    "supportive": "supportive",
    "weak_credit_warning": "weak credit warning",
    "mixed": "mixed",
    "selective": "selective",
    "risk_rising": "risk rising",
    "crisis_stress": "crisis stress",
    "stress": "stressed",
    "risk_off": "risk off",
    "serious_deterioration": "serious deterioration",
    "stress_zone": "stress",
    "normal": "normal",
    "rising": "rising",
    "slowing": "slowing",
    "falling": "falling",
    "improving": "improving",
    "rebound_risk": "rebound risk",
    "stable": "stable",
}


def _trigger_state_label(value):
    return _TRIGGER_STATE_LABELS.get(str(value))


def _trigger_label(trigger_id, fact):
    if trigger_id == "sp500_market_phase_change":
        return f"S&P 500 market phase changes from {_trigger_state_label(fact.get('phase'))}"
    if trigger_id == "credit_conditions_risk_state":
        return (
            f"Credit Conditions changes from {_trigger_state_label(fact.get('status'))}"
        )
    if trigger_id == "vix_stress_threshold":
        zone = _vix_zone(fact.get("level"))
        return f"VIX crosses the approved confirmation threshold from {_trigger_state_label(zone)}"
    if trigger_id == "ism_survey_direction_change":
        return f"ISM survey direction changes from {_trigger_state_label(fact.get('direction'))}"
    return ""


def _build_triggers(
    registry, macro_regime, expected_growth, market_environment, financial_conditions
):
    regime_code = macro_regime.get("code")
    direction = _direction_of_regime(macro_regime)
    triggers = []
    survey = _extract(
        registry,
        expected_growth,
        "survey_growth_direction",
        "macro_regime",
        ["regime_selector"],
    )
    phase = _extract(
        registry,
        market_environment,
        "sp500_market_phase",
        "market_confirmation",
        ["confirmation_test"],
    )
    credit = _extract(
        registry,
        financial_conditions,
        "credit_conditions",
        "market_confirmation",
        ["confirmation_test"],
    )
    vix = _extract(
        registry,
        financial_conditions,
        "vix_level",
        "market_confirmation",
        ["confirmation_test"],
    )

    if direction == "stable":
        if survey is not None and _fact_value_is_valid(
            "survey_growth_direction", survey
        ):
            triggers.append(
                {
                    "id": "ism_survey_direction_change",
                    "label": _trigger_label("ism_survey_direction_change", survey),
                    "condition_ref": _TRIGGER_DEFS["ism_survey_direction_change"][
                        "condition_ref"
                    ],
                    "effect": _TRIGGER_DEFS["ism_survey_direction_change"]["effect"],
                }
            )
        return triggers

    if direction is None:
        return []

    facts = {
        "sp500_market_phase_change": phase,
        "credit_conditions_risk_state": credit,
        "vix_stress_threshold": vix,
    }
    for trigger_id in _CONFIRMATION_MARKET_TRIGGERS:
        fact = facts[trigger_id]
        if fact is None:
            continue
        if not _fact_value_is_valid(_TRIGGER_FACT_IDS[trigger_id], fact):
            continue
        triggers.append(
            {
                "id": trigger_id,
                "label": _trigger_label(trigger_id, fact),
                "condition_ref": _TRIGGER_DEFS[trigger_id]["condition_ref"],
                "effect": _TRIGGER_DEFS[trigger_id]["effect"],
            }
        )
    if survey is not None and _fact_value_is_valid("survey_growth_direction", survey):
        triggers.append(
            {
                "id": "ism_survey_direction_change",
                "label": _trigger_label("ism_survey_direction_change", survey),
                "condition_ref": _TRIGGER_DEFS["ism_survey_direction_change"][
                    "condition_ref"
                ],
                "effect": _TRIGGER_DEFS["ism_survey_direction_change"]["effect"],
            }
        )
    return triggers


def _build_watch_items(
    registry,
    macro_regime,
    market_environment,
    financial_conditions,
    observation_only=None,
):
    direction = _direction_of_regime(macro_regime)
    watch_items = []
    if direction == "stable":
        phase = _extract(
            registry,
            market_environment,
            "sp500_market_phase",
            "market_confirmation",
            ["confirmation_test"],
        )
        credit = _extract(
            registry,
            financial_conditions,
            "credit_conditions",
            "market_confirmation",
            ["confirmation_test"],
        )
        vix = _extract(
            registry,
            financial_conditions,
            "vix_level",
            "market_confirmation",
            ["confirmation_test"],
        )
        stable_watch = [
            ("S&P 500 market phase", phase),
            ("Credit Conditions", credit),
            ("VIX", vix),
        ]
        for label, fact in stable_watch:
            if fact is None:
                continue
            watch_items.append(
                {
                    "id": label.lower().replace(" ", "_"),
                    "label": label,
                    "source_id": _source_id_for_watch(label),
                    "reason": "cannot change the current not_applicable confirmation state",
                    "decision_effect": "none",
                }
            )
    for fact_id, record in (observation_only or {}).items():
        if not isinstance(record, dict):
            continue
        watch_items.append(
            {
                "id": fact_id,
                "label": _watch_label(fact_id),
                "source_id": fact_id,
                "reason": "observation evidence without a defined decision effect",
                "decision_effect": "none",
            }
        )
    return watch_items


def _source_id_for_watch(label):
    return {
        "S&P 500 market phase": "sp500_market_phase",
        "Credit Conditions": "credit_conditions",
        "VIX": "vix_level",
    }.get(label, label.lower().replace(" ", "_"))


def _watch_label(fact_id):
    return _OBSERVATION_WATCH_ITEMS.get(fact_id, fact_id.replace("_", " ").title())


def _required_fact_states(
    registry, expected_growth, market_environment, financial_conditions, regime_code
):
    survey = _extract(
        registry,
        expected_growth,
        "survey_growth_direction",
        "macro_regime",
        ["regime_selector"],
    )
    required = [("survey_growth_direction", survey)]
    if regime_code != "growth_stable":
        phase = _extract(
            registry,
            market_environment,
            "sp500_market_phase",
            "market_confirmation",
            ["confirmation_test"],
        )
        credit = _extract(
            registry,
            financial_conditions,
            "credit_conditions",
            "market_confirmation",
            ["confirmation_test"],
        )
        vix = _extract(
            registry,
            financial_conditions,
            "vix_level",
            "market_confirmation",
            ["confirmation_test"],
        )
        required.extend(
            [
                ("sp500_market_phase", phase),
                ("credit_conditions", credit),
                ("vix_level", vix),
            ]
        )
    return required


_MISSING_LABELS = {
    "survey_growth_direction": "ISM survey synthesis",
    "sp500_market_phase": "S&P 500 market phase",
    "credit_conditions": "credit conditions",
    "vix_level": "VIX",
}

_MISSING_ORDER = [
    "ISM survey synthesis",
    "S&P 500 market phase",
    "credit conditions",
    "VIX",
]


def _missing_inputs(
    registry, expected_growth, market_environment, financial_conditions, regime_code
):
    required = _required_fact_states(
        registry,
        expected_growth,
        market_environment,
        financial_conditions,
        regime_code,
    )
    missing = []
    for fact_id, fact in required:
        label = _MISSING_LABELS[fact_id]
        if fact is None or not _fact_value_is_valid(fact_id, fact):
            missing.append(label)
    ordered = sorted(set(missing), key=lambda label: _MISSING_ORDER.index(label))
    return ordered


def _fact_value_is_valid(fact_id, fact):
    value = _fact_value(fact_id, fact)
    if fact_id == "survey_growth_direction":
        return value in _DIRECTION_TO_REGIME
    if fact_id == "sp500_market_phase":
        return value in ("bull_market", "bear_market")
    if fact_id == "credit_conditions":
        return value in _KNOWN_CREDIT_STATES
    if fact_id == "vix_level":
        return value is not None
    return True


def _fact_value(fact_id, fact):
    key = {
        "survey_growth_direction": "direction",
        "sp500_market_phase": "phase",
        "credit_conditions": "status",
        "vix_level": "level",
    }.get(fact_id)
    return fact.get(key) if key else None


def _evidence_through(
    registry, expected_growth, market_environment, financial_conditions, regime_code
):
    required = _required_fact_states(
        registry,
        expected_growth,
        market_environment,
        financial_conditions,
        regime_code,
    )
    dates = []
    for fact_id, fact in required:
        if fact is None:
            return None
        effective = _effective_date(fact)
        if effective is None:
            return None
        dates.append(effective)
    if not dates:
        return None
    return min(dates)


def build_market_setup_v2(
    expected_growth=None,
    market_environment=None,
    financial_conditions=None,
    policy_response=None,
    consumer_demand=None,
    observation_only=None,
    context_only=None,
    manual_review=None,
):
    registry = load_input_registry(REGISTRY_PATH)
    macro_regime = build_macro_regime(
        expected_growth,
        financial_conditions,
        policy_response,
        consumer_demand,
    )
    market_confirmation = build_market_confirmation(
        macro_regime,
        market_environment,
        financial_conditions,
        policy_response,
    )
    market_setup = build_market_setup(macro_regime, market_confirmation)
    portfolio_posture = build_portfolio_posture(market_setup)

    regime_code = macro_regime.get("code")
    missing_inputs = _missing_inputs(
        registry,
        expected_growth,
        market_environment,
        financial_conditions,
        regime_code,
    )
    evidence_through = _evidence_through(
        registry,
        expected_growth,
        market_environment,
        financial_conditions,
        regime_code,
    )

    macro_supports = list(macro_regime.get("supports", []))
    macro_conflicts = list(macro_regime.get("conflicts", []))
    supports = macro_supports
    conflicts = macro_conflicts
    offsets = list(market_confirmation.get("offsets", []))

    excluded_inputs = list(macro_regime.get("excluded_inputs", []))
    for extra in (observation_only, context_only, manual_review):
        if extra:
            excluded_inputs.extend(fact_id for fact_id in extra)

    next_triggers = _build_triggers(
        registry,
        macro_regime,
        expected_growth,
        market_environment,
        financial_conditions,
    )
    watch_items = _build_watch_items(
        registry,
        macro_regime,
        market_environment,
        financial_conditions,
        observation_only=observation_only,
    )

    method_versions = {
        "macro_regime": macro_regime.get("method_version"),
        "market_confirmation": market_confirmation.get("method_version"),
        "market_setup": MARKET_SETUP_VERSION,
        "portfolio_posture": portfolio_posture.get("method_version"),
    }

    return {
        "version": MARKET_SETUP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence_through": evidence_through,
        "macro_regime": macro_regime,
        "market_confirmation": market_confirmation,
        "market_setup": market_setup,
        "portfolio_posture": portfolio_posture,
        "interpretation": _INTERPRETATIONS.get(
            market_setup.get("code"), _INTERPRETATIONS["insufficient_data"]
        ),
        "supports": supports,
        "conflicts": conflicts,
        "offsets": offsets,
        "excluded_inputs": excluded_inputs,
        "method_versions": method_versions,
        "missing_inputs": missing_inputs,
        "next_triggers": next_triggers,
        "watch_items": watch_items,
    }
