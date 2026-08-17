import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.market_assistant_evidence_details import PROJECTION_DETAIL_KINDS
from app.tools.market_setup_evidence_facts import load_explanation_surface

REGISTRY_PATH = (
    Path(__file__).resolve().parent / "market_assistant_evidence_details.v1.json"
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

_UNSUPPORTED_VERSION = "market_assistant_evidence_detail_unsupported_v1"

_FACT_CONTRACTS = {
    "survey_growth_direction": {
        "scope": "decision_input",
        "detail_kind": "survey_synthesis",
        "topics": frozenset({"current", "drivers", "source"}),
        "default_topics": ("current", "drivers", "source"),
        "source_module": "ism_survey_synthesis",
        "aliases": (
            "manufacturing and services",
            "ISM survey",
            "survey direction",
            "制造业和服务业",
            "调查方向",
            "增长方向依据",
        ),
        "projection_version": "market_assistant_survey_synthesis_detail_v1",
    },
    "macro_financial_conditions": {
        "scope": "decision_input",
        "detail_kind": "financial_conditions",
        "topics": frozenset({"current", "drivers", "source"}),
        "default_topics": ("current", "drivers", "source"),
        "source_module": "us_rates_liquidity",
        "aliases": (
            "financial conditions",
            "yield curve",
            "real rates",
            "金融条件",
            "收益率曲线",
            "实际利率",
        ),
        "projection_version": "market_assistant_financial_conditions_detail_v1",
    },
    "macro_policy_response": {
        "scope": "decision_input",
        "detail_kind": "policy_response",
        "topics": frozenset({"current", "drivers", "source"}),
        "default_topics": ("current", "drivers", "source"),
        "source_module": "fomc_policy_tone",
        "aliases": (
            "FOMC",
            "Fed",
            "monetary policy",
            "美联储",
            "货币政策",
            "利率决定",
            "鹰派",
            "鸽派",
        ),
        "projection_version": "market_assistant_policy_response_detail_v1",
    },
    "consumer_demand_outlook": {
        "scope": "confirmation_input",
        "detail_kind": "consumer_demand",
        "topics": frozenset({"current", "drivers", "source"}),
        "default_topics": ("current", "drivers", "source"),
        "source_module": "consumer_sentiment",
        "aliases": (
            "consumer expectations",
            "consumer demand",
            "consumer confidence",
            "消费者预期",
            "消费者需求",
            "消费者信心",
        ),
        "projection_version": "market_assistant_consumer_demand_detail_v1",
    },
    "sp500_market_phase": {
        "scope": "confirmation_input",
        "detail_kind": "market_phase",
        "topics": frozenset({"current", "method", "source"}),
        "default_topics": ("current", "method", "source"),
        "source_module": "market_phase",
        "aliases": (
            "S&P 500 phase",
            "S&P 500",
            "market phase",
            "标普市场阶段",
            "标普",
            "牛市阶段",
            "熊市阶段",
        ),
        "projection_version": "market_assistant_market_phase_detail_v1",
    },
    "credit_conditions": {
        "scope": "confirmation_input",
        "detail_kind": "credit_conditions",
        "topics": frozenset({"current", "method", "source"}),
        "default_topics": ("current", "method", "source"),
        "source_module": "us_rates_liquidity",
        "aliases": (
            "credit conditions",
            "credit spreads",
            "信贷条件",
            "信用条件",
            "信用利差",
        ),
        "projection_version": "market_assistant_credit_conditions_detail_v1",
    },
    "vix_level": {
        "scope": "confirmation_input",
        "detail_kind": "vix",
        "topics": frozenset({"current", "method", "source"}),
        "default_topics": ("current", "method", "source"),
        "source_module": "us_rates_liquidity",
        "aliases": ("VIX", "波动率", "恐慌指数"),
        "projection_version": "market_assistant_vix_detail_v1",
    },
    "m2_liquidity": {
        "scope": "context_only",
        "detail_kind": "m2_liquidity",
        "topics": frozenset({"current", "method", "source"}),
        "default_topics": ("current", "method", "source"),
        "source_module": "m2_money_supply",
        "aliases": (
            "M2 liquidity",
            "M2 supply",
            "M2 流动性",
            "M2 货币供应",
        ),
        "projection_version": "market_assistant_m2_liquidity_detail_v1",
    },
}

_DISABLED_FACT_CONTRACTS = {
    "equity_breadth": {
        "scope": "observation_only",
        "source_module": "observation_only",
    },
    "jobless_claims": {
        "scope": "observation_only",
        "source_module": "observation_only",
    },
    "economic_confirmation": {
        "scope": "context_only",
        "source_module": "economic_confirmation",
    },
    "cyclical_commodities": {
        "scope": "observation_only",
        "source_module": "cyclical_commodities",
    },
    "nfib_regional_evidence": {
        "scope": "manual_review",
        "source_module": "nfib_sbo_regional",
    },
}

_DISABLED_FACT_IDS = frozenset(_DISABLED_FACT_CONTRACTS)

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
    fact_id = data["fact_id"]
    if fact_id in _DISABLED_FACT_IDS:
        contract = _DISABLED_FACT_CONTRACTS[fact_id]
        if data["detail_kind"] != "unsupported":
            raise ValueError(f"evidence detail fact is not enabled: {fact_id}")
        if data["supported_topics"]:
            raise ValueError(
                f"unsupported evidence detail fact declares topics: {fact_id}"
            )
        if data["projection_version"] != _UNSUPPORTED_VERSION:
            raise ValueError(
                f"unsupported evidence detail fact has an unknown projection version: {fact_id}"
            )
        if data["scope"] != contract["scope"]:
            raise ValueError(f"evidence detail fact has the wrong scope: {fact_id}")
        if data["source_module"] != contract["source_module"]:
            raise ValueError(
                f"evidence detail fact has the wrong source module: {fact_id}"
            )
    else:
        contract = _FACT_CONTRACTS[fact_id]
        if data["detail_kind"] != contract["detail_kind"]:
            raise ValueError(
                f"evidence detail fact has the wrong detail kind: {fact_id}"
            )
        if data["detail_kind"] not in PROJECTION_DETAIL_KINDS:
            raise ValueError(
                f"evidence detail projection is not registered: {data['detail_kind']}"
            )
        if not data["supported_topics"]:
            raise ValueError(
                f"evidence detail fact requires supported topics: {fact_id}"
            )
        if set(data["supported_topics"]) != contract["topics"]:
            raise ValueError(
                f"evidence detail fact declares unsupported topics: {fact_id}"
            )
        if data["projection_version"] != contract["projection_version"]:
            raise ValueError(
                f"evidence detail fact has the wrong projection version: {fact_id}"
            )
        if data["scope"] != contract["scope"]:
            raise ValueError(f"evidence detail fact has the wrong scope: {fact_id}")
        if tuple(data["default_topics"]) != contract["default_topics"]:
            raise ValueError(
                f"evidence detail fact has the wrong default topics: {fact_id}"
            )
        if data["source_module"] != contract["source_module"]:
            raise ValueError(
                f"evidence detail fact has the wrong source module: {fact_id}"
            )
        if tuple(data["aliases"]) != tuple(contract["aliases"]):
            raise ValueError(f"evidence detail fact has the wrong aliases: {fact_id}")
    if not set(data["default_topics"]).issubset(set(data["supported_topics"])):
        raise ValueError(f"evidence detail default topic is not supported: {fact_id}")
    if data["supported_topics"] and not data["aliases"]:
        raise ValueError(f"evidence detail fact requires aliases: {fact_id}")
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
