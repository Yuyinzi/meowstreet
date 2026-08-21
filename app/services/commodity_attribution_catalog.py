import json
from datetime import datetime, timezone
from pathlib import Path

from app.data_sources import commodity_attribution_catalog as catalog_source

VERSION = "commodity_attribution_evidence_catalog_v1"
SOURCE_DOCUMENT = "cyclical_commodities_demand_supply"


def build_commodity_attribution_catalog(source_path, generated_at=None):
    records = catalog_source.parse_commodity_attribution_pdf(source_path)
    resources = _normalize_resources(records)
    return {
        "version": VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_document": SOURCE_DOCUMENT,
        "resources": resources,
    }


def write_commodity_attribution_catalog(
    destination, source_path, generated_at=None
):
    payload = build_commodity_attribution_catalog(
        source_path, generated_at=generated_at
    )
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def load_commodity_attribution_catalog(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_version(payload)
    return payload


def _validate_version(payload):
    if payload.get("version") != VERSION:
        raise ValueError(
            f" attribution catalog version is invalid: {payload.get('version')}"
        )


def _normalize_resources(records):
    if not records:
        raise ValueError(" attribution catalog has no resources")
    seen = set()
    normalized = []
    for record in records:
        entry = _normalize_record(record)
        key = (entry["commodity_id"], entry["source_url"])
        if key in seen:
            raise ValueError(
                f"duplicate  attribution resource {entry['source_url']} for {entry['commodity_id']}"
            )
        seen.add(key)
        normalized.append(entry)
    return sorted(normalized, key=_resource_sort_key)


def _resource_sort_key(resource):
    return (resource["commodity_id"], resource["source_name"], resource["source_url"])


def _normalize_record(record):
    _validate_record(record)
    return {
        "commodity_id": record["commodity_id"],
        "source_name": record["source_name"],
        "source_url": record["source_url"],
        "source_type": record["source_type"],
        "coverage": list(record["coverage"]),
        "source_ref": record["source_ref"],
        "status": record["status"],
    }


def _validate_record(record):
    if record["commodity_id"] not in catalog_source.VALID_COMMODITY_IDS:
        raise ValueError(
            f" attribution commodity {record['commodity_id']} is not a valid commodity"
        )
    if record["source_type"] not in catalog_source.VALID_SOURCE_TYPES:
        raise ValueError(
            f" attribution source type {record['source_type']} is not a valid source type"
        )
    if not record["source_name"]:
        raise ValueError(" attribution record has an empty source name")
    if not record["source_url"]:
        raise ValueError(" attribution record has an empty source url")
    if not record["coverage"]:
        raise ValueError(
            f" attribution coverage is empty for {record['source_name']}"
        )
    unknown = [
        token
        for token in record["coverage"]
        if token not in catalog_source.COVERAGE_VOCABULARY
    ]
    if unknown:
        raise ValueError(
            f" attribution coverage {unknown} is not in the method vocabulary"
        )
