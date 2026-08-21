import json

import pytest

from app.services import commodity_attribution_catalog as service

COPPER_RECORD = {
    "commodity_id": "copper",
    "source_name": "Chilean Copper Commission",
    "source_url": "https://www.cochilco.cl/",
    "source_type": "official_data",
    "coverage": ["mining_production", "inventories"],
    "source_ref": "cyclical_commodities_demand_supply",
    "status": "cataloged",
}


def test_load_returns_artifact_and_rejects_invalid_version(tmp_path):
    valid = {
        "version": "commodity_attribution_evidence_catalog_v1",
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_document": "cyclical_commodities_demand_supply",
        "resources": [COPPER_RECORD],
    }
    valid_path = tmp_path / "valid.json"
    valid_path.write_text(json.dumps(valid))

    loaded = service.load_commodity_attribution_catalog(valid_path)
    assert loaded["resources"] == [COPPER_RECORD]

    invalid = dict(valid, version="commodity_attribution_evidence_catalog_v2")
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(invalid))

    with pytest.raises(ValueError, match="version is invalid"):
        service.load_commodity_attribution_catalog(invalid_path)
