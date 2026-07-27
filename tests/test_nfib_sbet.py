from pathlib import Path

import pytest

from app.data_sources import nfib_sbet


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "nfib_sbet_june_2026.txt"
SOURCE_URL = "https://www.nfib.com/sbet/june-2026"
RELEASE_DATE = "2026-07-14"
SOURCE_ID = "NFIB-June-2026-SBET-Report.pdf"

FIXTURE_TEXT = FIXTURE_PATH.read_text()


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
    assert values[("nfib_sbo_optimism", "2026-06-30")] == 98.5


def test_parse_sbet_report_text_includes_historical_data():
    payload = nfib_sbet.parse_sbet_report_text(
        FIXTURE_TEXT, SOURCE_URL, RELEASE_DATE, SOURCE_ID
    )
    values = {
        (row["series_id"], row["date"]): row["value"] for row in payload["observations"]
    }
    assert values[("nfib_sbo_employment_plans", "2021-01-30")] == 6.0
    assert values[("nfib_sbo_optimism", "2021-01-30")] == 95.0


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


@pytest.mark.parametrize("text", ["", "June 2026\nPlans to Increase Employment 11"])
def test_parse_sbet_report_text_rejects_missing_required_data(text):
    with pytest.raises(ValueError, match="nfib report is missing required"):
        nfib_sbet.parse_sbet_report_text(text, SOURCE_URL, RELEASE_DATE, "report.pdf")


def test_parse_sbet_report_text_rejects_duplicate_within_section():
    text = FIXTURE_TEXT.replace("2026-06  11", "2026-06  11\n2026-06  12", 1)
    with pytest.raises(ValueError, match="duplicate observation"):
        nfib_sbet.parse_sbet_report_text(text, SOURCE_URL, RELEASE_DATE, "dup.pdf")


def test_parse_sbet_report_rejects_missing_pdf(tmp_path):
    with pytest.raises(ValueError, match="pdf path does not exist"):
        nfib_sbet.parse_sbet_report(tmp_path / "nonexistent.pdf", SOURCE_URL)


def test_fetch_sbet_report_creates_parent_directory(monkeypatch, tmp_path):
    import urllib.request

    calls = []
    monkeypatch.setattr(
        urllib.request, "urlretrieve", lambda url, path: Path(path).write_text("fake")
    )
    dest = tmp_path / "subdir" / "report.pdf"
    result = nfib_sbet.fetch_sbet_report(dest, SOURCE_URL)
    assert result.parent.exists()
    assert result == dest
