import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.agents.catalyst_research.extraction.router import ExtractionRouter
from app.agents.catalyst_research.providers.firecrawl import FirecrawlProviderError
from app.agents.catalyst_research.scheduler import run_daily_update, update_plan

AS_OF = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def endpoint_payload(endpoint_id="cse_feed", channel="press_releases", **overrides):
    payload = {
        "endpoint_id": endpoint_id,
        "ticker": "NVDA",
        "channel": channel,
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/rss",
        "domain": "nvidianews.nvidia.com",
        "status": "active",
        "confidence": "high",
        "discovered_at": "2026-09-01T00:00:00+00:00",
        "last_checked_at": "2026-09-05T00:00:00+00:00",
        "consecutive_failures": 0,
    }
    payload.update(overrides)
    return payload


def config(**overrides):
    payload = {
        "gap_search_interval_days": 7,
        "gap_lookback_days": 14,
        "max_gap_queries_per_channel": 2,
        "search_result_limit": 10,
    }
    payload.update(overrides)
    return payload


def company():
    return {"ticker": "NVDA", "company_name": "NVIDIA Corporation"}


def registry(domains=("nvidia.com",)):
    return {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "official_domains": list(domains)}


def feed_item(url="https://nvidianews.nvidia.com/news/first", guid="guid-1"):
    return {
        "external_guid": guid,
        "title": "NVIDIA announces first",
        "url": url,
        "published_at": "2026-09-07T12:00:00+00:00",
        "summary": "summary",
        "discovery_method": "rss",
        "endpoint_id": "cse_feed",
    }


def parsed_feed(items):
    return {
        "format": "rss",
        "items": items,
        "item_count": len(items),
        "newest_item_at": "2026-09-07T12:00:00+00:00",
        "content_hash": "hash-1",
        "final_url": "https://nvidianews.nvidia.com/rss",
    }


class FakeFeedFetcher:
    def __init__(self, feeds=None, errors=None):
        self.feeds = feeds or {}
        self.errors = errors or {}
        self.calls = []

    async def fetch(self, endpoint, *, http_client=None, approved_domains=None):
        self.calls.append(endpoint["endpoint_id"])
        if endpoint["endpoint_id"] in self.errors:
            raise self.errors[endpoint["endpoint_id"]]
        return self.feeds[endpoint["endpoint_id"]]


class FakeIngestion:
    def __init__(self):
        self.seen = set()
        self.stored = []
        self.calls = []
        self.routers = []

    async def ingest(self, candidates, *, company, channel, endpoint=None, job=None, extraction_router=None, repository=None, connection=None, max_urls=None):
        self.calls.append(channel)
        self.routers.append(extraction_router)
        events = []
        for candidate in candidates:
            url = candidate.get("url")
            if url in self.seen:
                continue
            self.seen.add(url)
            self.stored.append(candidate)
            events.append({"url": url, "title": candidate.get("title")})
        return {"events": events}


class RouterUsingIngestion:
    def __init__(self, approved):
        self.approved = approved
        self.routers = []
        self.results = []

    async def ingest(self, candidates, *, company, channel, endpoint=None, job=None, extraction_router=None, repository=None, connection=None, max_urls=None):
        self.routers.append(extraction_router)
        events = []
        for candidate in candidates:
            result = extraction_router.extract(candidate, company=company, approved_domains=self.approved)
            self.results.append(result)
            if result.get("status") == "extracted":
                events.append({"url": result["url"], "title": result.get("title")})
        return {"events": events}


class FakeQueryExecutor:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.calls = []

    async def execute(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return self.rows


class FakeHealthStore:
    def __init__(self):
        self.checks = []
        self.updates = []
        self.order = []

    def record(self, check):
        self.checks.append(check)
        self.order.append("check")

    def update(self, endpoint_id, state):
        self.updates.append((endpoint_id, state))
        self.order.append("health")


class FakeModel:
    def __init__(self):
        self.calls = []

    async def complete(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {}


def base_dependencies(**overrides):
    store = FakeHealthStore()
    dependencies = {
        "record_endpoint_check": store.record,
        "update_endpoint_health": store.update,
        "execute_query": FakeQueryExecutor().execute,
    }
    dependencies.update(overrides)
    return dependencies, store


def run_update(dependencies, *, endpoints_value, as_of=AS_OF, config_value=None, company_value=None, registry_value=None):
    return asyncio.run(
        run_daily_update(
            company_value or company(),
            registry=registry_value or registry(),
            endpoints=endpoints_value,
            as_of=as_of,
            config=config_value or config(),
            dependencies=dependencies,
        )
    )


def test_update_plan_checks_feed_daily_but_searches_weekly():
    result = update_plan(
        [endpoint_payload()],
        {"press_releases": "2026-09-05T00:00:00+00:00"},
        datetime(2026, 9, 8, tzinfo=UTC),
        config(),
    )
    assert result["feed_endpoint_ids"] == ["cse_feed"]
    assert result["gap_channels"] == []


@pytest.mark.parametrize("status", ["failing", "stale"])
def test_update_plan_searches_immediately_for_failing_or_stale_feed(status):
    endpoints = [endpoint_payload(status=status, last_checked_at="2026-09-08T00:00:00+00:00")]
    result = update_plan(endpoints, {}, datetime(2026, 9, 8, tzinfo=UTC), config())
    assert result["gap_channels"] == ["press_releases"]
    reasons = {item["channel"]: item["reason"] for item in result["items"] if item["reason"] != "daily_feed"}
    assert reasons == {"press_releases": "feed_failure" if status == "failing" else "feed_stale"}


def test_update_plan_skips_feed_checked_same_utc_day():
    endpoints = [endpoint_payload(last_checked_at="2026-09-08T06:30:00+00:00")]
    result = update_plan(endpoints, {}, datetime(2026, 9, 8, 15, 0, tzinfo=UTC), config())
    assert result["feed_endpoint_ids"] == []
    assert result["gap_channels"] == ["press_releases"]


@pytest.mark.parametrize(
    ("last_gap", "expected"),
    [
        ("2026-09-02T00:00:00+00:00", []),
        ("2026-09-01T00:00:00+00:00", ["press_releases"]),
    ],
)
def test_update_plan_gap_search_due_on_exact_elapsed_days(last_gap, expected):
    result = update_plan(
        [endpoint_payload()],
        {"press_releases": last_gap},
        datetime(2026, 9, 8, tzinfo=UTC),
        config(),
    )
    assert result["gap_channels"] == expected


def test_update_plan_checks_quiet_feed_daily():
    endpoints = [endpoint_payload(status="quiet", last_item_at="2026-03-01T00:00:00+00:00")]
    result = update_plan(endpoints, {"press_releases": "2026-09-07T00:00:00+00:00"}, AS_OF, config())
    assert result["feed_endpoint_ids"] == ["cse_feed"]
    assert result["gap_channels"] == []


def test_update_plan_transient_failure_checks_feed_without_gap_search():
    endpoints = [
        endpoint_payload(status="active", consecutive_failures=1, last_checked_at="2026-09-07T00:00:00+00:00")
    ]
    result = update_plan(endpoints, {"press_releases": "2026-09-07T00:00:00+00:00"}, AS_OF, config())
    assert result["feed_endpoint_ids"] == ["cse_feed"]
    assert result["gap_channels"] == []


def test_update_plan_excludes_retired_endpoints():
    endpoints = [
        endpoint_payload(endpoint_id="cse_retired", status="retired"),
        endpoint_payload(endpoint_id="cse_active", channel="earnings_results"),
    ]
    result = update_plan(endpoints, {}, AS_OF, config())
    assert result["feed_endpoint_ids"] == ["cse_active"]
    assert result["gap_channels"] == ["earnings_results"]


def test_update_plan_normalizes_timezones_to_utc_days():
    pacific = timezone(timedelta(hours=-7))
    as_of = datetime(2026, 9, 8, 20, 0, tzinfo=pacific)
    endpoints = [endpoint_payload(last_checked_at="2026-09-08T23:00:00-07:00")]
    result = update_plan(endpoints, {"press_releases": "2026-09-01T20:00:00-07:00"}, as_of, config())
    assert result["feed_endpoint_ids"] == []
    assert result["gap_channels"] == ["press_releases"]


def test_update_plan_uses_configured_gap_interval():
    result = update_plan(
        [endpoint_payload()],
        {"press_releases": "2026-09-05T00:00:00+00:00"},
        datetime(2026, 9, 8, tzinfo=UTC),
        config(gap_search_interval_days=3),
    )
    assert result["gap_channels"] == ["press_releases"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda: update_plan("endpoints", {}, AS_OF, config()),
        lambda: update_plan([endpoint_payload()], {"press_releases": "not-a-date"}, AS_OF, config()),
        lambda: update_plan([endpoint_payload()], {}, "2026-09-08", config()),
        lambda: update_plan([endpoint_payload()], {}, AS_OF, {"gap_search_interval_days": 0}),
        lambda: update_plan([endpoint_payload()], {}, AS_OF, {"gap_search_interval_days": "seven"}),
    ],
)
def test_update_plan_validates_inputs(mutation):
    with pytest.raises(ValueError):
        mutation()


def test_daily_update_healthy_feed_makes_zero_model_calls():
    fetcher = FakeFeedFetcher(feeds={"cse_feed": parsed_feed([feed_item()])})
    ingestion = FakeIngestion()
    discovery = FakeModel()
    adapter_generation = FakeModel()
    dependencies, _ = base_dependencies(
        fetch_feed=fetcher.fetch,
        ingest_candidates=ingestion.ingest,
        latest_gap_search={"press_releases": "2026-09-07T00:00:00+00:00"},
        discovery_model=discovery,
        adapter_generation_model=adapter_generation,
    )
    run_update(dependencies, endpoints_value=[endpoint_payload()])
    assert discovery.calls == []
    assert adapter_generation.calls == []


def test_daily_update_unchanged_feed_creates_no_duplicate():
    fetcher = FakeFeedFetcher(feeds={"cse_feed": parsed_feed([feed_item()])})
    ingestion = FakeIngestion()
    dependencies, _ = base_dependencies(
        fetch_feed=fetcher.fetch,
        ingest_candidates=ingestion.ingest,
        latest_gap_search={"press_releases": "2026-09-07T00:00:00+00:00"},
    )
    first = run_update(dependencies, endpoints_value=[endpoint_payload()])
    second = run_update(dependencies, endpoints_value=[endpoint_payload()])
    assert first["feeds"][0]["outcome"] == "success_new"
    assert first["feeds"][0]["new_item_count"] == 1
    assert second["feeds"][0]["outcome"] == "success_empty"
    assert second["feeds"][0]["new_item_count"] == 0
    assert len(ingestion.stored) == 1


def test_daily_update_stores_new_feed_items():
    fetcher = FakeFeedFetcher(feeds={"cse_feed": parsed_feed([feed_item()])})
    ingestion = FakeIngestion()
    dependencies, _ = base_dependencies(
        fetch_feed=fetcher.fetch,
        ingest_candidates=ingestion.ingest,
        latest_gap_search={"press_releases": "2026-09-07T00:00:00+00:00"},
    )
    result = run_update(dependencies, endpoints_value=[endpoint_payload()])
    assert result["feeds"][0]["status"] == "active"
    assert ingestion.stored[0]["url"] == "https://nvidianews.nvidia.com/news/first"


def test_daily_update_records_check_before_transition_and_health_update():
    fetcher = FakeFeedFetcher(feeds={"cse_feed": parsed_feed([feed_item()])})
    ingestion = FakeIngestion()
    store = FakeHealthStore()
    run_update(
        {
            "fetch_feed": fetcher.fetch,
            "ingest_candidates": ingestion.ingest,
            "execute_query": FakeQueryExecutor().execute,
            "latest_gap_search": {"press_releases": "2026-09-07T00:00:00+00:00"},
            "record_endpoint_check": store.record,
            "update_endpoint_health": store.update,
        },
        endpoints_value=[endpoint_payload()],
    )
    assert store.order == ["check", "health"]
    assert store.checks[0]["outcome"] == "success_new"
    assert store.checks[0]["checked_at"] == AS_OF.isoformat()
    endpoint_id, state = store.updates[0]
    assert endpoint_id == "cse_feed"
    assert state["status"] == "active"
    assert state["consecutive_failures"] == 0
    assert state["last_checked_at"] == AS_OF.isoformat()


def test_daily_update_failed_feed_records_check_then_searches_gap():
    fetcher = FakeFeedFetcher(errors={"cse_feed": ValueError("feed request failed")})
    ingestion = FakeIngestion()
    store = FakeHealthStore()
    executor = FakeQueryExecutor(rows=[])
    result = run_update(
        {
            "fetch_feed": fetcher.fetch,
            "ingest_candidates": ingestion.ingest,
            "execute_query": executor.execute,
            "latest_gap_search": {"press_releases": "2026-09-07T00:00:00+00:00"},
            "record_endpoint_check": store.record,
            "update_endpoint_health": store.update,
        },
        endpoints_value=[endpoint_payload()],
    )
    assert store.order == ["check", "health"]
    assert store.checks[0]["outcome"] == "request_failed"
    assert store.checks[0]["error_code"] == "request_failed"
    assert store.updates[0][1]["consecutive_failures"] == 1
    assert result["feeds"][0]["outcome"] == "request_failed"
    assert [gap["channel"] for gap in result["gaps"]] == ["press_releases"]
    assert result["gaps"][0]["reason"] == "feed_failure"
    assert executor.calls


def test_daily_update_parse_failure_marks_parse_failed_outcome():
    fetcher = FakeFeedFetcher(errors={"cse_feed": ValueError("feed xml is invalid")})
    store = FakeHealthStore()
    run_update(
        {
            "fetch_feed": fetcher.fetch,
            "ingest_candidates": FakeIngestion().ingest,
            "execute_query": FakeQueryExecutor().execute,
            "latest_gap_search": {"press_releases": "2026-09-07T00:00:00+00:00"},
            "record_endpoint_check": store.record,
            "update_endpoint_health": store.update,
        },
        endpoints_value=[endpoint_payload()],
    )
    assert store.checks[0]["outcome"] == "parse_failed"
    assert store.checks[0]["error_code"] == "parse_failed"


def test_daily_update_gap_search_caps_queries_per_channel():
    domains = ("nvidia.com", "investor.nvidia.com", "news.nvidia.com")
    executor = FakeQueryExecutor(
        rows=[
            {
                "url": "https://investor.nvidia.com/news/press-release-1",
                "title": "NVIDIA press release",
                "snippet": "NVIDIA",
                "published_date": "2026-09-07",
                "provider_rank": 1,
            }
        ]
    )
    ingestion = FakeIngestion()
    result = run_update(
        base_dependencies(
            fetch_feed=FakeFeedFetcher(feeds={"cse_feed": parsed_feed([])}).fetch,
            ingest_candidates=ingestion.ingest,
            execute_query=executor.execute,
            latest_gap_search={},
        )[0],
        endpoints_value=[endpoint_payload(status="failing")],
        registry_value=registry(domains),
    )
    assert len(executor.calls) == 2
    assert len({query["domain"] for query in executor.calls}) == 2
    assert result["gaps"][0]["query_count"] == 2
    assert result["gaps"][0]["event_count"] == 1
    assert ingestion.stored[0]["url"] == "https://investor.nvidia.com/news/press-release-1"


def test_daily_update_shares_one_router_and_persists_firecrawl_disablement():
    rows = [
        {
            "url": "https://investor.nvidia.com/news/press-release-1",
            "title": "NVIDIA press release one",
            "snippet": "NVIDIA",
            "published_date": "2026-09-07",
            "provider_rank": 1,
        },
        {
            "url": "https://investor.nvidia.com/news/press-release-2",
            "title": "NVIDIA press release two",
            "snippet": "NVIDIA",
            "published_date": "2026-09-06",
            "provider_rank": 2,
        },
    ]

    def failing_direct_extractor(url, **kwargs):
        raise ValueError("page host is not allowed")

    class FakeFirecrawl:
        def __init__(self):
            self.calls = []

        def extract(self, url):
            self.calls.append(url)
            raise FirecrawlProviderError("rate_limited", "quota exceeded", disable_provider=True)

    firecrawl = FakeFirecrawl()
    router = ExtractionRouter(failing_direct_extractor, firecrawl_provider=firecrawl)
    ingestion = RouterUsingIngestion(["nvidia.com"])
    run_update(
        base_dependencies(
            fetch_feed=FakeFeedFetcher(feeds={"cse_feed": parsed_feed([])}).fetch,
            ingest_candidates=ingestion.ingest,
            execute_query=FakeQueryExecutor(rows=rows).execute,
            latest_gap_search={},
            extraction_router=router,
        )[0],
        endpoints_value=[endpoint_payload(status="failing")],
    )
    assert len(ingestion.routers) == 1
    assert ingestion.routers[0] is router
    assert len(firecrawl.calls) == 1
    assert ingestion.results[1]["status"] == "manual_review_required"
    firecrawl_attempts = [
        attempt for attempt in ingestion.results[1]["attempts"] if attempt["provider"] == "firecrawl"
    ]
    assert firecrawl_attempts == [{"provider": "firecrawl", "outcome": "rate_limited"}]


def test_daily_update_requires_ingestion_when_feed_has_items():
    fetcher = FakeFeedFetcher(feeds={"cse_feed": parsed_feed([feed_item()])})
    with pytest.raises(ValueError, match="ingest_candidates is required"):
        run_update(
            base_dependencies(
                fetch_feed=fetcher.fetch,
                latest_gap_search={"press_releases": "2026-09-07T00:00:00+00:00"},
            )[0],
            endpoints_value=[endpoint_payload()],
        )
