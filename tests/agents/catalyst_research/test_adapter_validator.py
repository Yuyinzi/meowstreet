import hashlib
from pathlib import Path

import pytest

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
    content_hash = hashlib.sha256(page.encode()).hexdigest()
    return {
        "snapshot_schema_version": "catalyst_structural_snapshot_v1",
        "requested_url": "https://investor.example.com/news?page=1",
        "final_url": "https://investor.example.com/news?page=1",
        "content_type": "text/html",
        "structural_html": page,
        "normalized": {"title": "Press Releases", "text": "December update June update"},
        "content_hash": content_hash,
        "redirect_chain": ["https://investor.example.com/news?page=1"],
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
    assert report["report"]["source_content_hashes"] == [hashlib.sha256(page.encode()).hexdigest()]
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


def _page(url, html, *, truncated=False, redirect_chain=None, content_type="text/html", response_bytes=None):
    return {
        "requested_url": url,
        "final_url": url,
        "redirect_chain": redirect_chain or [url],
        "content_type": content_type,
        "response_bytes": len(html.encode()) if response_bytes is None else response_bytes,
        "truncated": truncated,
        "html": html,
    }


def test_candidate_and_active_reject_pagination_loops():
    html = (FIXTURES / "press_releases_page_1.html").read_text()

    def fetch(url):
        return _page(url, html)

    candidate = validate_candidate(
        adapter({"type": "next_link", "selector": "a.next"}),
        snapshot(html),
        fetch_page=fetch,
        requested_start="2024-01-01",
        requested_end="2025-12-31",
    )
    active = validate_active_adapter(
        adapter({"type": "next_link", "selector": "a.next"}),
        fetch_page=fetch,
        requested_start="2024-01-01",
        requested_end="2025-12-31",
    )

    assert candidate["status"] == "failed"
    assert candidate["report"]["pagination"]["loop"] is True
    assert candidate["report"]["errors"]
    assert active["status"] == "stale"
    assert active["observations"] == []
    assert active["report"]["pagination"]["loop"] is True


@pytest.mark.parametrize(
    "pagination,urls,limits,expected_status",
    [
        (
            {"type": "next_link", "selector": "a.next"},
            ["https://investor.example.com/news?page=1", "https://investor.example.com/news?page=2"],
            None,
            "passed",
        ),
        (
            {"type": "page_parameter", "parameter": "page", "start": 1},
            ["https://investor.example.com/news?page=1", "https://investor.example.com/news?page=2"],
            None,
            "passed",
        ),
    ],
)
def test_pagination_requires_distinct_safe_page_and_observation(pagination, urls, limits, expected_status):
    pages = [
        (FIXTURES / "press_releases_page_1.html").read_text(),
        (FIXTURES / "press_releases_page_2.html").read_text(),
    ]

    def fetch(url):
        index = 0 if "page=1" in url else 1
        return _page(url, pages[index])

    result = validate_candidate(
        adapter(pagination),
        snapshot(pages[0]),
        fetch_page=fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
        limits=limits,
    )

    assert result["status"] == expected_status
    assert result["report"]["pagination"]["distinct_pages"] is True
    assert result["report"]["pagination"]["distinct_observations"] is True


@pytest.mark.parametrize(
    "limits,expected",
    [({"max_events": 1}, "max_events"), ({"max_elapsed_seconds": 0}, "max_elapsed_seconds")],
)
def test_candidate_reports_executor_limit_failures(limits, expected):
    fetch, _, page = page_fetcher()
    result = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
        limits=limits,
    )

    assert result["status"] == "failed"
    assert result["report"]["pagination"].get("truncation_reason") == expected or expected in result["errors"][0]
    assert result["report"]["errors"]


def test_candidate_rejects_response_truncation_and_oversize_page():
    page = (FIXTURES / "press_releases_page_1.html").read_text()

    truncated = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=lambda url: _page(url, page, truncated=True),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )
    oversized_html = page + (" " * 120_001)
    oversized = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=lambda url: _page(url, oversized_html),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert truncated["status"] == "failed"
    assert truncated["report"]["errors"]
    assert oversized["status"] == "failed"
    assert oversized["report"]["errors"]


def test_response_bytes_have_explicit_upper_bound_and_limit_evidence():
    page = (FIXTURES / "press_releases_page_1.html").read_text()
    too_large = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=lambda url: _page(url, page, response_bytes=2_000_001),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )
    too_small = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=lambda url: _page(url, page, response_bytes=1),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    for result in (too_large, too_small):
        assert result["status"] == "failed"
        checks = result["report"]["limit_checks"]
        assert checks["max_response_bytes"] == 2_000_000
        assert checks["observed_response_bytes"]
        assert checks["response_bytes_within_bounds"] is False
        assert checks["within_bounds"] is False
        assert result["report"]["errors"]

    snapshot_large = snapshot(page)
    snapshot_large["response_bytes"] = 2_000_001
    snapshot_small = snapshot(page)
    snapshot_small["response_bytes"] = 1
    for candidate_snapshot in (snapshot_large, snapshot_small):
        result = validate_candidate(
            adapter(),
            candidate_snapshot,
            fetch_page=lambda url: _page(url, page),
            requested_start="2025-01-01",
            requested_end="2025-12-31",
        )
        assert result["status"] == "failed"
        assert result["report"]["limit_checks"]["observed_response_bytes"]
        assert result["report"]["limit_checks"]["within_bounds"] is False


@pytest.mark.parametrize(
    "html",
    [
        '<article class="news-item"><time>January 3, 2025</time><a class="news-title" href="/release"></a></article>',
        '<article class="news-item"><time></time><a class="news-title" href="/release">Release</a></article>',
        '<article class="news-item"><time>not-a-date</time><a class="news-title" href="/release">Release</a></article>',
        '<article class="news-item"><time>January 3, 2025</time><a class="news-title" href="/release">Release</a></article><article class="news-item"><time>January 3, 2025</time><a class="news-title" href="/release">Release</a></article>',
    ],
)
def test_candidate_rejects_missing_invalid_and_duplicate_observations(html):
    result = validate_candidate(
        adapter(),
        snapshot(html),
        fetch_page=lambda url: _page(url, html),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert result["status"] == "failed"
    assert result["observations"] == []
    assert result["report"]["errors"]
    assert all("<" not in error and ">" not in error for error in result["report"]["errors"])


def test_candidate_rejects_unsafe_redirect_and_event_url():
    page = (FIXTURES / "press_releases_page_1.html").read_text()
    unsafe_redirect = validate_candidate(
        adapter(),
        snapshot(page),
        fetch_page=lambda url: _page(url, page, redirect_chain=[url, "https://evil.example.net/news"]),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )
    unsafe_event = '<article class="news-item"><time>January 3, 2025</time><a class="news-title" href="https://evil.example.net/release">Release</a></article>'
    unsafe_url = validate_candidate(
        adapter(),
        snapshot(unsafe_event),
        fetch_page=lambda url: _page(url, unsafe_event),
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert unsafe_redirect["status"] == "failed"
    assert unsafe_url["status"] == "failed"
    assert unsafe_redirect["report"]["errors"]
    assert unsafe_url["report"]["errors"]


def test_candidate_rejects_invalid_snapshot_hash_without_echoing_unverified_value():
    page = (FIXTURES / "press_releases_page_1.html").read_text()
    candidate_snapshot = snapshot(page)
    candidate_snapshot["content_hash"] = "not-a-real-hash"

    result = validate_candidate(
        adapter(), candidate_snapshot, fetch_page=lambda url: _page(url, page), requested_start="2025-01-01", requested_end="2025-12-31"
    )

    actual = hashlib.sha256(page.encode()).hexdigest()
    assert result["status"] == "failed"
    assert result["report"]["source_content_hashes"] == [actual]
    assert "not-a-real-hash" not in str(result["report"])
    assert result["report"]["errors"]


@pytest.mark.parametrize("htmls", [
    [
        '<article class="news-item"><time>January 3, 2025</time><a class="news-title" href="/same">Same</a></article><a class="next" href="/news?page=2">Next</a>',
        '<article class="news-item"><time>January 3, 2025</time><a class="news-title" href="/same">Same</a></article>',
    ],
    [
        '<article class="news-item"><time>January 3, 2026</time><a class="news-title" href="/old">Old</a></article><a class="next" href="/news?page=2">Next</a>',
        '<article class="news-item"><time>January 4, 2026</time><a class="news-title" href="/old-2">Old two</a></article>',
    ],
])
def test_candidate_rejects_paginated_pages_without_distinct_in_window_observation(htmls):
    def fetch(url):
        return _page(url, htmls[0] if "page=1" in url else htmls[1])

    result = validate_candidate(
        adapter({"type": "next_link", "selector": "a.next"}),
        snapshot(htmls[0]),
        fetch_page=fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert result["status"] == "failed"
    assert result["report"]["pagination"]["distinct_observations"] is False
    assert result["report"]["errors"]


def test_active_validation_returns_success_and_sanitized_stale_on_unexpected_fetch_failure():
    fetch, _, page = page_fetcher()
    success = validate_active_adapter(
        adapter(), fetch_page=fetch, requested_start="2025-01-01", requested_end="2025-12-31"
    )

    def failing_fetch(url):
        raise RuntimeError("provider <secret> failed")

    stale = validate_active_adapter(
        adapter(), fetch_page=failing_fetch, requested_start="2025-01-01", requested_end="2025-12-31"
    )

    assert success["status"] == "passed"
    assert success["promotable_observations"]
    assert stale["status"] == "stale"
    assert stale["observations"] == []
    assert stale["errors"] == ["provider failed"]
    assert stale["report"]["errors"] == stale["errors"]


def test_candidate_rejects_non_equivalent_snapshot_runs(monkeypatch):
    fetch, _, page = page_fetcher()
    calls = iter([([{"title": "first"}], {"source_content_hashes": ["hash"]}), ([{"title": "second"}], {"source_content_hashes": ["hash"]})])
    monkeypatch.setattr(
        "app.agents.catalyst_research.adapters.validator._execution_snapshot",
        lambda *args: next(calls),
    )

    result = validate_candidate(
        adapter(), snapshot(page), fetch_page=fetch, requested_start="2025-01-01", requested_end="2025-12-31"
    )

    assert result["status"] == "failed"
    assert result["report"]["repeatability"]["byte_equivalent"] is False
    assert result["report"]["errors"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(requested_url="https://evil.example.net/news?page=1"),
        lambda value: value.update(final_url="https://evil.example.net/news?page=1"),
        lambda value: value.update(redirect_chain=["https://investor.example.com/news?page=1", "https://evil.example.net/news?page=1"]),
        lambda value: value.update(truncated=True),
    ],
)
def test_candidate_rejects_unsafe_or_truncated_snapshot_metadata(mutation):
    page = (FIXTURES / "press_releases_page_1.html").read_text()
    candidate_snapshot = snapshot(page)
    mutation(candidate_snapshot)

    result = validate_candidate(
        adapter(), candidate_snapshot, fetch_page=lambda url: _page(url, page), requested_start="2025-01-01", requested_end="2025-12-31"
    )

    assert result["status"] == "failed"
    assert result["report"]["errors"]
