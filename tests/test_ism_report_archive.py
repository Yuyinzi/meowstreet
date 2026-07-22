"""Tests for survey-aware PR Newswire archive discovery."""

import pytest
from app.tools import ism_report_archive


# Mixed listing containing Manufacturing, Services, Hospital, awards, and unrelated releases
MIXED_LISTING_HTML = """
<html><body>
<a href="/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html">
Jul 01, 2026, 10:00 ET Manufacturing PMI at 53.3%; June 2026 ISM Manufacturing PMI Report
</a>
<a href="/news-releases/services-pmi-at-50-8-june-2026-services-ism-report-on-business-302814992.html">
Services PMI at 50.8%; June 2026 ISM Services PMI Report
</a>
<a href="/news-releases/hospital-pmi-at-51-2-june-2026-ism-hospital-pmi-report-302814993.html">
ISM Hospital PMI Report for June 2026
</a>
<a href="/news-releases/institute-for-supply-management-honors-award-302700000.html">
Institute for Supply Management Honors Award Winner
</a>
<a href="/news-releases/ism-forecast-june-2026-302700001.html">
ISM Economic Forecast for June 2026
</a>
</body></html>
"""


class TestParseArchiveListingManufacturing:
    def test_returns_only_manufacturing_reports(self):
        result = ism_report_archive.parse_archive_listing(
            MIXED_LISTING_HTML, "manufacturing"
        )
        assert len(result) == 1
        assert "Manufacturing PMI" in result[0]["title"]
        assert result[0]["report_id"].startswith("ism_manufacturing")

    def test_manufacturing_report_month_and_id(self):
        result = ism_report_archive.parse_archive_listing(
            MIXED_LISTING_HTML, "manufacturing"
        )
        assert result[0]["report_month"] == "2026-06-01"
        assert result[0]["report_id"] == "ism_manufacturing_2026_06"

    def test_manufacturing_rejects_services_title(self):
        html = """
        <a href="/news-releases/services-pmi-june-2026-services-ism-report-302814992.html">
        Services PMI at 50.8%; June 2026 ISM Services PMI Report
        </a>
        """
        result = ism_report_archive.parse_archive_listing(html, "manufacturing")
        assert result == []

    def test_rejects_awards_and_forecasts(self):
        result = ism_report_archive.parse_archive_listing(
            MIXED_LISTING_HTML, "manufacturing"
        )
        titles = [r["title"] for r in result]
        assert all("Honors Award" not in t for t in titles)
        assert all("Forecast" not in t for t in titles)


class TestParseArchiveListingServices:
    def test_returns_only_services_reports(self):
        result = ism_report_archive.parse_archive_listing(
            MIXED_LISTING_HTML, "services"
        )
        assert len(result) == 1
        assert "Services PMI" in result[0]["title"]
        assert result[0]["report_id"].startswith("ism_services")

    def test_services_report_month_and_id(self):
        result = ism_report_archive.parse_archive_listing(
            MIXED_LISTING_HTML, "services"
        )
        assert result[0]["report_month"] == "2026-06-01"
        assert result[0]["report_id"] == "ism_services_2026_06"

    def test_services_only_matches_services_title(self):
        html = """
        <a href="/news-releases/manufacturing-pmi-june-2026-ism-manufacturing-pmi-report-302814991.html">
        Manufacturing PMI at 53.3%; June 2026 ISM Manufacturing PMI Report
        </a>
        """
        result = ism_report_archive.parse_archive_listing(html, "services")
        assert result == []

    def test_rejects_hospital_and_unrelated_releases(self):
        result = ism_report_archive.parse_archive_listing(
            MIXED_LISTING_HTML, "services"
        )
        titles = [r["title"] for r in result]
        assert all("Hospital" not in t for t in titles)
        assert all("Honors Award" not in t for t in titles)


class TestCrossSurveyRejection:
    def test_manufacturing_not_found_as_services(self):
        html = """
        <a href="/news-releases/manufacturing-pmi-at-52-6-january-2026-ism-manufacturing-pmi-report-302700001.html">
        Manufacturing PMI at 52.6%; January 2026 ISM Manufacturing PMI Report
        </a>
        """
        manu = ism_report_archive.parse_archive_listing(html, "manufacturing")
        svcs = ism_report_archive.parse_archive_listing(html, "services")
        assert len(manu) == 1
        assert svcs == []

    def test_services_not_found_as_manufacturing(self):
        html = """
        <a href="/news-releases/services-pmi-at-50-8-june-2026-services-ism-report-on-business-302814992.html">
        Services PMI at 50.8%; June 2026 ISM Services PMI Report
        </a>
        """
        svcs = ism_report_archive.parse_archive_listing(html, "services")
        manu = ism_report_archive.parse_archive_listing(html, "manufacturing")
        assert len(svcs) == 1
        assert manu == []


class TestReportMonthFromTitle:
    def test_extracts_month_year_from_title(self):
        assert (
            ism_report_archive.report_month_from_title(
                "Manufacturing PMI at 52.6%; January 2026 ISM Manufacturing PMI Report"
            )
            == "2026-01-01"
        )

    def test_extracts_december_correctly(self):
        assert (
            ism_report_archive.report_month_from_title(
                "December 2025 Manufacturing PMI Report"
            )
            == "2025-12-01"
        )

    def test_raises_on_missing_month(self):
        with pytest.raises(ValueError, match="report month is missing"):
            ism_report_archive.report_month_from_title("No date here")


class TestReportMonthFromUrl:
    def test_extracts_month_year_from_url(self):
        url = "/news-releases/manufacturing-pmi-at-49-0-june-2025-ism-manufacturing-pmi-report-302000001.html"
        assert ism_report_archive.report_month_from_url(url) == "2025-06-01"

    def test_extracts_january_url(self):
        url = "/news-releases/manufacturing-pmi-at-52-6-january-2026-ism-manufacturing-pmi-report-302700001.html"
        assert ism_report_archive.report_month_from_url(url) == "2026-01-01"

    def test_raises_on_missing_month(self):
        with pytest.raises(ValueError, match="report month is missing"):
            ism_report_archive.report_month_from_url(
                "https://example.com/no-month-here.html"
            )


class TestReportId:
    def test_manufacturing_report_id(self):
        assert (
            ism_report_archive.report_id("2026-06-01", "manufacturing")
            == "ism_manufacturing_2026_06"
        )

    def test_services_report_id(self):
        assert (
            ism_report_archive.report_id("2026-06-01", "services")
            == "ism_services_2026_06"
        )

    def test_services_january_report_id(self):
        assert (
            ism_report_archive.report_id("2026-01-01", "services")
            == "ism_services_2026_01"
        )

    def test_unknown_survey_type_raises(self):
        with pytest.raises(ValueError, match="unknown survey type"):
            ism_report_archive.report_id("2026-06-01", "invalid")


class TestArchiveListingUrl:
    def test_default_pagesize(self):
        assert ism_report_archive.archive_listing_url(1) == (
            "https://www.prnewswire.com/news/institute-for-supply-management/"
            "?page=1&pagesize=25"
        )

    def test_custom_page_and_pagesize(self):
        assert ism_report_archive.archive_listing_url(3, 50) == (
            "https://www.prnewswire.com/news/institute-for-supply-management/"
            "?page=3&pagesize=50"
        )


class TestSurveyNeutralHelpers:
    def test_month_number_by_name(self):
        assert ism_report_archive.MONTH_NUMBER_BY_NAME["january"] == "01"
        assert ism_report_archive.MONTH_NUMBER_BY_NAME["december"] == "12"

    def test_base_url(self):
        assert ism_report_archive.BASE_URL == "https://www.prnewswire.com"

    def test_unknown_survey_type_for_parse(self):
        with pytest.raises(ValueError, match="unknown survey type"):
            ism_report_archive.parse_archive_listing("<html></html>", "invalid")
