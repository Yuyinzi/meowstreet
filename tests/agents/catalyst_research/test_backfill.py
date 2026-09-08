import asyncio
from datetime import UTC, datetime

import pytest

from app.agents.catalyst_research.backfill import run_historical_backfill
from app.agents.catalyst_research.persistence import repository


URL = "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform"
SECOND_URL = "https://nvidianews.nvidia.com/news/nvidia-second-story"
THIRD_URL = "https://nvidianews.nvidia.com/news/nvidia-third-story"
ARCHIVE_URL = "https://nvidianews.nvidia.com/news/nvidia-archive-record"
DOMAINS = ["nvidia.com"]


def company(**overrides):
    base = {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "official_domains": list(DOMAINS)}
    base.update(overrides)
    return base


def request(**overrides):
    base = {"ticker": "NVDA", "requested_start": "2025-09-08", "requested_end": "2026-09-08"}
    base.update(overrides)
    return base


def config(**overrides):
    base = {
        "historical_slice_days": 92,
        "max_historical_queries_per_channel": 16,
        "search_result_limit": 10,
        "max_unseen_urls_per_channel": 200,
        "archive_enrichment_enabled": False,
    }
    base.update(overrides)
    return base


def feed_endpoint(**overrides):
    base = {
        "endpoint_id": "cse_feed",
        "ticker": "NVDA",
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/rss",
        "domain": "nvidianews.nvidia.com",
        "status": "active",
        "confidence": "high",
    }
    base.update(overrides)
    return base


def endpoints(**overrides):
    rows = [feed_endpoint()]
    rows.extend(overrides.pop("extra", []))
    return rows


def feed_item(**overrides):
    base = {
        "external_guid": "guid-1",
        "title": "NVIDIA Announces New Platform",
        "url": URL,
        "published_at": "2026-09-07T12:00:00+00:00",
        "summary": "NVIDIA announced a new platform.",
        "discovery_method": "rss",
        "endpoint_id": "cse_feed",
    }
    base.update(overrides)
    return base


def search_row(**overrides):
    base = {
        "url": SECOND_URL,
        "title": "NVIDIA Second Story",
        "snippet": "NVIDIA announced a second story.",
        "published_date": "2026-09-05",
        "provider_rank": 1,
        "discovery_method": "search",
    }
    base.update(overrides)
    return base


def direct_article(**overrides):
    base = {
        "status": "extracted",
        "url": SECOND_URL,
        "final_url": SECOND_URL,
        "title": "NVIDIA Second Story",
        "published_at": "2026-09-05T09:00:00+00:00",
        "extraction_provider": "direct_http",
    }
    base.update(overrides)
    return base


def adapter_event(**overrides):
    base = {
        "ticker": "NVDA",
        "source_type": "press_releases",
        "title": "NVIDIA Archive Record",
        "count_date": "2026-08-01",
        "published_date": "2026-08-01",
        "canonical_url": ARCHIVE_URL,
        "discovery_method": "archive_adapter",
    }
    base.update(overrides)
    return base


def running_job(con, ticker="NVDA"):
    job = repository.create_job(
        con,
        {"ticker": ticker, "years": 2},
        {"name": "NVIDIA Corporation", "cik": "1045810"},
        datetime(2026, 9, 4, tzinfo=UTC),
    )
    repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    return job


@pytest.fixture
def env(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    for endpoint in endpoints():
        repository.upsert_source_endpoint(con, endpoint)
    return con, job


class FakeFeedFetcher:
    def __init__(self, items=None, error=None):
        self.items = list(items or [])
        self.error = error
        self.calls = []

    async def __call__(self, endpoint, *, http_client, approved_domains):
        self.calls.append(endpoint["endpoint_id"])
        if self.error is not None:
            raise self.error
        return {"items": [dict(item) for item in self.items], "item_count": len(self.items), "newest_item_at": None}


class FakeQueryExecutor:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.calls = []

    async def __call__(self, query):
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        if callable(self.rows):
            return self.rows(query)
        return [dict(row) for row in self.rows or []]


class FakeExtractionRouter:
    def __init__(self, result=None):
        self.result = result if result is not None else direct_article()
        self.calls = []

    def extract(self, extraction_input, *, company, approved_domains):
        self.calls.append(extraction_input["url"])
        return dict(self.result)


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def __call__(self, *, channel, company, request):
        self.calls.append(channel)
        if self.error is not None:
            raise self.error
        if callable(self.result):
            return self.result(channel)
        return self.result


class FakeProvider:
    def __init__(self, name, rows=None, error=None):
        self.name = name
        self.ready = True
        self.rows = list(rows or [])
        self.error = error
        self.calls = []

    async def search(self, query, *, limit):
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return [dict(row) for row in self.rows]


class FakeSearchRouter:
    def __init__(self, providers):
        self._providers = list(providers)

    def provider_chain(self):
        return list(self._providers)


def fakes(con, job_id, **overrides):
    dependencies = {
        "fetch_feed": FakeFeedFetcher(),
        "execute_query": FakeQueryExecutor(),
        "extraction_router": FakeExtractionRouter(),
        "repository": repository,
        "connection": con,
        "job": {"job_id": job_id},
        "adapter": FakeAdapter(),
    }
    dependencies.update(overrides)
    return dependencies


def run_backfill(dependencies, *, company_dict=None, request_dict=None, endpoints_list=None, config_dict=None):
    return asyncio.run(
        run_historical_backfill(
            company_dict or company(),
            request_dict or request(),
            endpoints=endpoints_list if endpoints_list is not None else endpoints(),
            config=config_dict or config(),
            dependencies=dependencies,
        )
    )


def test_backfill_combines_feed_and_search_without_requiring_adapter(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    result = run_backfill(dependencies)
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["discovery_methods"] == ["rss", "search"]
    assert channel["events"]
    assert channel["archive_boundary_proven"] is False
    assert dependencies["adapter"].calls == []


def test_backfill_feed_only_channel_reports_feed_discovery_method(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    result = run_backfill(dependencies)
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["discovery_methods"] == ["rss"]
    assert [event["count_date"] for event in channel["events"]] == ["2026-09-07"]
    assert channel["observed_start"] == "2026-09-07"
    assert channel["observed_end"] == "2026-09-07"
    assert "search and feed history may omit official records" in channel["warnings"]


def test_backfill_search_only_channel_discovers_without_feed(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["execute_query"].rows = [search_row()]
    result = run_backfill(dependencies, endpoints_list=[])
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["discovery_methods"] == ["search"]
    assert channel["events"]


def test_backfill_provider_fallback_uses_next_provider(env):
    con, job = env
    failing = FakeProvider("tavily", error=RuntimeError("provider down"))
    working = FakeProvider("ddgs", rows=[search_row()])
    dependencies = fakes(con, job["job_id"])
    dependencies.pop("execute_query")
    dependencies["search_router"] = FakeSearchRouter([failing, working])
    result = run_backfill(dependencies)
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["events"]
    assert len(failing.calls) == 3
    assert len(working.calls) == 3


def test_backfill_empty_channel_with_attempted_coverage_is_missing(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    result = run_backfill(dependencies)
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "missing"
    assert channel["events"] == []
    assert channel["observed_start"] is None
    assert channel["observed_end"] is None


def test_backfill_channel_without_feed_or_search_support_is_unsupported(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies.pop("execute_query")
    dependencies["search_router"] = FakeSearchRouter([])
    result = run_backfill(dependencies, endpoints_list=[])
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "unsupported"
    assert channel["events"] == []


def test_backfill_reports_missing_channels_for_every_event_bearing_channel(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    result = run_backfill(dependencies)
    assert set(result["channels"]) == {"press_releases", "events_presentations", "earnings_results"}
    assert result["channels"]["press_releases"]["coverage_status"] == "missing"
    assert result["channels"]["events_presentations"]["coverage_status"] == "missing"
    assert result["channels"]["earnings_results"]["coverage_status"] == "missing"


def test_backfill_marks_historical_query_limit_when_plan_is_truncated(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    result = run_backfill(
        dependencies,
        company_dict=company(official_domains=["nvidia.com", "investor.nvidia.com"]),
        config_dict=config(max_historical_queries_per_channel=1),
    )
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["limit_state"] == ["historical_query_limit"]
    press_queries = [query for query in dependencies["execute_query"].calls if query["channel"] == "press_releases"]
    assert len(press_queries) == 1


def test_backfill_marks_search_result_limit_when_provider_overflows(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row(), search_row(url=THIRD_URL, provider_rank=2)]
    result = run_backfill(dependencies, config_dict=config(search_result_limit=1))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert "search_result_limit" in channel["limit_state"]
    assert len(channel["events"]) == 2
    assert dependencies["extraction_router"].calls == [SECOND_URL]


def test_backfill_marks_unseen_url_limit_from_ingestion(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    result = run_backfill(dependencies, config_dict=config(max_unseen_urls_per_channel=1))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert "unseen_url_limit" in channel["limit_state"]
    assert len(channel["events"]) == 1
    assert "unseen_url_limit" in channel["warnings"]


def test_backfill_drops_candidates_outside_requested_window(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item(published_at="2020-01-01T12:00:00+00:00")]
    dependencies["execute_query"].rows = [search_row(), search_row(url=THIRD_URL, published_date="2020-06-01")]
    result = run_backfill(dependencies)
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert [event["count_date"] for event in channel["events"]] == ["2026-09-05"]
    assert "outside_requested_window" in channel["warnings"]


def test_backfill_feed_failure_falls_back_to_search(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"] = FakeFeedFetcher(error=RuntimeError("feed down"))
    dependencies["execute_query"].rows = [search_row()]
    result = run_backfill(dependencies)
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["discovery_methods"] == ["search"]
    assert "feed_fetch_failed" in channel["warnings"]


def test_backfill_adapter_with_boundary_proven_flips_only_its_channel_to_complete(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    dependencies["adapter"] = FakeAdapter(
        result=lambda channel: {
            "status": "complete",
            "events": [adapter_event()],
            "source": {"url": ARCHIVE_URL, "extraction_status": "complete"},
            "execution": {"boundary_reached": True},
        }
        if channel == "press_releases"
        else None
    )
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    press = result["channels"]["press_releases"]
    assert press["coverage_status"] == "complete"
    assert press["archive_boundary_proven"] is True
    assert "archive_adapter" in press["discovery_methods"]
    assert any(event["title"] == "NVIDIA Archive Record" for event in press["events"])
    earnings = result["channels"]["earnings_results"]
    assert earnings["coverage_status"] == "missing"
    assert earnings["archive_boundary_proven"] is False
    assert dependencies["adapter"].calls == ["press_releases", "events_presentations", "earnings_results"]


def test_backfill_adapter_partial_without_boundary_keeps_observed_partial(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    dependencies["adapter"] = FakeAdapter(
        result={"status": "partial", "events": [adapter_event()], "source": {"url": ARCHIVE_URL}}
    )
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["archive_boundary_proven"] is False
    assert "archive_adapter" in channel["discovery_methods"]
    assert len(channel["events"]) == 3
    assert channel["observed_start"] == "2026-08-01"
    assert channel["observed_end"] == "2026-09-07"


def test_backfill_adapter_failure_preserves_feed_and_search_events(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    dependencies["adapter"] = FakeAdapter(error=RuntimeError("adapter crashed"))
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert len(channel["events"]) == 2
    assert "archive_adapter_failed" in channel["warnings"]
    assert channel["archive_boundary_proven"] is False


def test_backfill_stale_adapter_discards_adapter_events(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    dependencies["adapter"] = FakeAdapter(result={"status": "stale", "events": [adapter_event()]})
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert len(channel["events"]) == 2
    assert "archive_adapter_failed" in channel["warnings"]
    assert channel["archive_boundary_proven"] is False


def test_backfill_zero_events_with_archive_exhaustion_is_complete(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["adapter"] = FakeAdapter(
        result={"status": "complete", "events": [], "execution": {"archive_exhausted": True}}
    )
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "complete"
    assert channel["events"] == []
    assert channel["archive_boundary_proven"] is True


def test_backfill_provider_success_and_item_counts_are_not_completeness_evidence(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    dependencies["adapter"] = FakeAdapter(
        result={
            "status": "complete",
            "events": [adapter_event()],
            "item_count": 500,
            "elapsed_seconds": 12.5,
            "provider_success": True,
        }
    )
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["archive_boundary_proven"] is False


def test_backfill_adapter_truncation_invalidates_boundary_proof(env):
    con, job = env
    dependencies = fakes(con, job["job_id"])
    dependencies["fetch_feed"].items = [feed_item()]
    dependencies["execute_query"].rows = [search_row()]
    dependencies["adapter"] = FakeAdapter(
        result={"status": "partial", "events": [adapter_event()], "execution": {"boundary_reached": True, "truncation_reason": "page_limit"}}
    )
    result = run_backfill(dependencies, config_dict=config(archive_enrichment_enabled=True))
    channel = result["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["archive_boundary_proven"] is False


def test_backfill_requires_valid_inputs():
    with pytest.raises(ValueError, match="requested window"):
        asyncio.run(
            run_historical_backfill(company(), {"ticker": "NVDA"}, endpoints=endpoints(), config=config(), dependencies={})
        )
    with pytest.raises(ValueError, match="approved domains"):
        asyncio.run(
            run_historical_backfill(
                {"ticker": "NVDA", "company_name": "NVIDIA Corporation"},
                request(),
                endpoints=endpoints(),
                config=config(),
                dependencies={},
            )
        )
    with pytest.raises(ValueError, match="endpoints"):
        asyncio.run(
            run_historical_backfill(company(), request(), endpoints="not-a-list", config=config(), dependencies={})
        )
    with pytest.raises(ValueError, match="collection config"):
        asyncio.run(
            run_historical_backfill(company(), request(), endpoints=endpoints(), config=None, dependencies={})
        )
    with pytest.raises(ValueError, match="dependencies"):
        asyncio.run(
            run_historical_backfill(company(), request(), endpoints=endpoints(), config=config(), dependencies=None)
        )
