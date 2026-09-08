import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from app.agents.catalyst_research import backfill, domain, registry, registry_discovery, scheduler
from app.agents.catalyst_research import statistics as v1_1_statistics
from app.agents.catalyst_research.adapters.executor import execute_adapter
from app.agents.catalyst_research.adapters.validator import validate_active_adapter, validate_candidate
from app.agents.catalyst_research.extraction.articles import extract_direct_article
from app.agents.catalyst_research.extraction.feeds import fetch_feed
from app.agents.catalyst_research.extraction.html import build_structural_snapshot
from app.agents.catalyst_research.extraction.router import ExtractionRouter
from app.agents.catalyst_research.persistence import repository
from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.firecrawl import FirecrawlExtractProvider
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.schemas import EventClassificationResponse, RegistrySelectionResponse
from app.agents.catalyst_research.statistics import calculate_statistics
from app.agents.catalyst_research.workflow import run_research
from app.http_client import HttpClient


FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "acceptance_manifest.json").read_text())
TICKERS = sorted(MANIFEST["tickers"])
_REQUIRED_CHANNELS = ("press_releases", "events_presentations")
_INFORMATIONAL_SOURCE_TYPES = ("ir_home", "earnings_results")
_FIXED_CLOCK = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class _FixtureSearchProvider:
    def __init__(self, name, entry, error=None):
        self.name = name
        self.entry = entry
        self.error = error
        self.ready = True
        self.last_request_id = None
        self.calls = []

    async def search(self, query, *, limit):
        self.calls.append((query, limit))
        if self.error is not None:
            raise self.error
        if "press releases" in query.lower():
            source_type = "press_releases"
            purpose = "Press Releases"
        elif "events presentations" in query.lower():
            source_type = "events_presentations"
            purpose = "Events and Presentations"
        elif "quarterly earnings" in query.lower():
            source_type = "earnings_results"
            purpose = "Quarterly Earnings Financial Results"
        else:
            source_type = "ir_home"
            purpose = "Investor Relations"
        if source_type in _REQUIRED_CHANNELS and not self.entry["channels"][source_type]["discovered"]:
            return []
        return [
            {
                "title": f"{self.entry['company_name']} {purpose}",
                "url": self.entry["fixture_source_urls"][source_type],
                "snippet": f"{self.entry['company_name']} Investor Relations {purpose}",
                "provider_rank": 1,
                "provider_metadata": {},
            }
        ]


class _FixtureSourceSelectionResponses:
    async def parse(self, *, input, **kwargs):
        candidates = json.loads(input[1]["content"].split("Search candidates:\n", 1)[1])
        candidate = candidates[0]
        query = candidate["query"].lower()
        if "press releases" in query:
            source_type = "press_releases"
        elif "events presentations" in query:
            source_type = "events_presentations"
        elif "quarterly earnings" in query:
            source_type = "earnings_results"
        else:
            source_type = "ir_home"
        parsed = {
            "selections": [
                {
                    "source_type": source_type,
                    "url": candidate["url"],
                    "evidence_result_ids": [candidate["result_id"]],
                    "confidence": 0.9,
                    "reason": "fixture evidence identifies the official Investor Relations source",
                }
            ]
        }
        return type("Response", (), {"output_parsed": parsed})()


class _FixtureSourceSelectionLLM:
    def __init__(self):
        self.responses = _FixtureSourceSelectionResponses()


class _FixtureClassificationResponses:
    def __init__(self, harness):
        self.harness = harness
        self.calls = 0

    async def parse(self, *, input, text_format, **kwargs):
        assert text_format is EventClassificationResponse
        self.calls += 1
        events = json.loads(input[1]["content"].split("Events to classify:\n", 1)[1])
        expected = self.harness._expected_labels()
        classifications = [
            {
                "id": event["id"],
                "earnings_state": expected[(event["source_type"], event["title"])]["earnings_state"],
                "reason": "fixture manually labeled title",
            }
            for event in events
        ]
        parsed = EventClassificationResponse.model_validate({"classifications": classifications})
        return type("Response", (), {"output_parsed": parsed})()


class _FixtureClassificationLLM:
    def __init__(self, harness):
        self.responses = _FixtureClassificationResponses(harness)


class _AcceptanceHarness:
    def __init__(self, tmp_path, ticker):
        if ticker not in MANIFEST["tickers"]:
            raise ValueError(f"acceptance ticker {ticker} is not in the manifest")
        self.ticker = ticker
        self.entry = MANIFEST["tickers"][ticker]
        self.ticker_dir = FIXTURES / ticker
        self.db_path = Path(tmp_path) / f"{ticker.lower()}_acceptance.sqlite"
        self.revision = None
        self.fetched_urls = []
        self.classification_llm = _FixtureClassificationLLM(self)
        self.provider_calls = {}
        self.provider_disabled = set()

    async def run(self, revision):
        if revision not in {"initial", "appended", "breaking"}:
            raise ValueError(f"acceptance revision {revision} is invalid")
        self.revision = revision
        request = {"ticker": self.ticker, "years": MANIFEST["years"], "as_of": MANIFEST["as_of"]}
        return await run_research(request, db_path=self.db_path, dependencies=self._dependencies())

    def _dependencies(self):
        return {
            "repository": repository,
            "clock": lambda: _FIXED_CLOCK,
            "llm_client": self.classification_llm,
            "models": {"adapter_generation": "fixture-adapter-model", "classification": "fixture-classification-model"},
            "resolver": self._resolve,
            "discover_sources": self._discover,
            "fetch_page": self._fetch,
            "build_snapshot": build_structural_snapshot,
            "generate_adapter": self._generate,
            "validate_candidate": validate_candidate,
            "validate_active_adapter": validate_active_adapter,
            "execute_adapter": execute_adapter,
            "classify_observations": domain.classify_observations,
            "normalize_observations": domain.normalize_observations,
            "calculate_statistics": calculate_statistics,
        }

    async def _resolve(self, request, **kwargs):
        return {"ticker": self.ticker, "company_name": self.entry["company_name"], "cik": self.entry["cik"]}

    async def _discover(self, company, **kwargs):
        return await self._discover_with_fixture_providers(company, **kwargs)

    async def provider_fallback_discovery(self):
        connection = repository.connect(self.db_path)
        try:
            job = repository.create_job(
                connection,
                {"ticker": self.ticker, "years": MANIFEST["years"], "as_of": MANIFEST["as_of"]},
                {"ticker": self.ticker, "company_name": self.entry["company_name"], "cik": self.entry["cik"]},
            )
            repository.start_job(connection, job["job_id"], _FIXED_CLOCK.isoformat())
            return await self._discover_with_fixture_providers(
                {"ticker": self.ticker, "company_name": self.entry["company_name"], "cik": self.entry["cik"]},
                job_id=job["job_id"],
                connection=connection,
                source_types={*_INFORMATIONAL_SOURCE_TYPES, *_REQUIRED_CHANNELS},
            )
        finally:
            connection.close()

    async def _discover_with_fixture_providers(self, company, **kwargs):
        tavily = _FixtureSearchProvider(
            "tavily",
            self.entry,
            SearchProviderError("authentication_failed", "fixture tavily key failed", disable_provider=True),
        )
        native = _FixtureSearchProvider(
            "native_search",
            self.entry,
            SearchProviderError("unsupported_tool", "fixture native search capability failed", disable_provider=True),
        )
        ddgs = _FixtureSearchProvider("ddgs", self.entry)
        router = SearchRouter(
            {
                "provider": "auto",
                "fallback": "auto",
                "native_search_supported": "auto",
                "tavily_api_key": None,
            },
            [tavily, native, ddgs],
        )
        result = await domain.discover_sources(
            company,
            router=router,
            llm_client=_FixtureSourceSelectionLLM(),
            model="fixture-source-selection-model",
            repository=repository,
            job_id=kwargs["job_id"],
            connection=kwargs["connection"],
            source_types=kwargs.get("source_types"),
        )
        self.provider_calls = {provider.name: len(provider.calls) for provider in (tavily, native, ddgs)}
        self.provider_disabled = router.disabled()
        return result

    def _page_file(self, url):
        if url == self.entry["fixture_source_urls"]["ir_home"]:
            return self.ticker_dir / "ir_home.html", False
        if url == self.entry["fixture_source_urls"]["earnings_results"]:
            return self.ticker_dir / "earnings_results.html", False
        for channel in _REQUIRED_CHANNELS:
            spec = self.entry["channels"][channel]
            if not spec["url"]:
                continue
            if url == spec["url"]:
                if self.revision == "breaking":
                    name = f"{channel}_breaking.html"
                elif self.revision == "appended" and channel == "press_releases":
                    name = f"{channel}_appended.html"
                else:
                    name = f"{channel}_initial.html"
                return self.ticker_dir / name, False
            if spec["paginated"] and url == f"{spec['url']}?page=2":
                return self.ticker_dir / f"{channel}_initial_page_2.html", bool(spec.get("page_2_truncated"))
        raise AssertionError(f"unexpected fetch url {url}")

    def _fetch(self, url, **kwargs):
        self.fetched_urls.append(url)
        path, truncated = self._page_file(url)
        if not path.exists():
            raise AssertionError(f"missing fixture for {url}")
        html = path.read_text()
        return {
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [url],
            "content_type": "text/html",
            "response_bytes": len(html.encode()),
            "truncated": truncated,
            "html": html,
        }

    def _adapter(self, channel):
        spec = self.entry["channels"][channel]
        if channel == "press_releases":
            extraction = {
                "item_selector": ".news-item",
                "date": {"selector": "time", "value_source": "text", "formats": ["%B %d, %Y"]},
                "title": {"selector": ".news-title", "value_source": "text"},
                "url": {"selector": ".news-title", "value_source": "attribute", "attribute": "href"},
            }
        else:
            extraction = {
                "item_selector": ".event-item",
                "date": {"selector": "[data-date]", "value_source": "attribute", "attribute": "data-date", "formats": ["%Y-%m-%d"]},
                "title": {"selector": ".event-title", "value_source": "text"},
                "url": {"selector": ".event-title", "value_source": "attribute", "attribute": "href"},
            }
        pagination = {"type": "next_link", "selector": "a.next"} if spec["paginated"] else {"type": "none"}
        return {
            "schema_version": "ir_source_adapter_v1",
            "ticker": self.ticker,
            "source_type": channel,
            "source_url": spec["url"],
            "allowed_hosts": [self.entry["host"]],
            "access_mode": "html",
            "extraction": extraction,
            "pagination": pagination,
        }

    async def _generate(self, company, source, snapshot, **kwargs):
        return {"adapter": self._adapter(source["source_type"])}

    def _expected_labels(self):
        observations = list(self.entry["observations"])
        if self.entry["appended_observation"]:
            observations.append(self.entry["appended_observation"])
        return {(obs["source_type"], obs["title"]): obs for obs in observations}


def acceptance_harness(tmp_path: Path, ticker: str):
    return _AcceptanceHarness(tmp_path, ticker)


def _projection(events):
    return sorted(
        (event["source_type"], event["count_date"], event["title"], event["canonical_url"], event["earnings_state"])
        for event in events
    )


def _manifest_projection(observations):
    return sorted((obs["source_type"], obs["date"], obs["title"], obs["url"], obs["earnings_state"]) for obs in observations)


def _job_events(db_path, ticker, job_id):
    connection = repository.connect(db_path)
    try:
        return repository.load_events_page(connection, ticker, job_id, 200, None)["events"]
    finally:
        connection.close()


def _expected_classification_batches(observations):
    unresolved = sum(1 for obs in observations if domain.classify_title_by_rule(obs["title"], obs["source_type"]) is None)
    return (unresolved + 49) // 50


def _cold_call_counts(entry):
    discovered = [channel for channel in _REQUIRED_CHANNELS if entry["channels"][channel]["discovered"]]
    return {
        "discovery": 1,
        "adapter_generation": len(discovered),
        "event_extraction": sum(1 for channel in _REQUIRED_CHANNELS if entry["channels"][channel]["activates"]),
    }


def _hot_call_counts(entry):
    cold_channels = [channel for channel in _REQUIRED_CHANNELS if not entry["channels"][channel]["activates"]]
    rediscovered = [channel for channel in cold_channels if entry["channels"][channel]["discovered"]]
    if not cold_channels:
        return {"discovery": 0, "adapter_generation": 0, "event_extraction": 0}
    return {
        "discovery": 1,
        "adapter_generation": len(rediscovered),
        "event_extraction": 0,
    }


def _channel_span_days(entry, channel):
    dates = [date.fromisoformat(obs["date"]) for obs in entry["observations"] if obs["source_type"] == channel]
    if len(dates) < 2:
        return 0
    return (max(dates) - min(dates)).days


def _manifest_dual_year(entry):
    return all(
        entry["channels"][channel]["activates"]
        and entry["channels"][channel]["complete"]
        and _channel_span_days(entry, channel) >= 365
        for channel in _REQUIRED_CHANNELS
    )


def _result_dual_year(result):
    for channel in _REQUIRED_CHANNELS:
        rows = [source for source in result["sources"] if source["source_type"] == channel and source["extraction_status"] == "complete"]
        if not rows:
            return False
        span = (date.fromisoformat(rows[0]["coverage_end"]) - date.fromisoformat(rows[0]["coverage_start"])).days
        if span < 365:
            return False
    return True


def test_acceptance_manifest_is_self_consistent():
    assert sorted(MANIFEST["tickers"]) == ["AAPL", "AMD", "BA", "JPM", "META", "MSFT", "NVDA", "PFE", "TSLA", "XOM"]
    start = date.fromisoformat(MANIFEST["window"]["start"])
    end = date.fromisoformat(MANIFEST["window"]["end"])
    assert (end - start).days >= 365 * MANIFEST["years"]
    supported = 0
    for ticker, entry in MANIFEST["tickers"].items():
        assert set(entry["channels"]) == set(_REQUIRED_CHANNELS)
        seen_keys = set()
        for obs in entry["observations"]:
            key = (obs["source_type"], obs["date"], obs["title"], obs["url"])
            assert key not in seen_keys
            seen_keys.add(key)
            assert start <= date.fromisoformat(obs["date"]) <= end
            assert obs["source_type"] in _REQUIRED_CHANNELS
            assert domain.url_host(obs["url"]) == entry["host"]
            assert domain.canonicalize_public_url(obs["url"]) == obs["url"]
            rule = domain.classify_title_by_rule(obs["title"], obs["source_type"])
            if obs["earnings_state"] == "earnings":
                assert rule == "earnings", (ticker, obs["title"])
            else:
                assert obs["earnings_state"] in {"non_earnings", "ambiguous"}
                assert rule is None, (ticker, obs["title"])
        for channel, spec in entry["channels"].items():
            channel_observations = [obs for obs in entry["observations"] if obs["source_type"] == channel]
            if spec["activates"]:
                assert spec["discovered"] and spec["complete"] and channel_observations
                assert spec["url"] and domain.url_host(spec["url"]) == entry["host"]
            if not spec["discovered"]:
                assert not channel_observations
        for url in entry["rejected_candidates"]:
            assert domain.url_host(url) != entry["host"]
        assert entry["appended_delta"] == (1 if entry["appended_observation"] else 0)
        if entry["appended_observation"]:
            appended = entry["appended_observation"]
            assert appended["source_type"] == "press_releases"
            assert start <= date.fromisoformat(appended["date"]) <= end
            assert domain.url_host(appended["url"]) == entry["host"]
            assert (appended["source_type"], appended["date"], appended["title"], appended["url"]) not in seen_keys
        assert entry["supports_dual_archive_year"] == _manifest_dual_year(entry)
        supported += int(entry["supports_dual_archive_year"])
    assert supported >= 7


def test_acceptance_manifest_separates_manually_reviewed_official_sources_from_fixture_urls():
    for entry in MANIFEST["tickers"].values():
        official_sources = entry["official_source_urls"]
        fixture_sources = entry["fixture_source_urls"]
        review = entry["official_source_review"]
        assert set(official_sources) == {*_INFORMATIONAL_SOURCE_TYPES, *_REQUIRED_CHANNELS}
        assert set(fixture_sources) == set(official_sources)
        assert review["status"] == "manual_reviewed"
        assert review["reviewed_at"] == "2026-09-07"
        assert review["fixture_url_policy"] == "sanitized_mirror"
        assert review["evidence"] == official_sources
        assert entry["company_name"] in review["company_identity_reason"]
        assert "purpose" in review["source_purpose_reason"].lower()
        for source_type, official_url in official_sources.items():
            assert official_url.startswith("https://")
            assert ".example" not in official_url
            assert domain.url_host(official_url) == review["official_hosts"][source_type]
            assert domain.url_host(fixture_sources[source_type]) == entry["host"]
            if source_type in _REQUIRED_CHANNELS and entry["channels"][source_type]["discovered"]:
                assert official_url != entry["channels"][source_type]["url"]


def test_acceptance_provider_fallback_uses_real_router_and_discovery_contract(tmp_path):
    harness = acceptance_harness(tmp_path, "NVDA")

    result = asyncio.run(harness.provider_fallback_discovery())

    assert {source["source_type"] for source in result["sources"]} == {*_INFORMATIONAL_SOURCE_TYPES, *_REQUIRED_CHANNELS}
    assert {source["discovery_provider"] for source in result["sources"]} == {"ddgs"}
    assert result["warnings"] == MANIFEST["provider_fallback"]["warnings"]
    assert harness.provider_calls == {"tavily": 1, "native_search": 1, "ddgs": 4}
    assert harness.provider_disabled == {"tavily", "native_search"}


@pytest.mark.parametrize("ticker", TICKERS)
def test_acceptance_ticker_lifecycle(tmp_path, ticker):
    harness = acceptance_harness(tmp_path, ticker)
    entry = MANIFEST["tickers"][ticker]
    fully_active = all(entry["channels"][channel]["activates"] for channel in _REQUIRED_CHANNELS)

    cold = asyncio.run(harness.run("initial"))
    assert cold["status"] == entry["expected_status"]
    for channel in _REQUIRED_CHANNELS:
        assert cold["execution_paths"][channel] == "cold"
    cold_counts = _cold_call_counts(entry)
    assert cold["call_counts"]["discovery"] == cold_counts["discovery"]
    assert cold["call_counts"]["adapter_generation"] == cold_counts["adapter_generation"]
    assert cold["call_counts"]["event_extraction"] == cold_counts["event_extraction"]
    assert cold["call_counts"]["classification"] == _expected_classification_batches(entry["observations"])
    for warning in MANIFEST["provider_fallback"]["warnings"]:
        assert warning in cold["warnings"]
    for url in entry["rejected_candidates"]:
        assert url not in harness.fetched_urls
    for channel in _REQUIRED_CHANNELS:
        spec = entry["channels"][channel]
        rows = [source for source in cold["sources"] if source["source_type"] == channel]
        if not spec["discovered"]:
            assert rows == []
            continue
        assert len(rows) == 1
        row = rows[0]
        assert row["url"] == spec["url"]
        assert row["execution_path"] == "cold"
        assert row["acceptance_status"] == "accepted"
        assert domain.url_host(row["url"]) == entry["host"]
        if spec["activates"]:
            assert row["extraction_status"] == "complete"
            assert row["active_adapter_id"]
            assert row["discovery_provider"] == MANIFEST["provider_fallback"]["succeeding_provider"]
            channel_dates = [obs["date"] for obs in entry["observations"] if obs["source_type"] == channel]
            assert row["coverage_start"] == min(channel_dates)
            assert row["coverage_end"] == max(channel_dates)
            assert row["coverage_continuous"] is True
        else:
            assert row["extraction_status"] == "failed"
            assert row["active_adapter_id"] is None
    cold_events = _job_events(harness.db_path, ticker, cold["job_id"])
    assert _projection(cold_events) == _manifest_projection(entry["observations"])
    expected_ambiguous = [obs for obs in entry["observations"] if obs["earnings_state"] == "ambiguous"]
    assert [event["title"] for event in cold_events if event["earnings_state"] == "ambiguous"] == [obs["title"] for obs in expected_ambiguous]
    assert all(event["classification_method"] == "llm_v1" for event in cold_events if event["earnings_state"] == "ambiguous")
    connection = repository.connect(harness.db_path)
    try:
        for source_type in _INFORMATIONAL_SOURCE_TYPES:
            informational = connection.execute(
                "select url, acceptance_status, extraction_status from catalyst_ir_sources where job_id = ? and source_type = ?",
                (cold["job_id"], source_type),
            ).fetchall()
            assert len(informational) == 1
            assert tuple(informational[0]) == (entry["fixture_source_urls"][source_type], "accepted", "pending")
        adapter_states = {row[0]: row[1] for row in connection.execute("select source_type, state from catalyst_source_adapters where ticker = ?", (ticker,))}
        assert "earnings_results" not in adapter_states
        for channel in _REQUIRED_CHANNELS:
            spec = entry["channels"][channel]
            if spec["activates"]:
                assert adapter_states.get(channel) == "active"
            elif spec["discovered"]:
                assert adapter_states.get(channel) == "failed_validation"
            else:
                assert channel not in adapter_states
    finally:
        connection.close()

    hot = asyncio.run(harness.run("initial"))
    assert hot["status"] == entry["expected_status"]
    assert hot["observation_count"] == cold["observation_count"]
    assert _projection(_job_events(harness.db_path, ticker, hot["job_id"])) == _manifest_projection(entry["observations"])
    for channel in _REQUIRED_CHANNELS:
        expected_path = "hot" if entry["channels"][channel]["activates"] else "cold"
        assert hot["execution_paths"][channel] == expected_path
    hot_counts = _hot_call_counts(entry)
    assert hot["call_counts"]["discovery"] == hot_counts["discovery"]
    assert hot["call_counts"]["adapter_generation"] == hot_counts["adapter_generation"]
    assert hot["call_counts"]["event_extraction"] == hot_counts["event_extraction"]
    hot_again = asyncio.run(harness.run("initial"))
    assert hot_again["observation_count"] == hot["observation_count"]
    assert _projection(_job_events(harness.db_path, ticker, hot_again["job_id"])) == _projection(_job_events(harness.db_path, ticker, hot["job_id"]))
    assert hot_again["call_counts"] == hot["call_counts"]

    appended = asyncio.run(harness.run("appended"))
    assert appended["status"] == entry["expected_status"]
    assert appended["observation_count"] == cold["observation_count"] + entry["appended_delta"]
    expected_after_append = list(entry["observations"])
    if entry["appended_observation"]:
        expected_after_append.append(entry["appended_observation"])
    assert _projection(_job_events(harness.db_path, ticker, appended["job_id"])) == _manifest_projection(expected_after_append)
    appended_counts = _hot_call_counts(entry)
    assert appended["call_counts"]["discovery"] == appended_counts["discovery"]
    assert appended["call_counts"]["adapter_generation"] == appended_counts["adapter_generation"]
    assert appended["call_counts"]["event_extraction"] == appended_counts["event_extraction"]
    if fully_active:
        assert all(source["execution_path"] == "hot" for source in appended["sources"] if source.get("active_adapter_id"))

    breaking = asyncio.run(harness.run("breaking"))
    assert breaking["status"] == "completed_partial"
    assert breaking["observation_count"] == 0
    assert "source_discovery_required" in breaking["warnings"]
    connection = repository.connect(harness.db_path)
    try:
        assert connection.execute("select count(*) from catalyst_ir_events where job_id = ?", (breaking["job_id"],)).fetchone()[0] == 0
        adapter_rows = connection.execute("select source_type, state from catalyst_source_adapters where ticker = ?", (ticker,)).fetchall()
        for channel in _REQUIRED_CHANNELS:
            spec = entry["channels"][channel]
            channel_states = [row[1] for row in adapter_rows if row[0] == channel]
            if spec["activates"]:
                assert "stale" in channel_states
                assert repository.load_active_adapter(connection, ticker, channel) is None
                source_statuses = [row[0] for row in connection.execute("select extraction_status from catalyst_ir_sources where job_id = ? and source_type = ?", (breaking["job_id"], channel))]
                assert "discovery_required" in source_statuses
                assert "failed" in source_statuses
        latest = repository.load_latest_result(connection, ticker)
        if entry["expected_status"] == "completed":
            assert latest["job_id"] == appended["job_id"]
            assert latest["observation_count"] == cold["observation_count"] + entry["appended_delta"]
        else:
            prior = repository.load_job_result(connection, cold["job_id"])
            assert prior["status"] == entry["expected_status"]
            assert prior["observation_count"] == cold["observation_count"]
        assert latest["latest_job_id"] == breaking["job_id"]
        assert latest["latest_job_status"] == "completed_partial"
    finally:
        connection.close()


def test_acceptance_portfolio_coverage_fallbacks_and_labels(tmp_path):
    total = 0
    matched = 0
    ambiguous_total = 0
    dual_year = []
    for ticker in TICKERS:
        entry = MANIFEST["tickers"][ticker]
        harness = acceptance_harness(tmp_path / ticker.lower(), ticker)
        cold = asyncio.run(harness.run("initial"))
        assert cold["status"] == entry["expected_status"]
        for warning in MANIFEST["provider_fallback"]["warnings"]:
            assert warning in cold["warnings"]
        assert harness.classification_llm.responses.calls == cold["call_counts"]["classification"]
        assert all(domain.url_host(source["url"]) == entry["host"] for source in cold["sources"])
        for url in entry["rejected_candidates"]:
            assert url not in harness.fetched_urls
        events = _job_events(harness.db_path, ticker, cold["job_id"])
        expected = {(obs["source_type"], obs["title"]): obs["earnings_state"] for obs in entry["observations"]}
        for event in events:
            total += 1
            matched += int(expected.get((event["source_type"], event["title"])) == event["earnings_state"])
            ambiguous_total += int(event["earnings_state"] == "ambiguous")
        if _result_dual_year(cold):
            dual_year.append(ticker)
    assert total == sum(len(entry["observations"]) for entry in MANIFEST["tickers"].values())
    assert dual_year == sorted(ticker for ticker, entry in MANIFEST["tickers"].items() if entry["supports_dual_archive_year"])
    assert len(dual_year) >= 7
    assert ambiguous_total >= 1
    assert ambiguous_total == sum(
        observation["earnings_state"] == "ambiguous"
        for entry in MANIFEST["tickers"].values()
        for observation in entry["observations"]
    )
    assert matched / total >= 0.95


V1_1_FIXTURES = FIXTURES / "v1_1"
V1_1_MANIFEST = json.loads((V1_1_FIXTURES / "acceptance_manifest.json").read_text())
V1_1_TICKERS = sorted(V1_1_MANIFEST["tickers"])
_V1_1_CHANNELS = ("press_releases", "events_presentations", "earnings_results")
_V1_1_DISCOVERY_PHRASES = {
    "press_releases": "press releases news feed",
    "events_presentations": "events presentations webcast",
    "earnings_results": "quarterly earnings financial results",
}
_V1_1_HISTORICAL_PHRASES = {
    "press_releases": " press release ",
    "events_presentations": " events presentations ",
    "earnings_results": "quarterly earnings financial results",
}
_V1_1_LISTING_PATHS = {
    "press_releases": "news",
    "events_presentations": "events",
    "earnings_results": "investor-relations",
}
_V1_1_CLOCK = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
_V1_1_UPDATE_CLOCK = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
_V1_1_RESOLVER_ADDRESSES = ["93.184.216.34"]
_V1_1_COLLECTION_CONFIG = {
    "historical_slice_days": 92,
    "max_historical_queries_per_channel": 8,
    "search_result_limit": 10,
    "max_unseen_urls_per_channel": 50,
    "gap_lookback_days": 14,
    "max_gap_queries_per_channel": 2,
    "gap_search_interval_days": 7,
    "feed_failure_threshold": 3,
    "firecrawl_api_key": None,
    "firecrawl_base_url": None,
    "archive_enrichment_enabled": False,
}
_AGENT_PACKAGE = Path(__file__).resolve().parents[3] / "app" / "agents" / "catalyst_research"


def _v1_1_observations(ticker, channel=None):
    entry = V1_1_MANIFEST["tickers"][ticker]
    channels = [channel] if channel else _V1_1_CHANNELS
    rows = []
    for name in channels:
        rows.extend(dict(obs, channel=name) for obs in entry["channels"][name]["observations"])
    return rows


def _v1_1_expected_events(ticker):
    return [obs for obs in _v1_1_observations(ticker) if obs["origin"] == "feed" or obs["direct"] == "ok"]


class _V11FixtureSearchProvider:
    def __init__(self, ticker):
        self.name = "ddgs"
        self.entry = V1_1_MANIFEST["tickers"][ticker]
        self.ready = True
        self.last_request_id = None
        self.calls = []

    async def search(self, query, *, limit):
        self.calls.append(query)
        if " official investor relations " in query:
            return self._discovery_rows(query)
        return self._historical_rows(query)

    def _channel_for(self, query):
        for channel, phrase in _V1_1_DISCOVERY_PHRASES.items():
            if phrase in query:
                return channel
        for channel, phrase in _V1_1_HISTORICAL_PHRASES.items():
            if phrase in query:
                return channel
        raise AssertionError(f"fixture search query is not recognized: {query}")

    def _discovery_rows(self, query):
        channel = self._channel_for(query)
        company = self.entry["company_name"]
        spec = self.entry["channels"][channel]
        rows = []
        feed = spec.get("feed")
        if feed:
            rows.append(
                {
                    "title": f"{company} {channel.replace('_', ' ').title()} Feed",
                    "url": feed["url"],
                    "snippet": f"{company} official investor relations {_V1_1_DISCOVERY_PHRASES[channel]}",
                    "provider_rank": 1,
                    "provider_metadata": {},
                }
            )
        rows.append(
            {
                "title": f"{company} Official Investor Relations {_V1_1_LISTING_PATHS[channel].replace('-', ' ').title()}",
                "url": f"https://{spec['search_domain']}/{_V1_1_LISTING_PATHS[channel]}",
                "snippet": f"{company} official {_V1_1_DISCOVERY_PHRASES[channel]} on {spec['search_domain']}",
                "provider_rank": 2,
                "provider_metadata": {},
            }
        )
        return rows

    def _historical_rows(self, query):
        channel = self._channel_for(query)
        domain = query.split("site:", 1)[1].split()[0].strip()
        spec = self.entry["channels"][channel]
        if domain != spec["search_domain"]:
            return []
        company = self.entry["company_name"]
        return [
            {
                "title": obs["title"],
                "url": obs["url"],
                "snippet": f"{company} official investor relations record",
                "provider_rank": index,
                "provider_metadata": {},
            }
            for index, obs in enumerate(spec["observations"], 1)
            if obs["origin"] == "search"
        ]


class _V11RegistryResponses:
    def __init__(self, llm):
        self.llm = llm

    async def parse(self, *, model, input, text_format, **kwargs):
        assert text_format is RegistrySelectionResponse
        self.llm.registry_selection_calls += 1
        user_text = input[1]["content"]
        candidates = json.loads(user_text.split("Search candidates:\n", 1)[1])
        query = candidates[0]["query"]
        for channel, phrase in _V1_1_DISCOVERY_PHRASES.items():
            if phrase in query:
                break
        else:
            raise AssertionError(f"registry selection prompt has an unrecognized query: {query}")
        spec = self.llm.entry["channels"][channel]
        ids_by_url = {row["url"]: row["result_id"] for row in candidates}
        endpoints = []
        feed = spec.get("feed")
        if feed:
            endpoints.append(
                {
                    "channel": channel,
                    "endpoint_type": feed["endpoint_type"],
                    "url": feed["url"],
                    "domain": domain.url_host(feed["url"]),
                    "evidence_result_ids": [ids_by_url[feed["url"]]],
                    "confidence": "high",
                    "reason": "fixture evidence identifies the official feed endpoint",
                }
            )
        listing_url = f"https://{spec['search_domain']}/{_V1_1_LISTING_PATHS[channel]}"
        endpoints.append(
            {
                "channel": channel,
                "endpoint_type": "search_domain",
                "url": None,
                "domain": spec["search_domain"],
                "evidence_result_ids": [ids_by_url[listing_url]],
                "confidence": "medium",
                "reason": "fixture evidence identifies the official search domain",
            }
        )
        parsed = RegistrySelectionResponse.model_validate({"endpoints": endpoints})
        return type("Response", (), {"output_parsed": parsed})()


class _V11ClassificationResponses:
    def __init__(self, llm):
        self.llm = llm

    async def parse(self, *, model, input, text_format, **kwargs):
        assert text_format is EventClassificationResponse
        self.llm.classification_calls += 1
        events = json.loads(input[1]["content"].split("Events to classify:\n", 1)[1])
        expected = {(obs["channel"], obs["title"]): obs["earnings_state"] for obs in _v1_1_observations(self.llm.ticker)}
        classifications = [
            {
                "id": event["id"],
                "earnings_state": expected[(event["source_type"], event["title"])],
                "reason": "fixture manually labeled title",
            }
            for event in events
        ]
        parsed = EventClassificationResponse.model_validate({"classifications": classifications})
        return type("Response", (), {"output_parsed": parsed})()


class _V11FixtureLLM:
    def __init__(self, ticker):
        self.ticker = ticker
        self.entry = V1_1_MANIFEST["tickers"][ticker]
        self.registry_selection_calls = 0
        self.classification_calls = 0
        self.responses = type(
            "Responses",
            (),
            {
                "parse": lambda _self, **kwargs: _V11RegistryResponses(self).parse(**kwargs)
                if kwargs.get("text_format") is RegistrySelectionResponse
                else _V11ClassificationResponses(self).parse(**kwargs)
            },
        )()


class _FixturePaymentRequiredError(Exception):
    status_code = 402


class _FakeFirecrawlClient:
    def __init__(self, markdown_by_url=None, error=None):
        self.markdown_by_url = markdown_by_url or {}
        self.error = error
        self.scrape_calls = []

    def scrape(self, url, formats=None):
        self.scrape_calls.append(url)
        if self.error is not None:
            raise self.error
        markdown = self.markdown_by_url[url]
        title = next(line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("# "))
        return {
            "markdown": markdown,
            "metadata": {
                "title": title,
                "url": url,
                "publishedDate": "2026-08-19T12:00:00.000Z",
                "requestId": "fc-fixture-request-1",
            },
        }


class _V11AcceptanceHarness:
    def __init__(self, tmp_path, ticker, *, firecrawl_markdown=None, firecrawl_error=None, archive_enrichment=False, extra_pages=None):
        if ticker not in V1_1_MANIFEST["tickers"]:
            raise ValueError(f"acceptance ticker {ticker} is not in the v1_1 manifest")
        self.ticker = ticker
        self.entry = V1_1_MANIFEST["tickers"][ticker]
        self.db_path = Path(tmp_path) / f"{ticker.lower()}_v1_1.sqlite"
        self.clock = _V1_1_CLOCK
        self.llm = _V11FixtureLLM(ticker)
        self.provider = _V11FixtureSearchProvider(ticker)
        self.firecrawl_client = None
        if firecrawl_markdown is not None or firecrawl_error is not None:
            self.firecrawl_client = _FakeFirecrawlClient(firecrawl_markdown, firecrawl_error)
        self.collection_config = {**_V1_1_COLLECTION_CONFIG, "archive_enrichment_enabled": archive_enrichment}
        self.extra_pages = dict(extra_pages or {})
        self.extraction_router = self._build_extraction_router()
        self.http_client = HttpClient(transport=httpx.MockTransport(self._handle_request), sleep=lambda _: None)

    def run(self, mode):
        request = {"ticker": self.ticker, "years": V1_1_MANIFEST["years"], "as_of": V1_1_MANIFEST["as_of"], "mode": mode}
        return asyncio.run(
            run_research(request, db_path=self.db_path, http_client=self.http_client, dependencies=self._dependencies())
        )

    def _dependencies(self):
        return {
            "repository": repository,
            "clock": lambda: self.clock,
            "llm_client": self.llm,
            "models": {"registry_selection": "fixture-registry-model", "classification": "fixture-classification-model"},
            "resolver": self._resolve_company,
            "discover_registry": registry_discovery.discover_registry,
            "run_historical_backfill": backfill.run_historical_backfill,
            "run_daily_update": scheduler.run_daily_update,
            "classify_observations": domain.classify_observations,
            "calculate_statistics": v1_1_statistics.calculate_statistics,
            "search_router": SearchRouter(
                {"provider": "auto", "fallback": "auto", "native_search_supported": "auto", "tavily_api_key": None},
                [self.provider],
            ),
            "http_client": self.http_client,
            "fetch_feed": self._fetch_feed,
            "url_resolver": self._resolve_host,
            "collection_config": self.collection_config,
            "extraction_router": self.extraction_router,
            "progress": lambda stage, **details: None,
        }

    def _resolve_company(self, request, **kwargs):
        return {"ticker": self.ticker, "company_name": self.entry["company_name"], "cik": self.entry["cik"]}

    def _resolve_host(self, host):
        return list(_V1_1_RESOLVER_ADDRESSES)

    def _build_extraction_router(self):
        def direct_extractor(url, **kwargs):
            kwargs.setdefault("resolver", self._resolve_host)
            return extract_direct_article(url, http_client=self.http_client, **kwargs)

        firecrawl_provider = None
        if self.firecrawl_client is not None:
            firecrawl_provider = FirecrawlExtractProvider(api_key="fixture-firecrawl-key", client=self.firecrawl_client)
        return ExtractionRouter(direct_extractor, firecrawl_provider=firecrawl_provider)

    async def _fetch_feed(self, endpoint, *, http_client, approved_domains, **kwargs):
        return fetch_feed(
            endpoint,
            http_client=http_client,
            approved_domains=approved_domains,
            resolver=self._resolve_host,
        )

    def _handle_request(self, request):
        url = str(request.url)
        for page_url, fixture_name in self.extra_pages.items():
            if url == page_url:
                return httpx.Response(200, headers={"Content-Type": "text/html"}, content=(V1_1_FIXTURES / fixture_name).read_bytes())
        for channel in _V1_1_CHANNELS:
            feed = self.entry["channels"][channel].get("feed")
            if feed and url == feed["url"]:
                return httpx.Response(
                    200,
                    headers={"Content-Type": "application/rss+xml"},
                    content=(V1_1_FIXTURES / feed["fixture"]).read_bytes(),
                )
        for obs in _v1_1_observations(self.ticker):
            if url == obs["url"] and obs.get("direct") == "blocked":
                return httpx.Response(403, content=b"fixture blocked direct extraction")
        for obs in _v1_1_observations(self.ticker):
            if url == obs["url"] and obs.get("article_fixture"):
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    content=(V1_1_FIXTURES / obs["article_fixture"]).read_bytes(),
                )
        return httpx.Response(404, content=f"missing fixture for {url}".encode())


def v1_1_harness(tmp_path: Path, ticker: str, **overrides):
    return _V11AcceptanceHarness(tmp_path, ticker, **overrides)


def _v1_1_events(db_path, job_id):
    connection = repository.connect(db_path)
    try:
        rows = connection.execute(
            "select source_type, count_date, title, canonical_url, earnings_state, classification_method, discovery_method, extraction_provider from catalyst_ir_events where job_id = ? order by source_type, count_date, title",
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _v1_1_projection(events):
    return sorted((event["source_type"], event["count_date"], event["title"], event["canonical_url"], event["earnings_state"]) for event in events)


def _v1_1_manifest_projection(observations):
    return sorted((obs["channel"], obs["date"], obs["title"], obs["url"], obs["earnings_state"]) for obs in observations)


def _registry_ready(db_path, ticker):
    connection = repository.connect(db_path)
    try:
        saved = repository.load_company_registry(connection, ticker)
        endpoints = repository.load_source_endpoints(connection, ticker)
        return saved is not None and registry.registry_ready(saved, endpoints)
    finally:
        connection.close()


def _adapter_row_count(db_path, ticker):
    connection = repository.connect(db_path)
    try:
        return connection.execute("select count(*) from catalyst_source_adapters where ticker = ?", (ticker,)).fetchone()[0]
    finally:
        connection.close()


def test_acceptance_v1_1_manifest_is_self_consistent():
    assert V1_1_MANIFEST["schema"] == "catalyst_acceptance_manifest_v1_1"
    assert V1_1_MANIFEST["fixture_url_policy"] == "sanitized_mirror"
    assert sorted(V1_1_MANIFEST["tickers"]) == ["AAPL", "AMD", "BA", "JPM", "META", "MSFT", "NVDA", "PFE", "TSLA", "XOM"]
    start = date.fromisoformat(V1_1_MANIFEST["as_of"]).replace(year=date.fromisoformat(V1_1_MANIFEST["as_of"]).year - V1_1_MANIFEST["years"])
    end = date.fromisoformat(V1_1_MANIFEST["as_of"])
    strong_feeds = 0
    for ticker, entry in V1_1_MANIFEST["tickers"].items():
        assert set(entry["channels"]) == set(_V1_1_CHANNELS)
        approved = entry["official_domains"]
        for channel, spec in entry["channels"].items():
            seen_titles = set()
            feed = spec.get("feed")
            if feed:
                assert (V1_1_FIXTURES / feed["fixture"]).exists()
                assert domain.url_host(feed["url"]) in approved
                strong_feeds += int(not feed.get("broken"))
            for obs in spec["observations"]:
                assert obs["title"] not in seen_titles
                seen_titles.add(obs["title"])
                assert start <= date.fromisoformat(obs["date"]) <= end
                assert obs["origin"] in {"feed", "search"}
                assert domain.canonicalize_public_url(obs["url"]) == obs["url"]
                host = domain.url_host(obs["url"])
                assert any(host == approved_domain or host.endswith(f".{approved_domain}") for approved_domain in approved)
                if channel == "earnings_results":
                    assert obs["earnings_state"] == "earnings", (ticker, channel, obs["title"])
                else:
                    rule = domain.classify_title_by_rule(obs["title"], channel)
                    if obs["rule"]:
                        assert rule == obs["earnings_state"], (ticker, channel, obs["title"])
                    else:
                        assert rule is None, (ticker, channel, obs["title"])
                        assert obs["earnings_state"] in {"non_earnings", "ambiguous"}
                if obs["origin"] == "feed":
                    assert feed and not feed.get("broken")
                if obs.get("direct") == "blocked":
                    assert obs["origin"] == "search"
                    assert not obs.get("article_fixture")
                elif obs["origin"] == "search":
                    assert obs.get("article_fixture") and (V1_1_FIXTURES / obs["article_fixture"]).exists()
                if obs.get("firecrawl_fixture"):
                    assert (V1_1_FIXTURES / obs["firecrawl_fixture"]).exists()
    assert strong_feeds >= 7


def test_acceptance_v1_1_trusted_source_registries(tmp_path):
    trusted = {}
    for ticker in V1_1_TICKERS:
        harness = v1_1_harness(tmp_path / ticker.lower(), ticker)
        result = harness.run("research")
        assert result["status"] == "completed_partial"
        trusted[ticker] = _registry_ready(harness.db_path, ticker)
    assert sum(trusted.values()) >= 7
    assert {ticker for ticker, ready in trusted.items() if ready} >= {"NVDA", "AAPL", "MSFT", "AMD", "TSLA", "META", "JPM", "BA"}


def test_acceptance_v1_1_working_feed_or_search_channel_and_manifest_projection(tmp_path):
    working = 0
    for ticker in V1_1_TICKERS:
        harness = v1_1_harness(tmp_path / ticker.lower(), ticker)
        result = harness.run("research")
        events = _v1_1_events(harness.db_path, result["job_id"])
        expected = _v1_1_expected_events(ticker)
        assert _v1_1_projection(events) == _v1_1_manifest_projection(expected)
        channels_with_events = {event["source_type"] for event in events}
        assert channels_with_events
        working += int(bool(channels_with_events))
    assert working == 10


def test_acceptance_v1_1_nvda_press_releases_from_feed_and_search_without_adapters(tmp_path):
    harness = v1_1_harness(tmp_path, "NVDA")
    result = harness.run("research")
    assert result["call_counts"]["discovery"] == 1
    assert result["call_counts"]["adapter_generation"] == 0
    events = _v1_1_events(harness.db_path, result["job_id"])
    press = [event for event in events if event["source_type"] == "press_releases"]
    assert len(press) == 3
    assert {event["discovery_method"] for event in press} == {"rss"}
    assert {event["extraction_provider"] for event in press} == {"feed_metadata"}
    assert all(event["classification_method"] == "llm_v1" for event in press)
    assert _adapter_row_count(harness.db_path, "NVDA") == 0
    connection = repository.connect(harness.db_path)
    try:
        adapters = connection.execute("select count(*) from catalyst_source_adapters where ticker = 'NVDA'").fetchone()[0]
        assert adapters == 0
        feed_endpoints = connection.execute(
            "select count(*) from catalyst_source_endpoints where ticker = 'NVDA' and endpoint_type in ('rss','atom') and status = 'active'"
        ).fetchone()[0]
        assert feed_endpoints == 2
    finally:
        connection.close()


def test_acceptance_v1_1_second_nvda_update_makes_zero_model_calls(tmp_path):
    harness = v1_1_harness(tmp_path, "NVDA")
    research = harness.run("research")
    assert research["call_counts"]["discovery"] == 1
    harness.clock = _V1_1_UPDATE_CLOCK
    first_update = harness.run("update")
    assert first_update["call_counts"]["discovery"] == 0
    connection = repository.connect(harness.db_path)
    try:
        gap_attempts = connection.execute(
            "select count(*) from catalyst_search_attempts where job_id = ? and search_purpose = 'incremental_gap_check'",
            (first_update["job_id"],),
        ).fetchone()[0]
        assert gap_attempts > 0
    finally:
        connection.close()
    llm_calls_before = (harness.llm.registry_selection_calls, harness.llm.classification_calls)
    second_update = harness.run("update")
    assert second_update["call_counts"]["discovery"] == 0
    assert second_update["call_counts"]["adapter_generation"] == 0
    assert second_update["call_counts"]["classification"] == 0
    assert (harness.llm.registry_selection_calls, harness.llm.classification_calls) == llm_calls_before
    assert _adapter_row_count(harness.db_path, "NVDA") == 0


def test_acceptance_v1_1_direct_failure_firecrawl_success_stores_one_event(tmp_path):
    blocked = [obs for obs in _v1_1_observations("NVDA") if obs.get("direct") == "blocked"]
    assert len(blocked) == 1
    markdown = {obs["url"]: (V1_1_FIXTURES / obs["firecrawl_fixture"]).read_text() for obs in blocked}
    harness = v1_1_harness(tmp_path, "NVDA", firecrawl_markdown=markdown)
    result = harness.run("research")
    events = _v1_1_events(harness.db_path, result["job_id"])
    firecrawl_events = [event for event in events if event["extraction_provider"] == "firecrawl"]
    assert len(firecrawl_events) == 1
    assert firecrawl_events[0]["source_type"] == "earnings_results"
    assert firecrawl_events[0]["count_date"] == blocked[0]["date"]
    assert firecrawl_events[0]["title"] == blocked[0]["title"]
    assert harness.firecrawl_client.scrape_calls == [blocked[0]["url"]]
    connection = repository.connect(harness.db_path)
    try:
        sources = connection.execute(
            "select extraction_status, extraction_provider from catalyst_ir_sources where job_id = ? and source_type = 'earnings_results'",
            (result["job_id"],),
        ).fetchall()
        assert len(sources) == 1
        assert tuple(sources[0]) == ("complete", "firecrawl")
    finally:
        connection.close()


def test_acceptance_v1_1_payment_required_disables_firecrawl_for_remaining_urls(tmp_path):
    blocked = [obs for obs in _v1_1_observations("XOM", "earnings_results") if obs.get("direct") == "blocked"]
    assert len(blocked) == 2
    harness = v1_1_harness(tmp_path, "XOM", firecrawl_error=_FixturePaymentRequiredError())
    result = harness.run("research")
    assert len(harness.firecrawl_client.scrape_calls) == 1
    assert harness.firecrawl_client.scrape_calls[0] in {obs["url"] for obs in blocked}
    assert harness.extraction_router.firecrawl_disabled_reason == "payment_required"
    events = _v1_1_events(harness.db_path, result["job_id"])
    assert [event for event in events if event["extraction_provider"] == "firecrawl"] == []
    connection = repository.connect(harness.db_path)
    try:
        rows = connection.execute(
            "select url, acceptance_status, extraction_status, verification_reason from catalyst_ir_sources where job_id = ? and source_type = 'earnings_results' order by url",
            (result["job_id"],),
        ).fetchall()
        assert [row[0] for row in rows] == sorted(obs["url"] for obs in blocked)
        assert all(row[1:] == ("ambiguous", "failed", "manual_review_required") for row in rows)
    finally:
        connection.close()


def test_acceptance_v1_1_feed_and_search_only_history_is_observed_partial(tmp_path):
    for ticker in V1_1_TICKERS:
        harness = v1_1_harness(tmp_path / ticker.lower(), ticker)
        result = harness.run("research")
        assert result["status"] == "completed_partial"
        for channel, stats in result["statistics"].items():
            assert stats["coverage_status"] in {"observed_partial", "missing", "unsupported"}
            if stats["observed_total"] > 0:
                assert stats["coverage_status"] == "observed_partial"
                assert stats["coverage_warning"]
                assert stats["observed_start"] and stats["observed_end"]
            elif stats["coverage_status"] == "unsupported":
                assert "coverage_warning" not in stats
            else:
                assert stats["coverage_status"] == "missing"
                assert stats["coverage_warning"]


def test_acceptance_v1_1_existing_v1_adapter_still_enriches_when_enabled(tmp_path):
    db_path = Path(tmp_path) / "nvda_enrichment.sqlite"
    connection = repository.connect(db_path)
    try:
        repository.save_company_registry(
            connection,
            {
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "cik": "1045810",
                "official_domains": V1_1_MANIFEST["tickers"]["NVDA"]["official_domains"],
                "source_confidence": "high",
                "registry_version": 1,
            },
        )
        for channel in ("press_releases", "events_presentations"):
            feed = V1_1_MANIFEST["tickers"]["NVDA"]["channels"][channel]["feed"]
            repository.upsert_source_endpoint(
                connection,
                {
                    "ticker": "NVDA",
                    "channel": channel,
                    "endpoint_type": feed["endpoint_type"],
                    "url": feed["url"],
                    "domain": domain.url_host(feed["url"]),
                    "status": "active",
                    "confidence": "high",
                },
            )
        seed_job = repository.create_job(connection, {"ticker": "NVDA", "years": 1}, {"company_name": "NVIDIA Corporation", "cik": "1045810"}, _V1_1_CLOCK)
        repository.start_job(connection, seed_job["job_id"], _V1_1_CLOCK.isoformat())
        adapter = {
            "schema_version": "ir_source_adapter_v1",
            "ticker": "NVDA",
            "source_type": "press_releases",
            "source_url": "https://nvidianews.nvidia.com/news",
            "allowed_hosts": ["nvidianews.nvidia.com"],
            "access_mode": "html",
            "extraction": {
                "item_selector": ".news-item",
                "date": {"selector": "time", "value_source": "text", "formats": ["%B %d, %Y"]},
                "title": {"selector": ".news-title", "value_source": "text"},
                "url": {"selector": ".news-title", "value_source": "attribute", "attribute": "href"},
            },
            "pagination": {"type": "none"},
        }
        candidate = repository.create_adapter_candidate(
            connection,
            {"job_id": seed_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": adapter["source_url"], "adapter": adapter},
        )
        repository.record_adapter_validation(connection, {"adapter_id": candidate["adapter_id"], "job_id": seed_job["job_id"], "status": "passed", "report": {}})
        repository.activate_adapter(connection, candidate["adapter_id"], _V1_1_CLOCK.isoformat())
    finally:
        connection.close()

    harness = v1_1_harness(
        tmp_path,
        "NVDA",
        archive_enrichment=True,
        extra_pages={"https://nvidianews.nvidia.com/news": "nvda-archive.html"},
    )
    harness.db_path = db_path
    result = harness.run("research")
    events = _v1_1_events(harness.db_path, result["job_id"])
    enriched = [event for event in events if event["discovery_method"] == "archive_adapter"]
    assert len(enriched) == 1
    assert enriched[0]["title"] == "NVIDIA Archived Release"
    assert enriched[0]["count_date"] == "2026-07-15"
    press = [event for event in events if event["source_type"] == "press_releases"]
    assert {event["discovery_method"] for event in press} == {"rss", "archive_adapter"}
    assert result["statistics"]["press_releases"]["coverage_status"] == "observed_partial"
    connection = repository.connect(harness.db_path)
    try:
        states = [row[0] for row in connection.execute("select state from catalyst_source_adapters where ticker = 'NVDA'").fetchall()]
        assert states == ["active"]
    finally:
        connection.close()


def test_acceptance_v1_1_no_browser_or_generic_crawl_dependency():
    forbidden_tokens = ("playwright", "selenium", "pyppeteer", "captcha", "cloudflare", "stealth", "undetected")
    for path in sorted(_AGENT_PACKAGE.rglob("*.py")):
        text = path.read_text().casefold()
        for token in forbidden_tokens:
            assert token not in text, (path, token)
    firecrawl_source = (_AGENT_PACKAGE / "providers" / "firecrawl.py").read_text()
    for api_call in (".search(", ".crawl(", ".map(", ".interact(", ".browser(", ".agent("):
        assert api_call not in firecrawl_source
    feeds_source = (_AGENT_PACKAGE / "extraction" / "feeds.py").read_text()
    assert "browser=False" in feeds_source
    workflow_source = (_AGENT_PACKAGE / "workflow.py").read_text()
    assert "Browser(" not in workflow_source
