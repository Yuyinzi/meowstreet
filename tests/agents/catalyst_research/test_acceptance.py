import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.agents.catalyst_research import domain
from app.agents.catalyst_research.adapters.executor import execute_adapter
from app.agents.catalyst_research.adapters.validator import validate_active_adapter, validate_candidate
from app.agents.catalyst_research.extraction.html import build_structural_snapshot
from app.agents.catalyst_research.persistence import repository
from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.schemas import EventClassificationResponse
from app.agents.catalyst_research.statistics import calculate_statistics
from app.agents.catalyst_research.workflow import run_research


FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "acceptance_manifest.json").read_text())
TICKERS = sorted(MANIFEST["tickers"])
_REQUIRED_CHANNELS = ("press_releases", "events_presentations")
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
                source_types={"ir_home", *_REQUIRED_CHANNELS},
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
    origin_rediscovery = any(not entry["channels"][channel]["discovered"] for channel in _REQUIRED_CHANNELS)
    return {
        "discovery": 2 if origin_rediscovery else 1,
        "adapter_generation": len(discovered),
        "event_extraction": sum(1 for channel in _REQUIRED_CHANNELS if entry["channels"][channel]["activates"]),
    }


def _hot_call_counts(entry):
    cold_channels = [channel for channel in _REQUIRED_CHANNELS if not entry["channels"][channel]["activates"]]
    rediscovered = [channel for channel in cold_channels if entry["channels"][channel]["discovered"]]
    if not cold_channels:
        return {"discovery": 0, "adapter_generation": 0, "event_extraction": 0}
    origin_rediscovery = any(not entry["channels"][channel]["discovered"] for channel in cold_channels)
    return {
        "discovery": 2 if origin_rediscovery else 1,
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
        assert set(official_sources) == {"ir_home", *_REQUIRED_CHANNELS}
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

    assert {source["source_type"] for source in result["sources"]} == {"ir_home", *_REQUIRED_CHANNELS}
    assert {source["discovery_provider"] for source in result["sources"]} == {"ddgs"}
    assert result["warnings"] == MANIFEST["provider_fallback"]["warnings"]
    assert harness.provider_calls == {"tavily": 1, "native_search": 1, "ddgs": 3}
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
        ir_home = connection.execute(
            "select url, acceptance_status, extraction_status from catalyst_ir_sources where job_id = ? and source_type = 'ir_home'",
            (cold["job_id"],),
        ).fetchone()
        assert ir_home is not None
        assert tuple(ir_home) == (entry["fixture_source_urls"]["ir_home"], "accepted", "pending")
        adapter_states = {row[0]: row[1] for row in connection.execute("select source_type, state from catalyst_source_adapters where ticker = ?", (ticker,))}
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
