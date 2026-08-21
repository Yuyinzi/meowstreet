import json
from pathlib import Path

VERSION = "commodity_attribution_evidence_catalog_v1"
SOURCE_DOCUMENT = "cyclical_commodities_demand_supply"


def load_commodity_attribution_catalog(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_version(payload)
    return payload


def _validate_version(payload):
    if payload.get("version") != VERSION:
        raise ValueError(
            f"commodities attribution catalog version is invalid: {payload.get('version')}"
        )
