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
_CANDIDATE_ACCESS_METHODS = frozenset(
    {"api", "csv_download", "xlsx_download", "html_table"}
)
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

_SOURCE_REF = "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf"
_AUDITED_AT = "2026-08-02"

AUDITED_RECORDS = [
    {
        "commodity_id": "copper",
        "source_name": "Chilean Copper Commission",
        "source_url": "https://www.cochilco.cl/",
        "source_type": "official_data",
        "source_coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
        "audit_status": "manual_review_only",
        "access_method": "reference_page",
        "factor_categories": ["price", "inventory", "supply"],
        "geography": "Global and Chile",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "USD/lb, t",
        "publication_date_status": "published",
        "stability": "interactive",
        "audit_basis": "Root resolves to the redesigned Cochilco site landing page linking to the interactive Base de Datos Electrónica statistics portal (daily/monthly/annual prices, exchange inventories, production, exports); the root URL itself is a navigation landing page, not a repeatable table.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "Chilean Copper Commission",
        "source_url": "https://www.cochilco.cl/Paginas/English/Statistics/Data-Base.aspx#",
        "source_type": "official_data",
        "source_coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
        "audit_status": "blocked",
        "access_method": "blocked",
        "factor_categories": ["price", "inventory", "supply"],
        "geography": "Global and Chile",
        "frequency": "not_published",
        "unit_status": "not_published",
        "units": None,
        "publication_date_status": "not_published",
        "stability": "blocked",
        "audit_basis": "Exact method URL returns HTTP 404; the Cochilco site was redesigned and the Data-Base page retired. A successor interactive statistics portal exists at cochilco.cl:4040/boletin-web but the method URL itself is no longer accessible.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "Chilean Copper Commission",
        "source_url": "https://www.cochilco.cl/Paginas/English/Statistics/Publications/Trading-Pit.aspx",
        "source_type": "official_data",
        "source_coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
        "audit_status": "blocked",
        "access_method": "blocked",
        "factor_categories": ["price", "inventory"],
        "geography": "Global",
        "frequency": "not_published",
        "unit_status": "not_published",
        "units": None,
        "publication_date_status": "not_published",
        "stability": "blocked",
        "audit_basis": "Exact method URL returns HTTP 404; the Trading Pit daily/monthly inventory page was retired in the Cochilco site redesign. Current daily/monthly LME/COMEX/SHFE inventory data is exposed in the successor Base de Datos Electrónica portal.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "Chilean Copper Commission",
        "source_url": "https://www.cochilco.cl/Paginas/Estadisticas/Publicaciones/BoletinMensualElectronico.aspx",
        "source_type": "official_data",
        "source_coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
        "audit_status": "blocked",
        "access_method": "blocked",
        "factor_categories": ["price", "inventory", "supply", "demand"],
        "geography": "Global and Chile",
        "frequency": "not_published",
        "unit_status": "not_published",
        "units": None,
        "publication_date_status": "not_published",
        "stability": "blocked",
        "audit_basis": "Exact method URL returns HTTP 404; the electronic monthly bulletin page was retired in the Cochilco site redesign and is now served under /web/boletin-mensual-electronico/.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "International Copper Study Group",
        "source_url": "https://www.icsg.org/",
        "source_type": "industry_body",
        "source_coverage": ["production", "usage", "stocks", "forecasts"],
        "audit_status": "manual_review_only",
        "access_method": "reference_page",
        "factor_categories": ["supply", "inventory", "demand"],
        "geography": "Global",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "kt",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Homepage describes monthly copper bulletin, statistical yearbook, factbook, and forecasts; the ICSG online statistical database is membership-gated and publications are order-based, so no repeatable public table is directly downloadable from this URL.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "International Wrought Copper Council",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "source_type": "industry_body",
        "source_coverage": ["semis_production", "demand", "end_use"],
        "audit_status": "structured_recurring_candidate",
        "access_method": "xlsx_download",
        "factor_categories": ["supply", "demand"],
        "geography": "Global (107 countries by region)",
        "frequency": "annual",
        "unit_status": "published",
        "units": "t",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "Page exposes direct public XLSX downloads for global semis production and demand (2012-2024) and end-use summaries, with country/region grouping; the Statistical Bulletin and World Trade Database require membership.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "Kitco Metals",
        "source_url": "http://www.kitcometals.com/charts/copper_historical.html",
        "source_type": "reference_market_data",
        "source_coverage": ["inventories"],
        "audit_status": "manual_review_only",
        "access_method": "reference_page",
        "factor_categories": ["price"],
        "geography": "Global",
        "frequency": "daily",
        "unit_status": "published",
        "units": "USD/lb",
        "publication_date_status": "published",
        "stability": "interactive",
        "audit_basis": "Method URL redirects to the current Kitco live copper price page (interactive bid/ask and chart in USD/lb); the method-listed historical LME copper inventory chart page is retired and no historical inventory series is directly downloadable.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "US Geological Survey",
        "source_url": "https://www.usgs.gov/centers/nmic/copper-statistics-and-information",
        "source_type": "official_data",
        "source_coverage": ["industry_surveys", "publications"],
        "audit_status": "manual_review_only",
        "access_method": "xlsx_download",
        "factor_categories": ["supply", "demand"],
        "geography": "US and world",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "t",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Page documents monthly Mineral Industry Surveys (PDF+XLSX) and annual Mineral Commodity Summaries (PDF) with data download links, but public MIS posting is paused pending a ScienceBase transition with the latest posted data dated December 2025 and no announced resumption date; the source cannot currently support a recurring importer and requires manual review.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "copper",
        "source_name": "World Bank Commodity Markets",
        "source_url": "https://www.worldbank.org/en/research/commodity-markets",
        "source_type": "reference_market_data",
        "source_coverage": ["prices"],
        "audit_status": "structured_recurring_candidate",
        "access_method": "xlsx_download",
        "factor_categories": ["price"],
        "geography": "Global",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "USD",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "Page publishes the monthly Pink Sheet commodity prices and historical monthly/annual price XLS downloads with named commodity series; the exact World Bank URL is shared across copper, lumber, and iron ore catalog entries.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "lumber",
        "source_name": "Food and Agriculture Organization of the United Nations",
        "source_url": "https://www.fao.org/faostat/en/#data/FO",
        "source_type": "official_data",
        "source_coverage": ["production", "imports", "exports"],
        "audit_status": "structured_recurring_candidate",
        "access_method": "api",
        "factor_categories": ["supply", "trade"],
        "geography": "Global by country",
        "frequency": "annual",
        "unit_status": "published",
        "units": "t, m3, USD",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "FAOSTAT Forestry Production and Trade bulk-download dataset (FO) exposes country/year quantities and values via bulk ZIP/CSV and the public FAOSTAT API; item and element filters are required.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "lumber",
        "source_name": "International Tropical Timber Organization",
        "source_url": "https://www.itto.int/",
        "source_type": "industry_body",
        "source_coverage": ["production", "trade"],
        "audit_status": "manual_review_only",
        "access_method": "reference_page",
        "factor_categories": ["supply", "trade"],
        "geography": "Tropical timber countries",
        "frequency": "annual",
        "unit_status": "published",
        "units": "m3",
        "publication_date_status": "published",
        "stability": "interactive",
        "audit_basis": "Root resolves to the ITTO homepage landing page linking to the biennial review statistics database and publications; the root URL itself does not expose a repeatable data table.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "lumber",
        "source_name": "International Tropical Timber Organization",
        "source_url": "https://www.itto.int/biennal_review/",
        "source_type": "industry_body",
        "source_coverage": ["production", "trade"],
        "audit_status": "manual_review_only",
        "access_method": "manual_report_download",
        "factor_categories": ["supply", "trade", "price"],
        "geography": "Global tropical timber",
        "frequency": "annual",
        "unit_status": "published",
        "units": "m3",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Page exposes biennial review editions as ZIP/PDF report downloads covering production and trade data from 1994 to present, and links the separate online statistics database; the page itself is a report archive, not a machine-readable table.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "lumber",
        "source_name": "Joint Forest Sector Questionnaire",
        "source_url": "https://www.forestresearch.gov.uk/tools-and-resources/statistics/statistics-by-topic/international-returns/joint-forest-sector-questionnaire/",
        "source_type": "official_data",
        "source_coverage": ["production", "trade"],
        "audit_status": "manual_review_only",
        "access_method": "manual_report_download",
        "factor_categories": ["supply", "trade"],
        "geography": "United Kingdom",
        "frequency": "annual",
        "unit_status": "published",
        "units": "m3",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Page exposes annual UK JFSQ returns as ODS downloads (final and provisional, 2015-2025) covering removals, production, and trade; Forest Research states this is the last release and future data moves to FAOSTAT.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "lumber",
        "source_name": "World Bank Commodity Markets",
        "source_url": "https://www.worldbank.org/en/research/commodity-markets",
        "source_type": "reference_market_data",
        "source_coverage": ["prices"],
        "audit_status": "structured_recurring_candidate",
        "access_method": "xlsx_download",
        "factor_categories": ["price"],
        "geography": "Global",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "USD",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "Same World Bank commodity-markets page: monthly Pink Sheet commodity prices and historical monthly/annual price XLS downloads with named commodity series.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "iron_ore",
        "source_name": "Government of Western Australia",
        "source_url": "https://www.dmp.wa.gov.au/",
        "source_type": "official_data",
        "source_coverage": [
            "statistics_digest",
            "statistics_releases",
            "industry_activity_indicators",
        ],
        "audit_status": "manual_review_only",
        "access_method": "reference_page",
        "factor_categories": ["supply", "trade", "price"],
        "geography": "Western Australia",
        "frequency": "annual",
        "unit_status": "published",
        "units": "kt, AUD m",
        "publication_date_status": "published",
        "stability": "interactive",
        "audit_basis": "Root resolves to the reshaped WA department landing page (LGIRS/DMPE); mining statistics are published on sub-pages for major commodities, economic indicators, and the statistics digest rather than on the root URL itself.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "iron_ore",
        "source_name": "Government of Western Australia",
        "source_url": "https://www.dmp.wa.gov.au/About-Us-Careers/Latest-Resources-Investment-4083.aspx",
        "source_type": "official_data",
        "source_coverage": [
            "statistics_digest",
            "statistics_releases",
            "industry_activity_indicators",
        ],
        "audit_status": "manual_review_only",
        "access_method": "xlsx_download",
        "factor_categories": ["context"],
        "geography": "Western Australia",
        "frequency": "annual",
        "unit_status": "published",
        "units": "AUD m, FTE",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Method URL redirects to the WA Economic indicators page with an annual Excel data file covering employment, investment, and exploration; the original ASPX URL is retired but resolves to the current data page.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "iron_ore",
        "source_name": "Government of Western Australia",
        "source_url": "https://www.dmp.wa.gov.au/About-Us-Careers/Latest-Statistics-Release-4081.aspx",
        "source_type": "official_data",
        "source_coverage": [
            "statistics_digest",
            "statistics_releases",
            "industry_activity_indicators",
        ],
        "audit_status": "manual_review_only",
        "access_method": "xlsx_download",
        "factor_categories": ["supply", "trade", "price"],
        "geography": "Western Australia",
        "frequency": "annual",
        "unit_status": "published",
        "units": "kt, AUD m",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Method URL redirects to the WA Resources industry data page exposing annual Excel data files for major commodities (sales values/quantities, prices, exports, production), economic indicators, and spatial/regional data; the original ASPX URL is retired.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "iron_ore",
        "source_name": "Government of Western Australia",
        "source_url": "https://www.dmp.wa.gov.au/About-Us-Careers/Statistics-Digest-3962.aspx",
        "source_type": "official_data",
        "source_coverage": [
            "statistics_digest",
            "statistics_releases",
            "industry_activity_indicators",
        ],
        "audit_status": "manual_review_only",
        "access_method": "manual_report_download",
        "factor_categories": ["supply", "trade", "price"],
        "geography": "Western Australia",
        "frequency": "annual",
        "unit_status": "published",
        "units": "kt, AUD m",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Method URL redirects to the WA Mineral and Petroleum statistics digest page, an annual document of record published as PDF with current and historical digests; the original ASPX URL is retired.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "iron_ore",
        "source_name": "US Geological Survey",
        "source_url": "https://www.usgs.gov/centers/nmic/iron-ore-statistics-and-information",
        "source_type": "official_data",
        "source_coverage": ["industry_surveys", "publications"],
        "audit_status": "manual_review_only",
        "access_method": "xlsx_download",
        "factor_categories": ["supply", "demand"],
        "geography": "US and world",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "t",
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": "Page documents monthly Mineral Industry Surveys (PDF+XLSX) and annual Mineral Commodity Summaries (PDF) with data download links, but public MIS posting is paused pending a ScienceBase transition with the latest posted data dated December 2025 and no announced resumption date; the source cannot currently support a recurring importer and requires manual review.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
    {
        "commodity_id": "iron_ore",
        "source_name": "World Bank Commodity Markets",
        "source_url": "https://www.worldbank.org/en/research/commodity-markets",
        "source_type": "reference_market_data",
        "source_coverage": ["prices"],
        "audit_status": "structured_recurring_candidate",
        "access_method": "xlsx_download",
        "factor_categories": ["price"],
        "geography": "Global",
        "frequency": "monthly",
        "unit_status": "published",
        "units": "USD",
        "publication_date_status": "published",
        "stability": "stable",
        "audit_basis": "Same World Bank commodity-markets page: monthly Pink Sheet commodity prices and historical monthly/annual price XLS downloads with named commodity series.",
        "audited_at": _AUDITED_AT,
        "source_ref": _SOURCE_REF,
    },
]


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
    if record["publication_date_status"] != "published":
        raise ValueError(
            " non-oil attribution structured recurring candidate requires a published publication date"
        )
    if record["access_method"] not in _CANDIDATE_ACCESS_METHODS:
        raise ValueError(
            " non-oil attribution structured recurring candidate requires a machine-readable access method"
        )
    if record["stability"] not in _CANDIDATE_STABILITIES:
        raise ValueError(
            " non-oil attribution structured recurring candidate requires a stable or interactive publication"
        )
