from datetime import date
from pathlib import Path
import time

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
        html = pages[url].read_text()
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

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
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": 200,
            "truncated": False,
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


def test_executor_marks_truncated_response_without_archive_completion():
    adapter = press_adapter({"type": "none"})
    html = (FIXTURES / "press_releases_page_1.html").read_text()

    def fetch(url):
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()) + 10,
            "truncated": True,
            "html": html,
        }

    result = execute_adapter(adapter, fetch_page=fetch, requested_start="2025-01-01", requested_end="2025-12-31")

    assert result["truncation_reason"] == "response_truncated"
    assert result["archive_exhausted"] is False


def test_executor_rejects_non_html_and_unsafe_redirect_chain():
    adapter = press_adapter({"type": "none"})
    html = (FIXTURES / "press_releases_page_1.html").read_text()

    def fetch_non_html(url):
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "application/json",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    with pytest.raises(ValueError, match="content type"):
        execute_adapter(adapter, fetch_page=fetch_non_html, requested_start="2025-01-01", requested_end="2025-12-31")

    def fetch_redirect(url):
        return {
            "requested_url": url,
            "final_url": "https://investor.example.com/news",
            "redirect_chain": [url, "https://evil.example.net/news"],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    with pytest.raises(ValueError, match="redirect"):
        execute_adapter(adapter, fetch_page=fetch_redirect, requested_start="2025-01-01", requested_end="2025-12-31")


def test_executor_marks_slow_injected_fetch_as_elapsed_truncation():
    adapter = press_adapter({"type": "none"})
    html = (FIXTURES / "press_releases_page_1.html").read_text()

    def slow_fetch(url):
        time.sleep(0.02)
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    result = execute_adapter(
        adapter,
        fetch_page=slow_fetch,
        requested_start="2025-01-01",
        requested_end="2025-12-31",
        limits={"max_elapsed_seconds": 0.001},
    )

    assert result["truncation_reason"] == "max_elapsed_seconds"
    assert result["archive_exhausted"] is False


def test_executor_detects_redirected_final_url_loop_and_content_loop():
    adapter = press_adapter({"type": "next_link", "selector": "a.next"})
    html = (FIXTURES / "press_releases_page_1.html").read_text()

    def fetch_final_loop(url):
        return {
            "requested_url": url,
            "final_url": "https://investor.example.com/news?page=2" if "page=1" in url else url,
            "redirect_chain": [url, "https://investor.example.com/news?page=2"] if "page=1" in url else [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    result = execute_adapter(adapter, fetch_page=fetch_final_loop, requested_start="2025-01-01", requested_end="2025-12-31")
    assert result["truncation_reason"] == "repeated_url"

    def fetch_content_loop(url):
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    content_result = execute_adapter(
        adapter,
        fetch_page=fetch_content_loop,
        requested_start="2024-01-01",
        requested_end="2025-12-31",
        limits={"max_pages": 2},
    )
    assert content_result["truncation_reason"] == "repeated_content"


def test_page_parameter_start_overwrites_existing_source_parameter():
    adapter_payload = press_adapter({"type": "page_parameter", "parameter": "page", "start": 1}).model_dump(mode="json")
    adapter_payload["source_url"] = "https://investor.example.com/news?page=1"
    adapter_payload["pagination"]["start"] = 3
    adapter = IRSourceAdapter.model_validate(adapter_payload)
    html = (FIXTURES / "press_releases_page_1.html").read_text()
    calls = []

    def fetch(url):
        calls.append(url)
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    execute_adapter(adapter, fetch_page=fetch, requested_start="2025-01-01", requested_end="2025-12-31", limits={"max_pages": 1})

    assert calls == ["https://investor.example.com/news?page=3"]


def test_page_parameter_start_none_derives_current_page_from_source_url():
    adapter_payload = press_adapter({"type": "page_parameter", "parameter": "page", "start": None}).model_dump(mode="json")
    adapter_payload["source_url"] = "https://investor.example.com/news?page=3"
    adapter = IRSourceAdapter.model_validate(adapter_payload)
    pages = [FIXTURES / "press_releases_page_1.html", FIXTURES / "press_releases_page_2.html"]
    calls = []

    def fetch(url):
        calls.append(url)
        html = pages[len(calls) - 1].read_text()
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": False,
            "html": html,
        }

    execute_adapter(adapter, fetch_page=fetch, requested_start="2024-01-01", requested_end="2025-12-31", limits={"max_pages": 2})

    assert calls == [
        "https://investor.example.com/news?page=3",
        "https://investor.example.com/news?page=4",
    ]


@pytest.mark.parametrize("query", ["page=", "page=0", "page=-1", "page=nope", "page=2&page=3"])
def test_page_parameter_start_none_rejects_invalid_source_page_parameter(query):
    adapter_payload = press_adapter({"type": "page_parameter", "parameter": "page", "start": None}).model_dump(mode="json")
    adapter_payload["source_url"] = f"https://investor.example.com/news?{query}"
    adapter = IRSourceAdapter.model_validate(adapter_payload)

    with pytest.raises(ValueError, match="page parameter"):
        execute_adapter(
            adapter,
            fetch_page=lambda url: {},
            requested_start="2025-01-01",
            requested_end="2025-12-31",
        )
