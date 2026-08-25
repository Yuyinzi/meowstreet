"""Tests for shared ISM report target selection."""

import argparse
from datetime import datetime
from unittest.mock import patch

import pytest
import sqlite3
from app.db import growth_cycle
from app.services import ism_report_ingestion as ingestion


class TestLatestReleasedReportMonth:
    def test_returns_previous_month(self):
        assert (
            ingestion.latest_released_report_month(datetime(2026, 7, 15))
            == "2026-06-01"
        )

    def test_january_returns_previous_december(self):
        assert (
            ingestion.latest_released_report_month(datetime(2026, 1, 15))
            == "2025-12-01"
        )

    def test_year_rollover(self):
        assert (
            ingestion.latest_released_report_month(datetime(2025, 1, 1)) == "2024-12-01"
        )

    def test_march_returns_february(self):
        assert (
            ingestion.latest_released_report_month(datetime(2026, 3, 1)) == "2026-02-01"
        )


class TestMonthName:
    def test_january(self):
        assert ingestion.month_name("2026-01-01") == "january"

    def test_december(self):
        assert ingestion.month_name("2026-12-01") == "december"

    def test_june(self):
        assert ingestion.month_name("2026-06-01") == "june"


class TestNormalizeReportMonth:
    def test_yyyymm_to_yyyymm01(self):
        assert ingestion.normalize_report_month("2026-06") == "2026-06-01"

    def test_yyyymm01_preserved(self):
        assert ingestion.normalize_report_month("2026-06-01") == "2026-06-01"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="report month must be"):
            ingestion.normalize_report_month("invalid")


class TestBuildTargetsMissingOnlyRetry:
    def test_missing_only_skips_promoted_months_and_retries_failed_months(
        self, monkeypatch
    ):
        discovered = [
            {
                "survey_type": "services",
                "report_month": "2025-08-01",
                "report_id": "ism_services_2025_08",
                "source_name": "prnewswire",
                "url": "https://example.test/august",
            },
            {
                "survey_type": "services",
                "report_month": "2025-09-01",
                "report_id": "ism_services_2025_09",
                "source_name": "prnewswire",
                "url": "https://example.test/september",
            },
        ]
        monkeypatch.setattr(
            ingestion,
            "discover_prnewswire_reports",
            lambda *args, **kwargs: discovered,
        )

        targets = ingestion.build_targets(
            "services",
            backfill_since=2025,
            missing_only=True,
            existing_months={"2025-09-01"},
            force_latest=False,
        )

        assert [target["report_month"] for target in targets] == ["2025-08-01"]


class TestBuildTargetsLatestOnly:
    def test_default_returns_one_prnewswire_target(self, monkeypatch):
        monkeypatch.setattr(
            ingestion,
            "discover_prnewswire_reports",
            lambda *args, **kwargs: [
                {
                    "url": "https://www.prnewswire.com/manufacturing.html",
                    "report_month": ingestion.latest_released_report_month(),
                    "report_id": "ism_manufacturing_2026_07",
                }
            ],
        )
        targets = ingestion.build_targets("manufacturing")
        assert len(targets) == 1
        assert targets[0]["source_name"] == "prnewswire"
        assert targets[0]["survey_type"] == "manufacturing"
        assert targets[0]["report_month"] is not None
        assert targets[0]["report_id"].startswith("ism_manufacturing")
        assert targets[0]["url"].startswith("https://www.prnewswire.com/")

    def test_default_returns_services_prnewswire_target(self, monkeypatch):
        monkeypatch.setattr(
            ingestion,
            "discover_prnewswire_reports",
            lambda *args, **kwargs: [
                {
                    "url": "https://www.prnewswire.com/services.html",
                    "report_month": ingestion.latest_released_report_month(),
                    "report_id": "ism_services_2026_07",
                }
            ],
        )
        targets = ingestion.build_targets("services")
        assert len(targets) == 1
        assert targets[0]["source_name"] == "prnewswire"
        assert targets[0]["survey_type"] == "services"
        assert targets[0]["report_id"].startswith("ism_services")
        assert targets[0]["url"].startswith("https://www.prnewswire.com/")

    def test_missing_only_with_existing_month_suppresses_latest(self, monkeypatch):
        latest = ingestion.latest_released_report_month()
        monkeypatch.setattr(
            ingestion,
            "discover_prnewswire_reports",
            lambda *args, **kwargs: [
                {
                    "url": "https://www.prnewswire.com/manufacturing.html",
                    "report_month": latest,
                    "report_id": "ism_manufacturing_2026_07",
                }
            ],
        )
        targets = ingestion.build_targets(
            "manufacturing",
            force_latest=True,
            missing_only=True,
            existing_months={latest},
        )
        assert len(targets) == 0

    def test_missing_only_without_existing_month_includes_latest(self, monkeypatch):
        latest = ingestion.latest_released_report_month()
        monkeypatch.setattr(
            ingestion,
            "discover_prnewswire_reports",
            lambda *args, **kwargs: [
                {
                    "url": "https://www.prnewswire.com/manufacturing.html",
                    "report_month": latest,
                    "report_id": "ism_manufacturing_2026_07",
                }
            ],
        )
        targets = ingestion.build_targets(
            "manufacturing",
            force_latest=True,
            missing_only=True,
            existing_months={"1999-01-01"},
        )
        assert len(targets) == 1
        assert targets[0]["report_month"] == latest


class TestBuildTargetsSpecificMonth:
    @patch("app.services.ism_report_ingestion.discover_prnewswire_reports")
    def test_report_month_generates_one_target(self, mock_discover):
        mock_discover.return_value = [
            {
                "url": "https://prnewswire.com/manufacturing-june-2026",
                "title": "Test",
                "report_month": "2026-06-01",
                "report_id": "ism_manufacturing_2026_06",
            }
        ]
        targets = ingestion.build_targets("manufacturing", report_month="2026-06")
        assert any(t["report_month"] == "2026-06-01" for t in targets)

    def test_report_month_uses_prnewswire_for_latest(self, monkeypatch):
        latest = ingestion.latest_released_report_month()
        monkeypatch.setattr(
            ingestion,
            "discover_prnewswire_reports",
            lambda *args, **kwargs: [
                {
                    "url": "https://www.prnewswire.com/services.html",
                    "report_month": latest,
                    "report_id": "ism_services_2026_07",
                }
            ],
        )
        targets = ingestion.build_targets("services", report_month=latest[:7])
        matching = [t for t in targets if t["report_month"] == latest]
        assert len(matching) >= 1
        assert matching[0]["source_name"] == "prnewswire"


class TestBuildTargetsCurrentYear:
    @patch("app.services.ism_report_ingestion.discover_prnewswire_reports")
    def test_current_year_includes_prnewswire_for_history_and_latest(
        self, mock_discover
    ):
        mock_discover.return_value = [
            {
                "url": f"https://prnewswire.com/{m}-2025",
                "title": "Test",
                "report_month": f"2025-{m:02d}-01",
                "report_id": f"ism_manufacturing_2025_{m:02d}",
            }
            for m in range(1, 7)
        ]
        targets = ingestion.build_targets("manufacturing", current_year=2025)
        pr_months = {
            t["report_month"]
            for t in targets
            if t["source_name"] == "prnewswire"
            and t["report_month"]
            and t["report_month"].startswith("2025")
        }
        assert pr_months == {f"2025-{m:02d}-01" for m in range(1, 7)}

    @patch("app.services.ism_report_ingestion.discover_prnewswire_reports")
    def test_current_year_latest_falls_back_to_ismworld_when_not_in_archive(
        self, mock_discover
    ):
        mock_discover.return_value = [
            {
                "url": "https://prnewswire.com/jan-2024",
                "title": "Test",
                "report_month": "2024-01-01",
                "report_id": "ism_services_2024_01",
            },
        ]
        targets = ingestion.build_targets("services", current_year=2024)
        latest = ingestion.latest_released_report_month()
        latest_targets = [t for t in targets if t["report_month"] == latest]
        for t in latest_targets:
            assert t["source_name"] == "ismworld"

    @patch("app.services.ism_report_ingestion.discover_prnewswire_reports")
    def test_current_year_missing_only_filters_existing(self, mock_discover):
        mock_discover.return_value = [
            {
                "url": f"https://prnewswire.com/{m}-2025",
                "title": "Test",
                "report_month": f"2025-{m:02d}-01",
                "report_id": f"ism_manufacturing_2025_{m:02d}",
            }
            for m in range(1, 7)
        ]
        targets = ingestion.build_targets(
            "manufacturing",
            current_year=2025,
            missing_only=True,
            existing_months={"2025-01-01", "2025-02-01"},
        )
        months = {t["report_month"] for t in targets}
        assert "2025-01-01" not in months
        assert "2025-02-01" not in months


class TestBuildTargetsRepairUrls:
    def test_repair_urls_included_as_direct_url(self):
        targets = ingestion.build_targets(
            "manufacturing",
            repair_urls=["http://example.com/repair"],
            force_latest=False,
        )
        assert any(
            t["source_name"] == "direct_url" and t["url"] == "http://example.com/repair"
            for t in targets
        )

    def test_repair_url_survey_type_set(self):
        targets = ingestion.build_targets(
            "services",
            repair_urls=["http://example.com/repair"],
            force_latest=False,
        )
        repair = [t for t in targets if t["source_name"] == "direct_url"]
        assert repair[0]["survey_type"] == "services"


class TestTargetDeduplication:
    @patch("app.services.ism_report_ingestion.discover_prnewswire_reports")
    def test_no_duplicate_months(self, mock_discover):
        mock_discover.return_value = [
            {
                "url": f"https://prnewswire.com/{m}-2025",
                "title": "Test",
                "report_month": f"2025-{m:02d}-01",
                "report_id": f"ism_manufacturing_2025_{m:02d}",
            }
            for m in range(1, 13)
        ]
        targets = ingestion.build_targets(
            "manufacturing",
            report_month="2026-06",
            backfill_since=2025,
            force_latest=True,
        )
        months = [t["report_month"] for t in targets if t["report_month"]]
        assert len(months) == len(set(months))

    @patch("app.services.ism_report_ingestion.discover_prnewswire_reports")
    def test_same_month_different_survey_is_not_a_duplicate(self, mock_discover):
        mock_discover.return_value = [
            {
                "url": "https://prnewswire.com/june-2026",
                "title": "Test",
                "report_month": "2026-06-01",
                "report_id": "ism_2026_06",
            }
        ]
        manu = ingestion.build_targets("manufacturing", report_month="2026-06")
        svcs = ingestion.build_targets("services", report_month="2026-06")
        manu_months = {
            (t["survey_type"], t["report_month"]) for t in manu if t["report_month"]
        }
        svcs_months = {
            (t["survey_type"], t["report_month"]) for t in svcs if t["report_month"]
        }
        assert len(manu_months & svcs_months) == 0  # different survey_type


class TestDiscoverPrnewswireReports:
    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_discover_manufacturing_returns_matching(self, mock_fetch):
        html = """
        <a href="/news-releases/manu-june-2026-ism-manufacturing-pmi-report-1.html">
        Manufacturing PMI; June 2026 ISM Manufacturing PMI Report
        </a>
        <a href="/news-releases/services-june-2026-services-ism-report-2.html">
        Services PMI; June 2026 ISM Services PMI Report
        </a>
        """
        mock_fetch.return_value = html
        reports = ingestion.discover_prnewswire_reports(
            2025, "manufacturing", pagesize=50
        )
        assert len(reports) == 1
        assert reports[0]["report_id"].startswith("ism_manufacturing")

    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_discover_services_returns_matching(self, mock_fetch):
        html = """
        <a href="/news-releases/services-june-2026-services-ism-report-2.html">
        Services PMI; June 2026 ISM Services PMI Report
        </a>
        <a href="/news-releases/manu-june-2026-ism-manufacturing-pmi-report-1.html">
        Manufacturing PMI; June 2026 ISM Manufacturing PMI Report
        </a>
        """
        mock_fetch.return_value = html
        reports = ingestion.discover_prnewswire_reports(2025, "services", pagesize=50)
        assert len(reports) == 1
        assert reports[0]["report_id"].startswith("ism_services")

    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_discover_stops_at_reached_before_since(self, mock_fetch):
        before = {
            "url": "https://prnewswire.com/old",
            "title": "Test",
            "report_month": "2020-01-01",
            "report_id": "ism_manufacturing_2020_01",
        }
        current = {
            "url": "https://prnewswire.com/cur",
            "title": "Test2",
            "report_month": "2025-06-01",
            "report_id": "ism_manufacturing_2025_06",
        }

        def fake_parse(html, survey_type):
            if "page=1" in html:
                return [current, before]
            return []

        def fake_has_links(html):
            return "page=1" in html

        with (
            patch(
                "app.services.ism_report_ingestion.ism_report_archive.parse_archive_listing",
                fake_parse,
            ),
            patch(
                "app.services.ism_report_ingestion._page_has_release_links",
                fake_has_links,
            ),
        ):
            mock_fetch.side_effect = ["page=1", "page=2"]
            reports = ingestion.discover_prnewswire_reports(
                2023, "manufacturing", pagesize=50
            )
            months = {r["report_month"] for r in reports}
            assert "2025-06-01" in months
            assert "2020-01-01" not in months

    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_discover_skips_non_ism_page_continues_to_next(self, mock_fetch):
        award_html = """
        <a href="/news-releases/institute-for-supply-management-honors-award-123.html">
        Institute for Supply Management Honors Supply Chain Leaders
        </a>
        <a href="/news-releases/ism-forecast-2026-business-outlook-456.html">
        ISM Forecast 2026: Business Outlook Remains Positive
        </a>
        """
        report_html = """
        <a href="/news-releases/manu-june-2026-ism-manufacturing-pmi-789.html">
        Manufacturing PMI; June 2026 ISM Manufacturing PMI Report
        </a>
        """

        def fake_parse(html, survey_type):
            if "award" in html:
                return []
            return [
                {
                    "url": "https://prnewswire.com/manu-june-2026",
                    "title": "June 2026 ISM Manufacturing PMI Report",
                    "report_month": "2026-06-01",
                    "report_id": "ism_manufacturing_2026_06",
                }
            ]

        with (
            patch(
                "app.services.ism_report_ingestion.ism_report_archive.parse_archive_listing",
                fake_parse,
            ),
        ):
            mock_fetch.side_effect = [award_html, report_html]
            reports = ingestion.discover_prnewswire_reports(
                2025, "manufacturing", pagesize=50, max_pages=2
            )
            assert len(reports) == 1
            assert reports[0]["report_id"] == "ism_manufacturing_2026_06"


MANUFACTURING_PARSED = {
    "survey_type": "manufacturing",
    "report": {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/pmi/june/",
        "source_hash": "abc123",
        "source_name": "ismworld",
        "fetched_at": "2026-07-14T10:00:00Z",
        "parse_status": "ok",
        "next_report_period": "2026-07-01",
        "next_release_at": "2026-08-03T10:00:00-04:00",
        "next_release_label": "Monday, August 3, 2026 at 10:00 a.m. ET",
    },
    "metrics": {
        "ism_manufacturing_pmi": 53.3,
        "ism_manufacturing_new_orders": 56.0,
        "ism_manufacturing_production": 52.2,
        "ism_manufacturing_employment": 49.7,
        "ism_manufacturing_supplier_deliveries": 57.4,
        "ism_manufacturing_inventories": 51.4,
        "ism_manufacturing_customer_inventories": 42.3,
        "ism_manufacturing_prices": 73.0,
        "ism_manufacturing_order_backlog": 50.5,
        "ism_manufacturing_exports": 48.5,
        "ism_manufacturing_imports": 52.9,
    },
    "rankings": [],
    "comments": [],
    "at_a_glance_rows": [],
}

SERVICES_PARSED = {
    "survey_type": "services",
    "report": {
        "report_id": "ism_services_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Services PMI Report",
        "source_url": "https://www.ismworld.org/services/june/",
        "source_hash": "def456",
        "source_name": "ismworld",
        "fetched_at": "2026-07-06T10:00:00-04:00",
        "parse_status": "ok",
        "next_report_period": None,
        "next_release_at": None,
        "next_release_label": "",
    },
    "metrics": {
        "ism_services_pmi": 54.0,
        "ism_services_business_activity": 55.4,
        "ism_services_new_orders": 55.1,
        "ism_services_order_backlog": 54.9,
    },
    "rankings": [],
    "comments": [],
}


class TestNormalizeParsed:
    def test_manufacturing_preserves_at_a_glance_rows(self):
        result = ingestion.normalize_parsed(MANUFACTURING_PARSED, "manufacturing")
        assert result["survey_type"] == "manufacturing"
        assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
        assert result["at_a_glance_rows"] == []

    def test_manufacturing_keeps_all_11_metrics(self):
        result = ingestion.normalize_parsed(MANUFACTURING_PARSED, "manufacturing")
        assert len(result["metrics"]) == 11
        assert result["metrics"]["ism_manufacturing_pmi"] == 53.3

    def test_services_adds_at_a_glance_rows(self):
        assert "at_a_glance_rows" not in SERVICES_PARSED
        result = ingestion.normalize_parsed(SERVICES_PARSED, "services")
        assert result["survey_type"] == "services"
        assert result["at_a_glance_rows"] == []

    def test_services_keeps_four_metrics(self):
        result = ingestion.normalize_parsed(SERVICES_PARSED, "services")
        assert len(result["metrics"]) == 4
        assert result["metrics"]["ism_services_pmi"] == 54.0

    def test_services_rejected_as_manufacturing(self):
        with pytest.raises(ValueError, match="survey mismatch"):
            ingestion.normalize_parsed(SERVICES_PARSED, "manufacturing")

    def test_manufacturing_rejected_as_services(self):
        with pytest.raises(ValueError, match="survey mismatch"):
            ingestion.normalize_parsed(MANUFACTURING_PARSED, "services")

    def test_wrong_report_id_prefix_raises(self):
        bad = dict(SERVICES_PARSED)
        bad["report"] = dict(SERVICES_PARSED["report"])
        bad["report"]["report_id"] = "ism_manufacturing_2026_06"
        with pytest.raises(ValueError, match="id prefix mismatch"):
            ingestion.normalize_parsed(bad, "services")

    def test_missing_report_month_raises(self):
        bad = dict(MANUFACTURING_PARSED)
        bad["report"] = dict(MANUFACTURING_PARSED["report"])
        bad["report"]["report_month"] = ""
        with pytest.raises(ValueError, match="report month is missing"):
            ingestion.normalize_parsed(bad, "manufacturing")

    def test_unexpected_metric_series_raises(self):
        bad = dict(MANUFACTURING_PARSED)
        bad["metrics"] = dict(MANUFACTURING_PARSED["metrics"])
        bad["metrics"]["ism_services_pmi"] = 99.0
        with pytest.raises(ValueError, match="unexpected metric series"):
            ingestion.normalize_parsed(bad, "manufacturing")

    def test_unknown_survey_type_raises_on_load(self):
        with pytest.raises(ValueError, match="unknown survey type"):
            ingestion.normalize_parsed(MANUFACTURING_PARSED, "invalid")

    def test_cross_survey_metric_series_rejected(self):
        bad = dict(SERVICES_PARSED)
        bad["metrics"] = dict(SERVICES_PARSED["metrics"])
        bad["metrics"]["ism_manufacturing_pmi"] = 53.3
        with pytest.raises(ValueError, match="unexpected metric series"):
            ingestion.normalize_parsed(bad, "services")


class TestSaveSourceSnapshot:
    def test_saves_raw_html_and_survey_type(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        target = {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/pmi/june/",
        }
        fetched_at = "2026-07-15T10:00:00Z"
        html = "<html>manufacturing report</html>"

        snapshot = ingestion.save_source_snapshot(con, target, html, fetched_at)

        assert snapshot["source_url"] == target["url"]
        assert snapshot["survey_type"] == "manufacturing"
        assert snapshot["parse_status"] == "fetched"
        assert snapshot["raw_html"] == html
        assert snapshot["report_id"] is None
        assert snapshot["report_month"] is None

        loaded = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert loaded["survey_type"] == "manufacturing"
        assert loaded["raw_html"] == html

    def test_saves_services_survey_type(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        target = {
            "survey_type": "services",
            "report_month": "2026-06-01",
            "report_id": "ism_services_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/services/june/",
        }
        fetched_at = "2026-07-15T10:00:00Z"
        html = "<html>services report</html>"

        snapshot = ingestion.save_source_snapshot(con, target, html, fetched_at)

        loaded = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert loaded["survey_type"] == "services"

    def test_replaces_existing_snapshot(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        target = {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/pmi/june/",
        }
        fetched_at = "2026-07-15T10:00:00Z"

        ingestion.save_source_snapshot(con, target, "first", fetched_at)
        ingestion.save_source_snapshot(con, target, "replaced", fetched_at)

        loaded = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert loaded["raw_html"] == "replaced"


class TestMarkSourceSnapshotSuccess:
    def test_updates_with_parsed_report(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        target = {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/pmi/june/",
        }
        ingestion.save_source_snapshot(
            con, target, "<html>report</html>", "2026-07-15T10:00:00Z"
        )

        parsed = {
            "survey_type": "manufacturing",
            "report": {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
            },
        }
        result = ingestion.mark_source_snapshot_success(con, target["url"], parsed)

        loaded = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert loaded["parse_status"] == "ok"
        assert loaded["report_id"] == "ism_manufacturing_2026_06"
        assert loaded["report_month"] == "2026-06-01"

    def test_raises_for_missing_snapshot(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        with pytest.raises(ValueError, match="not found"):
            ingestion.mark_source_snapshot_success(
                con,
                "https://example.com/nonexistent.html",
                {"report": {"report_id": "x", "report_month": "2026-01-01"}},
            )


class TestMarkSourceSnapshotFailed:
    def test_updates_with_error_text(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        target = {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/pmi/june/",
        }
        ingestion.save_source_snapshot(
            con, target, "<html>bad</html>", "2026-07-15T10:00:00Z"
        )

        result = ingestion.mark_source_snapshot_failed(
            con, target["url"], "no report page available"
        )

        loaded = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert loaded["parse_status"] == "failed"
        assert loaded["parse_error"] == "no report page available"
        assert loaded["report_id"] is None
        assert loaded["report_month"] is None

    def test_preserves_raw_html_on_failure(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        target = {
            "survey_type": "services",
            "report_month": "2026-06-01",
            "report_id": "ism_services_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/services/june/",
        }
        html = "<html>unparseable services</html>"
        ingestion.save_source_snapshot(con, target, html, "2026-07-15T10:00:00Z")
        ingestion.mark_source_snapshot_failed(con, target["url"], "metric not found")

        loaded = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert loaded["raw_html"] == html
        assert loaded["parse_status"] == "failed"
        assert loaded["survey_type"] == "services"

    def test_raises_for_missing_snapshot(self, tmp_path):
        con = growth_cycle.connect(tmp_path / "market_data.sqlite")
        with pytest.raises(ValueError, match="not found"):
            ingestion.mark_source_snapshot_failed(
                con,
                "https://example.com/nonexistent.html",
                "some error",
            )


class TestPersistParsedReport:
    @staticmethod
    def _init_db(path):
        """Create a connection with all tables needed by persist_parsed_report."""
        con = growth_cycle.connect(path)
        con.executescript(
            """
            create table if not exists macro_indicator_series (
                series_id text primary key,
                title text not null,
                units text not null,
                source text not null
            );
            create table if not exists macro_indicator_points (
                series_id text not null,
                date text not null,
                value real not null,
                source text not null,
                primary key(series_id, date),
                foreign key(series_id) references macro_indicator_series(series_id)
            );
            create index if not exists idx_macro_indicator_points_series_date
            on macro_indicator_points(series_id, date);
            """
        )
        return con

    def test_manufacturing_happy_path(self, tmp_path):
        con = self._init_db(tmp_path / "test_persist.sqlite")
        con.row_factory = sqlite3.Row
        parsed = dict(MANUFACTURING_PARSED)
        parsed["rankings"] = [
            {
                "date": "2026-06-01",
                "industry": "Fabricated Metal Products",
                "direction": "growth",
                "rank": 1,
                "source": "ISM official report",
            },
        ]
        parsed["comments"] = [
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "industry": "Fabricated Metal Products",
                "comment_index": 1,
                "comment_text": "Business activity is steady.",
                "source_url": "https://www.ismworld.org/pmi/june/",
                "source_hash": "abc123",
                "source": "ISM official report",
            },
        ]
        parsed["at_a_glance_rows"] = [
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "series_id": "ism_manufacturing_pmi",
                "label": "PMI®",
                "current_value": 53.3,
                "previous_value": 52.0,
                "point_change": 1.3,
                "direction": "growth",
                "rate_of_change": "faster",
                "trend_months": 12,
                "source_url": "https://www.ismworld.org/pmi/june/",
                "source_hash": "abc123",
            },
        ]

        result = ingestion.persist_parsed_report(con, "manufacturing", parsed)

        assert result["report_id"] == "ism_manufacturing_2026_06"
        assert result["survey_type"] == "manufacturing"
        assert result["source"] == "ismworld"
        assert result["reports"] == 1
        assert result["metrics"] == 11
        assert result["rankings"] == 1
        assert result["comments"] == 1

        snap = con.execute(
            "select * from ism_report_snapshots where report_id = ?",
            ("ism_manufacturing_2026_06",),
        ).fetchone()
        assert snap is not None
        assert snap["survey_type"] == "manufacturing"

        glance = con.execute(
            "select * from ism_at_a_glance_rows where report_id = ?",
            ("ism_manufacturing_2026_06",),
        ).fetchall()
        assert len(glance) == 1
        assert glance[0]["series_id"] == "ism_manufacturing_pmi"

        metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points where date = '2026-06-01'"
        ).fetchone()
        assert metrics["cnt"] == 11

    def test_services_happy_path(self, tmp_path):
        con = self._init_db(tmp_path / "test_persist.sqlite")
        con.row_factory = sqlite3.Row
        parsed = dict(SERVICES_PARSED)
        parsed["rankings"] = [
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
                "source": "ISM official report",
            },
        ]
        parsed["comments"] = [
            {
                "report_id": "ism_services_2026_06",
                "report_month": "2026-06-01",
                "industry": "Construction",
                "comment_index": 1,
                "comment_text": "Demand remains strong.",
                "source_url": "https://www.ismworld.org/services/june/",
                "source_hash": "def456",
                "source": "ISM official report",
            },
        ]

        result = ingestion.persist_parsed_report(con, "services", parsed)

        assert result["report_id"] == "ism_services_2026_06"
        assert result["survey_type"] == "services"
        assert result["metrics"] == 4
        assert result["rankings"] == 1
        assert result["comments"] == 1

        snap = con.execute(
            "select * from ism_report_snapshots where report_id = ?",
            ("ism_services_2026_06",),
        ).fetchone()
        assert snap is not None
        assert snap["survey_type"] == "services"

        glance = con.execute(
            "select * from ism_at_a_glance_rows where report_id = ?",
            ("ism_services_2026_06",),
        ).fetchall()
        assert len(glance) == 0

    def test_rollback_on_failure(self, tmp_path):
        con = self._init_db(tmp_path / "test_persist.sqlite")
        con.row_factory = sqlite3.Row
        parsed = dict(MANUFACTURING_PARSED)
        parsed["rankings"] = [
            {
                "date": "2026-06-01",
                "industry": "Fabricated Metal Products",
                "direction": "growth",
                "rank": 1,
                "source": "ISM official report",
            },
        ]

        with patch("app.db.ism_surveys.merge_industry_rankings") as mock_mr:
            mock_mr.side_effect = RuntimeError("db failure")
            with pytest.raises(RuntimeError, match="db failure"):
                ingestion.persist_parsed_report(con, "manufacturing", parsed)

        snap = con.execute(
            "select count(*) as cnt from ism_report_snapshots"
        ).fetchone()
        assert snap["cnt"] == 0

        metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points"
        ).fetchone()
        assert metrics["cnt"] == 0

    def test_idempotent_persist(self, tmp_path):
        con = self._init_db(tmp_path / "test_persist.sqlite")
        con.row_factory = sqlite3.Row
        parsed = dict(MANUFACTURING_PARSED)
        parsed["rankings"] = [
            {
                "date": "2026-06-01",
                "industry": "Fabricated Metal Products",
                "direction": "growth",
                "rank": 1,
                "source": "ISM official report",
            },
        ]

        ingestion.persist_parsed_report(con, "manufacturing", parsed)
        ingestion.persist_parsed_report(con, "manufacturing", parsed)

        snap = con.execute(
            "select count(*) as cnt from ism_report_snapshots where report_id = ?",
            ("ism_manufacturing_2026_06",),
        ).fetchone()
        assert snap["cnt"] == 1

        metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points where date = '2026-06-01'"
        ).fetchone()
        assert metrics["cnt"] == 11

    def test_coexistence_of_both_surveys(self, tmp_path):
        con = self._init_db(tmp_path / "test_persist.sqlite")
        con.row_factory = sqlite3.Row

        manu = dict(MANUFACTURING_PARSED)
        svcs = dict(SERVICES_PARSED)

        manu_result = ingestion.persist_parsed_report(con, "manufacturing", manu)
        svcs_result = ingestion.persist_parsed_report(con, "services", svcs)

        assert manu_result["report_id"] == "ism_manufacturing_2026_06"
        assert svcs_result["report_id"] == "ism_services_2026_06"

        both = con.execute(
            "select report_id, survey_type from ism_report_snapshots "
            "where report_month = '2026-06-01' order by report_id"
        ).fetchall()
        assert len(both) == 2
        assert both[0]["survey_type"] == "manufacturing"
        assert both[1]["survey_type"] == "services"

        manu_metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points "
            "where date = '2026-06-01' and series_id like 'ism_manufacturing_%'"
        ).fetchone()
        assert manu_metrics["cnt"] == 11

        svcs_metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points "
            "where date = '2026-06-01' and series_id like 'ism_services_%'"
        ).fetchone()
        assert svcs_metrics["cnt"] == 4


class TestImportSingleTarget:
    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_happy_path_manufacturing(self, mock_fetch, tmp_path):
        mock_fetch.return_value = "<html>mock manufacturing</html>"
        db = tmp_path / "test_single_import.sqlite"
        con = TestPersistParsedReport._init_db(db)
        con.row_factory = sqlite3.Row

        target = {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/pmi/june/",
        }
        mock_config = {
            "parse_report": lambda html, url, fetched_at, source_name: dict(
                MANUFACTURING_PARSED
            ),
            "allowed_metric_series": set(MANUFACTURING_PARSED["metrics"]),
            "report_id_prefix": "ism_manufacturing",
            "ismworld_monthly_url": lambda month_name: target["url"],
        }

        with patch(
            "app.services.ism_report_ingestion.ism_report_config.load_survey_config"
        ) as mock_cfg:
            mock_cfg.return_value = mock_config
            result = ingestion.import_single_target(
                con, "manufacturing", target, fetch=mock_fetch
            )

        assert result["report_id"] == "ism_manufacturing_2026_06"
        assert result["survey_type"] == "manufacturing"
        assert result["metrics"] == len(MANUFACTURING_PARSED["metrics"])

        snap = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert snap["parse_status"] == "ok"
        assert snap["report_month"] == "2026-06-01"

        metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points where date = '2026-06-01'"
        ).fetchone()
        assert metrics["cnt"] == len(MANUFACTURING_PARSED["metrics"])

    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_happy_path_services(self, mock_fetch, tmp_path):
        mock_fetch.return_value = "<html>mock services</html>"
        db = tmp_path / "test_single_import_services.sqlite"
        con = TestPersistParsedReport._init_db(db)
        con.row_factory = sqlite3.Row

        target = {
            "survey_type": "services",
            "report_month": "2026-06-01",
            "report_id": "ism_services_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/services/june/",
        }
        mock_config = {
            "parse_report": lambda html, url, fetched_at, source_name: dict(
                SERVICES_PARSED
            ),
            "allowed_metric_series": set(SERVICES_PARSED["metrics"]),
            "report_id_prefix": "ism_services",
            "ismworld_monthly_url": lambda month_name: target["url"],
        }

        with patch(
            "app.services.ism_report_ingestion.ism_report_config.load_survey_config"
        ) as mock_cfg:
            mock_cfg.return_value = mock_config
            result = ingestion.import_single_target(
                con, "services", target, fetch=mock_fetch
            )

        assert result["report_id"] == "ism_services_2026_06"
        assert result["survey_type"] == "services"
        assert result["metrics"] == len(SERVICES_PARSED["metrics"])

        metrics = con.execute(
            "select count(*) as cnt from macro_indicator_points where date = '2026-06-01' and series_id like 'ism_services_%'"
        ).fetchone()
        assert metrics["cnt"] == len(SERVICES_PARSED["metrics"])

    @patch("app.services.ism_report_ingestion._fetch_or_raise")
    def test_parse_failure_marks_snapshot_failed(self, mock_fetch, tmp_path):
        mock_fetch.return_value = "<html>bad data</html>"
        db = tmp_path / "test_import_fail.sqlite"
        con = TestPersistParsedReport._init_db(db)
        con.row_factory = sqlite3.Row

        target = {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://www.ismworld.org/pmi/june/",
        }

        def failing_parse(html, url, fetched_at, source_name):
            raise ValueError("parse error: metric not found")

        mock_config = {
            "parse_report": failing_parse,
            "allowed_metric_series": set(MANUFACTURING_PARSED["metrics"]),
            "report_id_prefix": "ism_manufacturing",
            "ismworld_monthly_url": lambda month_name: target["url"],
        }

        with patch(
            "app.services.ism_report_ingestion.ism_report_config.load_survey_config"
        ) as mock_cfg:
            mock_cfg.return_value = mock_config
            with pytest.raises(ValueError, match="metric not found"):
                ingestion.import_single_target(
                    con, "manufacturing", target, fetch=mock_fetch
                )

        snap = growth_cycle.load_ism_report_source_snapshot(con, target["url"])
        assert snap["parse_status"] == "failed"
        assert "metric not found" in snap["parse_error"]
        assert snap["raw_html"] == "<html>bad data</html>"


class TestImportTargets:
    @patch("app.services.ism_report_ingestion.import_target_from_db_path")
    def test_ordered_results(self, mock_import, tmp_path):
        db = tmp_path / "test_ordered.sqlite"
        targets = [
            {
                "survey_type": "manufacturing",
                "report_month": "2026-01-01",
                "url": "http://example.com/1",
            },
            {
                "survey_type": "manufacturing",
                "report_month": "2026-02-01",
                "url": "http://example.com/2",
            },
            {
                "survey_type": "manufacturing",
                "report_month": "2026-03-01",
                "url": "http://example.com/3",
            },
        ]
        mock_import.side_effect = [
            {
                "report_id": "ism_manufacturing_2026_01",
                "survey_type": "manufacturing",
                "source": "ismworld",
                "reports": 1,
                "metrics": 11,
                "rankings": 0,
                "comments": 0,
            },
            {
                "report_id": "ism_manufacturing_2026_02",
                "survey_type": "manufacturing",
                "source": "ismworld",
                "reports": 1,
                "metrics": 11,
                "rankings": 0,
                "comments": 0,
            },
            {
                "report_id": "ism_manufacturing_2026_03",
                "survey_type": "manufacturing",
                "source": "ismworld",
                "reports": 1,
                "metrics": 11,
                "rankings": 0,
                "comments": 0,
            },
        ]

        results, failed = ingestion.import_targets(
            str(db),
            "manufacturing",
            targets,
            fetch=lambda u: "<html>",
            report_concurrency=2,
        )

        assert failed == 0
        assert len(results) == 3
        assert results[0]["report_id"] == "ism_manufacturing_2026_01"
        assert results[1]["report_id"] == "ism_manufacturing_2026_02"
        assert results[2]["report_id"] == "ism_manufacturing_2026_03"

    @patch("app.services.ism_report_ingestion.import_target_from_db_path")
    def test_failure_does_not_block_others(self, mock_import, tmp_path):
        db = tmp_path / "test_failure_continue.sqlite"
        targets = [
            {
                "survey_type": "services",
                "report_month": "2026-01-01",
                "url": "http://example.com/1",
            },
            {
                "survey_type": "services",
                "report_month": "2026-02-01",
                "url": "http://example.com/2",
            },
        ]
        success = {
            "report_id": "ism_services_2026_01",
            "survey_type": "services",
            "source": "ismworld",
            "reports": 1,
            "metrics": 4,
            "rankings": 0,
            "comments": 0,
        }
        mock_import.side_effect = [success, ValueError("parse failed")]

        results, failed = ingestion.import_targets(
            str(db),
            "services",
            targets,
            fetch=lambda u: "<html>",
            report_concurrency=1,
        )

        assert failed == 1
        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is None

    def test_empty_targets(self, tmp_path):
        results, failed = ingestion.import_targets(
            tmp_path / "test_empty.sqlite",
            "manufacturing",
            [],
            fetch=lambda u: "<html>",
        )
        assert results == []
        assert failed == 0

    def test_positive_int_validates(self):
        assert ingestion.positive_int("5") == 5
        assert ingestion.positive_int("1") == 1

        with pytest.raises(
            argparse.ArgumentTypeError, match="concurrency must be at least 1"
        ):
            ingestion.positive_int("0")

        with pytest.raises(
            argparse.ArgumentTypeError, match="concurrency must be at least 1"
        ):
            ingestion.positive_int("-1")
