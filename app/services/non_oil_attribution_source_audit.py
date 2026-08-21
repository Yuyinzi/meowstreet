import json
from datetime import datetime, timezone
from pathlib import Path

from app.services import commodity_attribution_catalog as catalog_service
from app.data_sources import non_oil_attribution_source_audit as source

VERSION = "non_oil_attribution_source_audit_v1"
SOURCE_CATALOG_PATH = "app/resources/commodity_attribution_catalog.v1.json"


def build_non_oil_attribution_source_audit(catalog_path, generated_at=None):
    catalog = catalog_service.load_commodity_attribution_catalog(catalog_path)
    audits = source.validate_non_oil_attribution_audits(
        source.AUDITED_RECORDS, catalog["resources"]
    )
    return {
        "version": VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_catalog_version": catalog_service.VERSION,
        "source_catalog": SOURCE_CATALOG_PATH,
        "audits": sorted(
            audits,
            key=lambda row: (
                row["commodity_id"],
                row["source_name"],
                row["source_url"],
            ),
        ),
    }


def write_non_oil_attribution_source_audit(
    destination, catalog_path, generated_at=None
):
    payload = build_non_oil_attribution_source_audit(
        catalog_path, generated_at=generated_at
    )
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def load_non_oil_attribution_source_audit(path, catalog_path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    catalog = catalog_service.load_commodity_attribution_catalog(catalog_path)
    _validate_artifact(payload, catalog)
    return payload


def _validate_artifact(payload, catalog):
    if payload.get("version") != VERSION:
        raise ValueError(
            f"commodities non-oil source audit version is invalid: {payload.get('version')}"
        )
    if payload.get("source_catalog_version") != catalog_service.VERSION:
        raise ValueError(
            "commodities non-oil source audit source catalog version is invalid: "
            f"{payload.get('source_catalog_version')}"
        )
    audits = payload.get("audits")
    if audits is None:
        raise ValueError("commodities non-oil source audit payload is missing the audits key")
    source.validate_non_oil_attribution_audits(audits, catalog["resources"])
