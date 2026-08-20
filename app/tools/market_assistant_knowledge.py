import json
from pathlib import Path

from app.resources import resource_path

KNOWLEDGE_PATH = resource_path("assistant_knowledge")

_OBJECT_TYPES = frozenset(
    {"indicator_definition", "indicator_method", "indicator_source"}
)
_AUTHORITY = "method_knowledge"
_NO_DECISION_EFFECT = "none"
_NON_DECISION_RELATION = "non_decision"
_REQUIRED_KEYS = frozenset(
    {"record_id", "version", "object_type", "authority", "source"}
)
_APPROVED_FORMULAS = frozenset(
    {
        "% Better + 0.5 × % Same",
        "close <= rolling_high x 0.8",
    }
)


def load_knowledge_catalog(path=KNOWLEDGE_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_knowledge_catalog(payload)


def validate_knowledge_catalog(payload):
    if not isinstance(payload, dict) or "version" not in payload:
        raise ValueError("knowledge catalog version is required")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("knowledge catalog records are required")
    seen = set()
    for record in records:
        _validate_record(record, seen)
    return payload


def _validate_record(record, seen):
    if not isinstance(record, dict):
        raise ValueError("knowledge record is not an object")
    missing = sorted(_REQUIRED_KEYS - set(record))
    if missing:
        subject = _record_subject(record)
        raise ValueError(f"{subject} is missing required fields: {', '.join(missing)}")
    record_id = record["record_id"]
    if not isinstance(record_id, str) or not record_id:
        raise ValueError("knowledge record id is required")
    version = record["version"]
    if not isinstance(version, str) or not version:
        raise ValueError(f"knowledge record {record_id} version is required")
    version_key = (record_id, version)
    if version_key in seen:
        raise ValueError(
            f"knowledge record {record_id} version {version} is duplicated"
        )
    seen.add(version_key)
    object_type = record["object_type"]
    if object_type not in _OBJECT_TYPES:
        raise ValueError(
            f"knowledge record {record_id} has unknown object type: {object_type}"
        )
    if record["authority"] != _AUTHORITY:
        raise ValueError(
            f"knowledge record {record_id} has unknown authority: {record['authority']}"
        )
    decision_effect = record.get("decision_effect")
    if decision_effect is not None and decision_effect != _NO_DECISION_EFFECT:
        raise ValueError(f"knowledge record {record_id} must have no decision effect")
    market_setup_relation = record.get("market_setup_relation")
    if (
        market_setup_relation is not None
        and market_setup_relation != _NON_DECISION_RELATION
    ):
        raise ValueError(f"knowledge record {record_id} must be non-decision")
    formula = record.get("formula")
    if formula is not None and formula not in _APPROVED_FORMULAS:
        raise ValueError(f"knowledge record {record_id} has an unapproved formula")
    source = record.get("source")
    if not isinstance(source, dict) or not source:
        raise ValueError(f"knowledge record {record_id} source metadata is required")
    source_module = source.get("source_module")
    if not isinstance(source_module, str) or not source_module:
        raise ValueError(f"knowledge record {record_id} source module is required")
    if record.get("source_period_required"):
        periods = source.get("periods")
        if not _has_source_periods(periods):
            raise ValueError(
                f"knowledge record {record_id} source periods are required"
            )


def _record_subject(record):
    record_id = record.get("record_id")
    if isinstance(record_id, str) and record_id:
        return f"knowledge record {record_id}"
    return "knowledge record"


def _has_source_periods(periods):
    if not isinstance(periods, list) or not periods:
        return False
    return all(isinstance(period, str) and period for period in periods)


def get_knowledge_record(catalog, record_id, version=None):
    records = catalog.get("records") if isinstance(catalog, dict) else None
    if not isinstance(records, list):
        raise ValueError("knowledge catalog records are required")
    matches = [record for record in records if record.get("record_id") == record_id]
    if not matches:
        raise ValueError(f"knowledge record {record_id} is not available")
    if version is not None:
        for record in matches:
            if record.get("version") == version:
                return record
        raise ValueError(
            f"knowledge record {record_id} version {version} is not available"
        )
    return max(matches, key=lambda record: record["version"])
