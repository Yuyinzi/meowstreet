import asyncio
from pathlib import Path

import pytest

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.domain import discover_sources
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
        self.attempts.append(dict(attempt))

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
    assert result["sources"][0]["acceptance_status"] == "pending"
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
    assert by_type["press_releases"]["acceptance_status"] == "pending"
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
    assert result["sources"][0]["acceptance_status"] == "pending"
    saved = catalyst_repository.save_source(con, result["sources"][0])
    assert saved["acceptance_status"] == "pending"


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


def test_override_requires_mapping_and_safe_override_is_pending():
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [FakeProvider("ddgs")])
    with pytest.raises(ValueError, match="overrides are invalid"):
        asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=None, model=None, repository=FakeRepository(), job_id="job-7", overrides=[]))
    result = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=None, model=None, repository=FakeRepository(), job_id="job-8", overrides={"press_releases": "https://acme.example/news"}))
    assert result["sources"][0]["status"] == "ambiguous"
    assert result["sources"][0]["acceptance_status"] == "pending"


def test_transport_exhaustion_is_search_unavailable_but_rejected_selection_is_rejected():
    provider = FakeProvider("ddgs", error=SearchProviderError("timeout", "secret"))
    router = SearchRouter({"provider": "ddgs", "fallback": "none"}, [provider])
    exhausted = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=router, llm_client=None, model=None, repository=FakeRepository(), job_id="job-9"))
    assert exhausted["status"] == "search_unavailable"

    rejected_provider = FakeProvider("ddgs", rows=[{"title": "Acme Investor Relations", "url": "https://acme.example/ir", "snippet": "Acme investor relations"}])
    rejected = asyncio.run(discover_sources({"ticker": "ACM", "company_name": "Acme"}, router=SearchRouter({"provider": "ddgs", "fallback": "none"}, [rejected_provider]), llm_client=FakeLLM([]), model="selector", repository=FakeRepository(), job_id="job-10"))
    assert rejected["status"] == "rejected"
