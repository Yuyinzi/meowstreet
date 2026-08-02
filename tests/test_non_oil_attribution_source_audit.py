import json
from collections import Counter
from pathlib import Path

import pytest

from app.data_sources import commodity_attribution_catalog as catalog_source
from app.data_sources import non_oil_attribution_source_audit as audit
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

COMMODITY_DEFAULTS = {
    "copper": {
        "source_name": "Chilean Copper Commission",
        "source_type": "official_data",
        "coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
    },
    "lumber": {
        "source_name": "Food and Agriculture Organization of the United Nations",
        "source_type": "official_data",
        "coverage": ["production", "imports", "exports"],
    },
    "iron_ore": {
        "source_name": "Government of Western Australia",
        "source_type": "official_data",
        "coverage": [
            "statistics_digest",
            "statistics_releases",
            "industry_activity_indicators",
        ],
    },
}


def catalog_record(commodity_id, url):
    defaults = COMMODITY_DEFAULTS[commodity_id]
    return {
        "commodity_id": commodity_id,
        "source_name": defaults["source_name"],
        "source_url": url,
        "source_type": defaults["source_type"],
        "coverage": list(defaults["coverage"]),
        "source_ref": catalog_source.SOURCE_REF,
    }


def audit_record(commodity_id, url, catalog=None):
    catalog = catalog or catalog_record(commodity_id, url)
    return {
        "commodity_id": commodity_id,
        "source_name": catalog["source_name"],
        "source_url": url,
        "source_type": catalog["source_type"],
        "source_coverage": list(catalog["coverage"]),
        "audit_status": "structured_recurring_candidate",
        "access_method": "api",
        "factor_categories": ["supply", "demand", "inventory", "price"],
        "geography": "global",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "metric tons",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "audited against the method evidence catalog",
        "audited_at": "2026-08-02",
        "source_ref": catalog["source_ref"],
    }


def real_catalog_resources():
    payload = json.loads(CATALOG_PATH.read_text())
    return payload["resources"]


def non_oil_audit_records(catalog_resources):
    resources = [
        resource
        for resource in catalog_resources
        if resource["commodity_id"] in {"copper", "lumber", "iron_ore"}
    ]
    return [
        audit_record(resource["commodity_id"], resource["source_url"], catalog=resource)
        for resource in resources
    ]


def test_validate_accepts_one_audit_for_each_non_oil_catalog_url():
    records = [audit_record("copper", "https://example.test/copper")]
    catalog_resources = [catalog_record("copper", "https://example.test/copper")]

    assert (
        audit.validate_non_oil_attribution_audits(records, catalog_resources)
        == records
    )


def test_validate_accepts_audit_record_with_exact_contract_keys():
    record = audit_record("copper", "https://example.test/copper")

    assert set(record) == {
        "commodity_id",
        "source_name",
        "source_url",
        "source_type",
        "source_coverage",
        "audit_status",
        "access_method",
        "factor_categories",
        "geography",
        "frequency",
        "unit_status",
        "units",
        "publication_date_status",
        "stability",
        "audit_basis",
        "audited_at",
        "source_ref",
    }
    assert audit.validate_non_oil_attribution_audits(
        [record], [catalog_record("copper", "https://example.test/copper")]
    ) == [record]


def test_validate_rejects_audit_record_with_missing_key():
    record = audit_record("copper", "https://example.test/copper")
    del record["audit_basis"]

    with pytest.raises(ValueError, match="missing"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_audit_record_with_extra_key():
    record = audit_record("copper", "https://example.test/copper")
    record["extra_key"] = "surplus"

    with pytest.raises(ValueError, match="extra"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_oil_commodity_audit():
    record = audit_record("copper", "https://example.test/oil")
    record["commodity_id"] = "oil"

    with pytest.raises(ValueError, match="is not a valid commodity"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_missing_catalog_url():
    with pytest.raises(ValueError, match="does not match a non-oil catalog resource"):
        audit.validate_non_oil_attribution_audits(
            [audit_record("copper", "https://example.test/missing")],
            [catalog_record("copper", "https://example.test/copper")],
        )


def test_validate_rejects_candidate_without_published_unit_or_frequency():
    record = audit_record("lumber", "https://example.test/lumber")
    record["frequency"] = "not_published"

    with pytest.raises(
        ValueError,
        match="structured recurring candidate requires a published frequency",
    ):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("lumber", "https://example.test/lumber")]
        )


def test_validate_accepts_all_twenty_non_oil_catalog_resources():
    catalog_resources = real_catalog_resources()

    validated = audit.validate_non_oil_attribution_audits(
        non_oil_audit_records(catalog_resources), catalog_resources
    )

    assert len(validated) == 20
    assert Counter(record["commodity_id"] for record in validated) == {
        "copper": 9,
        "lumber": 5,
        "iron_ore": 6,
    }
    assert {record["commodity_id"] for record in validated} == {
        "copper",
        "lumber",
        "iron_ore",
    }


def test_validate_rejects_an_audit_that_does_not_cover_every_catalog_resource():
    catalog_resources = real_catalog_resources()

    with pytest.raises(ValueError, match="does not cover every catalog resource"):
        audit.validate_non_oil_attribution_audits(
            non_oil_audit_records(catalog_resources)[:-1], catalog_resources
        )


def test_validate_rejects_unknown_audit_status():
    record = audit_record("copper", "https://example.test/copper")
    record["audit_status"] = "fictional_status"

    with pytest.raises(ValueError, match="is not a valid audit status"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_unknown_access_method():
    record = audit_record("copper", "https://example.test/copper")
    record["access_method"] = "scraping"

    with pytest.raises(ValueError, match="is not a valid access method"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_unknown_factor_category():
    record = audit_record("copper", "https://example.test/copper")
    record["factor_categories"] = ["supply", "fictional_factor"]

    with pytest.raises(ValueError, match="is not a valid factor category"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_unknown_coverage_token():
    record = audit_record("copper", "https://example.test/copper")
    record["source_coverage"] = ["fictional_metric"]

    with pytest.raises(ValueError, match="not in the method vocabulary"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("frequency", "intraday"),
        ("unit_status", "archived"),
        ("publication_date_status", "archived"),
        ("stability", "volatile"),
        ("source_type", "brokerage"),
    ],
)
def test_validate_rejects_unknown_scalar_vocabulary(field, value):
    record = audit_record("copper", "https://example.test/copper")
    record[field] = value

    with pytest.raises(ValueError, match="is not a valid"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_duplicate_audit_key():
    catalog_resources = [catalog_record("copper", "https://example.test/copper")]
    records = [
        audit_record("copper", "https://example.test/copper"),
        audit_record("copper", "https://example.test/copper"),
    ]

    with pytest.raises(ValueError, match="duplicate"):
        audit.validate_non_oil_attribution_audits(records, catalog_resources)


def test_validate_rejects_audit_source_name_mismatch():
    record = audit_record("copper", "https://example.test/copper")
    record["source_name"] = "Some Other Copper Source"

    with pytest.raises(ValueError, match="source name does not match"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_audit_source_type_mismatch():
    record = audit_record("copper", "https://example.test/copper")
    record["source_type"] = "industry_body"

    with pytest.raises(ValueError, match="source type does not match"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_audit_source_coverage_mismatch():
    record = audit_record("copper", "https://example.test/copper")
    record["source_coverage"] = ["prices"]

    with pytest.raises(ValueError, match="method coverage does not match"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_audit_source_ref_mismatch():
    record = audit_record("copper", "https://example.test/copper")
    record["source_ref"] = "data/source_material/Video 12/some_other.pdf"

    with pytest.raises(ValueError, match="method reference does not match"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


@pytest.mark.parametrize(
    "audited_at",
    ["2026-13-99", "2026/08/02", "not-a-date", "2026-08-2"],
)
def test_validate_rejects_invalid_audit_date(audited_at):
    record = audit_record("copper", "https://example.test/copper")
    record["audited_at"] = audited_at

    with pytest.raises(ValueError, match="not a valid iso date"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_without_factor_categories():
    record = audit_record("copper", "https://example.test/copper")
    record["factor_categories"] = []

    with pytest.raises(ValueError, match="requires factor categories"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_without_geography():
    record = audit_record("copper", "https://example.test/copper")
    record["geography"] = ""

    with pytest.raises(ValueError, match="requires a geography"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_without_published_units():
    record = audit_record("copper", "https://example.test/copper")
    record["unit_status"] = "not_published"

    with pytest.raises(ValueError, match="requires published units"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_with_manual_stability():
    record = audit_record("copper", "https://example.test/copper")
    record["stability"] = "manual"

    with pytest.raises(ValueError, match="requires a stable or interactive"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_without_published_publication_date():
    record = audit_record("copper", "https://example.test/copper")
    record["publication_date_status"] = "not_published"

    with pytest.raises(ValueError, match="requires a published publication date"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_with_non_machine_readable_access_method():
    record = audit_record("copper", "https://example.test/copper")
    record["access_method"] = "reference_page"

    with pytest.raises(ValueError, match="requires a machine-readable access method"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_candidate_with_manual_report_access_method():
    record = audit_record("copper", "https://example.test/copper")
    record["access_method"] = "manual_report_download"

    with pytest.raises(ValueError, match="requires a machine-readable access method"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_rejects_blocked_record_with_non_blocked_access_method():
    record = audit_record("copper", "https://example.test/copper")
    record["audit_status"] = "blocked"
    record["access_method"] = "api"

    with pytest.raises(ValueError, match="access method must be blocked"):
        audit.validate_non_oil_attribution_audits(
            [record], [catalog_record("copper", "https://example.test/copper")]
        )


def test_validate_accepts_manual_review_only_record_without_published_factual_metadata():
    record = audit_record("copper", "https://example.test/copper")
    record["audit_status"] = "manual_review_only"
    record["frequency"] = "not_published"
    record["unit_status"] = "not_published"
    record["units"] = None
    record["publication_date_status"] = "not_published"
    record["stability"] = "manual"

    assert audit.validate_non_oil_attribution_audits(
        [record], [catalog_record("copper", "https://example.test/copper")]
    ) == [record]


def test_validate_accepts_blocked_record_without_published_factual_metadata():
    record = audit_record("copper", "https://example.test/copper")
    record["audit_status"] = "blocked"
    record["access_method"] = "blocked"
    record["frequency"] = "not_published"
    record["unit_status"] = "not_published"
    record["units"] = None
    record["publication_date_status"] = "not_published"
    record["stability"] = "blocked"

    assert audit.validate_non_oil_attribution_audits(
        [record], [catalog_record("copper", "https://example.test/copper")]
    ) == [record]


def test_checked_in_audit_covers_every_non_oil_price_page_url():
    payload = service.load_non_oil_attribution_source_audit(
        AUDIT_PATH, CATALOG_PATH
    )
    assert len(payload["audits"]) == 20
    assert {row["commodity_id"] for row in payload["audits"]} == {
        "copper",
        "lumber",
        "iron_ore",
    }
    assert {row["audit_status"] for row in payload["audits"]} <= {
        "structured_recurring_candidate",
        "manual_review_only",
        "blocked",
    }


def test_checked_in_audit_has_no_automatic_attribution_or_trade_fields():
    payload = service.load_non_oil_attribution_source_audit(
        AUDIT_PATH, CATALOG_PATH
    )
    forbidden = {
        "conclusion",
        "demand_led",
        "supply_led",
        "trade_signal",
        "direction",
        "score",
    }
    assert all(not (forbidden & set(row)) for row in payload["audits"])


def test_checked_in_audit_outcome_counts_match_research():
    payload = service.load_non_oil_attribution_source_audit(
        AUDIT_PATH, CATALOG_PATH
    )
    assert Counter(row["audit_status"] for row in payload["audits"]) == {
        "structured_recurring_candidate": 5,
        "manual_review_only": 12,
        "blocked": 3,
    }
    assert Counter(row["commodity_id"] for row in payload["audits"]) == {
        "copper": 9,
        "lumber": 5,
        "iron_ore": 6,
    }
