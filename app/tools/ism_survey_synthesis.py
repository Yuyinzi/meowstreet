SURVEY_SYNTHESIS_VERSION = "ism_survey_synthesis_v1"

_UNUSABLE_MANUFACTURING = {"unavailable", "partial", None}
_UNUSABLE_SERVICES = {"pending_inputs", "stale_periods", None}


def _mfg_usable(signal):
    if signal is None:
        return False
    if signal.get("status") not in ("available",):
        return False
    metrics = signal.get("metrics", {})
    pmi = metrics.get("pmi", {})
    orders = metrics.get("new_orders", {})
    if pmi.get("level_state") is None or pmi.get("momentum") is None:
        return False
    if orders.get("level_state") is None or orders.get("momentum") is None:
        return False
    return True


def _svc_usable(signal):
    if signal is None:
        return False
    state = signal.get("state")
    if state in _UNUSABLE_SERVICES:
        return False
    metrics = signal.get("metrics", {})
    for key in ("pmi", "business_activity", "new_orders"):
        m = metrics.get(key)
        if m is None or m.get("level") is None or m.get("momentum") is None:
            return False
    return True


def _manufacturing_component(signal):
    if not _mfg_usable(signal):
        return {
            "status": "unavailable",
            "period": None,
            "level": None,
            "momentum": None,
            "demand_level": None,
            "demand_momentum": None,
            "growth_impulse": None,
        }
    metrics = signal.get("metrics", {})
    return {
        "status": "available",
        "period": signal.get("period"),
        "level": metrics["pmi"]["level_state"],
        "momentum": metrics["pmi"]["momentum"],
        "demand_level": metrics["new_orders"]["level_state"],
        "demand_momentum": metrics["new_orders"]["momentum"],
        "growth_impulse": signal.get("growth_impulse"),
    }


def _services_component(signal):
    if not _svc_usable(signal):
        return {
            "status": "unavailable",
            "period": None,
            "level": None,
            "momentum": None,
            "demand_level": None,
            "demand_momentum": None,
            "growth_impulse": None,
            "backlog_confirmation": None,
            "activity_level": None,
            "activity_momentum": None,
        }
    metrics = signal.get("metrics", {})
    return {
        "status": "available",
        "period": signal.get("period"),
        "level": metrics["pmi"]["level"],
        "momentum": metrics["pmi"]["momentum"],
        "demand_level": metrics["new_orders"]["level"],
        "demand_momentum": metrics["new_orders"]["momentum"],
        "growth_impulse": signal.get("state"),
        "backlog_confirmation": signal.get("backlog_confirmation"),
        "activity_level": metrics["business_activity"]["level"],
        "activity_momentum": metrics["business_activity"]["momentum"],
    }


def _economic_direction(comp):
    manufacturing = comp["manufacturing"]
    services = comp["services"]
    if manufacturing["level"] is None or services["level"] is None:
        return None
    levels = (manufacturing["level"], services["level"])
    if levels == ("expanding", "expanding"):
        return "aligned_expansion"
    if levels == ("contracting", "contracting"):
        return "aligned_contraction"
    if levels == ("neutral", "neutral"):
        return "aligned_neutral"
    return "divergent"


def _shared_momentum(comp):
    mfg_m = comp["manufacturing"]["momentum"]
    svc_m = comp["services"]["momentum"]
    if mfg_m is None or svc_m is None:
        return None
    if mfg_m == svc_m:
        return mfg_m
    return "mixed"


def _survey_alignment(comp):
    direction = _economic_direction(comp)
    if direction in ("aligned_expansion", "aligned_contraction", "aligned_neutral"):
        return "aligned"
    if direction == "divergent":
        return "divergent"
    return "unresolved"


def _demand_alignment(comp):
    mfg_level = comp["manufacturing"]["demand_level"]
    mfg_mom = comp["manufacturing"]["demand_momentum"]
    svc_level = comp["services"]["demand_level"]
    svc_mom = comp["services"]["demand_momentum"]
    if mfg_level is None or svc_level is None:
        return None
    if mfg_level == svc_level:
        if mfg_mom == svc_mom:
            return f"aligned_{mfg_mom}"
        return "mixed_momentum"
    return "divergent"


def _expected_gdp_direction(comp):
    direction = _economic_direction(comp)
    momentum = _shared_momentum(comp)
    demand = _demand_alignment(comp)
    if direction is None or momentum is None:
        return "mixed"
    if direction == "aligned_expansion" and momentum == "rising":
        if demand != "divergent":
            return "rising"
        return "mixed"
    if direction == "aligned_expansion" and momentum == "falling":
        return "slowing"
    if direction == "aligned_contraction" and momentum == "falling":
        return "falling"
    if direction == "aligned_contraction" and momentum == "rising":
        return "improving"
    if direction == "aligned_neutral" and momentum == "flat":
        return "stable"
    return "mixed"


def _survey_portfolio_implication(economic_direction):
    if economic_direction == "aligned_expansion":
        return "long"
    if economic_direction == "aligned_contraction":
        return "short_or_neutral"
    if economic_direction in {"aligned_neutral", "divergent"}:
        return "neutral"
    return None


def _bias_confirmation(economic_direction, shared_momentum):
    if economic_direction == "aligned_expansion" and shared_momentum == "falling":
        return "awaiting_confirmation"
    if economic_direction == "aligned_contraction" and shared_momentum == "rising":
        return "awaiting_confirmation"
    if economic_direction:
        return "not_required"
    return None


def _cross_sector_comparison(comp):
    mfg = comp["manufacturing"]
    svc = comp["services"]
    mfg_orders_level = mfg.get("demand_level")
    mfg_orders_mom = mfg.get("demand_momentum")
    svc_activity_level = svc.get("activity_level")
    svc_activity_mom = svc.get("activity_momentum")
    if mfg_orders_level is None or svc_activity_level is None:
        return None
    if mfg_orders_level == svc_activity_level:
        if mfg_orders_mom == svc_activity_mom:
            return "aligned"
        if mfg_orders_mom == "falling" and svc_activity_mom == "rising":
            return "services_stronger"
        if mfg_orders_mom == "rising" and svc_activity_mom == "falling":
            return "manufacturing_stronger"
        return "unresolved"
    if mfg_orders_level == "contracting" and svc_activity_level == "expanding":
        return "services_stronger"
    if mfg_orders_level == "expanding" and svc_activity_level == "contracting":
        return "manufacturing_stronger"
    return "unresolved"


def _leading_side(comp):
    comparison = _cross_sector_comparison(comp)
    if comparison is None:
        return "not_applicable"
    leading_side_by_relationship = {
        "aligned": "not_applicable",
        "services_stronger": "services",
        "manufacturing_stronger": "manufacturing",
        "unresolved": "unresolved",
    }
    return leading_side_by_relationship.get(comparison, "not_applicable")


def _agreements(comp, direction, demand):
    result = []
    mfg_level = comp["manufacturing"]["level"]
    svc_level = comp["services"]["level"]
    if mfg_level == svc_level and mfg_level == "expanding":
        result.append("Manufacturing and Services are both expanding")
    elif mfg_level == svc_level and mfg_level == "contracting":
        result.append("Manufacturing and Services are both contracting")
    elif mfg_level == svc_level and mfg_level == "neutral":
        result.append("Manufacturing and Services are both neutral")
    mfg_dm = comp["manufacturing"]["demand_momentum"]
    svc_dm = comp["services"]["demand_momentum"]
    if mfg_dm and svc_dm and mfg_dm == svc_dm and mfg_dm is not None:
        result.append(
            f"Manufacturing New Orders and Services New Orders are both {mfg_dm}"
        )
    return result


def _conflicts(comp, direction):
    result = []
    if direction == "divergent":
        mfg_label = comp["manufacturing"]["level"]
        svc_label = comp["services"]["level"]
        result.append(f"Manufacturing is {mfg_label} but Services is {svc_label}")
    return result


def _backlog_reason(backlog_confirmation):
    backlog_reason_by_state = {
        "supports_growth": "Services Order Backlog supports ongoing demand",
        "supports_contraction": "Services Order Backlog supports weaker demand",
        "neutral": "Services Order Backlog is neutral",
    }
    return backlog_reason_by_state.get(backlog_confirmation)


def _reasons(comp, direction, gdp_direction):
    result = []
    if direction in ("aligned_expansion",):
        result.append("Business surveys indicate broad expansion")
    elif direction in ("aligned_contraction",):
        result.append("Business surveys indicate broad contraction")
    elif direction == "aligned_neutral":
        result.append("Business surveys indicate neutral conditions")
    elif direction == "divergent":
        result.append(
            "Manufacturing and Services surveys are sending conflicting signals"
        )
    mfg_dl = comp["manufacturing"].get("demand_level")
    svc_dl = comp["services"].get("demand_level")
    mfg_dm = comp["manufacturing"]["demand_momentum"]
    svc_dm = comp["services"]["demand_momentum"]
    if mfg_dm and svc_dm and mfg_dm == svc_dm:
        if mfg_dm == "rising":
            result.append("Demand momentum is accelerating across both surveys")
        elif mfg_dm == "falling":
            if mfg_dl == "expanding" and svc_dl == "expanding":
                result.append(
                    "Demand remains expansionary but is slowing across both surveys"
                )
            elif mfg_dl == "contracting" and svc_dl == "contracting":
                result.append(
                    "Demand is contracting and continues to weaken across both surveys"
                )
            else:
                result.append("Demand is slowing across both surveys")
    elif mfg_dm and svc_dm and mfg_dm != svc_dm:
        result.append("Demand momentum differs between surveys")
    backlog_reason = _backlog_reason(
        comp.get("services", {}).get("backlog_confirmation")
    )
    if backlog_reason:
        result.append(backlog_reason)
    bc = _bias_confirmation(direction, _shared_momentum(comp))
    if bc == "awaiting_confirmation":
        if direction == "aligned_expansion":
            result.append(
                "Expansion remains intact; weaker one-period momentum is caution, not a confirmed reversal"
            )
        elif direction == "aligned_contraction":
            result.append(
                "Contraction remains intact; one-period improvement awaits confirmation"
            )
    return result


def build_survey_synthesis(manufacturing_signal, services_signal):
    comp = {
        "manufacturing": _manufacturing_component(manufacturing_signal),
        "services": _services_component(services_signal),
    }
    mfg_ok = comp["manufacturing"]["status"] == "available"
    svc_ok = comp["services"]["status"] == "available"

    if not mfg_ok and not svc_ok:
        missing = []
        if not mfg_ok:
            missing.append("ISM Manufacturing")
        if not svc_ok:
            missing.append("ISM Services")
        return {
            "version": SURVEY_SYNTHESIS_VERSION,
            "status": "partial",
            "period": None,
            "economic_direction": None,
            "growth_momentum": None,
            "survey_alignment": "unresolved",
            "demand_alignment": None,
            "leading_side": "not_applicable",
            "cross_sector_comparison": None,
            "expected_gdp_direction": None,
            "survey_portfolio_implication": None,
            "bias_confirmation": None,
            "backlog_confirmation": None,
            "components": comp,
            "agreements": [],
            "conflicts": [],
            "missing_inputs": missing,
            "pending_questions": [],
            "reasons": [],
        }

    if not mfg_ok:
        missing = ["ISM Manufacturing"]
        return {
            "version": SURVEY_SYNTHESIS_VERSION,
            "status": "partial",
            "period": comp["services"]["period"],
            "economic_direction": None,
            "growth_momentum": None,
            "survey_alignment": "unresolved",
            "demand_alignment": None,
            "leading_side": "not_applicable",
            "cross_sector_comparison": None,
            "expected_gdp_direction": None,
            "survey_portfolio_implication": None,
            "bias_confirmation": None,
            "backlog_confirmation": comp["services"]["backlog_confirmation"],
            "components": comp,
            "agreements": [],
            "conflicts": [],
            "missing_inputs": missing,
            "pending_questions": [],
            "reasons": [],
        }

    if not svc_ok:
        missing = ["ISM Services"]
        return {
            "version": SURVEY_SYNTHESIS_VERSION,
            "status": "partial",
            "period": comp["manufacturing"]["period"],
            "economic_direction": None,
            "growth_momentum": None,
            "survey_alignment": "unresolved",
            "demand_alignment": None,
            "leading_side": "not_applicable",
            "cross_sector_comparison": None,
            "expected_gdp_direction": None,
            "survey_portfolio_implication": None,
            "bias_confirmation": None,
            "backlog_confirmation": None,
            "components": comp,
            "agreements": [],
            "conflicts": [],
            "missing_inputs": missing,
            "pending_questions": [],
            "reasons": [],
        }

    mfg_period = comp["manufacturing"]["period"]
    svc_period = comp["services"]["period"]
    if mfg_period != svc_period:
        return {
            "version": SURVEY_SYNTHESIS_VERSION,
            "status": "mixed_periods",
            "period": None,
            "economic_direction": None,
            "growth_momentum": None,
            "survey_alignment": "unresolved",
            "demand_alignment": None,
            "leading_side": "not_applicable",
            "cross_sector_comparison": None,
            "expected_gdp_direction": None,
            "survey_portfolio_implication": None,
            "bias_confirmation": None,
            "backlog_confirmation": None,
            "components": comp,
            "agreements": [],
            "conflicts": ["Manufacturing and Services observation periods differ"],
            "missing_inputs": [],
            "pending_questions": [],
            "reasons": [],
        }

    direction = _economic_direction(comp)
    momentum = _shared_momentum(comp)
    alignment = _survey_alignment(comp)
    demand = _demand_alignment(comp)
    gdp_direction = _expected_gdp_direction(comp)
    implication = _survey_portfolio_implication(direction)
    bias_confirm = _bias_confirmation(direction, momentum)
    leading = _leading_side(comp)
    cross = _cross_sector_comparison(comp)

    return {
        "version": SURVEY_SYNTHESIS_VERSION,
        "status": "available",
        "period": mfg_period,
        "economic_direction": direction,
        "growth_momentum": momentum,
        "survey_alignment": alignment,
        "demand_alignment": demand,
        "leading_side": leading,
        "cross_sector_comparison": cross,
        "expected_gdp_direction": gdp_direction,
        "survey_portfolio_implication": implication,
        "bias_confirmation": bias_confirm,
        "backlog_confirmation": comp["services"].get("backlog_confirmation"),
        "components": comp,
        "agreements": _agreements(comp, direction, demand),
        "conflicts": _conflicts(comp, direction),
        "missing_inputs": [],
        "pending_questions": [],
        "reasons": _reasons(comp, direction, gdp_direction),
    }
