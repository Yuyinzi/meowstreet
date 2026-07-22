"""Survey configuration adapters for ISM Manufacturing and Services reports.

Each survey type exposes a config dict with:
- survey_type
- report_id_prefix
- ismworld_monthly_url(month_name) — ISM World monthly URL builder
- prnewswire_title_matcher(title) — PR Newswire title recognizer
- parse_report(html, source_url, fetched_at, source_name) — parser callable
- allowed_metric_series — frozenset of valid series IDs
- normalize_industry(name) — industry name normalizer
- has_ai_extraction — whether the survey uses AI-based metric extraction
"""

import functools

from app.tools import ism_official_report
from app.tools import ism_services_report
from app.tools import ism_industry_analysis
from app.tools import ism_services_industry


def _manufacturing_ismworld_url(month_name):
    return (
        "https://www.ismworld.org/supply-management-news-and-reports/"
        f"reports/ism-pmi-reports/pmi/{month_name}/"
    )


def _services_ismworld_url(month_name):
    return (
        "https://www.ismworld.org/supply-management-news-and-reports/"
        f"reports/ism-pmi-reports/services/{month_name}/"
    )


def _manufacturing_prnewswire_matcher(title):
    """Return True if *title* describes a Manufacturing PMI report on PR Newswire."""
    import re as _re

    normalized = _re.sub(r"\s+", " ", title)
    return (
        "Manufacturing PMI" in normalized
        and "ISM" in normalized
        and "Report" in normalized
        and "Services" not in normalized
        and "Hospital" not in normalized
    )


def _services_prnewswire_matcher(title):
    """Return True if *title* describes a Services PMI report on PR Newswire."""
    return "Services PMI" in title and "ISM" in title and "Report" in title


_MANUFACTURING_METRICS = frozenset(
    {
        "ism_manufacturing_pmi",
        "ism_manufacturing_new_orders",
        "ism_manufacturing_production",
        "ism_manufacturing_employment",
        "ism_manufacturing_supplier_deliveries",
        "ism_manufacturing_inventories",
        "ism_manufacturing_customer_inventories",
        "ism_manufacturing_prices",
        "ism_manufacturing_order_backlog",
        "ism_manufacturing_exports",
        "ism_manufacturing_imports",
    }
)

_SERVICES_METRICS = frozenset(
    {
        "ism_services_pmi",
        "ism_services_business_activity",
        "ism_services_new_orders",
        "ism_services_order_backlog",
    }
)


def _manufacturing_parse_report(html, source_url, fetched_at, source_name="ismworld"):
    return ism_official_report.parse_report(html, source_url, fetched_at, source_name)


def _services_parse_report(html, source_url, fetched_at, source_name="ismworld"):
    return ism_services_report.parse_report(html, source_url, fetched_at, source_name)


_SURVEY_CONFIGS = {
    "manufacturing": {
        "survey_type": "manufacturing",
        "report_id_prefix": "ism_manufacturing",
        "ismworld_monthly_url": _manufacturing_ismworld_url,
        "prnewswire_title_matcher": _manufacturing_prnewswire_matcher,
        "parse_report": _manufacturing_parse_report,
        "allowed_metric_series": _MANUFACTURING_METRICS,
        "normalize_industry": ism_industry_analysis.normalize_industry,
        "has_ai_extraction": True,
    },
    "services": {
        "survey_type": "services",
        "report_id_prefix": "ism_services",
        "ismworld_monthly_url": _services_ismworld_url,
        "prnewswire_title_matcher": _services_prnewswire_matcher,
        "parse_report": _services_parse_report,
        "allowed_metric_series": _SERVICES_METRICS,
        "normalize_industry": ism_services_industry.normalize_industry,
        "has_ai_extraction": True,
    },
}

_VALID_SURVEY_TYPES = frozenset(_SURVEY_CONFIGS)


@functools.lru_cache(maxsize=None)
def load_survey_config(survey_type):
    """Return the survey config dict for *survey_type*.

    Raises ``ValueError`` with a lowercase descriptive message for unknown types.
    """
    config = _SURVEY_CONFIGS.get(survey_type)
    if config is None:
        raise ValueError(f"unknown survey type: {survey_type}")
    return config


def valid_survey_types():
    """Return a frozenset of registered survey type strings."""
    return _VALID_SURVEY_TYPES
