_VALID_TOPICS = frozenset({"current", "drivers", "method", "source"})

_SURVEY_CURRENT_KEYS = (
    "economic_direction",
    "growth_momentum",
    "survey_alignment",
    "demand_alignment",
    "leading_side",
    "cross_sector_comparison",
    "bias_confirmation",
    "backlog_confirmation",
)

_SURVEY_DRIVER_KEYS = ("agreements", "conflicts", "missing_inputs", "reasons")

_FINANCIAL_CURRENT_KEYS = ("state", "growth_confirmation")

_FINANCIAL_DETAIL_KEYS = (
    "curve_status",
    "credit_conditions_status",
    "vix",
    "ten_year_real_rate",
)

_POLICY_CURRENT_KEYS = (
    "policy_action",
    "guidance_bias",
    "language_tone",
    "overall_bias",
    "tone_change",
    "confidence",
)

_POLICY_DETAIL_KEYS = (
    "fomc_tone",
    "fomc_action",
    "m2_status",
    "inflation_above_target",
    "fed_balance_sheet_available",
)

_CONSUMER_CURRENT_KEYS = (
    "state",
    "direction",
    "percentile_zone",
    "momentum",
    "percentile_label",
    "confirmation_state",
)

_PHASE_CURRENT_KEYS = ("state", "starting_posture", "reason")

_SOURCE_KEYS = ("source_module", "source_id", "source_period", "method_references")


def project_evidence_detail(fact, record, topics, method_contracts):
    _validate_inputs(fact, record, topics, method_contracts)
    if record["detail_kind"] == "unsupported":
        return _unsupported_result(fact, record, topics)
    state = _fact_state(fact)
    if state != "available":
        return _non_available_result(fact, record, topics, state)
    builder = _PROJECTION_BUILDERS.get(record["detail_kind"])
    if builder is None:
        raise ValueError(
            f"evidence detail projection is not registered: {record['detail_kind']}"
        )
    return _compose(builder(fact, record, method_contracts), fact, record, topics)


def _validate_inputs(fact, record, topics, method_contracts):
    if not isinstance(record, dict) or not record.get("fact_id"):
        raise ValueError("evidence detail record is required")
    if not isinstance(topics, list) or not topics:
        raise ValueError("evidence detail topics are required")
    if any(not isinstance(topic, str) or not topic for topic in topics):
        raise ValueError("evidence detail topics are required")
    if len(topics) != len(set(topics)):
        raise ValueError("evidence detail topics are duplicated")
    for topic in topics:
        if topic not in _VALID_TOPICS:
            raise ValueError(f"evidence detail topic is unknown: {topic}")
    if not isinstance(method_contracts, dict):
        raise ValueError("evidence detail method contracts are required")
    if fact is not None and not isinstance(fact, dict):
        raise ValueError("evidence detail fact is required")


def _base_result(fact, record, topics, status):
    label = ""
    if isinstance(fact, dict) and fact.get("label"):
        label = fact["label"]
    return {
        "fact_id": record["fact_id"],
        "label": label,
        "detail_kind": record["detail_kind"],
        "topics": list(topics),
        "status": status,
    }


def _unsupported_result(fact, record, topics):
    result = _base_result(fact, record, topics, "unsupported")
    result["supported_topics"] = []
    return result


def _non_available_result(fact, record, topics, state):
    result = _base_result(fact, record, topics, state)
    reason = _reason_code(fact)
    if reason is not None:
        result["reason"] = reason
    if "source" in topics and isinstance(fact, dict):
        source = _source_projection(fact)
        if source:
            result["source"] = source
    return result


def _compose(payloads, fact, record, topics):
    result = _base_result(fact, record, topics, "available")
    supported = set(record.get("supported_topics") or [])
    for topic in topics:
        if topic in supported and topic in payloads:
            result[topic] = payloads[topic]
    return result


def _fact_state(fact):
    if not isinstance(fact, dict):
        return "missing"
    data_status = fact.get("data_status")
    if not isinstance(data_status, dict):
        return "missing"
    return data_status.get("state", "missing")


def _reason_code(fact):
    if not isinstance(fact, dict):
        return None
    participation = fact.get("participation")
    if isinstance(participation, dict) and participation.get("reason_code") is not None:
        return participation["reason_code"]
    finding = fact.get("finding")
    if isinstance(finding, dict) and finding.get("reason_code") is not None:
        return finding["reason_code"]
    return None


def _source_projection(fact):
    provenance = fact.get("provenance")
    if not isinstance(provenance, dict):
        return {}
    return {key: provenance[key] for key in _SOURCE_KEYS if key in provenance}


def _method_projection(fact, method_contracts):
    provenance = fact.get("provenance")
    references = (
        list(provenance["method_references"])
        if isinstance(provenance, dict)
        and isinstance(provenance.get("method_references"), list)
        else []
    )
    projection = {"method_references": references}
    contracts = _matching_method_contracts(fact.get("fact_id"), method_contracts)
    if contracts:
        projection["method_contracts"] = contracts
    return projection


def _matching_method_contracts(fact_id, method_contracts):
    methods = method_contracts.get("methods")
    if not isinstance(methods, dict):
        return []
    matches = []
    for method_id, method in methods.items():
        if not isinstance(method, dict) or method.get("kind") != "predicate_method":
            continue
        decision_contract = method.get("decision_contract")
        if not isinstance(decision_contract, dict):
            continue
        input_contract = decision_contract.get("input_contract")
        if not isinstance(input_contract, dict):
            continue
        if input_contract.get("fact_id") != fact_id:
            continue
        entry = {"method_id": method_id}
        entry.update(method)
        matches.append(entry)
    return matches


def _pick(payload, keys):
    return {key: payload[key] for key in keys if payload.get(key) is not None}


def _survey_synthesis_detail(fact, record, method_contracts):
    explanation = fact.get("explanation") or {}
    accepted = fact.get("accepted_values") or {}
    current = _pick(explanation, _SURVEY_CURRENT_KEYS)
    if accepted.get("direction") is not None:
        current["direction"] = accepted["direction"]
    drivers = _pick(explanation, _SURVEY_DRIVER_KEYS)
    return {
        "current": current,
        "drivers": drivers,
        "source": _source_projection(fact),
    }


def _financial_conditions_detail(fact, record, method_contracts):
    explanation = fact.get("explanation") or {}
    accepted = fact.get("accepted_values") or {}
    current = _pick(explanation, _FINANCIAL_CURRENT_KEYS)
    details = _pick(explanation.get("details") or {}, _FINANCIAL_DETAIL_KEYS)
    if details:
        current["details"] = details
    relationship = accepted.get("relationship_to_growth_direction")
    if relationship is not None:
        current["relationship_to_growth_direction"] = relationship
    drivers = _pick(explanation, ("reasons",))
    return {
        "current": current,
        "drivers": drivers,
        "source": _source_projection(fact),
    }


def _policy_response_detail(fact, record, method_contracts):
    explanation = fact.get("explanation") or {}
    accepted = fact.get("accepted_values") or {}
    policy_read = explanation.get("policy_read") or {}
    current = _pick(policy_read, _POLICY_CURRENT_KEYS)
    if explanation.get("state") is not None:
        current["state"] = explanation["state"]
    details = _pick(explanation.get("details") or {}, _POLICY_DETAIL_KEYS)
    if details:
        current["details"] = details
    relationship = accepted.get("relationship_to_growth_direction")
    if relationship is not None:
        current["relationship_to_growth_direction"] = relationship
    drivers = {}
    if policy_read.get("reason") is not None:
        drivers["policy_reason"] = policy_read["reason"]
    if explanation.get("reasons") is not None:
        drivers["reasons"] = explanation["reasons"]
    return {
        "current": current,
        "drivers": drivers,
        "source": _source_projection(fact),
    }


def _consumer_demand_detail(fact, record, method_contracts):
    explanation = fact.get("explanation") or {}
    accepted = fact.get("accepted_values") or {}
    current = _pick(explanation, _CONSUMER_CURRENT_KEYS)
    relationship = accepted.get("relationship_to_growth_direction")
    if relationship is not None:
        current["relationship_to_growth_direction"] = relationship
    drivers = {}
    if explanation.get("reason") is not None:
        drivers["reason"] = explanation["reason"]
    return {
        "current": current,
        "drivers": drivers,
        "source": _source_projection(fact),
    }


def _market_phase_detail(fact, record, method_contracts):
    explanation = fact.get("explanation") or {}
    accepted = fact.get("accepted_values") or {}
    current = _pick(explanation, _PHASE_CURRENT_KEYS)
    if accepted.get("phase") is not None:
        current["phase"] = accepted["phase"]
    return {
        "current": current,
        "method": _method_projection(fact, method_contracts),
        "source": _source_projection(fact),
    }


def _credit_conditions_detail(fact, record, method_contracts):
    accepted = fact.get("accepted_values") or {}
    current = {}
    if accepted.get("status") is not None:
        current["status"] = accepted["status"]
    return {
        "current": current,
        "method": _method_projection(fact, method_contracts),
        "source": _source_projection(fact),
    }


def _vix_detail(fact, record, method_contracts):
    accepted = fact.get("accepted_values") or {}
    current = {}
    if accepted.get("level") is not None:
        current["level"] = accepted["level"]
    return {
        "current": current,
        "method": _method_projection(fact, method_contracts),
        "source": _source_projection(fact),
    }


def _m2_liquidity_detail(fact, record, method_contracts):
    explanation = fact.get("explanation") or {}
    accepted = fact.get("accepted_values") or {}
    current = {}
    if accepted.get("status") is not None:
        current["status"] = accepted["status"]
    if explanation.get("status_label") is not None:
        current["status_label"] = explanation["status_label"]
    return {
        "current": current,
        "method": _method_projection(fact, method_contracts),
        "source": _source_projection(fact),
    }


_PROJECTION_BUILDERS = {
    "survey_synthesis": _survey_synthesis_detail,
    "financial_conditions": _financial_conditions_detail,
    "policy_response": _policy_response_detail,
    "consumer_demand": _consumer_demand_detail,
    "market_phase": _market_phase_detail,
    "credit_conditions": _credit_conditions_detail,
    "vix": _vix_detail,
    "m2_liquidity": _m2_liquidity_detail,
}
