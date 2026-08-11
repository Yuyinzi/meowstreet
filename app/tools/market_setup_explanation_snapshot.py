import hashlib
import json
import math
import unicodedata
from datetime import datetime
from datetime import timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.tools import market_setup_evidence_facts

SNAPSHOT_SCHEMA_VERSION = "market_setup_explanation_snapshot_v1"
METHOD_CONTRACTS_VERSION = "market_setup_explanation_methods_v1"
RELATIONSHIP_ADAPTER_VERSION = "market_setup_v2_relationship_v1"

_RESULT_LAYERS = (
    "macro_regime",
    "market_confirmation",
    "market_setup",
    "portfolio_posture",
)

_EVIDENCE_SEMANTIC_FIELDS = (
    "accepted_value",
    "data_status",
    "participation",
    "decision_result",
)

_ORDERED_LIST_KEYS = frozenset(
    {
        "decision_path",
        "evidence",
        "next_triggers",
        "positioning",
        "avoid",
        "rows",
        "time_series",
        "history",
        "governance",
    }
)

_TIMESTAMP_KEYS = frozenset(
    {
        "created_at",
        "as_of",
        "evidence_through",
        "generated_at",
        "resolved_at",
        "searched_at",
        "effective_date",
        "observation_date",
        "release_date",
    }
)

_DECISION_PATH_STEPS = (
    {
        "step_id": "macro_thesis",
        "object_type": "market_setup_result",
        "object_id": "macro_regime",
        "label": "Macro Thesis",
    },
    {
        "step_id": "market_test",
        "object_type": "market_setup_result",
        "object_id": "market_confirmation",
        "label": "Market Test",
    },
    {
        "step_id": "setup_relationship",
        "object_type": "market_setup_result",
        "object_id": "market_setup",
        "label": "Setup Relationship",
    },
    {
        "step_id": "portfolio_action",
        "object_type": "market_setup_result",
        "object_id": "portfolio_posture",
        "label": "Portfolio Action",
    },
)


class _ResultCodes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str
    label: str


class _MacroRegimeResult(_ResultCodes):
    primary_source: str
    supports: list[dict]
    conflicts: list[dict]
    missing_inputs: list[str]
    excluded_inputs: list[str]
    method_version: str
    source_periods: dict


class _MarketConfirmationResult(_ResultCodes):
    confirmation_test_count: int | None
    evidence: dict
    offsets: list[dict]
    missing_inputs: list[str]
    method_version: str
    source_periods: dict


class _MarketSetupResult(_ResultCodes):
    agreement: str


class _PortfolioPostureResult(_ResultCodes):
    net_exposure: str
    gross_exposure: str
    implementation: str
    broad_beta: str
    positioning: list[dict]
    avoid: list[dict]
    method_version: str


class _Results(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    macro_regime: _MacroRegimeResult
    market_confirmation: _MarketConfirmationResult
    market_setup: _MarketSetupResult
    portfolio_posture: _PortfolioPostureResult


class _DecisionPathStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    step_id: Literal[
        "macro_thesis",
        "market_test",
        "setup_relationship",
        "portfolio_action",
    ]
    object_type: Literal["market_setup_result"]
    object_id: Literal[
        "macro_regime",
        "market_confirmation",
        "market_setup",
        "portfolio_posture",
    ]
    label: str
    code: str


class _ConfirmationCrossing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    counterfactual_id: str
    object_type: Literal["confirmation_test"]
    object_id: str
    predicate_ref: dict
    transition: Literal["accepted_value_crosses_boundary"]
    decision_effect: Literal["confirmation_test_result_change"]


class _SetupTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    counterfactual_id: str
    object_type: Literal["market_setup"]
    object_id: str
    from_code: str
    to_code: str
    confirmation_change: dict
    posture_change: dict
    decision_effect: Literal["market_setup_and_posture_change"]


_Counterfactual = Annotated[
    _ConfirmationCrossing | _SetupTransition,
    Field(discriminator="object_type"),
]


class _NextTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    label: str
    condition_ref: str
    effect: str


class _GovernanceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    fact_id: str
    decision_scope: str
    function: str
    target_layer: str | None
    participation: dict
    decision_result_kind: str


class _MethodEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    method_version: str
    kind: str
    decision_contract: dict
    explanation_contract: dict


class _MethodContracts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: str
    methods: dict[str, _MethodEntry]


class _SnapshotState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot_schema_version: str
    as_of: str
    evidence_through: str | None
    market_setup_version: str
    input_registry_version: str
    explanation_surface_version: str
    method_manifest: dict
    results: _Results
    decision_path: list[_DecisionPathStep]
    evidence: list[market_setup_evidence_facts.EvidenceFact]
    method_contracts: _MethodContracts
    counterfactuals: list[_Counterfactual]
    next_triggers: list[_NextTrigger]
    governance: list[_GovernanceEntry]

    @model_validator(mode="after")
    def _validate_schema_version(self):
        if self.snapshot_schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("snapshot schema version is invalid")
        return self

    @model_validator(mode="after")
    def _validate_evidence_fact_ids(self):
        fact_ids = [fact.fact_id for fact in self.evidence]
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("evidence fact ids are duplicated")
        return self


class _Snapshot(_SnapshotState):
    context_id: str
    created_at: str
    decision_fingerprint: str
    explanation_fingerprint: str
    snapshot_hash: str


def canonical_json(payload):
    if not isinstance(payload, dict):
        raise ValueError("canonical payload must be a dictionary")
    return json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonicalize(value, key=None):
    if isinstance(value, str):
        return _normalize_string(value, key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("canonical payload contains a non-finite number")
        if isinstance(value, float) and value == 0.0:
            return 0.0
        return value
    if isinstance(value, (list, tuple)):
        items = [_canonicalize(item) for item in value]
        if key in _ORDERED_LIST_KEYS:
            return items
        return sorted(
            items,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
        )
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(k)): _canonicalize(v, k)
            for k, v in value.items()
        }
    if value is None:
        return None
    raise ValueError("canonical payload contains an unsupported value type")


def _normalize_string(value, key):
    normalized = unicodedata.normalize("NFC", value)
    if key in _TIMESTAMP_KEYS:
        return _normalize_timestamp(normalized)
    return normalized


def _normalize_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    normalized = parsed.astimezone(timezone.utc)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(payload):
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _decision_relevant(fact):
    return fact["role"]["function"] not in ("watch_only", "display_only")


def _decision_contract_projection(method_contracts):
    return {
        method_id: {
            "method_version": method["method_version"],
            "kind": method["kind"],
            "decision_contract": method["decision_contract"],
        }
        for method_id, method in method_contracts["methods"].items()
    }


def compute_decision_fingerprint(state):
    projection = {
        "market_setup_version": state["market_setup_version"],
        "results": state["results"],
        "decision_path": state["decision_path"],
        "evidence": [fact for fact in state["evidence"] if _decision_relevant(fact)],
        "decision_contracts": _decision_contract_projection(state["method_contracts"]),
        "counterfactuals": state["counterfactuals"],
    }
    return _sha256(projection)


def compute_explanation_fingerprint(state):
    projection = {
        "market_setup_version": state["market_setup_version"],
        "results": state["results"],
        "decision_path": state["decision_path"],
        "evidence": state["evidence"],
        "method_contracts": state["method_contracts"],
        "counterfactuals": state["counterfactuals"],
        "next_triggers": state["next_triggers"],
        "governance": state["governance"],
    }
    return _sha256(projection)


def _snapshot_hash(state):
    payload = {key: value for key, value in state.items() if key != "snapshot_hash"}
    return _sha256(payload)


def _project_results(setup_result):
    return {layer: setup_result[layer] for layer in _RESULT_LAYERS}


def _method_manifest(setup_result, method_contracts):
    manifest = {"market_setup": setup_result["version"]}
    for method_id, method in method_contracts["methods"].items():
        manifest[method_id] = method["method_version"]
    return manifest


def _build_decision_path(results):
    path = []
    for step in _DECISION_PATH_STEPS:
        entry = dict(step)
        entry["code"] = results[step["object_id"]]["code"]
        path.append(entry)
    return path


def build_snapshot_state(
    *,
    setup_result,
    evidence,
    method_contracts,
    as_of,
    evidence_through,
    input_registry_version,
    explanation_surface_version,
):
    results = _project_results(setup_result)
    return {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "as_of": as_of,
        "evidence_through": evidence_through,
        "market_setup_version": setup_result["version"],
        "input_registry_version": input_registry_version,
        "explanation_surface_version": explanation_surface_version,
        "method_manifest": _method_manifest(setup_result, method_contracts),
        "results": results,
        "decision_path": _build_decision_path(results),
        "evidence": evidence,
        "method_contracts": method_contracts,
        "counterfactuals": build_counterfactuals(
            setup_result, evidence, method_contracts
        ),
        "next_triggers": setup_result["next_triggers"],
        "governance": market_setup_evidence_facts.build_governance_index(evidence),
    }


def _confirmation_direction(setup_result):
    code = setup_result["market_confirmation"]["code"]
    if code.endswith("_downside"):
        return "downside"
    if code.endswith("_upside"):
        return "upside"
    return None


def _confirmation_crossings(setup_result, evidence, method_contracts):
    direction = _confirmation_direction(setup_result)
    if direction is None:
        return []
    fact_ids = {fact["fact_id"] for fact in evidence}
    crossings = []
    for method_id, method in method_contracts["methods"].items():
        if method["kind"] != "predicate_method":
            continue
        fact_id = method["decision_contract"]["input_contract"]["fact_id"]
        if fact_id not in fact_ids:
            continue
        predicate_entry = method["decision_contract"]["predicates"][direction]
        crossings.append(
            {
                "counterfactual_id": f"{method_id}_{direction}_crossing",
                "object_type": "confirmation_test",
                "object_id": fact_id,
                "predicate_ref": predicate_entry["predicate_ref"],
                "transition": "accepted_value_crosses_boundary",
                "decision_effect": "confirmation_test_result_change",
            }
        )
    return crossings


def _setup_transitions(setup_result, method_contracts):
    cells = method_contracts["methods"]["setup_matrix"]["decision_contract"]["cells"]
    postures = method_contracts["methods"]["posture_matrix"]["decision_contract"][
        "postures"
    ]
    regime = setup_result["macro_regime"]["code"]
    current_confirmation = setup_result["market_confirmation"]["code"]
    current_setup = setup_result["market_setup"]["code"]
    current_posture = setup_result["portfolio_posture"]["code"]
    transitions = []
    for cell in cells:
        if cell["macro_regime"] != regime:
            continue
        if cell["market_confirmation"] == current_confirmation:
            continue
        to_setup = cell["setup_code"]
        to_posture = postures[to_setup]["code"]
        counterfactual_id = (
            f"setup_{cell['macro_regime']}_{cell['market_confirmation']}"
        )
        transitions.append(
            {
                "counterfactual_id": counterfactual_id,
                "object_type": "market_setup",
                "object_id": counterfactual_id,
                "from_code": current_setup,
                "to_code": to_setup,
                "confirmation_change": {
                    "from": current_confirmation,
                    "to": cell["market_confirmation"],
                },
                "posture_change": {
                    "from": current_posture,
                    "to": to_posture,
                },
                "decision_effect": "market_setup_and_posture_change",
            }
        )
    return transitions


def build_counterfactuals(setup_result, evidence, method_contracts):
    counterfactuals = []
    counterfactuals.extend(
        _confirmation_crossings(setup_result, evidence, method_contracts)
    )
    counterfactuals.extend(_setup_transitions(setup_result, method_contracts))
    return counterfactuals


def _fact_accepted_value(fact):
    accepted = fact.get("accepted_values") or {}
    if len(accepted) == 1:
        return next(iter(accepted.values()))
    return accepted if accepted else None


def _evidence_semantic_values(fact):
    return {
        "accepted_value": _fact_accepted_value(fact),
        "data_status": fact["data_status"],
        "participation": fact["participation"],
        "decision_result": fact["decision_result"],
    }


def _results_changed(previous, current):
    return any(
        previous["results"][layer]["code"] != current["results"][layer]["code"]
        for layer in _RESULT_LAYERS
    )


def _evidence_changes(previous, current):
    previous_by_id = {fact["fact_id"]: fact for fact in previous["evidence"]}
    current_by_id = {fact["fact_id"]: fact for fact in current["evidence"]}
    changes = []
    for fact_id in sorted(set(previous_by_id) | set(current_by_id)):
        before = (
            _evidence_semantic_values(previous_by_id[fact_id])
            if fact_id in previous_by_id
            else None
        )
        after = (
            _evidence_semantic_values(current_by_id[fact_id])
            if fact_id in current_by_id
            else None
        )
        for field_id in _EVIDENCE_SEMANTIC_FIELDS:
            before_value = before.get(field_id) if before else None
            after_value = after.get(field_id) if after else None
            if before_value != after_value:
                changes.append(
                    {
                        "object_type": "evidence_fact",
                        "object_id": fact_id,
                        "field_id": field_id,
                        "before": before_value,
                        "after": after_value,
                    }
                )
    return changes


def build_semantic_delta(previous, current):
    if previous is None:
        return {"results_changed": True, "changes": []}
    return {
        "results_changed": _results_changed(previous, current),
        "changes": _evidence_changes(previous, current),
    }


def finalize_snapshot(state, *, context_id, created_at):
    try:
        normalized = _SnapshotState.model_validate(state).model_dump(mode="json")
    except ValidationError as exc:
        raise ValueError("explanation snapshot is invalid") from exc
    normalized["governance"] = market_setup_evidence_facts.build_governance_index(
        normalized["evidence"]
    )
    normalized["context_id"] = context_id
    normalized["created_at"] = created_at
    normalized["decision_fingerprint"] = compute_decision_fingerprint(normalized)
    normalized["explanation_fingerprint"] = compute_explanation_fingerprint(normalized)
    normalized["snapshot_hash"] = _snapshot_hash(normalized)
    return validate_snapshot(normalized)


def _verify_fingerprints(snapshot):
    if compute_decision_fingerprint(snapshot) != snapshot["decision_fingerprint"]:
        raise ValueError("decision fingerprint is invalid")
    if compute_explanation_fingerprint(snapshot) != snapshot["explanation_fingerprint"]:
        raise ValueError("explanation fingerprint is invalid")
    if _snapshot_hash(snapshot) != snapshot["snapshot_hash"]:
        raise ValueError("snapshot hash is invalid")


def _verify_governance(snapshot):
    expected = market_setup_evidence_facts.build_governance_index(snapshot["evidence"])
    if snapshot["governance"] != expected:
        raise ValueError("governance index does not match evidence")


def validate_snapshot(payload):
    if not isinstance(payload, dict):
        raise ValueError("explanation snapshot is required")
    try:
        validated = _Snapshot.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("explanation snapshot is invalid") from exc
    dumped = validated.model_dump(mode="json")
    _verify_fingerprints(dumped)
    _verify_governance(dumped)
    return dumped
