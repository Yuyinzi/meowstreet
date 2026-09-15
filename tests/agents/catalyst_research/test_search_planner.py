from datetime import date

import pytest

from app.agents.catalyst_research.search_planner import filter_official_candidates
from app.agents.catalyst_research.search_planner import gap_queries
from app.agents.catalyst_research.search_planner import historical_queries
from app.agents.catalyst_research.search_planner import historical_slices


URL = "https://nvidianews.nvidia.com/news/nvidia-announces-aaa"
DOMAINS = frozenset({"nvidianews.nvidia.com"})


def company():
    return {"ticker": "NVDA", "company_name": "NVIDIA"}


def config():
    return {
        "historical_slice_days": 92,
        "max_historical_queries_per_channel": 16,
        "search_result_limit": 10,
        "max_unseen_urls_per_channel": 200,
        "gap_lookback_days": 14,
        "max_gap_queries_per_channel": 2,
        "gap_search_interval_days": 7,
        "feed_failure_threshold": 3,
    }


def test_filter_official_candidates_rejects_archive_label_pages():
    detail = "https://nvidianews.nvidia.com/news-events/press-releases/detail/1781/nvidia-announces-new-platform"
    rows = [
        {"url": "https://nvidianews.nvidia.com/news-events/press-releases", "title": "NVIDIA Press Releases", "snippet": "NVIDIA news"},
        {"url": "https://nvidianews.nvidia.com/news-events/press-releases?page=4", "title": "NVIDIA Press Releases", "snippet": "NVIDIA news"},
        {"url": "https://nvidianews.nvidia.com/news-events/ir-calendar/past", "title": "NVIDIA Past Events", "snippet": "NVIDIA events"},
        {"url": "https://nvidianews.nvidia.com/filings-reports", "title": "NVIDIA Filings & Reports", "snippet": "NVIDIA filings"},
        {"url": "https://nvidianews.nvidia.com/news-events", "title": "NVIDIA News & Events", "snippet": "NVIDIA news"},
        {"url": detail, "title": "NVIDIA Announces New Platform", "snippet": "NVIDIA announcement"},
    ]

    accepted = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)

    assert [row["url"] for row in accepted] == [detail]


def window():
    return {"start": "2025-09-08", "end": "2025-12-08"}


def search_row(url, result_id=1, **overrides):
    row = {
        "result_id": result_id,
        "title": "NVIDIA Announces AAA",
        "snippet": "NVIDIA press release detail",
        "url": url,
        "published_date": "2025-10-01",
        "provider_rank": 1,
    }
    row.update(overrides)
    return row


def test_four_year_window_uses_at_most_sixteen_non_overlapping_slices():
    result = historical_slices(date(2022, 9, 8), date(2026, 9, 8), slice_days=92, max_queries=16)
    assert len(result["slices"]) == 16
    assert result["slices"][0]["start"] == "2022-09-08"
    assert result["slices"][-1]["end"] == "2026-09-08"
    assert result["truncated"] is False
    assert result["truncation_reason"] is None


def test_historical_slices_cover_one_day_window():
    result = historical_slices(date(2025, 3, 1), date(2025, 3, 1), slice_days=92, max_queries=16)
    assert result["slices"] == [{"index": 0, "start": "2025-03-01", "end": "2025-03-01"}]
    assert result["truncated"] is False


def test_historical_slices_are_contiguous_chronological_and_deterministic():
    result = historical_slices(date(2023, 1, 10), date(2024, 3, 20), slice_days=92, max_queries=16)
    repeat = historical_slices(date(2023, 1, 10), date(2024, 3, 20), slice_days=92, max_queries=16)
    assert result == repeat
    slices = result["slices"]
    assert [item["index"] for item in slices] == list(range(len(slices)))
    for previous, current in zip(slices, slices[1:]):
        assert previous["end"] < current["start"]
        gap = (date.fromisoformat(current["start"]) - date.fromisoformat(previous["end"])).days
        assert gap == 1


def test_historical_slices_cover_leap_day():
    result = historical_slices(date(2024, 2, 25), date(2024, 3, 10), slice_days=7, max_queries=16)
    assert result["slices"] == [
        {"index": 0, "start": "2024-02-25", "end": "2024-03-02"},
        {"index": 1, "start": "2024-03-03", "end": "2024-03-09"},
        {"index": 2, "start": "2024-03-10", "end": "2024-03-10"},
    ]
    covered = []
    for item in result["slices"]:
        day = date.fromisoformat(item["start"])
        while day.isoformat() <= item["end"]:
            covered.append(day)
            day += date.resolution * 1
    assert date(2024, 2, 29) in covered


def test_historical_slices_truncate_under_lower_cap_with_reason():
    result = historical_slices(date(2022, 9, 8), date(2026, 9, 8), slice_days=86, max_queries=16)
    assert len(result["slices"]) == 16
    assert result["truncated"] is True
    assert result["truncation_reason"] == "historical_query_limit"
    assert result["slices"][-1]["end"] < "2026-09-08"


def test_historical_slices_reject_inverted_window_and_invalid_limits():
    with pytest.raises(ValueError, match="date window is invalid"):
        historical_slices(date(2025, 3, 2), date(2025, 3, 1), slice_days=92, max_queries=16)
    with pytest.raises(ValueError, match="slice days must be a positive integer"):
        historical_slices(date(2025, 3, 1), date(2025, 3, 2), slice_days=0, max_queries=16)
    with pytest.raises(ValueError, match="max queries must be a positive integer"):
        historical_slices(date(2025, 3, 1), date(2025, 3, 2), slice_days=92, max_queries=0)


def test_historical_query_is_site_scoped_and_channel_specific():
    result = historical_queries(company(), "press_releases", ["nvidianews.nvidia.com"], window(), config())
    assert result["queries"][0]["query"].startswith("site:nvidianews.nvidia.com NVIDIA press release")
    assert "after:2025-09-07" in result["queries"][0]["query"]
    assert "before:" in result["queries"][0]["query"]


def test_historical_queries_preserve_inclusive_window_with_exclusive_operators():
    result = historical_queries(company(), "press_releases", ["nvidianews.nvidia.com"], window(), config())
    query = result["queries"][0]
    assert "after:2025-09-07" in query["query"]
    assert "before:2025-12-09" in query["query"]
    assert query["window"] == {"start": "2025-09-08", "end": "2025-12-08"}
    assert query["channel"] == "press_releases"
    assert query["domain"] == "nvidianews.nvidia.com"
    assert query["purpose"] == "historical_backfill"
    assert query["result_limit"] == 10


def test_historical_queries_emit_one_query_per_domain_and_cap_with_reason():
    domains = [f"source{index}.nvidia.com" for index in range(18)]
    result = historical_queries(company(), "press_releases", domains, window(), config())
    assert len(result["queries"]) == 16
    assert result["truncated"] is True
    assert result["truncation_reason"] == "historical_query_limit"
    uncapped = historical_queries(company(), "press_releases", domains[:2], window(), config())
    assert len(uncapped["queries"]) == 2
    assert uncapped["truncated"] is False
    assert uncapped["truncation_reason"] is None


def test_historical_queries_use_channel_phrases():
    events = historical_queries(company(), "events_presentations", ["nvidianews.nvidia.com"], window(), config())
    earnings = historical_queries(company(), "earnings_results", ["nvidianews.nvidia.com"], window(), config())
    assert "events presentations" in events["queries"][0]["query"]
    assert "quarterly earnings financial results" in earnings["queries"][0]["query"]


def test_historical_queries_reject_unknown_channel_and_missing_identity():
    with pytest.raises(ValueError, match="channel"):
        historical_queries(company(), "ir_home", ["nvidianews.nvidia.com"], window(), config())
    with pytest.raises(ValueError, match="company identity is required"):
        historical_queries({"ticker": ""}, "press_releases", ["nvidianews.nvidia.com"], window(), config())
    with pytest.raises(ValueError, match="approved domains are required"):
        historical_queries(company(), "press_releases", [], window(), config())


def test_gap_queries_use_configured_lookback_and_two_query_cap():
    domains = ["nvidianews.nvidia.com", "investor.nvidia.com"]
    queries = gap_queries(company(), "press_releases", domains, date(2026, 9, 8), config())
    assert len(queries) == 2
    for query in queries:
        assert "after:2026-08-25" in query["query"]
        assert "before:2026-09-09" in query["query"]
        assert query["window"] == {"start": "2026-08-26", "end": "2026-09-08"}
        assert query["purpose"] == "incremental_gap_check"
        assert query["channel"] == "press_releases"
    assert [query["domain"] for query in queries] == domains


def test_gap_queries_enforce_configured_cap():
    domains = [f"source{index}.nvidia.com" for index in range(4)]
    queries = gap_queries(company(), "press_releases", domains, date(2026, 9, 8), config())
    assert len(queries) == 2
    narrowed = dict(config(), max_gap_queries_per_channel=1)
    queries = gap_queries(company(), "press_releases", domains, date(2026, 9, 8), narrowed)
    assert len(queries) == 1


def test_filter_rejects_third_party_and_archive_root_results():
    rows = [search_row(URL), search_row("https://news.example.com/nvidia", result_id=2), search_row("https://nvidianews.nvidia.com/news", result_id=3)]
    assert [row["url"] for row in filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)] == [URL]


def test_filter_canonicalizes_and_preserves_result_id():
    row = search_row(
        "https://NVIDIANEWS.NVIDIA.com/news/nvidia-announces-aaa?utm_source=x#frag",
        result_id=7,
    )
    accepted = filter_official_candidates([row], company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert len(accepted) == 1
    assert accepted[0]["url"] == URL
    assert accepted[0]["canonical_url"] == URL
    assert accepted[0]["result_id"] == 7


def test_filter_accepts_subdomain_but_rejects_lookalike_host():
    rows = [
        search_row("https://ir.nvidianews.nvidia.com/news/nvidia-announces-aaa", result_id=1),
        search_row("https://nvidianews.nvidia.com.evil.example/news/nvidia-announces-aaa", result_id=2),
    ]
    accepted = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert [row["result_id"] for row in accepted] == [1]


def test_filter_rejects_search_cached_and_archive_hosts():
    rows = [
        search_row("https://www.google.com/search?q=nvidia+press+release", result_id=1),
        search_row("https://webcache.googleusercontent.com/search?q=cache:nvidianews", result_id=2),
        search_row("https://web.archive.org/web/2021/https://nvidianews.nvidia.com/news/x", result_id=3),
        search_row("https://www.reddit.com/r/nvidia/comments/x/", result_id=4),
    ]
    accepted = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert accepted == []


def test_filter_rejects_list_roots_and_search_paths():
    rows = [
        search_row("https://nvidianews.nvidia.com", result_id=1),
        search_row("https://nvidianews.nvidia.com/", result_id=2),
        search_row("https://nvidianews.nvidia.com/news/", result_id=3),
        search_row("https://nvidianews.nvidia.com/press-releases", result_id=4),
        search_row("https://nvidianews.nvidia.com/search?q=nvidia", result_id=5),
        search_row("https://nvidianews.nvidia.com/news?page=2", result_id=6),
        search_row("https://nvidianews.nvidia.com/news/nvidia-announces-aaa", result_id=7),
    ]
    accepted = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert [row["result_id"] for row in accepted] == [7]


def test_filter_rejects_unsafe_urls_and_requires_identity_evidence():
    rows = [
        search_row("ftp://nvidianews.nvidia.com/news/nvidia-announces-aaa", result_id=1),
        search_row(
            "https://nvidianews.nvidia.com/news/company-announces-aaa",
            result_id=2,
            title="Some Other Firm Announces AAA",
            snippet="An unrelated company announcement",
        ),
    ]
    accepted = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert accepted == []


def test_filter_stable_sorts_by_published_date_then_provider_rank_then_url():
    rows = [
        search_row("https://nvidianews.nvidia.com/news/nvidia-c", result_id=1, published_date="2025-10-02", provider_rank=1),
        search_row("https://nvidianews.nvidia.com/news/nvidia-a", result_id=2, published_date="2025-10-01", provider_rank=3),
        search_row("https://nvidianews.nvidia.com/news/nvidia-b", result_id=3, published_date="2025-10-01", provider_rank=2),
        search_row("https://nvidianews.nvidia.com/news/nvidia-d", result_id=4, published_date=None, provider_rank=1),
    ]
    accepted = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert [row["result_id"] for row in accepted] == [3, 2, 1, 4]


def test_filter_is_deterministic_for_duplicate_canonical_urls():
    rows = [
        search_row("https://nvidianews.nvidia.com/news/nvidia-a?utm_source=x", result_id=1, published_date="2025-10-01", provider_rank=2),
        search_row("https://NVIDIANEWS.NVIDIA.com/news/nvidia-a", result_id=2, published_date="2025-10-01", provider_rank=1),
    ]
    first = filter_official_candidates(rows, company=company(), channel="press_releases", approved_domains=DOMAINS)
    second = filter_official_candidates(list(reversed(rows)), company=company(), channel="press_releases", approved_domains=DOMAINS)
    assert [row["result_id"] for row in first] == [row["result_id"] for row in second] == [2, 1]


def test_filter_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="candidate rows are required"):
        filter_official_candidates("rows", company=company(), channel="press_releases", approved_domains=DOMAINS)
    with pytest.raises(ValueError, match="candidate row is invalid"):
        filter_official_candidates([{"url": URL}, "row"], company=company(), channel="press_releases", approved_domains=DOMAINS)
    with pytest.raises(ValueError, match="channel"):
        filter_official_candidates([], company=company(), channel="ir_home", approved_domains=DOMAINS)
