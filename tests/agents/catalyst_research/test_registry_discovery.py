import asyncio
import json
from pathlib import Path

import httpx

from app.agents.catalyst_research.persistence import repository
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.registry_discovery import discover_registry
from app.http_client import HttpClient


COMPANY = {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "cik": "1045810"}

NEWSROOM_HTML = """<!doctype html>
<html><head>
<link rel="stylesheet" href="/style.css">
<link rel="alternate" type="application/rss+xml" href="/news/rss/">
<link rel="alternate" type="application/atom+xml" href="https://nvidianews.nvidia.com/events.atom">
</head><body>NVIDIA Newsroom</body></html>"""

IR_HTML = """<html><head><title>NVIDIA Investor Relations</title></head><body>Investor Relations</body></html>"""

RSS_XML = """<rss version="2.0"><channel>
<item><title>NVIDIA Announces Platform</title><link>https://nvidianews.nvidia.com/news/platform</link><guid>nvda-1</guid><pubDate>Mon, 07 Sep 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM_XML = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>urn:nvda:event:day</id><title>NVIDIA Investor Day</title>
<link rel="alternate" href="https://nvidianews.nvidia.com/events/investor-day"/><updated>2026-09-05T09:30:00+00:00</updated>
</entry></feed>"""

SEARCH_ROWS = [
    {"title": "NVIDIA Newsroom", "url": "https://nvidianews.nvidia.com/", "snippet": "NVIDIA press releases and news"},
    {"title": "NVIDIA Newsroom RSS Feed", "url": "https://nvidianews.nvidia.com/news/rss/", "snippet": "NVIDIA official press release feed"},
    {"title": "NVIDIA Investor Relations", "url": "https://investor.nvidia.com/", "snippet": "NVIDIA investor relations earnings results"},
]

MODEL_SELECTIONS = [
    {
        "channel": "press_releases",
        "endpoint_type": "search_domain",
        "url": "https://nvidianews.nvidia.com/",
        "domain": "nvidianews.nvidia.com",
        "evidence_result_ids": [1],
        "confidence": "high",
        "reason": "official NVIDIA newsroom",
    },
    {
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/news/rss/",
        "domain": "nvidianews.nvidia.com",
        "evidence_result_ids": [2],
        "confidence": "high",
        "reason": "official newsroom feed",
    },
    {
        "channel": "earnings_results",
        "endpoint_type": "search_domain",
        "url": "https://investor.nvidia.com/",
        "domain": "investor.nvidia.com",
        "evidence_result_ids": [3],
        "confidence": "medium",
        "reason": "official IR site",
    },
]


class FakeProvider:
    def __init__(self, name, ready=True, rows=None, error=None):
        self.name = name
        self.ready = ready
        self.rows = rows or []
        self.error = error
        self.calls = []
        self.last_request_id = None

    async def search(self, query, *, limit):
        self.calls.append((query, limit))
        if self.error:
            raise self.error
        return self.rows


class FakeParsed:
    def __init__(self, endpoints):
        self.endpoints = endpoints

    def model_dump(self, mode="json"):
        return {"endpoints": self.endpoints}


class FakeResponses:
    def __init__(self, selections, error=None):
        self.selections = selections
        self.error = error
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        candidates = json.loads(kwargs["input"][1]["content"].split("Search candidates:\n", 1)[1])
        ids = {row["result_id"] for row in candidates}
        chosen = [selection for selection in self.selections if set(selection["evidence_result_ids"]) & ids]
        return type("Response", (), {"output_parsed": FakeParsed(chosen)})()


class FakeLLM:
    def __init__(self, selections=None, error=None):
        self.responses = FakeResponses(selections or [], error=error)


def client_for(handler):
    transport = httpx.MockTransport(handler)
    return HttpClient(transport=transport, sleep=lambda _: None, max_attempts=1)


def http_handler(request):
    host = request.url.host
    path = request.url.path
    if host == "nvidianews.nvidia.com" and path == "/":
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=NEWSROOM_HTML)
    if host == "nvidianews.nvidia.com" and path == "/news/rss/":
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=RSS_XML)
    if host == "nvidianews.nvidia.com" and path == "/events.atom":
        return httpx.Response(200, headers={"Content-Type": "application/atom+xml"}, content=ATOM_XML)
    if host == "investor.nvidia.com" and path == "/":
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=IR_HTML)
    return httpx.Response(404, headers={"Content-Type": "text/html"}, content="missing")


def make_job(tmp_path, ticker="NVDA"):
    con = repository.connect(Path(tmp_path) / "market_data.sqlite")
    job = repository.create_job(con, {"ticker": ticker, "years": 1}, {"name": "NVIDIA Corporation"})
    repository.start_job(con, job["job_id"], "2026-09-08T00:00:00+00:00")
    return con, job


def seed_registry(con, ticker="NVDA", version=1, endpoint_status="failing"):
    for registry_version in range(1, version + 1):
        repository.save_company_registry(
            con,
            {
                "ticker": ticker,
                "company_name": "NVIDIA Corporation",
                "official_domains": ["nvidia.com"],
                "source_confidence": "medium",
                "registry_version": registry_version,
            },
        )
    repository.upsert_source_endpoint(
        con,
        {
            "ticker": ticker,
            "channel": "press_releases",
            "endpoint_type": "rss",
            "url": "https://nvidianews.nvidia.com/news/rss/",
            "domain": "nvidia.com",
            "status": endpoint_status,
            "confidence": "high",
        },
    )


def run_discovery(company, *, con, job_id, llm=None, model=None, provider_rows=None, overrides=None, handler=http_handler):
    provider = FakeProvider("ddgs", rows=provider_rows or [])
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider])
    result = asyncio.run(
        discover_registry(
            company,
            router=router,
            llm_client=llm,
            model=model,
            repository=repository,
            job_id=job_id,
            connection=con,
            http_client=client_for(handler),
            overrides=overrides,
            resolver=lambda host: ["93.184.216.34"],
        )
    )
    return result, provider


def endpoint_index(endpoints):
    return {(row["channel"], row["endpoint_type"], row["url"]): row for row in endpoints}


def test_discovery_builds_registry_from_nvidia_search_evidence_and_detects_feeds(tmp_path):
    con, job = make_job(tmp_path)
    llm = FakeLLM(MODEL_SELECTIONS)

    result, provider = run_discovery(
        COMPANY,
        con=con,
        job_id=job["job_id"],
        llm=llm,
        model="selector",
        provider_rows=list(SEARCH_ROWS),
    )

    assert result["registry"]["registry_version"] == 1
    assert result["registry"]["official_domains"] == ["investor.nvidia.com", "nvidianews.nvidia.com"]
    assert result["registry"]["source_confidence"] == "high"
    assert result["status"] == "partial"

    endpoints = endpoint_index(result["endpoints"])
    assert set(endpoints) == {
        ("press_releases", "search_domain", "https://nvidianews.nvidia.com/"),
        ("press_releases", "rss", "https://nvidianews.nvidia.com/news/rss/"),
        ("press_releases", "atom", "https://nvidianews.nvidia.com/events.atom"),
        ("earnings_results", "search_domain", "https://investor.nvidia.com/"),
    }
    assert endpoints[("press_releases", "rss", "https://nvidianews.nvidia.com/news/rss/")]["status"] == "active"
    assert endpoints[("press_releases", "rss", "https://nvidianews.nvidia.com/news/rss/")]["evidence_result_ids"] == [2]
    assert endpoints[("press_releases", "search_domain", "https://nvidianews.nvidia.com/")]["evidence_result_ids"] == [1]
    assert endpoints[("press_releases", "atom", "https://nvidianews.nvidia.com/events.atom")]["discovery_method"] == "html"
    assert endpoints[("press_releases", "search_domain", "https://nvidianews.nvidia.com/")]["status"] == "unverified"

    stored = endpoint_index(repository.load_source_endpoints(con, "NVDA"))
    assert ("press_releases", "rss", "https://nvidianews.nvidia.com/news/rss/") in stored
    assert ("press_releases", "atom", "https://nvidianews.nvidia.com/events.atom") in stored
    assert len([row for row in repository.load_source_endpoints(con, "NVDA") if row["url"] == "https://nvidianews.nvidia.com/news/rss/"]) == 1

    attempts = con.execute(
        "select search_purpose, outcome from catalyst_search_attempts where job_id = ?",
        (job["job_id"],),
    ).fetchall()
    assert len(attempts) == 3
    assert all(row["search_purpose"] == "source_discovery" for row in attempts)

    checks = con.execute("select outcome, item_count from catalyst_endpoint_checks").fetchall()
    assert sorted((row["outcome"], row["item_count"]) for row in checks) == [("success_new", 1), ("success_new", 1)]

    assert provider.calls
    assert result["provider_provenance"]
    assert any(provenance["outcome"] == "accepted" for provenance in result["provider_provenance"])
    con.close()


def test_discovery_rejects_third_party_feed_and_keeps_it_as_rejected_source(tmp_path):
    con, job = make_job(tmp_path)
    rows = [{"title": "NVIDIA press feed", "url": "https://feeds.prnewswire.com/nvidia/rss", "snippet": "NVIDIA press releases"}]
    selections = [
        {
            "channel": "press_releases",
            "endpoint_type": "rss",
            "url": "https://feeds.prnewswire.com/nvidia/rss",
            "domain": "feeds.prnewswire.com",
            "evidence_result_ids": [1],
            "confidence": "high",
            "reason": "looks like a feed",
        }
    ]

    result, _ = run_discovery(COMPANY, con=con, job_id=job["job_id"], llm=FakeLLM(selections), model="selector", provider_rows=rows)

    assert result["registry"] is None
    assert result["status"] == "insufficient"
    assert repository.load_source_endpoints(con, "NVDA") == []
    sources = con.execute(
        "select url, acceptance_status, verification_reason from catalyst_ir_sources where job_id = ?",
        (job["job_id"],),
    ).fetchall()
    assert len(sources) == 1
    assert sources[0]["acceptance_status"] == "rejected"
    assert "third-party" in sources[0]["verification_reason"]
    con.close()


def test_discovery_rejects_unvalidated_feed_candidate_without_saving_endpoint(tmp_path):
    con, job = make_job(tmp_path)
    rows = [{"title": "NVIDIA Newsroom RSS", "url": "https://nvidianews.nvidia.com/broken-feed/", "snippet": "NVIDIA press release feed"}]
    selections = [
        {
            "channel": "press_releases",
            "endpoint_type": "rss",
            "url": "https://nvidianews.nvidia.com/broken-feed/",
            "domain": "nvidianews.nvidia.com",
            "evidence_result_ids": [1],
            "confidence": "high",
            "reason": "official newsroom feed",
        }
    ]

    result, _ = run_discovery(COMPANY, con=con, job_id=job["job_id"], llm=FakeLLM(selections), model="selector", provider_rows=rows)

    assert result["registry"] is None
    assert repository.load_source_endpoints(con, "NVDA") == []
    sources = con.execute(
        "select acceptance_status, verification_reason from catalyst_ir_sources where job_id = ?",
        (job["job_id"],),
    ).fetchall()
    assert len(sources) == 1
    assert sources[0]["acceptance_status"] == "rejected"
    assert sources[0]["verification_reason"] == "feed validation failed"
    con.close()


def test_discovery_accepts_manual_override_without_llm_and_validates_override_feed(tmp_path):
    con, job = make_job(tmp_path)

    result, provider = run_discovery(
        COMPANY,
        con=con,
        job_id=job["job_id"],
        llm=None,
        model=None,
        provider_rows=[],
        overrides={"press_releases": "https://nvidianews.nvidia.com/news/rss/"},
    )

    assert result["registry"]["registry_version"] == 1
    assert result["registry"]["source_confidence"] == "high"
    assert result["status"] == "partial"
    endpoints = endpoint_index(result["endpoints"])
    override = endpoints[("press_releases", "rss", "https://nvidianews.nvidia.com/news/rss/")]
    assert override["status"] == "active"
    assert override["confidence"] == "high"
    assert override["discovery_method"] == "manual"
    assert provider.calls
    con.close()


def test_discovery_reports_insufficient_when_no_endpoint_is_accepted(tmp_path):
    con, job = make_job(tmp_path)

    result, _ = run_discovery(COMPANY, con=con, job_id=job["job_id"], llm=FakeLLM([]), model="selector", provider_rows=list(SEARCH_ROWS))

    assert result["registry"] is None
    assert result["endpoints"] == []
    assert result["status"] == "insufficient"
    assert "provide a verified official source override" in result["next_actions"]
    assert repository.load_company_registry(con, "NVDA") is None
    con.close()


def test_discovery_keeps_existing_registry_when_selection_model_is_unavailable(tmp_path):
    con, job = make_job(tmp_path)
    seed_registry(con, version=2, endpoint_status="failing")

    result, _ = run_discovery(
        COMPANY,
        con=con,
        job_id=job["job_id"],
        llm=FakeLLM(error=RuntimeError("provider balance and secret details")),
        model="selector",
        provider_rows=list(SEARCH_ROWS),
    )

    assert result["registry"]["registry_version"] == 2
    assert result["status"] == "insufficient"
    assert "catalyst_llm_request_failed" in result["warnings"]
    assert "configure_catalyst_llm" in result["next_actions"]
    assert "provider balance" not in str(result)
    con.close()


def test_discovery_does_not_call_model_or_search_when_registry_is_healthy(tmp_path):
    con, job = make_job(tmp_path)
    seed_registry(con, version=1, endpoint_status="active")
    llm = FakeLLM(error=AssertionError("model must not be called"))

    result, provider = run_discovery(COMPANY, con=con, job_id=job["job_id"], llm=llm, model="selector", provider_rows=list(SEARCH_ROWS))

    assert result["status"] == "unchanged"
    assert result["registry"]["registry_version"] == 1
    assert provider.calls == []
    assert llm.responses.calls == []
    assert repository.load_company_registry(con, "NVDA")["registry_version"] == 1
    con.close()


def test_discovery_requires_mapping_overrides(tmp_path):
    con, job = make_job(tmp_path)

    import pytest

    with pytest.raises(ValueError, match="overrides are invalid"):
        run_discovery(COMPANY, con=con, job_id=job["job_id"], llm=None, model=None, provider_rows=[], overrides=["https://nvidianews.nvidia.com/news/rss/"])
    con.close()
