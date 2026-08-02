import re
from datetime import date

from app.data_sources.commodity_attribution_catalog import (
    COVERAGE_VOCABULARY,
    VALID_SOURCE_TYPES,
)

VERSION = "non_oil_attribution_source_audit_v1"

NON_OIL_COMMODITY_IDS = frozenset({"copper", "lumber", "iron_ore"})
AUDIT_STATUSES = frozenset(
    {"structured_recurring_candidate", "manual_review_only", "blocked"}
)
ACCESS_METHODS = frozenset(
    {
        "api",
        "csv_download",
        "xlsx_download",
        "html_table",
        "manual_report_download",
        "reference_page",
        "blocked",
    }
)
FACTOR_CATEGORIES = frozenset(
    {"supply", "demand", "inventory", "trade", "price", "context"}
)
FREQUENCIES = frozenset(
    {"daily", "weekly", "monthly", "quarterly", "annual", "irregular", "not_published"}
)
UNIT_STATUSES = frozenset({"published", "not_published"})
PUBLICATION_DATE_STATUSES = frozenset({"published", "not_published"})
STABILITY_STATES = frozenset({"stable", "interactive", "manual", "blocked"})

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CANDIDATE_STABILITIES = frozenset({"stable", "interactive"})
_REQUIRED_RECORD_KEYS = frozenset(
    {
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
)


def validate_non_oil_attribution_audits(records, catalog_resources):
    catalog_by_key = {
        (resource["commodity_id"], resource["source_url"]): resource
        for resource in catalog_resources
        if resource["commodity_id"] in NON_OIL_COMMODITY_IDS
    }
    seen = set()
    validated = [_validate_record(record, catalog_by_key, seen) for record in records]
    audited_keys = {
        (record["commodity_id"], record["source_url"]) for record in validated
    }
    if audited_keys != set(catalog_by_key):
        raise ValueError(
            " non-oil attribution audit does not cover every catalog resource"
        )
    return validated


def _validate_record(record, catalog_by_key, seen):
    _reject_record_shape(record)
    _reject_unknown_field_values(record)
    key = (record["commodity_id"], record["source_url"])
    if key in seen:
        raise ValueError(
            f"duplicate  non-oil attribution audit for {record['source_url']}"
        )
    seen.add(key)
    catalog_resource = catalog_by_key.get(key)
    if catalog_resource is None:
        raise ValueError(
            f" non-oil attribution audit for {record['source_url']} does not match a non-oil catalog resource"
        )
    _reject_catalog_mismatch(record, catalog_resource)
    _reject_invalid_audit_date(record["audited_at"])
    if record["audit_status"] == "structured_recurring_candidate":
        _reject_candidate_missing_factual_metadata(record)
    if record["audit_status"] == "blocked" and record["access_method"] != "blocked":
        raise ValueError(
            " non-oil attribution blocked record access method must be blocked"
        )
    return record


def _reject_record_shape(record):
    missing = sorted(_REQUIRED_RECORD_KEYS - set(record))
    extra = sorted(set(record) - _REQUIRED_RECORD_KEYS)
    if missing or extra:
        raise ValueError(
            f" non-oil attribution audit record keys are not the audit contract: missing {missing}, extra {extra}"
        )


def _reject_unknown_field_values(record):
    _reject_unknown_value("commodity", record["commodity_id"], NON_OIL_COMMODITY_IDS)
    _reject_unknown_value("audit status", record["audit_status"], AUDIT_STATUSES)
    _reject_unknown_value("access method", record["access_method"], ACCESS_METHODS)
    _reject_unknown_value("frequency", record["frequency"], FREQUENCIES)
    _reject_unknown_value("unit status", record["unit_status"], UNIT_STATUSES)
    _reject_unknown_value(
        "publication date status",
        record["publication_date_status"],
        PUBLICATION_DATE_STATUSES,
    )
    _reject_unknown_value("stability", record["stability"], STABILITY_STATES)
    _reject_unknown_value("source type", record["source_type"], VALID_SOURCE_TYPES)
    _reject_unknown_factor_categories(record["factor_categories"])
    _reject_unknown_coverage_tokens(record["source_coverage"])


def _reject_unknown_value(label, value, valid_values):
    if value not in valid_values:
        raise ValueError(
            f" non-oil attribution {label} {value} is not a valid {label}"
        )


def _reject_unknown_factor_categories(factor_categories):
    unknown = [
        category for category in factor_categories if category not in FACTOR_CATEGORIES
    ]
    if unknown:
        raise ValueError(
            f" non-oil attribution factor category {unknown} is not a valid factor category"
        )


def _reject_unknown_coverage_tokens(source_coverage):
    unknown = [token for token in source_coverage if token not in COVERAGE_VOCABULARY]
    if unknown:
        raise ValueError(
            f" non-oil attribution method coverage {unknown} is not in the method vocabulary"
        )


def _reject_catalog_mismatch(record, catalog_resource):
    if record["source_name"] != catalog_resource["source_name"]:
        raise ValueError(
            f" non-oil attribution source name does not match the catalog for {record['source_url']}"
        )
    if record["source_type"] != catalog_resource["source_type"]:
        raise ValueError(
            f" non-oil attribution source type does not match the catalog for {record['source_url']}"
        )
    if record["source_coverage"] != catalog_resource["coverage"]:
        raise ValueError(
            f" non-oil attribution method coverage does not match the catalog for {record['source_url']}"
        )
    if record["source_ref"] != catalog_resource["source_ref"]:
        raise ValueError(
            f" non-oil attribution method reference does not match the catalog for {record['source_url']}"
        )


def _reject_invalid_audit_date(audited_at):
    if not isinstance(audited_at, str) or not _ISO_DATE_RE.match(audited_at):
        raise ValueError(
            f" non-oil attribution audit date {audited_at} is not a valid iso date"
        )
    try:
        date.fromisoformat(audited_at)
    except ValueError as exc:
        raise ValueError(
            f" non-oil attribution audit date {audited_at} is not a valid iso date"
        ) from exc


def _reject_candidate_missing_factual_metadata(record):
    if not record["factor_categories"]:
        raise ValueError(
            " non-oil attribution structured recurring candidate requires factor categories"
        )
    if not record["geography"]:
        raise ValueError(
            " non-oil attribution structured recurring candidate requires a geography"
        )
    if record["frequency"] == "not_published":
        raise ValueError(
            " non-oil attribution structured recurring candidate requires a published frequency"
        )
    if record["unit_status"] != "published":
        raise ValueError(
            " non-oil attribution structured recurring candidate requires published units"
        )
    if record["stability"] not in _CANDIDATE_STABILITIES:
        raise ValueError(
            " non-oil attribution structured recurring candidate requires a stable or interactive publication"
        )
