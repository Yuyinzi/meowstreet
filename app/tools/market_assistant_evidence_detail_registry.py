import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.market_setup_evidence_facts import load_explanation_surface

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = (
    ROOT / "data" / "local_system" / "market_assistant_evidence_details.v1.json"
)
REGISTRY_VERSION = "market_assistant_evidence_details_v1"

DETAIL_TOPICS = ("current", "drivers", "method", "source")

EVIDENCE_DETAIL_FACT_IDS = (
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
)

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_WHITESPACE_RE = re.compile(r"\s+")


class EvidenceDetailRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    fact_id: str = Field(min_length=1)
    scope: Literal[
        "decision_input",
        "confirmation_input",
        "context_only",
        "observation_only",
        "manual_review",
    ]
    detail_kind: str = Field(min_length=1)
    supported_topics: list[Literal[*DETAIL_TOPICS]]
    default_topics: list[Literal[*DETAIL_TOPICS]]
    aliases: list[str]
    source_module: str = Field(min_length=1)
    projection_version: str = Field(min_length=1)


def load_evidence_detail_registry(path=REGISTRY_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _validate_registry(payload)


def evidence_detail_record(registry, fact_id):
    facts = registry.get("facts") if isinstance(registry, dict) else None
    if not isinstance(facts, list):
        raise ValueError("evidence detail registry facts are required")
    for record in facts:
        if record.get("fact_id") == fact_id:
            return record
    raise ValueError(f"evidence detail fact is not registered: {fact_id}")


def match_evidence_detail_question(question, registry=None):
    if registry is None:
        registry = load_evidence_detail_registry()
    if not isinstance(question, str) or not question.strip():
        return None
    normalized = _normalize_question(question)
    matched_ids = set()
    for record in registry["facts"]:
        if _record_matches(record["aliases"], normalized):
            matched_ids.add(record["fact_id"])
    if len(matched_ids) != 1:
        return None
    fact_id = next(iter(matched_ids))
    record = evidence_detail_record(registry, fact_id)
    return {"fact_id": fact_id, "default_topics": list(record["default_topics"])}


def _validate_registry(payload):
    if not isinstance(payload, dict):
        raise ValueError("evidence detail registry is required")
    version = payload.get("version")
    if version != REGISTRY_VERSION:
        raise ValueError(f"evidence detail registry version is unknown: {version}")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise ValueError("evidence detail registry facts are required")
    surface_ids = set(load_explanation_surface()["facts"])
    seen = set()
    records = []
    for item in facts:
        if not isinstance(item, dict):
            raise ValueError("evidence detail registry record is required")
        fact_id = item.get("fact_id")
        if not isinstance(fact_id, str) or not fact_id:
            raise ValueError("evidence detail registry fact id is required")
        if fact_id in seen:
            raise ValueError(f"evidence detail fact is duplicated: {fact_id}")
        seen.add(fact_id)
        if fact_id not in surface_ids:
            raise ValueError(f"evidence detail fact is unknown: {fact_id}")
        records.append(_validate_record(item))
    missing = [fact_id for fact_id in surface_ids if fact_id not in seen]
    if missing:
        raise ValueError(f"evidence detail fact is missing: {missing[0]}")
    return {"version": version, "facts": records}


def _validate_record(item):
    try:
        record = EvidenceDetailRecord(**item)
    except ValidationError as exc:
        raise ValueError(
            f"evidence detail record is invalid: {item['fact_id']}"
        ) from exc
    data = record.model_dump()
    _validate_unique_topics(data, "supported_topics")
    _validate_unique_topics(data, "default_topics")
    if not set(data["default_topics"]).issubset(set(data["supported_topics"])):
        raise ValueError(
            f"evidence detail default topic is not supported: {data['fact_id']}"
        )
    if data["supported_topics"] and not data["aliases"]:
        raise ValueError(f"evidence detail fact requires aliases: {data['fact_id']}")
    return data


def _validate_unique_topics(record, key):
    topics = record[key]
    if len(topics) != len(set(topics)):
        raise ValueError(f"evidence detail topic is duplicated: {record['fact_id']}")


def _record_matches(aliases, normalized_question):
    for alias in aliases:
        if _alias_matches(alias, normalized_question):
            return True
    return False


def _alias_matches(alias, normalized_question):
    if not isinstance(alias, str) or not alias:
        return False
    if _CJK_RE.search(alias):
        return _compact_text(alias.lower()) in _compact_text(normalized_question)
    pattern = rf"(?<![a-zA-Z0-9]){re.escape(alias.lower())}(?![a-zA-Z0-9])"
    return re.search(pattern, normalized_question) is not None


def _normalize_question(question):
    return " ".join(question.lower().split())


def _compact_text(text):
    return _WHITESPACE_RE.sub("", text)
