import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.data_sources import non_oil_attribution_source_audit as source
from app.services import non_oil_attribution_source_audit as service

ROOT = Path(__file__).resolve().parents[1]

CATALOG_PATH = (
    ROOT
    / "data"
    / "local_system"
    / "commodity_attribution_evidence_catalog.v1.json"
)

AUDIT_PATH = (
    ROOT / "data" / "local_system" / "non_oil_attribution_source_audit.v1.json"
)

SOURCE_REF = "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf"
CATALOG_VERSION = "commodity_attribution_evidence_catalog_v1"
AUDITED_AT = "2026-08-02"


def copper_audit():
    catalog = copper_catalog()
    return {
        "commodity_id": "copper",
        "source_name": catalog["source_name"],
        "source_url": catalog["source_url"],
        "source_type": catalog["source_type"],
        "source_coverage": list(catalog["coverage"]),
        "audit_status": "structured_recurring_candidate",
        "access_method": "html_table",
        "factor_categories": ["demand", "supply"],
        "geography": "Global",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "t",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "official statistics published monthly by the commission",
        "audited_at": AUDITED_AT,
        "source_ref": catalog["source_ref"],
    }


def lumber_audit():
    catalog = lumber_catalog()
    return {
        "commodity_id": "lumber",
        "source_name": catalog["source_name"],
        "source_url": catalog["source_url"],
        "source_type": catalog["source_type"],
        "source_coverage": list(catalog["coverage"]),
        "audit_status": "structured_recurring_candidate",
        "access_method": "csv_download",
        "factor_categories": ["supply", "demand"],
        "geography": "Global",
        "frequency": "annual",
        "unit_status": "published",
        "units": "t",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "official statistical database maintained by the united nations",
        "audited_at": AUDITED_AT,
        "source_ref": catalog["source_ref"],
    }


def copper_catalog():
    return {
        "commodity_id": "copper",
        "source_name": "Chilean Copper Commission",
        "source_url": "https://www.cochilco.cl/",
        "source_type": "official_data",
        "coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
        "source_ref": SOURCE_REF,
    }


def lumber_catalog():
    return {
        "commodity_id": "lumber",
        "source_name": "Food and Agriculture Organization of the United Nations",
        "source_url": "https://www.fao.org/faostat/en/#data/FO",
        "source_type": "official_data",
        "coverage": ["production", "imports", "exports"],
        "source_ref": SOURCE_REF,
    }


def write_catalog(tmp_path, resources):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": CATALOG_VERSION,
                "generated_at": "2026-08-02T00:00:00+00:00",
                "source_document": SOURCE_REF,
                "resources": resources,
            }
        ),
        encoding="utf-8",
    )
    return catalog_path


def test_build_returns_sorted_versioned_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(
        source, "AUDITED_RECORDS", [lumber_audit(), copper_audit()], raising=False
    )
    catalog_path = write_catalog(tmp_path, [lumber_catalog(), copper_catalog()])

    payload = service.build_non_oil_attribution_source_audit(
        catalog_path, generated_at="2026-08-02T00:00:00+00:00"
    )

    assert payload["version"] == "non_oil_attribution_source_audit_v1"
    assert [row["commodity_id"] for row in payload["audits"]] == ["copper", "lumber"]


def test_load_rejects_wrong_catalog_version(tmp_path):
    artifact_path = tmp_path / "audit.json"
    catalog_path = write_catalog(tmp_path, [copper_catalog()])
    artifact_path.write_text(
        json.dumps(
            {
                "version": service.VERSION,
                "source_catalog_version": "wrong",
                "audits": [],
            }
        )
    )

    with pytest.raises(ValueError, match="source catalog version is invalid"):
        service.load_non_oil_attribution_source_audit(artifact_path, catalog_path)


def test_write_persists_deterministic_json(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "AUDITED_RECORDS", [copper_audit()], raising=False)
    catalog_path = write_catalog(tmp_path, [copper_catalog()])
    destination = tmp_path / "nested" / "audit.v1.json"

    payload = service.write_non_oil_attribution_source_audit(
        destination,
        catalog_path,
        generated_at="2026-08-02T00:00:00+00:00",
    )

    assert destination.exists()
    written = json.loads(destination.read_text())
    assert written == payload
    assert payload["version"] == "non_oil_attribution_source_audit_v1"
    assert [row["commodity_id"] for row in payload["audits"]] == ["copper"]


def test_build_defaults_timestamp_when_not_injected(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "AUDITED_RECORDS", [copper_audit()], raising=False)
    catalog_path = write_catalog(tmp_path, [copper_catalog()])

    payload = service.build_non_oil_attribution_source_audit(catalog_path)

    assert payload["generated_at"]


def test_load_returns_artifact_and_rejects_invalid_version(tmp_path):
    catalog_path = write_catalog(tmp_path, [copper_catalog()])
    valid = {
        "version": service.VERSION,
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_catalog_version": CATALOG_VERSION,
        "source_catalog": "data/local_system/commodity_attribution_evidence_catalog.v1.json",
        "audits": [copper_audit()],
    }
    valid_path = tmp_path / "valid.json"
    valid_path.write_text(json.dumps(valid))

    loaded = service.load_non_oil_attribution_source_audit(valid_path, catalog_path)
    assert loaded["audits"] == [copper_audit()]

    invalid = dict(valid, version="non_oil_attribution_source_audit_v2")
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(invalid))

    with pytest.raises(ValueError, match="version is invalid"):
        service.load_non_oil_attribution_source_audit(invalid_path, catalog_path)


def test_load_rejects_artifact_with_missing_audits_key(tmp_path):
    catalog_path = write_catalog(tmp_path, [copper_catalog()])
    artifact_path = tmp_path / "no-audits.json"
    artifact_path.write_text(
        json.dumps(
            {
                "version": service.VERSION,
                "source_catalog_version": CATALOG_VERSION,
            }
        )
    )

    with pytest.raises(ValueError, match="missing the audits key"):
        service.load_non_oil_attribution_source_audit(artifact_path, catalog_path)


def test_seed_regeneration_matches_checked_in_audit():
    built = service.build_non_oil_attribution_source_audit(
        CATALOG_PATH, generated_at="2026-08-02T00:00:00+00:00"
    )
    loaded = service.load_non_oil_attribution_source_audit(AUDIT_PATH, CATALOG_PATH)

    assert built["audits"] == loaded["audits"]


def test_build_script_writes_audit_and_exits_zero(tmp_path):
    script = ROOT / "scripts" / "build_non_oil_attribution_source_audit.py"
    destination = tmp_path / "audit.v1.json"
    catalog = (
        ROOT
        / "data"
        / "local_system"
        / "commodity_attribution_evidence_catalog.v1.json"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--catalog-path",
            str(catalog),
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
    assert payload["version"] == "non_oil_attribution_source_audit_v1"
    assert len(payload["audits"]) == 20
