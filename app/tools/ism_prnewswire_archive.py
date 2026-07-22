"""Manufacturing-only compatibility facade for ISM PR Newswire archive discovery.

Deprecated: New code should use ``app.tools.ism_report_archive`` directly
with an explicit ``survey_type`` parameter.
"""

from app.tools.ism_report_archive import (  # noqa: F401  — re-exported for compat
    BASE_URL,
    ARCHIVE_URL,
    MONTH_NUMBER_BY_NAME,
    LinkExtractor,
    archive_listing_url,
    extract_all_links,
    report_month_from_title,
    report_month_from_url,
)
from app.tools.ism_report_archive import report_id as _report_id
from app.tools.ism_report_archive import parse_archive_listing as _parse_archive_listing

import re


def is_manufacturing_report_title(title):
    """Return True if *title* describes a Manufacturing PMI report on PR Newswire."""
    normalized = re.sub(r"\s+", " ", title)
    return (
        "Manufacturing PMI" in normalized
        and "ISM" in normalized
        and "Report" in normalized
        and "Services" not in normalized
        and "Hospital" not in normalized
    )


def report_id(report_month):
    return _report_id(report_month, "manufacturing")


def parse_archive_listing(html):
    return _parse_archive_listing(html, "manufacturing")
