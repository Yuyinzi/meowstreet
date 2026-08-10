import json
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import model_validator

from app.tools import market_setup_predicates
from app.tools import market_setup_v2

ROOT = Path(__file__).resolve().parents[2]
SURFACE_PATH = ROOT / "data" / "local_system" / "market_assistant_surface.v1.json"
SURFACE_VERSION = "market_assistant_surface_v1"
REGISTRY_PATH = ROOT / "data" / "local_system" / "market_setup_input_registry.v1.json"

KNOWN_FACT_IDS = frozenset(
    {
        "survey_growth_direction",
        "macro_financial_conditions",
        "macro_policy_response",
        "consumer_demand_outlook",
        "sp500_market_phase",
        "credit_conditions",
        "vix_level",
        "m2_liquidity",
        "equity_breadth",
        "jobless_claims",
        "economic_confirmation",
        "cyclical_commodities",
        "nfib_regional_evidence",
    }
)

_FACT_BUNDLES = {
    "survey_growth_direction": "expected_growth",
    "macro_financial_conditions": "financial_conditions",
    "macro_policy_response": "policy_response",
    "consumer_demand_outlook": "consumer_demand",
    "sp500_market_phase": "market_environment",
    "credit_conditions": "financial_conditions",
    "vix_level": "financial_conditions",
    "m2_liquidity": "policy_response",
    "equity_breadth": "observation_only",
    "jobless_claims": "observation_only",
    "economic_confirmation": "context_only",
    "cyclical_commodities": "observation_only",
    "nfib_regional_evidence": "manual_review",
}

_FACT_LABELS = {
    "survey_growth_direction": "ISM Survey Synthesis Direction",
    "macro_financial_conditions": "Financial Conditions",
    "macro_policy_response": "Monetary Policy",
    "consumer_demand_outlook": "Consumer Demand Outlook",
    "sp500_market_phase": "S&P 500 Market Phase",
    "credit_conditions": "Credit Conditions",
    "vix_level": "VIX",
    "m2_liquidity": "M2 Liquidity",
    "equity_breadth": "Equity Breadth",
    "jobless_claims": "Jobless Claims",
    "economic_confirmation": "Economic Confirmation",
    "cyclical_commodities": " Cyclical Commodities",
    "nfib_regional_evidence": "NFIB Regional Evidence",
}

_INDICATOR_IDS = {
    "survey_growth_direction": "ism_survey_synthesis",
    "macro_financial_conditions": "financial_conditions",
    "macro_policy_response": "monetary_policy",
    "consumer_demand_outlook": "consumer_sentiment",
    "sp500_market_phase": "sp500_market_phase",
    "credit_conditions": "credit_conditions",
    "vix_level": "vix",
    "m2_liquidity": "m2_money_supply",
    "equity_breadth": "equity_breadth",
    "jobless_claims": "jobless_claims",
    "economic_confirmation": "economic_confirmation",
    "cyclical_commodities": "cyclical_commodities",
    "nfib_regional_evidence": "nfib_regional_evidence",
}

_VALUE_FIELDS = {
    "survey_growth_direction": "direction",
    "sp500_market_phase": "phase",
    "credit_conditions": "status",
    "vix_level": "level",
    "m2_liquidity": "status",
    "macro_financial_conditions": "relationship_to_growth_direction",
    "macro_policy_response": "relationship_to_growth_direction",
    "consumer_demand_outlook": "relationship_to_growth_direction",
}

_FUNCTION_BY_EFFECTS = {
    ("regime_selector",): "selector",
    ("supports", "conflicts"): "contextual_relationship",
    ("confirmation_test",): "confirmation_test",
    ("offset",): "offset",
    ("display_only",): "display_only",
}

_DIRECTIONS = {
    "rising",
    "slowing",
    "falling",
    "improving",
    "rebound_risk",
    "stable",
}
_PHASES = {"bull_market", "bear_market"}
_M2_OFFSET_STATUSES = {"expanding", "shock"}
_RELATIONSHIP_VALUES = {"supports", "conflicts", "neutral"}
_NEUTRAL_CREDIT_STATES = {"weak_credit_warning", "mixed", "selective"}

_DOWNSIDE_REGIMES = {"growth_decelerating", "contraction_risk_rising"}
_UPSIDE_REGIMES = {"growth_accelerating", "early_recovery"}
_STABLE_REGIME = "growth_stable"
_INSUFFICIENT_DATA = "insufficient_data"

_CONFIRMATION_EVIDENCE_KEYS = {
    "sp500_market_phase": "equity_trend",
    "credit_conditions": "credit",
    "vix_level": "volatility",
}

_CONFIRMATION_METHOD_IDS = {
    "sp500_market_phase": "equity_confirmation_v2",
    "credit_conditions": "credit_confirmation_v2",
    "vix_level": "vix_confirmation_v2",
}

_METHOD_CONTRACTS = market_setup_predicates.load_method_contracts()


def _credit_confirmation_states():
    downside = market_setup_predicates.confirmation_predicate(
        "credit_confirmation_v2", "downside", _METHOD_CONTRACTS
    )["operand"]
    upside = market_setup_predicates.confirmation_predicate(
        "credit_confirmation_v2", "upside", _METHOD_CONTRACTS
    )["operand"]
    return set(downside) | set(upside)


_CREDIT_STATES = _credit_confirmation_states() | _NEUTRAL_CREDIT_STATES


class Role(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision_scope: Literal[
        "decision_input",
        "confirmation_input",
        "context_only",
        "observation_only",
        "manual_review",
    ]
    function: Literal[
        "selector",
        "contextual_relationship",
        "confirmation_test",
        "offset",
        "watch_only",
        "display_only",
    ]
    target_layer: Literal["macro_regime", "market_confirmation"] | None = None
    allowed_effects: list[str]


class DataStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: Literal["available", "missing", "stale", "invalid"]


class Participation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: Literal["applied", "not_applied"]
    reason_code: (
        Literal[
            "data_missing",
            "data_stale",
            "data_invalid",
            "target_layer_not_applicable",
            "watch_only",
            "display_only",
            "method_scope_excludes",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def _validate_reason_code(self):
        if self.state == "not_applied" and self.reason_code is None:
            raise ValueError("participation reason is required when not applied")
        if self.state == "applied" and self.reason_code is not None:
            raise ValueError("participation reason is not allowed when applied")
        return self


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    level: str | int | float | None = None
    direction: str | None = None


class EvaluatedEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: Literal["evaluated"]
    actual_value: str | int | float | None = None
    result: bool


class NotEvaluatedEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: Literal["not_evaluated"]
    actual_value: str | int | float | None = None
    reason_code: Literal[
        "data_missing",
        "data_stale",
        "data_invalid",
        "target_layer_not_applicable",
        "participation_not_applied",
    ]


Evaluation = Annotated[
    EvaluatedEvaluation | NotEvaluatedEvaluation,
    Field(discriminator="state"),
]


class SelectorResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["selector"]
    input_state: str | None = None
    selected: str | None = None


class RelationshipResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["relationship"]
    relationship: Literal["supports", "conflicts", "neutral", "unavailable"]


class ConfirmationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["confirmation_test"]
    predicate_ref: dict | None = None
    predicate: dict | None = None
    evaluation: Evaluation


class OffsetResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["offset"]
    state: Literal["active", "inactive", "not_evaluated"]


class NoneResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["none"]


DecisionResult = Annotated[
    SelectorResult
    | RelationshipResult
    | ConfirmationResult
    | OffsetResult
    | NoneResult,
    Field(discriminator="kind"),
]


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_module: str
    source_id: str
    source_period: dict | None = None
    method_references: list[str] = Field(default_factory=list)


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    fact_id: str
    indicator_id: str
    label: str
    accepted_values: dict
    classifications: Classification
    role: Role
    data_status: DataStatus
    participation: Participation
    decision_result: DecisionResult
    provenance: Provenance
    finding: dict


def load_explanation_surface(path=SURFACE_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _validate_surface(payload)


def _validate_surface(surface):
    if not isinstance(surface, dict) or not surface.get("version"):
        raise ValueError("explanation surface version is required")
    if surface["version"] != SURFACE_VERSION:
        raise ValueError(
            f"explanation surface version is unknown: {surface['version']}"
        )
    facts = surface.get("facts")
    if not isinstance(facts, list):
        raise ValueError("explanation surface facts are required")
    seen = set()
    for fact_id in facts:
        if not isinstance(fact_id, str):
            raise ValueError("explanation surface fact ids must be strings")
        if not fact_id:
            raise ValueError("explanation surface fact id is empty")
        if fact_id in seen:
            raise ValueError(f"explanation surface fact id is duplicated: {fact_id}")
        if fact_id not in KNOWN_FACT_IDS:
            raise ValueError(f"explanation surface fact id is unknown: {fact_id}")
        seen.add(fact_id)
    return surface


def build_evidence_facts(*, setup_result, inputs, evidence_layers, surface):
    registry = market_setup_v2.load_input_registry(REGISTRY_PATH)
    facts = []
    for fact_id in _validate_surface(surface)["facts"]:
        record = registry["facts"].get(fact_id)
        fact = _fact_record(inputs, fact_id)
        built = _build_fact(setup_result, fact_id, fact, record)
        facts.append(_validate_fact(built))
    return facts


def build_governance_index(evidence):
    index = {}
    for fact in evidence:
        if not isinstance(fact, dict) or not fact.get("fact_id"):
            raise ValueError("governance index requires evidence fact records")
        fact_id = fact["fact_id"]
        if fact_id in index:
            raise ValueError(f"governance index fact is duplicated: {fact_id}")
        role = fact.get("role")
        decision_result = fact.get("decision_result")
        if not isinstance(role, dict) or not isinstance(decision_result, dict):
            raise ValueError(f"governance index fact is incomplete: {fact_id}")
        index[fact_id] = {
            "decision_scope": role["decision_scope"],
            "function": role["function"],
            "target_layer": role["target_layer"],
            "participation": fact["participation"],
            "decision_result_kind": decision_result["kind"],
        }
    return index


def _build_fact(setup_result, fact_id, fact, record):
    role = _role(record)
    data_status = _data_status(fact_id, fact)
    participation, decision_result, finding = _decision_parts(
        setup_result, fact_id, fact, role, data_status
    )
    return {
        "fact_id": fact_id,
        "indicator_id": _INDICATOR_IDS[fact_id],
        "label": _FACT_LABELS[fact_id],
        "accepted_values": _accepted_values(fact) if fact else {},
        "classifications": _classifications(fact),
        "role": role,
        "data_status": data_status,
        "participation": participation,
        "decision_result": decision_result,
        "provenance": _provenance(record, fact_id, fact),
        "finding": finding,
    }


def _validate_fact(fact):
    try:
        EvidenceFact(**fact)
    except ValidationError as exc:
        raise ValueError(f"evidence fact is invalid: {fact['fact_id']}") from exc
    return fact


def _fact_record(inputs, fact_id):
    bundle_key = _FACT_BUNDLES[fact_id]
    bundle = inputs.get(bundle_key)
    if bundle_key in ("observation_only", "context_only", "manual_review"):
        if isinstance(bundle, dict):
            record = bundle.get(fact_id)
            return record if isinstance(record, dict) else None
        return None
    if not isinstance(bundle, dict):
        return None
    facts = bundle.get("facts")
    if not isinstance(facts, dict):
        return None
    record = facts.get(fact_id)
    return record if isinstance(record, dict) else None


def _role(record):
    if record is None:
        return {
            "decision_scope": "observation_only",
            "function": "watch_only",
            "target_layer": None,
            "allowed_effects": [],
        }
    effects = tuple(record["allowed_effects"])
    function = _FUNCTION_BY_EFFECTS.get(effects)
    if function is None:
        effects_text = ", ".join(effects)
        raise ValueError(
            f"registry fact {record['fact_id']} has unknown allowed effects: "
            f"{effects_text}"
        )
    target_layers = record.get("target_layers") or []
    return {
        "decision_scope": record["decision_scope"],
        "function": function,
        "target_layer": target_layers[0] if target_layers else None,
        "allowed_effects": list(record["allowed_effects"]),
    }


def _data_status(fact_id, fact):
    if fact is None:
        return {"state": "missing"}
    if _effective_date(fact) is None:
        return {"state": "stale"}
    if not _value_field_valid(fact_id, fact):
        return {"state": "invalid"}
    return {"state": "available"}


def _effective_date(fact):
    period = fact.get("source_period")
    if not isinstance(period, dict):
        return None
    effective = period.get("effective_date")
    if not _is_valid_iso_date(effective):
        return None
    return str(effective)


def _is_valid_iso_date(value):
    if value is None:
        return False
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _value_field_valid(fact_id, fact):
    if fact_id in _VALUE_FIELDS:
        return _is_valid_value(fact_id, fact.get(_VALUE_FIELDS[fact_id]))
    return any(
        key != "source_period" and "sync" not in key and value is not None
        for key, value in fact.items()
    )


def _is_valid_value(fact_id, value):
    if fact_id == "survey_growth_direction":
        return value in _DIRECTIONS
    if fact_id == "sp500_market_phase":
        return value in _PHASES
    if fact_id == "credit_conditions":
        return value in _CREDIT_STATES
    if fact_id == "vix_level":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
        )
    if fact_id == "m2_liquidity":
        return isinstance(value, str) and bool(value)
    return value in _RELATIONSHIP_VALUES


def _accepted_values(fact):
    return {
        key: value
        for key, value in fact.items()
        if key != "source_period" and "sync" not in key
    }


def _classifications(fact):
    classifications = {}
    if fact is None:
        return classifications
    level = fact.get("level")
    direction = fact.get("direction")
    if level is not None:
        classifications["level"] = level
    if direction is not None:
        classifications["direction"] = direction
    return classifications


def _provenance(record, fact_id, fact):
    provenance = {
        "source_module": record["source_module"] if record else "observation_only",
        "source_id": fact_id,
        "method_references": _method_references(record),
    }
    period = fact.get("source_period") if fact else None
    if isinstance(period, dict):
        provenance["source_period"] = period
    return provenance


def _method_references(record):
    if record is None:
        return []
    references = [record["method_version"]]
    if record.get("relationship_method_version"):
        references.append(record["relationship_method_version"])
    return references


def _decision_parts(setup_result, fact_id, fact, role, data_status):
    function = role["function"]
    if function == "watch_only":
        return _fixed_not_applied("watch_only")
    if function == "display_only":
        return _fixed_not_applied("display_only")
    if function == "selector":
        return _selector_parts(setup_result, fact, data_status)
    if function == "contextual_relationship":
        return _relationship_parts(setup_result, fact, data_status)
    if function == "confirmation_test":
        return _confirmation_parts(setup_result, fact_id, fact, data_status)
    return _offset_parts(setup_result, fact, data_status)


def _fixed_not_applied(reason):
    return (
        _participation("not_applied", reason),
        {"kind": "none"},
        {"state": "not_applied", "reason_code": reason},
    )


def _participation(state, reason_code=None):
    participation = {"state": state}
    if reason_code is not None:
        participation["reason_code"] = reason_code
    return participation


def _not_applied_finding(reason):
    return {"state": "not_applied", "reason_code": reason}


def _selector_parts(setup_result, fact, data_status):
    state = data_status["state"]
    regime_code = _regime_code(setup_result)
    if state != "available":
        reason = _data_reason(state)
        return (
            _participation("not_applied", reason),
            _selector_result(fact, None),
            _not_applied_finding(reason),
        )
    if regime_code == _INSUFFICIENT_DATA:
        return (
            _participation("not_applied", "method_scope_excludes"),
            _selector_result(fact, None),
            _not_applied_finding("method_scope_excludes"),
        )
    return (
        _participation("applied"),
        _selector_result(fact, regime_code),
        {"state": "selected", "selected": regime_code},
    )


def _selector_result(fact, selected):
    result = {"kind": "selector"}
    direction = fact.get("direction") if fact else None
    if direction is not None:
        result["input_state"] = direction
    if selected is not None:
        result["selected"] = selected
    return result


def _relationship_parts(setup_result, fact, data_status):
    state = data_status["state"]
    if state != "available":
        reason = _data_reason(state)
        return (
            _participation("not_applied", reason),
            _relationship_result(fact, False),
            _not_applied_finding(reason),
        )
    if _regime_code(setup_result) == _INSUFFICIENT_DATA:
        return (
            _participation("not_applied", "method_scope_excludes"),
            _relationship_result(fact, False),
            _not_applied_finding("method_scope_excludes"),
        )
    return (
        _participation("applied"),
        _relationship_result(fact, True),
        {"state": fact["relationship_to_growth_direction"]},
    )


def _relationship_result(fact, applied):
    if applied:
        return {
            "kind": "relationship",
            "relationship": fact["relationship_to_growth_direction"],
        }
    return {"kind": "relationship", "relationship": "unavailable"}


def _confirmation_parts(setup_result, fact_id, fact, data_status):
    confirmation_code = _confirmation_code(setup_result)
    state = data_status["state"]
    if confirmation_code == "not_applicable":
        return (
            _participation("not_applied", "target_layer_not_applicable"),
            _confirmation_result(
                setup_result, fact_id, fact, None, "target_layer_not_applicable"
            ),
            _not_applied_finding("target_layer_not_applicable"),
        )
    if state != "available":
        reason = _data_reason(state)
        return (
            _participation("not_applied", reason),
            _confirmation_result(setup_result, fact_id, fact, None, reason),
            _not_applied_finding(reason),
        )
    evidence = _evidence_record(setup_result, fact_id)
    if evidence is None:
        return (
            _participation("not_applied", "method_scope_excludes"),
            _confirmation_result(
                setup_result, fact_id, fact, None, "participation_not_applied"
            ),
            _not_applied_finding("method_scope_excludes"),
        )
    return (
        _participation("applied"),
        _confirmation_result(setup_result, fact_id, fact, evidence, None),
        {"state": "evaluated", "confirms": evidence["evaluation"]["result"]},
    )


def _confirmation_result(setup_result, fact_id, fact, evidence, reason_code):
    if evidence is not None:
        return {
            "kind": "confirmation_test",
            "predicate_ref": evidence["predicate_ref"],
            "predicate": evidence["predicate"],
            "evaluation": evidence["evaluation"],
        }
    result = {"kind": "confirmation_test"}
    predicate_ref = _predicate_ref_for_direction(
        fact_id, _direction_of_regime(_regime_code(setup_result))
    )
    if predicate_ref is not None:
        result["predicate_ref"] = predicate_ref
    result["evaluation"] = _not_evaluated_evaluation(fact, reason_code)
    return result


def _not_evaluated_evaluation(fact, reason_code):
    return {
        "state": "not_evaluated",
        "actual_value": _actual_value(fact),
        "reason_code": reason_code,
    }


def _actual_value(fact):
    if fact is None:
        return None
    for key in ("level", "direction", "phase", "status"):
        value = fact.get(key)
        if value is not None:
            return value
    return None


def _offset_parts(setup_result, fact, data_status):
    confirmation_code = _confirmation_code(setup_result)
    state = data_status["state"]
    if confirmation_code == "not_applicable":
        return (
            _participation("not_applied", "target_layer_not_applicable"),
            _offset_result(fact, False),
            _not_applied_finding("target_layer_not_applicable"),
        )
    if state != "available":
        reason = _data_reason(state)
        return (
            _participation("not_applied", reason),
            _offset_result(fact, False),
            _not_applied_finding(reason),
        )
    if confirmation_code == _INSUFFICIENT_DATA:
        return (
            _participation("not_applied", "method_scope_excludes"),
            _offset_result(fact, False),
            _not_applied_finding("method_scope_excludes"),
        )
    result = _offset_result(fact, True)
    return _participation("applied"), result, {"state": result["state"]}


def _offset_result(fact, applied):
    if not applied:
        return {"kind": "offset", "state": "not_evaluated"}
    status = fact.get("status")
    return {
        "kind": "offset",
        "state": "active" if status in _M2_OFFSET_STATUSES else "inactive",
    }


def _data_reason(state):
    return f"data_{state}"


def _regime_code(setup_result):
    regime = setup_result.get("macro_regime")
    return regime.get("code") if isinstance(regime, dict) else None


def _confirmation_code(setup_result):
    confirmation = setup_result.get("market_confirmation")
    return confirmation.get("code") if isinstance(confirmation, dict) else None


def _direction_of_regime(code):
    if code in _DOWNSIDE_REGIMES:
        return "downside"
    if code in _UPSIDE_REGIMES:
        return "upside"
    if code == _STABLE_REGIME:
        return "stable"
    return None


def _predicate_ref_for_direction(fact_id, direction):
    if direction not in ("downside", "upside"):
        return None
    return market_setup_predicates.predicate_ref(
        _CONFIRMATION_METHOD_IDS[fact_id], direction, _METHOD_CONTRACTS
    )


def _evidence_record(setup_result, fact_id):
    confirmation = setup_result.get("market_confirmation")
    if not isinstance(confirmation, dict):
        return None
    evidence = confirmation.get("evidence")
    if not isinstance(evidence, dict):
        return None
    return evidence.get(_CONFIRMATION_EVIDENCE_KEYS[fact_id])
