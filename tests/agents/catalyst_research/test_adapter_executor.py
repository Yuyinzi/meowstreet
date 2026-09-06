from datetime import date
from pathlib import Path

import pytest

from app.agents.catalyst_research.adapters.executor import execute_adapter
from app.agents.catalyst_research.adapters.schema import IRSourceAdapter


FIXTURES = Path(__file__).parent / "fixtures"


def press_adapter(pagination):
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
            "pagination": pagination,
        }
    )


def event_adapter():
    return IRSourceAdapter.model_validate(
        {
            "schema_version": "ir_source_adapter_v1",
            "ticker": "NVDA",
            "source_type": "events_presentations",
            "source_url": "https://investor.example.com/events",
            "allowed_hosts": ["investor.example.com", "cdn.example.com"],
            "access_mode": "html",
            "extraction": {
                "item_selector": ".event-item",
                "date": {
                    "selector": "[data-date]",
                    "value_source": "attribute",
                    "attribute": "data-date",
                    "formats": ["%Y-%m-%d"],
                },
                "title": {"selector": ".event-title", "value_source": "text"},
                "url": None,
            },
            "pagination": {"type": "none"},
        }
    )


def fixture_fetcher():
    pages = {
        "https://investor.example.com/news?page=1": FIXTURES / "press_releases_page_1.html",
        "https://investor.example.com/news?page=2": FIXTURES / "press_releases_page_2.html",
        "https://investor.example.com/events": FIXTURES / "events_page.html",
    }
    calls = []

    def fetch(url):
        calls.append(url)
        return {"requested_url": url, "final_url": url, "html": pages[url].read_text()}

    return fetch, calls


def test_executor_extracts_press_release_pages_and_stops_at_requested_start():
    fetch_page, calls = fixture_fetcher()

    result = execute_adapter(
        press_adapter({"type": "next_link", "selector": "a.next"}),
        fetch_page=fetch_page,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert [row["published_date"] for row in result["observations"]] == ["2025-12-20", "2025-06-04", "2025-01-03"]
    assert result["observations"][0]["url"] == "https://investor.example.com/releases/december"
    assert result["coverage_start"] == "2025-01-03"
    assert result["coverage_end"] == "2025-12-20"
    assert result["boundary_reached"] is True
    assert result["archive_exhausted"] is False
    assert result["truncation_reason"] is None
    assert calls == [
        "https://investor.example.com/news?page=1",
        "https://investor.example.com/news?page=2",
    ]


def test_executor_supports_page_parameter_and_event_date_mapping():
    fetch_page, calls = fixture_fetcher()
    adapter = press_adapter({"type": "page_parameter", "parameter": "page", "start": 1})

    result = execute_adapter(
        adapter,
        fetch_page=fetch_page,
        requested_start=date(2025, 1, 1),
        requested_end=date(2025, 12, 31),
        limits={"max_pages": 2},
    )
    event_result = execute_adapter(
        event_adapter(),
        fetch_page=fetch_page,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
    )

    assert len(result["observations"]) == 3
    assert calls[:2] == [
        "https://investor.example.com/news?page=1",
        "https://investor.example.com/news?page=2",
    ]
    assert event_result["observations"][0]["event_date"] == "2025-11-12"
    assert event_result["observations"][0]["url"] is None


def test_executor_rejects_cross_host_event_urls_and_reports_bounded_truncation():
    fetch_page, _ = fixture_fetcher()
    adapter = press_adapter({"type": "none"})

    def unsafe_fetch(url):
        return {
            "requested_url": url,
            "final_url": url,
            "html": '<article class="news-item"><time>January 3, 2025</time><a class="news-title" href="https://evil.example.net/releases/old">Old update</a></article>',
        }

    with pytest.raises(ValueError, match="event url host is not allowed"):
        execute_adapter(
            adapter,
            fetch_page=unsafe_fetch,
            requested_start="2025-01-01",
            requested_end="2025-12-31",
        )

    limited = execute_adapter(
        press_adapter({"type": "next_link", "selector": "a.next"}),
        fetch_page=fetch_page,
        requested_start="2024-01-01",
        requested_end="2025-12-31",
        limits={"max_pages": 1},
    )
    assert limited["truncation_reason"] == "max_pages"
    assert limited["boundary_reached"] is False


def test_executor_is_deterministic_for_repeated_fixture_runs():
    adapter = press_adapter({"type": "next_link", "selector": "a.next"})
    first_fetch, _ = fixture_fetcher()
    second_fetch, _ = fixture_fetcher()

    first = execute_adapter(adapter, fetch_page=first_fetch, requested_start="2025-01-01", requested_end="2025-12-31")
    second = execute_adapter(adapter, fetch_page=second_fetch, requested_start="2025-01-01", requested_end="2025-12-31")

    assert first == second


def test_executor_enforces_event_and_time_limits():
    fetch_page, _ = fixture_fetcher()
    limited_events = execute_adapter(
        press_adapter({"type": "none"}),
        fetch_page=fetch_page,
        requested_start="2024-01-01",
        requested_end="2025-12-31",
        limits={"max_events": 1},
    )
    limited_time = execute_adapter(
        press_adapter({"type": "none"}),
        fetch_page=fetch_page,
        requested_start="2024-01-01",
        requested_end="2025-12-31",
        limits={"max_elapsed_seconds": 0},
    )

    assert len(limited_events["observations"]) == 1
    assert limited_events["truncation_reason"] == "max_events"
    assert limited_time["observations"] == []
    assert limited_time["truncation_reason"] == "max_elapsed_seconds"
