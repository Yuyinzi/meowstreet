from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Authority = Literal[
    "decision_fact",
    "method_knowledge",
    "local_observation",
    "external_research",
    "hypothetical",
]

ArtifactKind = Literal[
    "explanation_snapshot",
    "knowledge_record",
    "exploration_result",
    "research_result",
]

MarketSetupRelation = Literal["authoritative_snapshot", "non_decision"]

Purpose = Literal[
    "decision_explanation",
    "counterfactual_explanation",
    "method_explanation",
    "source_explanation",
    "governance_explanation",
    "observation",
    "bounded_interpretation",
    "illustration",
]

_PURPOSE_AUTHORITIES = {
    "decision_explanation": {"decision_fact"},
    "counterfactual_explanation": {"decision_fact"},
    "method_explanation": {"method_knowledge"},
    "source_explanation": {"method_knowledge", "external_research"},
    "governance_explanation": {"decision_fact", "method_knowledge"},
    "observation": {"local_observation", "external_research"},
    "bounded_interpretation": {"local_observation", "external_research"},
    "illustration": {"hypothetical"},
}

_PRIMARY_AUTHORITY_BY_KIND = {
    "explanation_snapshot": "decision_fact",
    "knowledge_record": "method_knowledge",
    "exploration_result": "local_observation",
    "research_result": "external_research",
}

_OBJECT_AUTHORITIES_BY_KIND = {
    "explanation_snapshot": frozenset({"decision_fact", "method_knowledge"}),
    "knowledge_record": frozenset({"method_knowledge"}),
    "exploration_result": frozenset({"local_observation"}),
    "research_result": frozenset({"external_research"}),
}

_MARKET_SETUP_RELATION_BY_KIND = {
    "explanation_snapshot": "authoritative_snapshot",
    "knowledge_record": "non_decision",
    "exploration_result": "non_decision",
    "research_result": "non_decision",
}


class ArtifactObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    authority: Authority
    payload: dict


class ArtifactEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_id: str = Field(min_length=1)
    artifact_kind: ArtifactKind
    schema_version: str = Field(min_length=1)
    primary_authority: Authority
    market_setup_relation: MarketSetupRelation
    payload: dict
    object_index: list[ArtifactObject]
    integrity_hash: str = Field(min_length=1)


class SemanticRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)


def authority_allows_purpose(authority, purpose):
    return authority in _PURPOSE_AUTHORITIES.get(purpose, set())


def build_object_index(objects):
    if not isinstance(objects, list):
        raise ValueError("artifact object index is required")
    try:
        validated = [ArtifactObject.model_validate(obj).model_dump() for obj in objects]
    except ValidationError as exc:
        raise ValueError("artifact object is invalid") from exc
    seen = set()
    for obj in validated:
        key = (obj["object_type"], obj["object_id"])
        if key in seen:
            raise ValueError(f"artifact object is duplicated: {key[0]}.{key[1]}")
        seen.add(key)
    return validated


def validate_artifact(payload):
    if not isinstance(payload, dict):
        raise ValueError("artifact payload is required")
    try:
        ArtifactEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("artifact payload is invalid") from exc
    kind = payload["artifact_kind"]
    if payload["primary_authority"] != _PRIMARY_AUTHORITY_BY_KIND[kind]:
        raise ValueError("artifact primary authority is not permitted")
    if payload["market_setup_relation"] != _MARKET_SETUP_RELATION_BY_KIND[kind]:
        raise ValueError("artifact market setup relation is invalid")
    index = build_object_index(payload["object_index"])
    allowed = _OBJECT_AUTHORITIES_BY_KIND[kind]
    for obj in index:
        if obj["authority"] not in allowed:
            raise ValueError(
                f"artifact authority is not permitted: {obj['authority']} in {kind}"
            )
    return payload


def resolve_artifact_ref(artifacts, ref):
    if not isinstance(artifacts, dict):
        raise ValueError("artifact references are required")
    if not isinstance(ref, dict):
        raise ValueError("artifact reference is required")
    try:
        SemanticRef.model_validate(ref)
    except ValidationError as exc:
        raise ValueError("artifact reference is invalid") from exc
    artifact = artifacts.get(ref["artifact_id"])
    if artifact is None:
        raise ValueError(f"artifact reference is not found: {ref['artifact_id']}")
    index = artifact.get("object_index")
    if not isinstance(index, list):
        raise ValueError("artifact object index is required")
    for obj in index:
        if (
            obj.get("object_type") == ref["object_type"]
            and obj.get("object_id") == ref["object_id"]
        ):
            return obj
    raise ValueError(
        f"artifact object is not found: {ref['object_type']}.{ref['object_id']}"
    )
