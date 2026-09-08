import asyncio
from pathlib import Path

import pytest

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.domain import MAX_ALTERNATE_SOURCES_PER_TYPE, _alternate_sources_truncated, _shape_source_candidates, discover_sources
from app.agents.catalyst_research.persistence import repository as catalyst_repository


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


def test_provider_chain_respects_auto_order_and_process_disablement():
    tavily = FakeProvider("tavily")
    native = FakeProvider("native_search")
    ddgs = FakeProvider("ddgs")
    router = SearchRouter(
        {"provider": "auto", "fallback": "auto"},
        [ddgs, native, tavily],
    )

    assert [provider.name for provider in router.provider_chain()] == ["tavily", "native_search", "ddgs"]
    router.disable("native_search")
    assert [provider.name for provider in router.provider_chain()] == ["tavily", "ddgs"]
    assert router.provider_chain() == router.provider_chain()


@pytest.mark.parametrize(
    "config",
    [{"provider": "unknown", "fallback": "auto"}, {"provider": "auto", "fallback": "unknown"}],
)
def test_router_rejects_unknown_configuration(config):
    with pytest.raises(ValueError):
        SearchRouter(config, [FakeProvider("ddgs")])


def test_alternate_sources_are_stably_capped_per_source_type_without_losing_primary_evidence():
    candidates = [
        {"source_type": "press_releases", "url": f"https://acme.example/news-{index}", "discovery_provider": "ddgs", "provider_rank": index, "evidence_result_ids": [index], "provider_provenance": []}
        for index in range(5)
    ]
    candidates.append({"source_type": "press_releases", "url": "https://acme.example/news-0", "discovery_provider": "ddgs", "provider_rank": 1, "evidence_result_ids": [99], "provider_provenance": []})
    primaries, alternates = _shape_source_candidates(candidates, SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")]))

    assert MAX_ALTERNATE_SOURCES_PER_TYPE == 2
    assert primaries[0]["url"] == "https://acme.example/news-0"
    assert primaries[0]["evidence_result_ids"] == [0, 99]
    assert len(alternates) == MAX_ALTERNATE_SOURCES_PER_TYPE
    assert [row["url"] for row in alternates] == ["https://acme.example/news-1", "https://acme.example/news-2"]
    assert _alternate_sources_truncated(candidates) == {"press_releases": 2}


def test_discovery_reports_deferred_same_site_capability_and_bounds_attempts():
    providers = [FakeProvider(name) for name in ("tavily", "native_search", "ddgs")]
    result = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=SearchRouter({"provider": "auto", "fallback": "auto"}, providers), llm_client=None, model=None, repository=FakeRepository(), job_id="job-deferred"))

    assert result["deferred_capabilities"] == ["same_site_traversal_from_trusted_snapshot"]
    assert len(result["provider_provenance"]) <= 12
    assert all(len(provider.calls) <= 4 for provider in providers)
    assert result["alternate_sources_truncated"] == {}


def test_discovery_restricts_queries_to_requested_channels():
    providers = [FakeProvider("ddgs")]
    result = asyncio.run(
        discover_sources(
            {"ticker": "ACM", "company_name": "Acme"},
            router=SearchRouter({"provider": "ddgs", "fallback": "none"}, providers),
            llm_client=None,
            model=None,
            repository=FakeRepository(),
            job_id="job-targeted",
            source_types={"press_releases"},
        )
    )

    assert len(providers[0].calls) == 1
    assert "press releases" in providers[0].calls[0][0].lower()
    assert result["provider_provenance"][0]["query"] == providers[0].calls[0][0]


@pytest.mark.parametrize(
    ("fallback", "expected"),
    [("auto", ["tavily", "native_search", "ddgs"]), ("ddgs", ["tavily", "ddgs"]), ("none", ["tavily"])],
)
def test_explicit_primary_fallback_chain_deduplicates(fallback, expected):
    providers = [FakeProvider("tavily"), FakeProvider("native_search"), FakeProvider("ddgs")]
    router = SearchRouter({"provider": "tavily", "fallback": fallback}, providers)

    assert [provider.name for provider in router.provider_chain()] == expected


class FakeRepository:
    def __init__(self):
        self.attempts = []
        self.results = []

    def record_search_attempt(self, attempt):
        saved = dict(attempt)
        saved["attempt_id"] = f"fake_attempt_{len(self.attempts) + 1}"
        self.attempts.append(saved)
        return saved["attempt_id"]

    def record_search_results(self, job_id, attempt_id, results):
        rows = []
        for row in results:
            saved = dict(row)
            rows.append(saved)
            self.results.append(saved)
        return rows

    def update_search_attempt(self, attempt_id, *, outcome, diagnostics=None, completed_at=None, provider_request_id=None):
        for attempt in self.attempts:
            if attempt["attempt_id"] == attempt_id:
                attempt["outcome"] = outcome


class FakeParsed:
    def __init__(self, selections):
        self.selections = selections

    def model_dump(self, mode="json"):
        return {"selections": self.selections}


class FakeResponses:
    def __init__(self, selections):
        self.selections = selections
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"output_parsed": FakeParsed(self.selections)})()


class FakeLLM:
    def __init__(self, selections):
        self.responses = FakeResponses(selections)


def test_discovery_allocates_job_local_ids_and_persists_each_attempt_before_fallback():
    first = FakeProvider(
        "tavily",
        rows=[{"title": "Acme IR", "url": "https://company.example/ir", "snippet": "investor relations"}],
        error=SearchProviderError("empty_results", "empty"),
    )
    second = FakeProvider(
        "ddgs",
        rows=[{"title": "Acme IR", "url": "https://company.example/ir", "snippet": "Investor Relations Press Releases"}],
    )
    router = SearchRouter({"provider": "tavily", "fallback": "ddgs"}, [first, second])
    repo = FakeRepository()
    llm = FakeLLM(
        [{
            "source_type": "ir_home",
            "url": "https://company.example/ir",
            "evidence_result_ids": [1],
            "confidence": 0.9,
            "reason": "official IR candidate",
        }]
    )

    result = asyncio.run(
        discover_sources(
            {"ticker": "CMP", "company_name": "Acme"},
            router=router,
            llm_client=llm,
            model="selector",
            repository=repo,
            job_id="job-1",
        )
    )

    assert result["sources"][0]["status"] == "ambiguous"
    assert result["sources"][0]["acceptance_status"] == "ambiguous"
    assert result["sources"][0]["evidence_result_ids"] == [1]
    assert [attempt["outcome"] for attempt in repo.attempts][:2] == ["empty_results", "ambiguous"]
    assert [row["result_id"] for row in repo.results] == [1, 2, 3, 4]
    assert first.calls and second.calls


def test_discovery_rejects_third_party_and_hostname_only_candidates():
    provider = FakeProvider(
        "ddgs",
        rows=[
            {"title": "Acme news", "url": "https://company-news.example/story", "snippet": "Acme"},
            {"title": "Investor Relations", "url": "https://company.example/ir", "snippet": "Investor Relations"},
        ],
    )
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider])
    repo = FakeRepository()
    llm = FakeLLM(
        [{
            "source_type": "ir_home",
            "url": "https://company.example/ir",
            "evidence_result_ids": [2],
            "confidence": 0.8,
            "reason": "hostname resembles company",
        }]
    )

    result = asyncio.run(
        discover_sources(
            {"ticker": "CMP", "company_name": "Acme"},
            router=router,
            llm_client=llm,
            model="selector",
            repository=repo,
            job_id="job-2",
        )
    )

    source = result["sources"][0]
    assert source["status"] in {"ambiguous", "rejected"}
    assert source["status"] != "accepted"


def test_discovery_manual_override_records_provenance_and_unsafe_override_rejected():
    repo = FakeRepository()
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")])

    result = asyncio.run(
        discover_sources(
            {"ticker": "CMP", "company_name": "Company"},
            router=router,
            llm_client=None,
            model=None,
            repository=repo,
            job_id="job-3",
            overrides={"press_releases": "https://company.example/news", "events_presentations": "file:///bad"},
        )
    )

    by_type = {row["source_type"]: row for row in result["sources"]}
    assert by_type["press_releases"]["discovery_provider"] == "manual_override"
    assert by_type["press_releases"]["status"] == "ambiguous"
    assert by_type["press_releases"]["acceptance_status"] == "ambiguous"
    assert by_type["events_presentations"]["status"] == "rejected"


def test_authentication_failure_disables_provider_for_later_queries():
    bad = FakeProvider(
        "tavily",
        error=SearchProviderError("authentication_failed", "secret", disable_provider=True),
    )
    good = FakeProvider("ddgs")
    router = SearchRouter({"provider": "auto", "fallback": "auto"}, [bad, good])
    repo = FakeRepository()

    result = asyncio.run(
        discover_sources(
            {"ticker": "CMP", "company_name": "Acme"},
            router=router,
            llm_client=None,
            model=None,
            repository=repo,
            job_id="job-4",
        )
    )

    assert len(bad.calls) == 1
    assert any("disabled" in warning for warning in result["warnings"])


def test_invalid_llm_url_is_rejected_without_leaking_url_as_accepted():
    provider = FakeProvider(
        "ddgs",
        rows=[{"title": "Acme Investor Relations", "url": "https://acme.example/ir", "snippet": "Acme investor relations"}],
    )
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider])
    repo = FakeRepository()
    llm = FakeLLM(
        [{
            "source_type": "ir_home",
            "url": "file:///secret",
            "evidence_result_ids": [1],
            "confidence": 0.9,
            "reason": "bad url",
        }]
    )

    result = asyncio.run(
        discover_sources(
            {"ticker": "CMP", "company_name": "Acme"},
            router=router,
            llm_client=llm,
            model="selector",
            repository=repo,
            job_id="job-5",
        )
    )

    assert result["sources"][0]["status"] == "rejected"


def test_real_repository_persists_attempts_and_results_before_selection(tmp_path):
    con = catalyst_repository.connect(Path(tmp_path) / "market_data.sqlite")
    job = catalyst_repository.create_job(con, {"ticker": "ACM", "years": 1}, {"name": "Acme"})
    catalyst_repository.start_job(con, job["job_id"], "2026-09-07T00:00:00+00:00")
    provider = FakeProvider(
        "ddgs",
        rows=[{"title": "Acme Investor Relations", "url": "https://acme.example/ir", "snippet": "Acme investor relations"}],
    )
    llm = FakeLLM(
        [{
            "source_type": "ir_home",
            "url": "https://acme.example/ir",
            "evidence_result_ids": [1],
            "confidence": 0.8,
            "reason": "candidate",
        }]
    )

    result = asyncio.run(
        discover_sources(
            {"ticker": "ACM", "company_name": "Acme"},
            router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider]),
            llm_client=llm,
            model="selector",
            repository=catalyst_repository,
            connection=con,
            job_id=job["job_id"],
        )
    )

    attempts = con.execute("select attempt_id, outcome from catalyst_search_attempts where job_id = ?", (job["job_id"],)).fetchall()
    results = con.execute("select result_id, attempt_id from catalyst_search_results where job_id = ? order by result_id", (job["job_id"],)).fetchall()
    assert len(attempts) == 4
    assert len({row[0] for row in attempts}) == 4
    assert [row[0] for row in results] == [1, 2, 3, 4]
    assert all(row[1] in {attempt[0] for attempt in attempts} for row in results)
    assert result["sources"][0]["acceptance_status"] == "ambiguous"
    saved = catalyst_repository.save_source(con, result["sources"][0])
    assert saved["acceptance_status"] == "ambiguous"


def test_attempt_ids_are_unique_across_jobs_in_one_sqlite_database(tmp_path):
    con = catalyst_repository.connect(Path(tmp_path) / "market_data.sqlite")
    first_job = catalyst_repository.create_job(con, {"ticker": "ACM", "years": 1}, {"name": "Acme"})
    second_job = catalyst_repository.create_job(con, {"ticker": "BETA", "years": 1}, {"name": "Beta"})
    catalyst_repository.start_job(con, first_job["job_id"], "2026-09-07T00:00:00+00:00")
    catalyst_repository.start_job(con, second_job["job_id"], "2026-09-07T00:00:00+00:00")
    for job in (first_job, second_job):
        asyncio.run(discover_sources({"ticker": job["ticker"], "company_name": job["company_name"]}, router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")] ), llm_client=None, model=None, repository=catalyst_repository, connection=con, job_id=job["job_id"]))
    ids = [row[0] for row in con.execute("select attempt_id from catalyst_search_attempts")]
    assert len(ids) == 8
    assert len(ids) == len(set(ids))


def test_job_id_punctuation_does_not_cause_attempt_id_collision(tmp_path):
    con = catalyst_repository.connect(Path(tmp_path) / "market_data.sqlite")
    jobs = []
    for ticker in ("A", "B"):
        job = catalyst_repository.create_job(con, {"ticker": ticker, "years": 1}, {"name": "Acme"})
        catalyst_repository.start_job(con, job["job_id"], "2026-09-07T00:00:00+00:00")
        jobs.append(job)
    original_ids = [job["job_id"] for job in jobs]
    for original, replacement in zip(original_ids, ("job/a", "job?a")):
        con.execute("update catalyst_research_jobs set job_id = ? where job_id = ?", (replacement, original))
    con.commit()
    for job, replacement in zip(jobs, ("job/a", "job?a")):
        job["job_id"] = replacement

    for job in jobs:
        asyncio.run(discover_sources({"ticker": job["ticker"], "company_name": "Acme"}, router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")]), llm_client=None, model=None, repository=catalyst_repository, connection=con, job_id=job["job_id"]))
    ids = [row[0] for row in con.execute("select attempt_id from catalyst_search_attempts")]
    assert len(ids) == len(set(ids))


def test_primary_and_alternates_are_stable_and_merge_same_url_evidence():
    tavily = FakeProvider("tavily", rows=[
        {"title": "Acme Press Releases", "url": "https://acme.example/news", "snippet": "Acme press releases", "provider_rank": 2},
        {"title": "Acme Press Releases alternate", "url": "https://acme.example/releases", "snippet": "Acme press releases", "provider_rank": 1},
    ])
    ddgs = FakeProvider("ddgs", rows=[
        {"title": "Acme News", "url": "https://acme.example/news", "snippet": "Acme press releases", "provider_rank": 1},
    ])
    class SelectionLLM(FakeLLM):
        def __init__(self):
            super().__init__([])
            self.index = 0

        async def _parse(self, **kwargs):
            return None

    class Responses:
        def __init__(self):
            self.calls = []

        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            rows = kwargs["input"][1]["content"]
            import json

            candidates = json.loads(rows.split("Search candidates:\n", 1)[1])
            row = candidates[1] if len(candidates) > 1 and len(self.calls) == 3 else candidates[0]
            selections = [{"source_type": "press_releases", "url": row["url"], "evidence_result_ids": [row["result_id"]], "confidence": 0.7, "reason": "candidate"}]
            return type("Response", (), {"output_parsed": FakeParsed(selections)})()

    llm = type("LLM", (), {"responses": Responses()})()
    result = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=SearchRouter({"provider": "tavily", "fallback": "ddgs"}, [tavily, ddgs]), llm_client=llm, model="selector", repository=FakeRepository(), job_id="job-13"))

    primary = [row for row in result["sources"] if row["source_type"] == "press_releases"]
    alternates = [row for row in result["alternate_sources"] if row["source_type"] == "press_releases"]
    assert primary[0]["url"] == "https://acme.example/releases"
    assert [row["url"] for row in alternates] == ["https://acme.example/news"]
    assert alternates[0]["evidence_result_ids"][:2] == [1, 3]


def test_discovery_does_not_accept_unknown_domain_or_provider_metadata_links():
    provider = FakeProvider(
        "ddgs",
        rows=[{
            "title": "Acme Investor Relations",
            "url": "https://unknown.example/ir",
            "snippet": "Acme investor relations",
            "provider_metadata": {"links": [{"url": "/official", "title": "Acme"}]},
        }],
    )
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider])
    repo = FakeRepository()
    llm = FakeLLM([{
        "source_type": "ir_home",
        "url": "https://unknown.example/official",
        "evidence_result_ids": [1],
        "confidence": 0.9,
        "reason": "same site",
    }])

    result = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=llm, model="selector", repository=repo, job_id="job-6"))

    assert result["sources"] == [] or result["sources"][0]["status"] == "rejected"


@pytest.mark.parametrize("url", ["file:///secret", "https://user:pass@example.com/ir", "https://127.0.0.1/ir"])
def test_unsafe_search_results_are_not_persisted_or_sent_to_llm(url):
    provider = FakeProvider("ddgs", rows=[{"title": "Acme IR", "url": url, "snippet": "Acme investor relations"}])
    repo = FakeRepository()
    llm = FakeLLM([])
    result = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider]), llm_client=llm, model="selector", repository=repo, job_id="job-12"))
    assert repo.results == []
    assert llm.responses.calls == []
    assert result["provider_provenance"][0]["outcome"] == "rejected"


def test_override_requires_mapping_and_safe_override_is_pending():
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")])
    with pytest.raises(ValueError, match="overrides are invalid"):
        asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=None, model=None, repository=FakeRepository(), job_id="job-7", overrides=[]))
    result = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=None, model=None, repository=FakeRepository(), job_id="job-8", overrides={"press_releases": "https://acme.example/news"}))
    assert result["sources"][0]["status"] == "ambiguous"
    assert result["sources"][0]["acceptance_status"] == "ambiguous"


def test_transport_exhaustion_is_search_unavailable_but_rejected_selection_is_rejected():
    provider = FakeProvider("ddgs", error=SearchProviderError("timeout", "secret"))
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider])
    exhausted = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=None, model=None, repository=FakeRepository(), job_id="job-9"))
    assert exhausted["status"] == "search_unavailable"

    rejected_provider = FakeProvider("ddgs", rows=[{"title": "Acme Investor Relations", "url": "https://acme.example/ir", "snippet": "Acme investor relations"}])
    rejected = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [rejected_provider]), llm_client=FakeLLM([]), model="selector", repository=FakeRepository(), job_id="job-10"))
    assert rejected["status"] == "rejected"


def test_discovery_reports_runtime_llm_failure_as_configuration_action():
    provider = FakeProvider(
        "ddgs",
        rows=[{"title": "Acme Investor Relations", "url": "https://acme.example/ir", "snippet": "Acme investor relations"}],
    )

    class FailingResponses:
        async def parse(self, **kwargs):
            raise RuntimeError("provider balance and secret details")

    llm = type("LLM", (), {"responses": FailingResponses()})()
    result = asyncio.run(
        discover_sources(
            {"ticker": "ACM", "company_name": "Acme"},
            router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider]),
            llm_client=llm,
            model="selector",
            repository=FakeRepository(),
            job_id="job-llm-failure",
            source_types={"ir_home"},
        )
    )

    assert result["warnings"] == ["catalyst_llm_request_failed"]
    assert "configure_catalyst_llm" in result["next_actions"]
    assert "provider balance" not in str(result)


def test_owned_repository_connection_closes_when_identity_validation_fails():
    class OwnedConnection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class RepositoryWithConnection(FakeRepository):
        def __init__(self):
            super().__init__()
            self.connection = OwnedConnection()

        def connect(self):
            return self.connection

    repository = RepositoryWithConnection()
    with pytest.raises(ValueError, match="company identity"):
        asyncio.run(discover_sources({}, router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")]), llm_client=None, model=None, repository=repository, job_id="job-11"))
    assert repository.connection.closed is True
