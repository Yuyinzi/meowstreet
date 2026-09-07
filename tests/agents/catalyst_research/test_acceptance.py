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
from app.agents.catalyst_research.statistics import calculate_statistics
from app.agents.catalyst_research.workflow import run_research


FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "acceptance_manifest.json").read_text())
TICKERS = sorted(MANIFEST["tickers"])
_REQUIRED_CHANNELS = ("press_releases", "events_presentations")
_FIXED_CLOCK = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


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
        self.llm_classification_calls = 0

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
            "llm_client": object(),
            "models": {"adapter_generation": "fixture-adapter-model", "classification": "fixture-classification-model"},
            "resolver": self._resolve,
            "discover_sources": self._discover,
            "fetch_page": self._fetch,
            "build_snapshot": build_structural_snapshot,
            "generate_adapter": self._generate,
            "validate_candidate": validate_candidate,
            "validate_active_adapter": validate_active_adapter,
            "execute_adapter": execute_adapter,
            "classify_observations": self._classify,
            "normalize_observations": domain.normalize_observations,
            "calculate_statistics": calculate_statistics,
        }

    async def _resolve(self, request, **kwargs):
        return {"ticker": self.ticker, "company_name": self.entry["company_name"], "cik": self.entry["cik"]}

    async def _discover(self, company, **kwargs):
        requested = set(kwargs.get("source_types") or _REQUIRED_CHANNELS)
        sources = []
        for channel in _REQUIRED_CHANNELS:
            spec = self.entry["channels"][channel]
            if channel in requested and spec["discovered"]:
                sources.append({"source_type": channel, "url": spec["url"], "acceptance_status": "pending", "discovery_provider": "ddgs"})
        if "press_releases" in requested and self.entry["channels"]["press_releases"]["discovered"]:
            for url in self.entry["rejected_candidates"]:
                sources.append({"source_type": "press_releases", "url": url, "status": "rejected", "discovery_provider": "tavily"})
        pending = [source for source in sources if source.get("status") != "rejected"]
        warnings = list(MANIFEST["provider_fallback"]["warnings"]) if pending else []
        return {"status": "accepted" if pending else "rejected", "sources": sources, "alternate_sources": [], "warnings": warnings, "next_actions": []}

    def _page_file(self, url):
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

    async def _classify(self, events, **kwargs):
        expected = {key: obs["earnings_state"] for key, obs in self._expected_labels().items()}
        classified = []
        lookups = 0
        for event in events:
            label = domain.classify_title_by_rule(event["title"], event["source_type"])
            method = "rule_v1"
            if label is None:
                label = expected.get((event["source_type"], event["title"]))
                method = "fixture_llm_v1"
                lookups += 1
                if label is None:
                    label = "ambiguous"
                    method = "unresolved"
            classified.append({**event, "earnings_state": label, "classification_method": method})
        self.llm_classification_calls += lookups
        return {"events": classified, "llm_call_count": lookups}

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


def _expected_lookup_count(entry, observations):
    return sum(1 for obs in observations if domain.classify_title_by_rule(obs["title"], obs["source_type"]) is None)


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
                assert obs["earnings_state"] == "non_earnings"
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
    assert supported == 7


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
    assert cold["call_counts"]["classification"] == _expected_lookup_count(entry, entry["observations"])
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
    assert _projection(_job_events(harness.db_path, ticker, cold["job_id"])) == _manifest_projection(entry["observations"])
    connection = repository.connect(harness.db_path)
    try:
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
    dual_year = []
    for ticker in TICKERS:
        entry = MANIFEST["tickers"][ticker]
        harness = acceptance_harness(tmp_path / ticker.lower(), ticker)
        cold = asyncio.run(harness.run("initial"))
        assert cold["status"] == entry["expected_status"]
        for warning in MANIFEST["provider_fallback"]["warnings"]:
            assert warning in cold["warnings"]
        assert harness.llm_classification_calls == _expected_lookup_count(entry, entry["observations"])
        assert all(domain.url_host(source["url"]) == entry["host"] for source in cold["sources"])
        for url in entry["rejected_candidates"]:
            assert url not in harness.fetched_urls
        events = _job_events(harness.db_path, ticker, cold["job_id"])
        expected = {(obs["source_type"], obs["title"]): obs["earnings_state"] for obs in entry["observations"]}
        for event in events:
            total += 1
            matched += int(expected.get((event["source_type"], event["title"])) == event["earnings_state"])
        if _result_dual_year(cold):
            dual_year.append(ticker)
    assert total == sum(len(entry["observations"]) for entry in MANIFEST["tickers"].values())
    assert dual_year == sorted(ticker for ticker, entry in MANIFEST["tickers"].items() if entry["supports_dual_archive_year"])
    assert len(dual_year) >= 7
    assert matched / total >= 0.95
