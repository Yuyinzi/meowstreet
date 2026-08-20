import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import commodity_attribution_catalog as service
from app.data_sources import commodity_attribution_catalog as catalog_source

ROOT = Path(__file__).resolve().parents[1]

COPPER_RECORD = {
    "commodity_id": "copper",
    "source_name": "Chilean Copper Commission",
    "source_url": "https://www.cochilco.cl/",
    "source_type": "official_data",
    "coverage": ["mining_production", "inventories"],
    "source_ref": catalog_source.SOURCE_REF,
    "status": "cataloged",
}

OIL_RECORD = {
    "commodity_id": "oil",
    "source_name": "BP World Energy",
    "source_url": "https://www.bp.com/en/global/corporate/energy-economics/statistical-review-of-world-energy.html",
    "source_type": "reference_market_data",
    "coverage": ["reserves", "prices"],
    "source_ref": catalog_source.SOURCE_REF,
    "status": "cataloged",
}

LUMBER_RECORD = {
    "commodity_id": "lumber",
    "source_name": "Food and Agriculture Organization of the United Nations",
    "source_url": "https://www.fao.org/faostat/en/#data/FO",
    "source_type": "official_data",
    "coverage": ["production", "imports"],
    "source_ref": catalog_source.SOURCE_REF,
    "status": "cataloged",
}


def _stub_parser(monkeypatch, records):
    monkeypatch.setattr(
        catalog_source,
        "parse_commodity_attribution_pdf",
        lambda path: list(records),
    )


def test_build_returns_versioned_artifact_with_injected_timestamp(monkeypatch):
    _stub_parser(monkeypatch, [OIL_RECORD, COPPER_RECORD, LUMBER_RECORD])

    payload = service.build_commodity_attribution_catalog(
        "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    assert payload["version"] == "commodity_attribution_evidence_catalog_v1"
    assert payload["generated_at"] == "2026-08-02T00:00:00+00:00"
    assert payload["source_document"] == (
        "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf"
    )


def test_build_sorts_resources_by_commodity_name_url(monkeypatch):
    _stub_parser(monkeypatch, [OIL_RECORD, LUMBER_RECORD, COPPER_RECORD])

    payload = service.build_commodity_attribution_catalog(
        "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    names = [r["source_name"] for r in payload["resources"]]
    assert names == [
        "Chilean Copper Commission",
        "Food and Agriculture Organization of the United Nations",
        "BP World Energy",
    ]


def test_build_defaults_timestamp_when_not_injected(monkeypatch):
    _stub_parser(monkeypatch, [OIL_RECORD])

    payload = service.build_commodity_attribution_catalog(
        "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf"
    )

    assert payload["generated_at"]


def test_build_rejects_duplicate_commodity_url_pair(monkeypatch):
    dup = dict(COPPER_RECORD)
    _stub_parser(monkeypatch, [COPPER_RECORD, dup])

    with pytest.raises(ValueError, match="duplicate  attribution resource"):
        service.build_commodity_attribution_catalog("path.pdf")


def test_build_rejects_unknown_coverage_label(monkeypatch):
    bad = dict(COPPER_RECORD, coverage=["inventories", "fictional_metric"])
    _stub_parser(monkeypatch, [bad])

    with pytest.raises(ValueError, match="coverage.*not in the method vocabulary"):
        service.build_commodity_attribution_catalog("path.pdf")


def test_build_rejects_absent_resources(monkeypatch):
    _stub_parser(monkeypatch, [])

    with pytest.raises(ValueError, match="no resources"):
        service.build_commodity_attribution_catalog("path.pdf")


def test_build_rejects_invalid_commodity_id(monkeypatch):
    bad = dict(COPPER_RECORD, commodity_id="gasoline")
    _stub_parser(monkeypatch, [bad])

    with pytest.raises(ValueError, match="not a valid commodity"):
        service.build_commodity_attribution_catalog("path.pdf")


def test_build_rejects_invalid_source_type(monkeypatch):
    bad = dict(COPPER_RECORD, source_type="brokerage")
    _stub_parser(monkeypatch, [bad])

    with pytest.raises(ValueError, match="not a valid source type"):
        service.build_commodity_attribution_catalog("path.pdf")


def test_write_persists_deterministic_json(tmp_path, monkeypatch):
    _stub_parser(monkeypatch, [OIL_RECORD, COPPER_RECORD, LUMBER_RECORD])
    destination = tmp_path / "nested" / "catalog.v1.json"

    payload = service.write_commodity_attribution_catalog(
        destination,
        "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    assert destination.exists()
    written = json.loads(destination.read_text())
    assert written == payload
    assert payload["version"] == "commodity_attribution_evidence_catalog_v1"


def test_load_returns_artifact_and_rejects_invalid_version(tmp_path):
    valid = {
        "version": "commodity_attribution_evidence_catalog_v1",
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_document": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
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


def test_build_script_writes_catalog_and_exits_zero(tmp_path):
    script = ROOT / "scripts" / "build_commodity_attribution_catalog.py"
    destination = tmp_path / "catalog.v1.json"
    source = (
        ROOT
        / "data"
        / "materials"
        / "Video 12"
        / "Cyclical_Commodities_Demand_Supply_Factors.pdf"
    )
    if not source.is_file():
        pytest.skip(" attribution source pdf is not available locally")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source-path",
            str(source),
            "--output-path",
            str(destination),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr
    assert destination.exists()
    payload = json.loads(destination.read_text())
    assert payload["version"] == "commodity_attribution_evidence_catalog_v1"
    assert len(payload["resources"]) == 35
