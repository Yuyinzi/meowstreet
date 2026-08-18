from datetime import date
from pathlib import Path

import httpx
import pytest

from app.data_sources import nfib_sbet
from app.http_client import HttpClient


ROOT = Path(__file__).resolve().parents[1]
REAL_LAYOUT_FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "nfib_sbet_june_2026_real_layout.txt"
)
SOURCE_URL = "https://www.nfib.com/sbet/june-2026"
RELEASE_DATE = "2026-07-14"
SOURCE_ID = "NFIB-June-2026-SBET-Report.pdf"

FIXTURE_TEXT = REAL_LAYOUT_FIXTURE_PATH.read_text()


def test_parse_sbet_report_text_extracts_june_component_values():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_employment_plans", "2026-06-30")] == 11.0
    assert values[("nfib_sbo_expansion_outlook", "2026-06-30")] == 8.0
    assert values[("nfib_sbo_inventory_plans", "2026-06-30")] == -3.0
    assert values[("nfib_sbo_economic_expectations", "2026-06-30")] == 13.0
    assert values[("nfib_sbo_real_sales_expectations", "2026-06-30")] == 9.0


def test_parse_sbet_report_text_includes_optimism_index():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_optimism", "2026-06-30")] == 97.4


def test_parse_sbet_report_text_extracts_context_component_values():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_capital_outlay_plans", "2026-06-30")] == 20.0
    assert values[("nfib_sbo_current_inventory_low", "2026-06-30")] == 0.0
    assert values[("nfib_sbo_job_openings", "2026-06-30")] == 32.0
    assert values[("nfib_sbo_credit_conditions_expectations", "2026-06-30")] == -5.0
    assert values[("nfib_sbo_earnings_trends", "2026-06-30")] == -20.0


def test_parse_sbet_report_text_includes_historical_data():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_employment_plans", "2021-01-31")] == 17.0
    assert values[("nfib_sbo_optimism", "2021-01-31")] == 95.0


def test_parse_sbet_report_text_does_not_mix_actual_sales_changes():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_real_sales_expectations", "2026-01-31")] == 16.0
    assert values[("nfib_sbo_real_sales_expectations", "2026-02-28")] == 8.0
    assert values[("nfib_sbo_real_sales_expectations", "2026-03-31")] == 7.0
    assert values[("nfib_sbo_real_sales_expectations", "2026-04-30")] == 3.0
    assert values[("nfib_sbo_real_sales_expectations", "2026-05-31")] == 1.0
    assert values[("nfib_sbo_real_sales_expectations", "2026-06-30")] == 9.0


def test_parse_sbet_report_text_carries_official_provenance():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    for obs in payload["observations"]:
        assert obs["source"] == "nfib_sbet_pdf"
        assert obs["revision_status"] == "official_current_history"
        assert obs["source_url"] == SOURCE_URL
        assert obs["release_date"] == RELEASE_DATE


def test_parse_sbet_report_text_emits_series_ids():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    series_ids = {row["series_id"] for row in payload["observations"]}
    assert series_ids == nfib_sbet.SERIES_IDS


def test_parse_sbet_report_text_retains_complete_unique_history_from_real_layout():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    expected_months = {
        f"{year:04d}-{month:02d}"
        for year in range(2021, 2027)
        for month in range(1, 13)
        if (year, month) <= (2026, 6)
    }
    months_by_series = {}
    for observation in payload["observations"]:
        months_by_series.setdefault(observation["series_id"], set()).add(
            observation["date"][:7]
        )

    assert set(months_by_series) == nfib_sbet.SERIES_IDS
    for series_id in nfib_sbet.SERIES_IDS:
        assert months_by_series[series_id] == expected_months

    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_inventory_plans", "2026-05-31")] == 1.0
    assert values[("nfib_sbo_current_inventory_low", "2026-05-31")] == -4.0
    assert values[("nfib_sbo_current_inventory_low", "2026-06-30")] == 0.0
    assert values[("nfib_sbo_job_openings", "2026-06-30")] == 32.0
    assert values[("nfib_sbo_credit_conditions_expectations", "2026-05-31")] == -3.0
    assert values[("nfib_sbo_credit_conditions_expectations", "2026-06-30")] == -5.0
    assert values[("nfib_sbo_earnings_trends", "2026-06-30")] == -20.0


def test_parse_sbet_report_text_uses_section_headings_not_grid_order():
    unrelated_grid = """UNRELATED MONTHLY TABLE
Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
2021 1 1 1 1 1 1 1 1 1 1 1 1
2022 1 1 1 1 1 1 1 1 1 1 1 1
2023 1 1 1 1 1 1 1 1 1 1 1 1
2024 1 1 1 1 1 1 1 1 1 1 1 1
2025 1 1 1 1 1 1 1 1 1 1 1 1
2026 1 1 1 1 1 1
"""
    text = FIXTURE_TEXT.replace(
        "OVERVIEW – SMALL BUSINESS OPTIMISM",
        unrelated_grid + "OVERVIEW – SMALL BUSINESS OPTIMISM",
        1,
    )

    payload = nfib_sbet.parse_sbet_report_text(
        text, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }

    assert values[("nfib_sbo_optimism", "2026-06-30")] == 97.4
    assert values[("nfib_sbo_employment_plans", "2026-06-30")] == 11.0
    assert values[("nfib_sbo_earnings_trends", "2026-06-30")] == -20.0


def test_parse_sbet_report_text_rejects_conflicting_cover_and_historical_values():
    conflicting_text = FIXTURE_TEXT.replace(
        "Plans to Increase Employment (net)   11%",
        "Plans to Increase Employment (net)   12%",
        1,
    )

    with pytest.raises(ValueError, match="nfib report has conflicting values"):
        nfib_sbet.parse_sbet_report_text(
            conflicting_text, SOURCE_URL, RELEASE_DATE, SOURCE_ID
        )


def test_parse_sbet_report_text_rejects_missing_historical_month():
    missing_month_text = FIXTURE_TEXT.replace(
        "2021 95.0 95.8 98.2 99.8 99.6 102.5 99.7 100.1 99.1 98.2 98.4 98.9 ",
        "2021 95.0 95.8 98.2 99.8 99.6 102.5 99.7 100.1 99.1 98.2 98.4",
        1,
    )

    with pytest.raises(ValueError, match="nfib report is missing historical months"):
        nfib_sbet.parse_sbet_report_text(
            missing_month_text, SOURCE_URL, RELEASE_DATE, SOURCE_ID
        )


@pytest.mark.parametrize("text", ["", "June 2026\nPlans to Increase Employment 11"])
def test_parse_sbet_report_text_rejects_missing_required_data(text):
    with pytest.raises(ValueError, match="nfib report is missing required"):
        nfib_sbet.parse_sbet_report_text(text, SOURCE_URL, RELEASE_DATE, "report.pdf")


def test_parse_sbet_report_text_rejects_missing_required_data_02():
    with pytest.raises(ValueError, match="nfib report is missing required"):
        nfib_sbet.parse_sbet_report_text("", SOURCE_URL, RELEASE_DATE, "empty.pdf")


def test_parse_sbet_report_rejects_missing_pdf(tmp_path):
    with pytest.raises(ValueError, match="report path does not exist"):
        nfib_sbet.parse_sbet_report(tmp_path / "nonexistent.pdf", SOURCE_URL)


def test_fetch_sbet_report_creates_parent_directory(tmp_path):
    def handler(request):
        assert request.headers["User-Agent"] == "Meowstreet/1.0"
        return httpx.Response(200, content=b"%PDF-fake")

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    dest = tmp_path / "subdir" / "report.pdf"
    result = nfib_sbet.fetch_sbet_report(dest, SOURCE_URL, http_client=client)
    assert result.parent.exists()
    assert result == dest
    assert dest.read_bytes() == b"%PDF-fake"


def test_discover_latest_sbet_url_probes_candidates_in_priority_order():
    requested = []

    def handler(request):
        assert request.method == "HEAD"
        requested.append(str(request.url))
        if (
            str(request.url)
            == "https://www.nfib.com/wp-content/uploads/2026/08/NFIB-SBET-Report-July-2026.pdf"
        ):
            return httpx.Response(200)
        return httpx.Response(404)

    client = HttpClient(transport=httpx.MockTransport(handler))
    url = nfib_sbet.discover_latest_sbet_url(
        reference_date=date(2026, 8, 18), http_client=client
    )
    assert (
        url
        == "https://www.nfib.com/wp-content/uploads/2026/08/NFIB-SBET-Report-July-2026.pdf"
    )
    assert requested[:3] == [
        "https://www.nfib.com/wp-content/uploads/2026/08/NFIB-July-2026-SBET-Report.pdf",
        "https://www.nfib.com/wp-content/uploads/2026/07/NFIB-July-2026-SBET-Report.pdf",
        "https://www.nfib.com/wp-content/uploads/2026/08/NFIB-SBET-Report-July-2026.pdf",
    ]


def test_discover_latest_sbet_url_skips_missing_months():
    def handler(request):
        if (
            str(request.url)
            == "https://www.nfib.com/wp-content/uploads/2026/07/NFIB-June-2026-SBET-Report.pdf"
        ):
            return httpx.Response(200)
        return httpx.Response(404)

    client = HttpClient(transport=httpx.MockTransport(handler))
    url = nfib_sbet.discover_latest_sbet_url(
        reference_date=date(2026, 8, 18), http_client=client
    )
    assert (
        url
        == "https://www.nfib.com/wp-content/uploads/2026/07/NFIB-June-2026-SBET-Report.pdf"
    )


def test_discover_latest_sbet_url_supports_legacy_monthly_economic_report_name():
    def handler(request):
        if (
            str(request.url)
            == "https://www.nfib.com/wp-content/uploads/2025/08/Monthly-Economic-Report-July-2025.pdf"
        ):
            return httpx.Response(200)
        return httpx.Response(404)

    client = HttpClient(transport=httpx.MockTransport(handler))
    url = nfib_sbet.discover_latest_sbet_url(
        reference_date=date(2025, 8, 20), http_client=client
    )
    assert (
        url
        == "https://www.nfib.com/wp-content/uploads/2025/08/Monthly-Economic-Report-July-2025.pdf"
    )


def test_discover_latest_sbet_url_raises_when_no_candidate_exists():
    def handler(request):
        return httpx.Response(404)

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="no report pdf found"):
        nfib_sbet.discover_latest_sbet_url(
            reference_date=date(2026, 8, 18), http_client=client
        )


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.nfib.com/wp-content/uploads/2026/07/NFIB-June-2026-SBET-Report.pdf",
            (2026, 6),
        ),
        (
            "https://www.nfib.com/wp-content/uploads/2026/08/NFIB-SBET-Report-July-2026.pdf",
            (2026, 7),
        ),
        (
            "https://www.nfib.com/wp-content/uploads/2025/08/Monthly-Economic-Report-August-2025.pdf",
            (2025, 8),
        ),
    ],
)
def test_report_month_from_url_extracts_month_and_year(url, expected):
    assert nfib_sbet.report_month_from_url(url) == expected


def test_report_month_from_url_rejects_unrecognized_name():
    with pytest.raises(ValueError, match="cannot determine report month"):
        nfib_sbet.report_month_from_url("https://www.nfib.com/wp-content/uploads/report.pdf")
