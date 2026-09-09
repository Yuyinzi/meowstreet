import pytest

from app.agents.catalyst_research.report import render_report


def result(**overrides):
    payload = {
        "ticker": "NVDA",
        "job_id": "cr_1",
        "status": "completed_partial",
        "mode": "research",
        "completed_at": "2026-09-09T03:33:37+00:00",
        "observation_count": 9,
        "requested_window": {"start": "2025-09-09", "end": "2026-09-09", "years": 1},
        "statistics": {
            "press_releases": {"coverage_status": "observed_partial", "observed_total": 6, "observed_start": "2026-08-17", "observed_end": "2026-08-31"},
        },
        "sources": [],
        "warnings": [],
        "next_actions": [],
    }
    payload.update(overrides)
    return payload


def failed_source(channel="earnings_results", url="https://example.com/report.pdf", reason="manual_review_required"):
    return {"source_type": channel, "url": url, "extraction_status": "failed", "verification_reason": reason}


def test_render_report_lists_failed_sources_for_manual_review():
    report = render_report(result(sources=[failed_source(), failed_source(channel="press_releases", url="https://example.com/news")]))

    assert "## Manual review required (2)" in report
    assert "- [earnings_results] https://example.com/report.pdf" in report
    assert "- [press_releases] https://example.com/news" in report


def test_render_report_shows_header_and_channel_coverage():
    report = render_report(result())

    assert report.startswith("# Catalyst research report\n")
    assert "- ticker: NVDA" in report
    assert "- job_id: cr_1" in report
    assert "- window: 2025-09-09..2026-09-09" in report
    assert "- press_releases: observed_partial (6 observed, 2026-08-17..2026-08-31)" in report


def test_render_report_without_failed_sources_says_none():
    report = render_report(result(sources=[{"source_type": "press_releases", "extraction_status": "complete"}]))

    assert "## Manual review required (0)" in report
    assert "- none" in report


def test_render_report_includes_warnings_and_next_actions():
    report = render_report(result(warnings=["search and feed history may omit official records"], next_actions=["review partial extraction"]))

    assert "## Warnings" in report
    assert "- search and feed history may omit official records" in report
    assert "## Next actions" in report
    assert "- review partial extraction" in report


def test_render_report_shows_non_default_failure_reason():
    report = render_report(result(sources=[failed_source(reason="parse_failed")]))

    assert "(parse_failed)" in report


@pytest.mark.parametrize("bad", [None, [], "result", 42])
def test_render_report_validates_result(bad):
    with pytest.raises(ValueError, match="result is required"):
        render_report(bad)
