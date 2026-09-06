from pathlib import Path

from app.agents.catalyst_research.adapters.schema import IRSourceAdapter
from app.agents.catalyst_research.adapters.validator import validate_active_adapter, validate_candidate


FIXTURES = Path(__file__).parent / "fixtures"


def adapter(pagination=None):
    return IRSourceAdapter.model_validate(
        {
            "schema_version": "ir_source_adapter_v1",
            "ticker": "NVDA",
            "source_type": "press_releases",
            "source_url": "https://investor.example.com/news?page=1",
            "allowed_hosts": ["investor.example.com"],
            "access_mode": "html",
            "extraction": {
                "item_selector": ".news-item",
                "date": {"selector": "time", "value_source": "text", "formats": ["%B %d, %Y"]},
                "title": {"selector": ".news-title", "value_source": "text"},
                "url": {"selector": ".news-title", "value_source": "attribute", "attribute": "href"},
            },
            "pagination": pagination or {"type": "none"},
        }
    )


def page_fetcher():
    page = (FIXTURES / "press_releases_page_1.html").read_text()
    calls = []

    def fetch(url):
        calls.append(url)
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(page.encode()),
            "truncated": False,
            "html": page,
        }

    return fetch, calls, page


def snapshot(page):
    return {
        "snapshot_schema_version": "catalyst_structural_snapshot_v1",
        "requested_url": "https://investor.example.com/news?page=1",
        "final_url": "https://investor.example.com/news?page=1",
        "content_type": "text/html",
        "structural_html": page,
        "normalized": {"title": "Press Releases", "text": "December update June update"},
        "content_hash": "snapshot-hash",
    }


def test_candidate_validation_reports_safe_repeatable_snapshot_and_live_execution():
    fetch, calls, page = page_fetcher()
    report = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert report["status"] == "passed"
    assert report["validator_version"]
    assert report["executor_version"]
    assert report["report"]["source_content_hashes"] == ["snapshot-hash"]
    assert report["report"]["match_counts"]["items"] == 2
    assert report["report"]["valid_observation_count"] == 2
    assert report["report"]["parsed_date_formats"] == ["%B %d, %Y"]
    assert report["report"]["pagination"]["type"] == "none"
    assert report["report"]["safety_failures"] == []
    assert report["report"]["page_content_hashes"]
    assert report["observations"]
    assert calls == ["https://investor.example.com/news?page=1"]
    assert "<article" not in str(report)


def test_candidate_validation_rejects_excluded_regions_and_sanitizes_error():
    fetch, _, page = page_fetcher()
    broken = (FIXTURES / "press_releases_broken.html").read_text()
    report = validate_candidate(
        adapter(),
        snapshot(broken),
        fetch_page=fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert report["status"] == "failed"
    assert report["observations"] == []
    assert report["errors"]
    assert all("<" not in error and ">" not in error for error in report["errors"])


def test_active_validation_returns_stale_without_promotable_observations_on_drift():
    def fetch(url):
        page = (FIXTURES / "press_releases_broken.html").read_text()
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(page.encode()),
            "truncated": False,
            "html": page,
        }

    result = validate_active_adapter(
        adapter(),
        fetch_page=fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert result["status"] == "stale"
    assert result["observations"] == []
    assert result["promotable_observations"] == []
    assert result["report"]["safety_failures"]
