import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.agents.catalyst_research import scheduler as catalyst_scheduler
from app.agents.catalyst_research import statistics as catalyst_statistics
from app.agents.catalyst_research.config import RESULT_SCHEMA_VERSION
from app.agents.catalyst_research.workflow import _UnavailableSearchRouter, _javascript_archive_shell, run_research
from app.agents.catalyst_research.extraction.pages import fetch_html_page
from app.http_client import HttpClient


FIXTURES = Path(__file__).parent / "fixtures"


class FakeRepository:
    def __init__(self):
        self.calls = []
        self.job = {
            "job_id": "cr_test",
            "ticker": "ACME",
            "requested_start": "2025-01-01",
            "requested_end": "2026-01-01",
            "status": "queued",
        }
        self.result = {"job_id": "cr_test", "status": "queued"}

    def connect(self, db_path=None):
        self.calls.append("connect")
        return object()

    def create_job(self, connection, request, company=None, now=None):
        self.calls.append("create")
        self.job.update({"ticker": request["ticker"], "requested_start": "2025-01-01", "requested_end": request["as_of"]})
        return dict(self.job)

    def start_job(self, connection, job_id, started_at):
        self.calls.append("start")
        self.job["status"] = "running"

    def update_resolved_company(self, connection, job_id, company):
        self.calls.append("company")
        self.job.update({"company_name": company.get("company_name"), "cik": company.get("cik")})
        return dict(self.job)

    def save_source(self, connection, source):
        self.calls.append(f"source:{source['source_type']}")
        return {**source, "source_id": f"source_{source['source_type']}"}

    def save_snapshot(self, connection, snapshot):
        self.calls.append(f"snapshot:{snapshot['source_type']}")
        return snapshot.get("content_hash", "hash")

    def create_adapter_candidate(self, connection, candidate):
        self.calls.append(f"candidate:{candidate['source_type']}")
        return {**candidate, "adapter_id": f"adapter_{candidate['source_type']}", "version": 1}

    def record_adapter_validation(self, connection, validation):
        self.calls.append(f"validate:{validation['source_type']}")

    def activate_adapter(self, connection, adapter_id, activated_at):
        self.calls.append(f"activate:{adapter_id}")

    def activate_adapter_with_source(self, connection, adapter_id, activated_at, source):
        self.calls.append(f"activate:{adapter_id}")
        return {**source, "source_id": f"source_{source['source_type']}"}

    def save_finalized_observations(self, connection, job_id, events, classifications):
        self.calls.append("save_observations")
        self.saved_events = events

    def finalize_job(self, connection, job_id, result):
        self.calls.append("finalize")
        self.job["status"] = result["status"]
        self.result = {**self.result, **result, "status": result["status"]}

    def finalize_job_with_observations(self, connection, job_id, events, classifications, result):
        self.save_finalized_observations(connection, job_id, events, classifications)
        self.finalize_job(connection, job_id, result)

    def fail_job(self, connection, job_id, error_summary, **kwargs):
        self.calls.append("fail")
        self.job["status"] = "failed"
        self.result = {**self.result, "status": "failed", "error_summary": error_summary}

    def load_job_result(self, connection, job_id):
        self.calls.append("load_result")
        return self.result


def _deps(repository, calls, *, fail_resolve=False):
    class FakeLLM:
        pass

    async def resolve(request, **kwargs):
        calls.append("resolve")
        if fail_resolve:
            raise ValueError("company resolution failed")
        return {"ticker": "ACME", "company_name": "Acme Corporation", "cik": 123}

    async def discover(company, **kwargs):
        calls.append("discover")
        return {
            "status": "accepted",
            "sources": [
                {"source_type": "ir_home", "url": "https://ir.acme.example/", "acceptance_status": "pending"},
                {"source_type": "press_releases", "url": "https://ir.acme.example/news", "acceptance_status": "pending"},
                {"source_type": "events_presentations", "url": "https://ir.acme.example/events", "acceptance_status": "pending"},
            ],
            "warnings": ["provider fallback used"],
            "next_actions": [],
        }

    def fetch(url, **kwargs):
        calls.append(f"fetch:{url.rsplit('/', 1)[-1] or 'home'}")
        purpose = "Events Presentations" if "/events" in url else "Press Releases"
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme Investor Relations {purpose}</body></html>"}

    def snapshot(page, **kwargs):
        source_type = kwargs["source"]["source_type"]
        calls.append(f"inspect:{source_type}")
        return {**page, "source_type": source_type, "text": page["html"]}

    async def generate(company, source, snapshot, **kwargs):
        calls.append(f"generate:{source['source_type']}")
        return {"source_type": source["source_type"], "source_url": source["url"], "allowed_hosts": ["ir.acme.example"], "adapter": {"source_type": source["source_type"]}}

    def validate(adapter, snapshot, **kwargs):
        calls.append(f"validate_stage:{adapter['source_type']}")
        date_key = "published_date" if adapter["source_type"] == "press_releases" else "event_date"
        return {"status": "passed", "observations": [{"source_type": adapter["source_type"], "title": "Acme update", "count_date": "2025-06-01", date_key: "2025-06-01", "url": "https://ir.acme.example/item"}], "report": {}}

    def execute(adapter, **kwargs):
        calls.append(f"execute:{adapter['source_type']}")
        date_key = "published_date" if adapter["source_type"] == "press_releases" else "event_date"
        return {"observations": [{"source_type": adapter["source_type"], "title": "Acme update", "count_date": "2025-06-01", date_key: "2025-06-01", "url": "https://ir.acme.example/item"}], "coverage_start": "2025-01-01", "coverage_end": "2026-01-01", "boundary_reached": True, "archive_exhausted": False, "page_count": 1, "item_count": 1}

    async def classify(events, **kwargs):
        calls.append("classify")
        return {"events": [{**event, "earnings_state": "non_earnings", "classification_method": "rule_v1"} for event in events], "llm_call_count": 0, "provenance": []}

    def stats(events, sources, requested_window):
        calls.append("stats")
        return {"press_releases": {"status": "complete"}, "events_presentations": {"status": "complete"}}

    return {
        "repository": repository,
        "llm_client": FakeLLM(),
        "models": {"adapter_generation": "adapter-model", "classification": "classification-model"},
        "resolver": resolve,
        "discover_sources": discover,
        "fetch_page": fetch,
        "build_snapshot": snapshot,
        "generate_adapter": generate,
        "validate_candidate": validate,
        "execute_adapter": execute,
        "classify_observations": classify,
        "calculate_statistics": stats,
    }


def test_cold_workflow_uses_fixed_order_and_one_adapter_per_required_channel():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    result = asyncio.run(
        run_research(
            {"ticker": "acme", "years": 1, "as_of": "2026-01-01"},
            dependencies=dependencies,
        )
    )

    assert result["status"] == "completed"
    assert calls[:3] == ["resolve", "discover", "fetch:home"]
    assert calls[-2:] == ["classify", "stats"]
    assert repository.calls[-2:] == ["finalize", "load_result"]
    assert [call for call in calls if call.startswith("generate:")] == ["generate:press_releases", "generate:events_presentations"]
    assert repository.calls.count("save_observations") == 1
    assert repository.calls[-1] == "load_result"


def test_cold_workflow_tries_alternate_source_after_adapter_validation_failure():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)

    async def discover(company, **kwargs):
        return {
            "status": "ambiguous",
            "sources": [
                {"source_type": "press_releases", "url": "https://ir.acme.example/news/detail", "acceptance_status": "ambiguous"},
                {"source_type": "events_presentations", "url": "https://ir.acme.example/events", "acceptance_status": "ambiguous"},
            ],
            "alternate_sources": [
                {"source_type": "press_releases", "url": "https://ir.acme.example/news", "acceptance_status": "ambiguous"},
            ],
            "warnings": [],
            "next_actions": [],
        }

    async def generate(company, source, snapshot, **kwargs):
        calls.append(f"generate:{source['url']}")
        return {
            "source_type": source["source_type"],
            "source_url": source["url"],
            "allowed_hosts": ["ir.acme.example"],
            "adapter": {"source_type": source["source_type"], "source_url": source["url"]},
        }

    def validate(adapter, snapshot, **kwargs):
        status = "failed" if adapter["source_url"].endswith("/detail") else "passed"
        return {"status": status, "observations": [], "report": {}}

    dependencies.update({"discover_sources": discover, "generate_adapter": generate, "validate_candidate": validate})

    result = asyncio.run(
        run_research(
            {"ticker": "ACME", "years": 1, "as_of": "2026-01-01"},
            dependencies=dependencies,
        )
    )

    assert result["status"] == "completed"
    assert [call for call in calls if call.startswith("generate:https://ir.acme.example/news")] == [
        "generate:https://ir.acme.example/news/detail",
        "generate:https://ir.acme.example/news",
    ]


def test_cold_workflow_reports_stage_progress_in_order():
    repository = FakeRepository()
    calls = []
    stages = []
    dependencies = _deps(repository, calls)
    dependencies["progress"] = lambda stage, **details: stages.append((stage, details))
    result = asyncio.run(
        run_research(
            {"ticker": "acme", "years": 1, "as_of": "2026-01-01"},
            dependencies=dependencies,
        )
    )

    assert result["status"] == "completed"
    stage_names = [stage for stage, _ in stages]
    assert stage_names == [
        "company_resolved",
        "discovery",
        "adapter_generation",
        "adapter_validated",
        "adapter_generation",
        "adapter_validated",
        "classification",
        "finalizing",
    ]
    assert ("company_resolved", {"ticker": "ACME"}) in stages
    assert ("finalizing", {"status": "completed"}) in stages


def test_workflow_ignores_failing_progress_callback():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)

    def progress(stage, **details):
        raise RuntimeError("progress sink unavailable")

    dependencies["progress"] = progress
    result = asyncio.run(
        run_research(
            {"ticker": "acme", "years": 1, "as_of": "2026-01-01"},
            dependencies=dependencies,
        )
    )

    assert result["status"] == "completed"


def test_cold_workflow_persists_validated_earnings_results_without_an_adapter():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)

    discovery_source_types = []

    async def discover(company, **kwargs):
        discovery_source_types.append(set(kwargs["source_types"]))
        return {
            "status": "accepted",
            "sources": [
                {"source_type": "ir_home", "url": "https://ir.acme.example/"},
                {"source_type": "earnings_results", "url": "https://ir.acme.example/earnings"},
                {"source_type": "press_releases", "url": "https://ir.acme.example/news"},
                {"source_type": "events_presentations", "url": "https://ir.acme.example/events"},
            ],
            "warnings": [],
            "next_actions": [],
        }

    def fetch(url, **kwargs):
        purpose = "Quarterly Financial Results" if url.endswith("earnings") else ("Events Presentations" if url.endswith("events") else "Press Releases")
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme Investor Relations {purpose}</body></html>"}

    dependencies.update({"discover_sources": discover, "fetch_page": fetch})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed"
    assert discovery_source_types == [{"ir_home", "earnings_results", "press_releases", "events_presentations"}]
    assert "source:ir_home" in repository.calls
    assert "source:earnings_results" in repository.calls
    assert "candidate:earnings_results" not in repository.calls
    assert "activate:adapter_earnings_results" not in repository.calls


def test_cold_workflow_unexpected_resolution_failure_finalizes_failed_without_events():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls, fail_resolve=True)
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "failed"
    assert "company resolution failed" in result["error_summary"]
    assert "save_observations" not in repository.calls
    assert repository.calls[-2:] == ["fail", "load_result"]


def test_cold_workflow_traverses_only_trusted_origin_snapshot_links():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)

    async def discover(company, **kwargs):
        calls.append("discover")
        return {"status": "accepted", "sources": [{"source_type": "ir_home", "url": "https://ir.acme.example/"}], "warnings": [], "next_actions": []}

    async def fetch(url, **kwargs):
        calls.append(f"fetch:{url}")
        purpose = "Investor Relations Home" if url.endswith("/") else ("Press Releases" if "news" in url else "Events Presentations")
        final_url = "https://ir.acme.example/ir/index.html" if url.endswith("/") else url
        if url != "https://ir.acme.example/":
            assert kwargs["allowed_hosts"] == ["ir.acme.example"]
        return {"requested_url": url, "final_url": final_url, "html": f"<html><body>Acme {purpose}</body></html>"}

    def snapshot(page, **kwargs):
        source_type = kwargs["source"]["source_type"]
        calls.append(f"inspect:{source_type}")
        links = []
        if source_type == "ir_home":
            links = [{"href": "news", "text": "Press Releases"}, {"href": "/events", "text": "Events & Presentations"}, {"href": "https://other.example/news", "text": "Press Releases"}]
        return {**page, "source_type": source_type, "text": page["html"], "normalized": {"links": links}}

    dependencies.update({"discover_sources": discover, "fetch_page": fetch, "build_snapshot": snapshot})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed"
    assert "fetch:https://ir.acme.example/ir/news" in calls
    assert "fetch:https://ir.acme.example/events" in calls
    assert "fetch:https://other.example/news" not in calls


def test_cold_workflow_happy_path_persists_to_real_sqlite(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "market_data.sqlite", dependencies=dependencies))

    assert result["status"] == "completed"
    connection = repository.connect(tmp_path / "market_data.sqlite")
    try:
        assert connection.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 2
        assert connection.execute("select count(*) from catalyst_source_adapters where state = 'active'").fetchone()[0] == 2
    finally:
        connection.close()


def test_cold_workflow_failure_path_persists_terminal_failed_job(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls, fail_resolve=True)
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "market_data.sqlite", dependencies=dependencies))

    assert result["status"] == "failed"
    connection = repository.connect(tmp_path / "market_data.sqlite")
    try:
        assert connection.execute("select status from catalyst_research_jobs").fetchone()[0] == "failed"
        assert connection.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0
    finally:
        connection.close()


def test_ambiguous_source_is_pending_in_real_sqlite_not_invalid_enum(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)

    async def discover(company, **kwargs):
        return {"status": "accepted", "sources": [{"source_type": "press_releases", "url": "https://ir.acme.example/news"}], "warnings": [], "next_actions": []}

    def snapshot(page, **kwargs):
        return {**page, "text": "A different company news page"}

    dependencies.update({"discover_sources": discover, "build_snapshot": snapshot})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))

    assert result["status"] == "unsupported"
    connection = repository.connect(tmp_path / "db.sqlite")
    try:
        row = connection.execute("select acceptance_status, verification_reason from catalyst_ir_sources").fetchone()
        assert row[0] == "ambiguous"
        assert row[1] == "company identity is ambiguous"
    finally:
        connection.close()


def test_cold_workflow_closes_owned_http_client_but_not_caller_client(monkeypatch):
    repository = FakeRepository()
    calls = []
    owned = type("OwnedClient", (), {"close": lambda self: calls.append("owned-close")})()
    monkeypatch.setattr("app.agents.catalyst_research.workflow.HttpClient", lambda: owned)
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=_deps(repository, calls)))
    assert result["status"] == "completed"
    assert "owned-close" in calls

    caller = type("CallerClient", (), {"close": lambda self: calls.append("caller-close")})()
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, http_client=caller, dependencies=_deps(repository, calls)))
    assert result["status"] == "completed"
    assert "caller-close" not in calls


def test_missing_catalyst_llm_is_partial_and_requests_configuration():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    dependencies.update({"llm_client": None, "models": {}})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))
    assert result["status"] == "completed_partial"
    assert "configure_catalyst_llm" in result["next_actions"]


def test_adapter_generation_llm_failure_requests_configuration_without_raw_error():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)

    async def generate(company, source, snapshot, **kwargs):
        raise ValueError("insufficient balance api_key=secret")

    dependencies["generate_adapter"] = generate

    result = asyncio.run(
        run_research(
            {"ticker": "ACME", "years": 1, "as_of": "2026-01-01"},
            dependencies=dependencies,
        )
    )

    assert result["status"] == "completed_partial"
    assert "catalyst_llm_request_failed" in result["warnings"]
    assert "configure_catalyst_llm" in result["next_actions"]
    assert "secret" not in str(result)


def test_non_html_source_is_unsupported_with_stable_action_code(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)

    async def fetch(url, **kwargs):
        if url == "https://ir.acme.example/news":
            raise ValueError("page content type is not html")
        purpose = "Events Presentations" if "/events" in url else "Investor Relations Home"
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme {purpose}</body></html>"}

    dependencies["fetch_page"] = fetch
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert result["status"] == "completed_partial"
    source = next(item for item in result["sources"] if item["source_type"] == "press_releases")
    assert source["extraction_status"] == "unsupported"
    assert "source_javascript_unsupported" in result["warnings"]


def test_malformed_execution_result_never_activates_candidate(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)

    def execute(adapter, **kwargs):
        if adapter["source_type"] == "press_releases":
            return {"observations": "not-a-list"}
        return {"observations": [], "boundary_reached": True, "coverage_start": "2025-01-01", "coverage_end": "2026-01-01"}

    dependencies["execute_adapter"] = execute
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert result["status"] == "completed_partial"
    connection = repository.connect(tmp_path / "db.sqlite")
    try:
        assert connection.execute("select count(*) from catalyst_source_adapters where state = 'active'").fetchone()[0] == 1
        assert connection.execute("select count(*) from catalyst_source_adapters where state = 'failed_validation'").fetchone()[0] == 1
    finally:
        connection.close()


def test_ambiguous_classification_exposes_stable_warning_and_action_codes():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)

    async def classify(events, **kwargs):
        return {"events": [{**event, "earnings_state": "ambiguous", "classification_method": "llm_v1"} for event in events], "llm_call_count": 1}

    dependencies["classify_observations"] = classify
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))
    assert result["status"] == "completed_partial"
    assert "classification_ambiguous" in result["warnings"]
    assert "review_ambiguous_classification" in result["next_actions"]


def test_inference_configuration_failure_is_visible_without_raw_error(monkeypatch):
    repository = FakeRepository()
    calls = []
    monkeypatch.setattr("app.agents.catalyst_research.workflow.load_inference_bundle", lambda: (_ for _ in ()).throw(ValueError("api_key=secret")))
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=_deps(repository, calls)))
    assert result["status"] == "completed"
    assert "catalyst_llm_configuration_failed" in result["warnings"]
    assert "secret" not in str(result)


def test_connection_is_closed_when_owned_http_client_setup_fails(monkeypatch):
    class Connection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    repository = FakeRepository()
    repository.connect = lambda db_path=None: connection
    monkeypatch.setattr("app.agents.catalyst_research.workflow.HttpClient", lambda: (_ for _ in ()).throw(RuntimeError("client setup failed")))
    try:
        asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies={"repository": repository}))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected client setup failure")
    assert connection.closed


def test_real_discovery_with_provider_and_missing_llm_is_completed_partial(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    domain = __import__("app.agents.catalyst_research.domain", fromlist=["domain"])

    class Provider:
        name = "fixture"

        async def search(self, query, limit=10):
            return [{"title": "Acme Investor Relations", "url": "https://ir.acme.example/", "snippet": "Acme IR archive"}]

    class Router:
        def provider_chain(self):
            return [Provider()]

        def provider_order(self):
            return ["fixture"]

        def unavailable(self):
            return []

    dependencies = _deps(repository, [])
    dependencies.update({"discover_sources": domain.discover_sources, "search_router": Router(), "llm_client": None, "models": {}})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert result["status"] == "completed_partial"
    assert "catalyst_llm_unavailable" in result["warnings"]
    assert "configure_catalyst_llm" in result["next_actions"]


def test_failure_to_fail_job_logs_only_safe_context(caplog):
    repository = FakeRepository()
    calls = []

    def fail_job(connection, job_id, error_summary, **kwargs):
        raise RuntimeError("Cookie: session=secret-token")

    repository.fail_job = fail_job
    dependencies = _deps(repository, calls, fail_resolve=True)
    with caplog.at_level("ERROR"):
        result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))
    assert result["status"] == "queued"
    assert "secret-token" not in caplog.text
    assert "Traceback" not in caplog.text
    assert "cr_test" in caplog.text


def test_js_only_archive_shell_is_unsupported_but_script_enhanced_content_is_not(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)
    shell = "<html><body><div id='__next'></div>" + "<script>window.__DATA__={}</script>" * 6 + "</body></html>"

    async def fetch(url, **kwargs):
        if "/news" in url:
            return {"requested_url": url, "final_url": url, "html": shell, "content_type": "text/html"}
        purpose = "Events Presentations" if "/events" in url else "Investor Relations Home"
        return {"requested_url": url, "final_url": url, "html": f"<html><body><script>enhance()</script><h1>Acme {purpose}</h1><a href='/archive'>Archive</a><time>2025-01-01</time></body></html>"}

    dependencies.update({"fetch_page": fetch})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert result["status"] == "completed_partial"
    source = next(item for item in result["sources"] if item["source_type"] == "press_releases")
    assert source["extraction_status"] == "unsupported"
    assert "javascript_archive_unsupported" in result["warnings"]
    assert "events_presentations" in [item["source_type"] for item in result["sources"]]


def test_statistics_failure_terminally_fails_without_events(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    dependencies = _deps(repository, [])
    dependencies["calculate_statistics"] = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stats failed"))
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert result["status"] == "failed"
    connection = repository.connect(tmp_path / "db.sqlite")
    try:
        assert connection.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0
        assert connection.execute("select status from catalyst_research_jobs").fetchone()[0] == "failed"
    finally:
        connection.close()


def test_finalization_failure_terminally_fails_without_events(tmp_path, monkeypatch):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    original = repository.finalize_job_with_observations

    def fail_finalize(*args, **kwargs):
        raise RuntimeError("finalize failed")

    monkeypatch.setattr(repository, "finalize_job_with_observations", fail_finalize)
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=_deps(repository, [])))
    assert result["status"] == "failed"
    connection = repository.connect(tmp_path / "db.sqlite")
    try:
        assert connection.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0
        assert connection.execute("select status from catalyst_research_jobs").fetchone()[0] == "failed"
    finally:
        connection.close()
    assert original is not None


def test_source_promotion_failure_leaves_candidates_inactive(tmp_path, monkeypatch):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    dependencies = _deps(repository, [])
    monkeypatch.setattr(repository, "activate_adapter_with_source", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("source persistence failed")))
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert result["status"] == "failed"
    connection = repository.connect(tmp_path / "db.sqlite")
    try:
        assert connection.execute("select count(*) from catalyst_source_adapters where state = 'active'").fetchone()[0] == 0
    finally:
        connection.close()


def test_verified_source_passes_trusted_final_host_to_real_generator():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    seen = []

    async def generate(company, source, snapshot, **kwargs):
        seen.append((source["source_type"], source["allowed_hosts"]))
        assert source["allowed_hosts"] == ["ir.acme.example"]
        return {"source_type": source["source_type"], "source_url": source["url"], "allowed_hosts": ["ir.acme.example"], "adapter": {"source_type": source["source_type"]}}

    dependencies["generate_adapter"] = generate
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed"
    assert seen == [("press_releases", ["ir.acme.example"]), ("events_presentations", ["ir.acme.example"])]


def test_adapter_stages_receive_bound_fetch_that_rejects_offsite_redirect():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    requested = []

    async def fetch(url, **kwargs):
        requested.append((url, dict(kwargs)))
        if url.endswith("/offsite"):
            assert kwargs["allowed_hosts"] == ["ir.acme.example"]
            raise ValueError("page redirect host is not allowed")
        purpose = "Events Presentations" if "/events" in url else "Press Releases"
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme Investor Relations {purpose}</body></html>"}

    async def validate(adapter, snapshot, **kwargs):
        await kwargs["fetch_page"]("https://ir.acme.example/offsite")
        return {"status": "passed", "observations": [], "report": {}}

    dependencies.update({"fetch_page": fetch, "validate_candidate": validate})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed_partial"
    assert [url for url, _ in requested if url.endswith("/offsite")] == ["https://ir.acme.example/offsite"] * 2
    assert not any("evil" in url for url, _ in requested)


def test_bound_fetch_mock_transport_rejects_offsite_redirect_before_evil_request():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/offsite":
            return httpx.Response(302, headers={"Location": "https://evil.example/item"}, request=request)
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html><body>Acme archive</body></html>", request=request)

    client = HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None, max_attempts=1)

    def fetch(url, **kwargs):
        if url.endswith("/offsite"):
            return fetch_html_page(url, http_client=client, resolver=lambda host: ["93.184.216.34"], **kwargs)
        purpose = "Events Presentations" if "/events" in url else "Press Releases"
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme Investor Relations {purpose}</body></html>"}

    def validate(adapter, snapshot, **kwargs):
        kwargs["fetch_page"]("https://ir.acme.example/offsite")
        return {"status": "passed", "observations": [], "report": {}}

    dependencies.update({"fetch_page": fetch, "validate_candidate": validate})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed_partial"
    assert requests == ["https://ir.acme.example/offsite", "https://ir.acme.example/offsite"]
    assert not any("evil.example" in url for url in requests)


def test_executor_receives_same_bound_fetch_as_validator():
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    probes = []

    async def fetch(url, **kwargs):
        if url.endswith("/probe"):
            probes.append(dict(kwargs))
        purpose = "Events Presentations" if "/events" in url else "Press Releases"
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme Investor Relations {purpose}</body></html>"}

    def validate(adapter, snapshot, **kwargs):
        return {"status": "passed", "observations": [], "report": {}}

    async def execute(adapter, **kwargs):
        await kwargs["fetch_page"]("https://ir.acme.example/probe")
        return {"observations": [], "coverage_start": "2025-01-01", "coverage_end": "2026-01-01", "boundary_reached": True, "archive_exhausted": False, "page_count": 1, "item_count": 0}

    dependencies.update({"fetch_page": fetch, "validate_candidate": validate, "execute_adapter": execute})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed"
    assert len(probes) == 2
    assert all(item["allowed_hosts"] == ["ir.acme.example"] for item in probes)


def test_static_zero_archive_with_many_scripts_is_not_marked_javascript_unsupported(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)
    zero_archive = "<html><body><div id='app'><h1>Acme Press Releases</h1><p>No press releases available</p></div>" + "<script>analytics()</script>" * 6 + "</body></html>"

    async def fetch(url, **kwargs):
        if "/news" in url:
            return {"requested_url": url, "final_url": url, "html": zero_archive, "content_type": "text/html"}
        purpose = "Events Presentations" if "/events" in url else "Investor Relations Home"
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme {purpose}</body></html>"}

    def snapshot(page, **kwargs):
        source_type = kwargs["source"]["source_type"]
        return {**page, "source_type": source_type, "text": page["html"], "normalized": {"text": page["html"], "links": []}}

    dependencies.update({"fetch_page": fetch, "build_snapshot": snapshot})
    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=tmp_path / "db.sqlite", dependencies=dependencies))

    assert result["status"] == "completed"
    source = next(item for item in result["sources"] if item["source_type"] == "press_releases")
    assert source["extraction_status"] == "complete"
    assert "javascript_archive_unsupported" not in result["warnings"]


def test_loading_press_archive_shell_with_app_root_and_bundle_is_javascript_unsupported():
    html = "<html><body><div id='__next'><h1>Acme Press Releases</h1><p>Loading archive...</p></div>" + "<script src='/bundle.js'></script>" * 6 + "</body></html>"
    page = {"html": html}
    snapshot = {"normalized": {"text": html, "links": []}, "structural_html": html}

    assert _javascript_archive_shell(page, snapshot) is True


def test_loading_events_archive_shell_is_javascript_unsupported():
    html = "<html><body><main id='root'><h1>Acme Events &amp; Presentations</h1><p>Please wait while archive loads</p></main>" + "<script src='/events.bundle.js'></script>" * 6 + "</body></html>"
    page = {"html": html}
    snapshot = {"normalized": {"text": html, "links": []}, "structural_html": html}

    assert _javascript_archive_shell(page, snapshot) is True


def test_static_zero_short_phrase_wins_over_archive_shell_detection():
    html = "<html><body><div id='app'><h1>Acme Press Releases</h1><p>No releases currently available</p></div>" + "<script src='/analytics.js'></script>" * 6 + "</body></html>"
    page = {"html": html}
    snapshot = {"normalized": {"text": html, "links": []}, "structural_html": html}

    assert _javascript_archive_shell(page, snapshot) is False


def test_ordinary_script_enhanced_content_is_not_javascript_archive_shell():
    html = "<html><body><div id='app'><h1>Acme Investor Relations</h1><p>Contact our team for shareholder information.</p></div>" + "<script src='/analytics.js'></script>" * 6 + "</body></html>"
    page = {"html": html}
    snapshot = {"normalized": {"text": html, "links": [], "headings": [{"level": 1, "text": "Acme Investor Relations"}]}, "structural_html": html}

    assert _javascript_archive_shell(page, snapshot) is False


def test_hot_workflow_reuses_active_adapters_without_discovery_or_generation(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    calls = []
    dependencies = _deps(repository, calls)
    press_adapter = {
        "schema_version": "ir_source_adapter_v1", "ticker": "ACME", "source_type": "press_releases",
        "source_url": "https://ir.acme.example/news", "allowed_hosts": ["ir.acme.example"], "access_mode": "html",
        "extraction": {"item_selector": ".news-item", "date": {"selector": "time", "value_source": "text", "formats": ["%B %d, %Y"]}, "title": {"selector": ".news-title", "value_source": "text"}, "url": {"selector": ".news-title", "value_source": "attribute", "attribute": "href"}},
        "pagination": {"type": "next_link", "selector": "a.next"},
    }
    events_adapter = {
        "schema_version": "ir_source_adapter_v1", "ticker": "ACME", "source_type": "events_presentations",
        "source_url": "https://ir.acme.example/events", "allowed_hosts": ["ir.acme.example"], "access_mode": "html",
        "extraction": {"item_selector": ".event-item", "date": {"selector": "[data-date]", "value_source": "attribute", "attribute": "data-date", "formats": ["%Y-%m-%d"]}, "title": {"selector": ".event-title", "value_source": "text"}},
        "pagination": {"type": "none"},
    }
    adapters = {"press_releases": press_adapter, "events_presentations": events_adapter}
    pages = {
        "https://ir.acme.example/news": FIXTURES / "press_releases_page_1.html",
        "https://ir.acme.example/news?page=2": FIXTURES / "press_releases_page_2.html",
        "https://ir.acme.example/events": FIXTURES / "events_page.html",
    }
    fetch_urls = []

    def fetch(url, **kwargs):
        fetch_urls.append(url)
        path = pages[url]
        html = path.read_text()
        return {"requested_url": url, "final_url": url, "redirect_chain": [url], "content_type": "text/html", "response_bytes": len(html.encode()), "truncated": False, "html": html}

    def snapshot(page, **kwargs):
        purpose = "Events Presentations" if "/events" in page["requested_url"] else "Press Releases"
        return {"requested_url": page["requested_url"], "final_url": page["final_url"], "redirect_chain": [page["requested_url"]], "content_type": "text/html", "structural_html": page["html"], "text": f"Acme Investor Relations {purpose}", "normalized": {"text": page["html"], "links": []}}

    async def discover(*args, **kwargs):
        calls.append("discover")
        return {"status": "accepted", "sources": [{"source_type": "press_releases", "url": "https://ir.acme.example/news"}, {"source_type": "events_presentations", "url": "https://ir.acme.example/events"}], "warnings": [], "next_actions": []}

    async def generate(company, source, snapshot, **kwargs):
        calls.append(f"generate:{source['source_type']}")
        return {"adapter": adapters[source["source_type"]]}

    def validate(adapter, snapshot, **kwargs):
        return {"status": "passed", "observations": [], "report": {}}

    dependencies.update({"fetch_page": fetch, "build_snapshot": snapshot, "discover_sources": discover, "generate_adapter": generate, "validate_candidate": validate, "execute_adapter": __import__("app.agents.catalyst_research.adapters.executor", fromlist=["execute_adapter"]).execute_adapter, "validate_active_adapter": __import__("app.agents.catalyst_research.adapters.validator", fromlist=["validate_active_adapter"]).validate_active_adapter})
    request = {"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}
    cold = asyncio.run(run_research(request, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert cold["status"] == "completed"
    calls.clear()
    fetch_urls.clear()
    dependencies["discover_sources"] = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("discovery should not run"))
    dependencies["generate_adapter"] = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("generation should not run"))
    hot = asyncio.run(run_research(request, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert hot["status"] == "completed"
    assert all(source["execution_path"] == "hot" for source in hot["sources"])
    assert hot["call_counts"]["discovery"] == 0
    assert hot["call_counts"]["adapter_generation"] == 0
    assert hot["call_counts"]["event_extraction"] == 0
    assert {source["adapter_version"] for source in hot["sources"]} == {1}
    assert all(source["content_hash"] for source in hot["sources"])
    assert all(source["snapshot_hash"] for source in hot["sources"])
    assert all(fetch_urls.count(url) == 1 for url in pages)
    pages["https://ir.acme.example/news"] = FIXTURES / "press_releases_appended.html"
    appended = asyncio.run(run_research(request, db_path=tmp_path / "db.sqlite", dependencies=dependencies))
    assert appended["status"] == "completed"
    assert appended["observation_count"] == hot["observation_count"] + 1
    assert all(source["execution_path"] == "hot" for source in appended["sources"])
    assert appended["call_counts"]["discovery"] == 0
    assert appended["call_counts"]["adapter_generation"] == 0
    assert appended["call_counts"]["event_extraction"] == 0
    connection = repository.connect(tmp_path / "db.sqlite")
    try:
        provenance = connection.execute("select adapter_id, adapter_version, executor_version, content_hash from catalyst_ir_events where job_id = ?", (appended["job_id"],)).fetchall()
        assert len(provenance) == appended["observation_count"]
        assert all(row[0] and row[1] == 1 and row[2] and row[3] for row in provenance)
        runtime = connection.execute("select page_content_hashes_json, report_json from catalyst_adapter_validations where job_id = ? order by rowid desc limit 2", (appended["job_id"],)).fetchall()
        hashes = {value for row in runtime for value in __import__("json").loads(row[0])}
        assert hashes
        assert all(connection.execute("select 1 from catalyst_source_snapshots where content_hash = ?", (value,)).fetchone() for value in hashes)
        assert all("html" not in row[1] and "raw_html" not in row[1] and "structural_html" not in row[1] for row in runtime)
        assert repository.prune_unreferenced_snapshots(connection) == 0
    finally:
        connection.close()


def test_drift_marks_only_failed_active_adapter_stale_before_cold_recovery():
    from app.agents.catalyst_research.workflow import _run_source

    marked = []
    saved = []

    class Repository:
        def mark_adapter_stale(self, connection, adapter_id, stale_at):
            marked.append(adapter_id)

        def save_source(self, connection, source):
            saved.append(source)
            return source

    async def validate_active(*args, **kwargs):
        return {"status": "stale", "observations": [], "promotable_observations": [], "errors": ["selector drift"]}

    context = {
        "repository": Repository(), "connection": object(), "request": {"ticker": "ACME"},
        "job": {"job_id": "job", "requested_start": "2025-01-01", "requested_end": "2026-01-01"},
        "clock": datetime(2026, 1, 1, tzinfo=UTC), "fetch_page": lambda *args, **kwargs: None,
        "validate_active_adapter": validate_active, "warnings": [], "next_actions": [], "execution_paths": {},
        "url_resolver": None,
    }
    adapter = {"adapter_id": "adapter-1", "source_type": "press_releases", "adapter": {}}

    result = asyncio.run(_run_source(context, {}, "press_releases", adapter))

    assert result is None
    assert marked == ["adapter-1"]
    assert context["execution_paths"]["press_releases"] == "cold"
    assert "source_discovery_required" in context["warnings"]
    assert saved == []


def test_real_sqlite_drift_requires_discovery_and_preserves_prior_result_on_replacement_failure(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "drift.sqlite"
    connection = repository.connect(db_path)
    prior = repository.create_job(connection, {"ticker": "ACME", "years": 1}, {"name": "Acme Corporation", "cik": "123"}, datetime(2026, 9, 4, tzinfo=UTC))
    repository.start_job(connection, prior["job_id"], "2026-09-04T00:01:00+00:00")
    adapters = {}
    for source_type, url in (("press_releases", "https://ir.acme.example/news"), ("events_presentations", "https://ir.acme.example/events")):
        candidate = repository.create_adapter_candidate(connection, {"job_id": prior["job_id"], "ticker": "ACME", "source_type": source_type, "source_url": url, "adapter": {"source_type": source_type, "source_url": url, "allowed_hosts": ["ir.acme.example"]}})
        repository.record_adapter_validation(connection, {"adapter_id": candidate["adapter_id"], "job_id": prior["job_id"], "status": "passed", "report": {}})
        repository.activate_adapter(connection, candidate["adapter_id"], "2026-09-04T01:00:00+00:00")
        adapters[source_type] = candidate
    prior_sources = {}
    prior_events = []
    for source_type, url in (("press_releases", "https://ir.acme.example/news"), ("events_presentations", "https://ir.acme.example/events")):
        source = repository.save_source(connection, {"job_id": prior["job_id"], "ticker": "ACME", "source_type": source_type, "url": url, "acceptance_status": "accepted", "extraction_status": "complete", "active_adapter_id": adapters[source_type]["adapter_id"], "adapter_version": 1})
        prior_sources[source_type] = source
        date_key = "published_date" if source_type == "press_releases" else "event_date"
        prior_events.append({"source_id": source["source_id"], "ticker": "ACME", "source_type": source_type, date_key: "2025-06-01", "count_date": "2025-06-01", "title": f"Prior {source_type}", "url": f"https://ir.acme.example/{source_type}/prior"})
    repository.finalize_job_with_observations(connection, prior["job_id"], prior_events, [{"id": index, "earnings_state": "non_earnings", "classification_method": "rule_v1"} for index, _ in enumerate(prior_events, 1)], {"status": "completed", "statistics": {"total": 2}, "execution_paths": {"press_releases": "cold", "events_presentations": "cold"}, "call_counts": {"discovery": 1}})
    connection.close()

    calls = []

    async def resolve(request, **kwargs):
        return {"ticker": "ACME", "company_name": "Acme Corporation", "cik": 123}

    async def discover(company, **kwargs):
        calls.append(kwargs.get("source_types"))
        return {"status": "accepted", "sources": [{"source_type": "press_releases", "url": "https://ir.acme.example/news"}], "alternate_sources": [], "warnings": [], "next_actions": []}

    def fetch(url, **kwargs):
        return {"requested_url": url, "final_url": url, "content_type": "text/html", "response_bytes": 80, "html": "<html><body>Acme Press Releases archive</body></html>"}

    def snapshot(page, **kwargs):
        return {"requested_url": page["requested_url"], "final_url": page["final_url"], "content_type": "text/html", "structural_html": page["html"], "text": "Acme Press Releases archive", "normalized": {"text": "Acme Press Releases archive", "links": []}}

    def validate_active(adapter, **kwargs):
        source_type = adapter["source_type"]
        if source_type == "press_releases":
            page = kwargs["fetch_page"](adapter["source_url"])
            page_hash = hashlib.sha256(page["html"].encode()).hexdigest()
            return {"status": "stale", "observations": [], "promotable_observations": [], "errors": ["selector drift"], "report": {"safety_failures": ["selector drift"], "page_content_hashes": [page_hash]}, "page_content_hashes": [page_hash], "validator_version": "validator-v1", "executor_version": "executor-v1"}
        page = kwargs["fetch_page"](adapter["source_url"])
        page_hash = hashlib.sha256(page["html"].encode()).hexdigest()
        return {"status": "passed", "promotable_observations": [{"source_type": source_type, "title": "Healthy event", "count_date": "2025-07-01", "event_date": "2025-07-01", "url": "https://ir.acme.example/events/healthy"}], "execution": {"observations": [{"source_type": source_type, "title": "Healthy event", "count_date": "2025-07-01", "event_date": "2025-07-01", "url": "https://ir.acme.example/events/healthy"}], "boundary_reached": True, "page_count": 1, "item_count": 1, "content_hashes": [page_hash]}, "report": {"page_content_hashes": [page_hash]}, "page_content_hashes": [page_hash], "validator_version": "validator-v1", "executor_version": "executor-v1"}

    async def generate(company, source, snapshot, **kwargs):
        return {"adapter": {"source_type": source["source_type"]}}

    def validate_candidate(adapter, snapshot, **kwargs):
        return {"status": "passed", "observations": [], "report": {}}

    async def execute(adapter, **kwargs):
        raise ValueError("replacement selector failed")

    async def classify(events, **kwargs):
        return {"events": [{**event, "earnings_state": "non_earnings", "classification_method": "rule_v1"} for event in events], "llm_call_count": 0}

    def stats(events, sources, requested_window):
        return {"total": len(events)}

    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, db_path=db_path, dependencies={"repository": repository, "llm_client": object(), "models": {"adapter_generation": "adapter-model"}, "resolver": resolve, "discover_sources": discover, "fetch_page": fetch, "build_snapshot": snapshot, "validate_active_adapter": validate_active, "generate_adapter": generate, "validate_candidate": validate_candidate, "execute_adapter": execute, "classify_observations": classify, "calculate_statistics": stats}))

    assert result["status"] == "completed_partial"
    assert result["call_counts"]["discovery"] == 1
    assert calls == [{"ir_home", "earnings_results", "press_releases"}]
    connection = repository.connect(db_path)
    try:
        latest = repository.load_latest_result(connection, "ACME")
        assert latest["job_id"] == prior["job_id"]
        assert latest["latest_job_status"] == "completed_partial"
        assert connection.execute("select state from catalyst_source_adapters where adapter_id = ?", (adapters["press_releases"]["adapter_id"],)).fetchone()[0] == "stale"
        assert connection.execute("select state from catalyst_source_adapters where adapter_id = ?", (adapters["events_presentations"]["adapter_id"],)).fetchone()[0] == "active"
        stale_source = connection.execute("select snapshot_hash from catalyst_ir_sources where job_id = ? and source_type = 'press_releases' and extraction_status = 'discovery_required'", (result["job_id"],)).fetchone()
        assert stale_source and connection.execute("select 1 from catalyst_source_snapshots where content_hash = ?", (stale_source[0],)).fetchone()
        assert connection.execute("select extraction_status from catalyst_ir_sources where job_id = ? and source_type = 'press_releases' order by rowid desc limit 1", (result["job_id"],)).fetchone()[0] == "failed"
        assert connection.execute("select count(*) from catalyst_ir_events where job_id = ?", (prior["job_id"],)).fetchone()[0] == 2
        assert connection.execute("select status from catalyst_adapter_validations where adapter_id = ? order by rowid desc limit 1", (adapters["press_releases"]["adapter_id"],)).fetchone()[0] == "failed"
    finally:
        connection.close()


def test_hot_workflow_with_real_snapshot_builder_reuses_active_adapters(tmp_path):
    from app.agents.catalyst_research.adapters.executor import execute_adapter
    from app.agents.catalyst_research.adapters.validator import validate_active_adapter
    from app.agents.catalyst_research.extraction.html import build_structural_snapshot
    from app.agents.catalyst_research.persistence import repository

    db_path = tmp_path / "hot_real.sqlite"
    press_adapter = {
        "schema_version": "ir_source_adapter_v1", "ticker": "ACME", "source_type": "press_releases",
        "source_url": "https://ir.acme.example/news", "allowed_hosts": ["ir.acme.example"], "access_mode": "html",
        "extraction": {"item_selector": ".news-item", "date": {"selector": "time", "value_source": "text", "formats": ["%B %d, %Y"]}, "title": {"selector": ".news-title", "value_source": "text"}, "url": {"selector": ".news-title", "value_source": "attribute", "attribute": "href"}},
        "pagination": {"type": "next_link", "selector": "a.next"},
    }
    events_adapter = {
        "schema_version": "ir_source_adapter_v1", "ticker": "ACME", "source_type": "events_presentations",
        "source_url": "https://ir.acme.example/events", "allowed_hosts": ["ir.acme.example"], "access_mode": "html",
        "extraction": {"item_selector": ".event-item", "date": {"selector": "[data-date]", "value_source": "attribute", "attribute": "data-date", "formats": ["%Y-%m-%d"]}, "title": {"selector": ".event-title", "value_source": "text"}},
        "pagination": {"type": "none"},
    }
    connection = repository.connect(db_path)
    seed_job = repository.create_job(connection, {"ticker": "ACME", "years": 1}, {"name": "Acme Corporation", "cik": 123}, datetime(2026, 9, 4, tzinfo=UTC))
    repository.start_job(connection, seed_job["job_id"], "2026-09-04T00:01:00+00:00")
    for adapter in (press_adapter, events_adapter):
        candidate = repository.create_adapter_candidate(connection, {"job_id": seed_job["job_id"], "ticker": "ACME", "source_type": adapter["source_type"], "source_url": adapter["source_url"], "adapter": adapter})
        repository.record_adapter_validation(connection, {"adapter_id": candidate["adapter_id"], "job_id": seed_job["job_id"], "status": "passed", "report": {}})
        repository.activate_adapter(connection, candidate["adapter_id"], "2026-09-04T01:00:00+00:00")
    connection.close()

    pages = {
        "https://ir.acme.example/news": FIXTURES / "press_releases_page_1.html",
        "https://ir.acme.example/news?page=2": FIXTURES / "press_releases_page_2.html",
        "https://ir.acme.example/events": FIXTURES / "events_page.html",
    }

    def fetch(url, **kwargs):
        html = pages[url].read_text()
        return {"requested_url": url, "final_url": url, "redirect_chain": [url], "content_type": "text/html", "response_bytes": len(html.encode()), "truncated": False, "html": html}

    async def resolve(request, **kwargs):
        return {"ticker": "ACME", "company_name": "Acme Corporation", "cik": 123}

    async def discover(*args, **kwargs):
        raise AssertionError("discovery should not run")

    async def generate(*args, **kwargs):
        raise AssertionError("generation should not run")

    async def classify(events, **kwargs):
        return {"events": [{**event, "earnings_state": "non_earnings", "classification_method": "rule_v1"} for event in events], "llm_call_count": 0}

    def stats(events, sources, requested_window):
        return {"total": len(events)}

    dependencies = {
        "repository": repository, "llm_client": object(), "models": {"adapter_generation": "adapter-model"},
        "resolver": resolve, "discover_sources": discover, "generate_adapter": generate,
        "fetch_page": fetch, "build_snapshot": build_structural_snapshot,
        "validate_active_adapter": validate_active_adapter, "execute_adapter": execute_adapter,
        "classify_observations": classify, "calculate_statistics": stats,
    }
    request = {"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}
    hot = asyncio.run(run_research(request, db_path=db_path, dependencies=dependencies))
    assert hot["status"] == "completed"
    assert all(source["execution_path"] == "hot" for source in hot["sources"])
    assert hot["call_counts"]["discovery"] == 0
    assert hot["call_counts"]["adapter_generation"] == 0
    assert hot["call_counts"]["event_extraction"] == 0

    pages["https://ir.acme.example/news"] = FIXTURES / "press_releases_appended.html"
    appended = asyncio.run(run_research(request, db_path=db_path, dependencies=dependencies))
    assert appended["status"] == "completed"
    assert appended["observation_count"] == hot["observation_count"] + 1
    assert all(source["execution_path"] == "hot" for source in appended["sources"])
    assert appended["call_counts"]["discovery"] == 0
    assert appended["call_counts"]["adapter_generation"] == 0
    assert appended["call_counts"]["event_extraction"] == 0

    appended_hash = hashlib.sha256((FIXTURES / "press_releases_appended.html").read_text().encode()).hexdigest()
    connection = repository.connect(db_path)
    try:
        assert connection.execute("select 1 from catalyst_source_snapshots where content_hash = ?", (appended_hash,)).fetchone()
        states = [row[0] for row in connection.execute("select state from catalyst_source_adapters where ticker = 'ACME'").fetchall()]
        assert states == ["active", "active"]
    finally:
        connection.close()


def test_workflow_forwards_config_args_to_default_config_loaders(monkeypatch):
    from app.agents.catalyst_research import workflow

    seen = {}

    def inference(args=None, root=None):
        seen["inference"] = args
        return {"client": None, "models": {}, "warnings": []}

    def search(args=None, root=None):
        seen["search"] = args
        return {"provider": "none", "fallback": "none", "native_search_supported": "false", "tavily_api_key": None}

    monkeypatch.setattr(workflow, "load_inference_bundle", inference)
    monkeypatch.setattr(workflow, "load_search_config", search)
    repository = FakeRepository()
    calls = []
    dependencies = _deps(repository, calls)
    marker = object()
    dependencies["config_args"] = marker

    result = asyncio.run(run_research({"ticker": "ACME", "years": 1, "as_of": "2026-01-01"}, dependencies=dependencies))

    assert result["status"] == "completed"
    assert seen["inference"] is marker
    assert seen["search"] is marker


V1_1_COLLECTION_CONFIG = {
    "historical_query_limit": 16,
    "search_result_limit": 10,
    "unseen_url_limit": 200,
    "max_unseen_urls_per_channel": 200,
    "slice_days": 92,
    "max_historical_queries_per_channel": 16,
    "gap_lookback_days": 14,
    "max_gap_queries_per_channel": 2,
    "gap_search_interval_days": 7,
    "feed_failure_threshold": 3,
    "firecrawl_api_key": None,
    "firecrawl_base_url": None,
    "archive_enrichment_enabled": False,
}


def v1_1_registry(overrides=None):
    registry = {
        "ticker": "NVDA",
        "company_name": "NVIDIA Corporation",
        "cik": "1045810",
        "official_domains": ["nvidia.com", "nvidianews.nvidia.com"],
        "source_confidence": "high",
        "registry_version": 1,
    }
    registry.update(overrides or {})
    return registry


def v1_1_endpoint(overrides=None):
    endpoint = {
        "ticker": "NVDA",
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/rss",
        "domain": "nvidianews.nvidia.com",
        "status": "active",
        "confidence": "high",
    }
    endpoint.update(overrides or {})
    return endpoint


def v1_1_event(channel="press_releases", title="NVIDIA announces launch"):
    event = {
        "ticker": "NVDA",
        "source_type": channel,
        "title": title,
        "published_date": "2026-08-15",
        "count_date": "2026-08-15",
        "url": "https://nvidianews.nvidia.com/news/launch",
        "canonical_url": "https://nvidianews.nvidia.com/news/launch",
        "source_id": f"source_{channel}",
        "discovery_method": "rss",
        "discovery_methods": ["rss"],
    }
    if channel == "events_presentations":
        event["event_date"] = "2026-08-15"
    return event


def v1_1_channel_payload(events):
    days = sorted({event["count_date"] for event in events if event.get("count_date")})
    return {
        "coverage_status": "observed_partial" if events else "unsupported",
        "discovery_methods": ["rss"] if events else [],
        "observed_start": days[0] if days else None,
        "observed_end": days[-1] if days else None,
        "events": events,
        "sources": [],
        "warnings": [],
        "limit_state": [],
        "archive_boundary_proven": False,
    }


class FakeRegistryRepository:
    def __init__(self, registry=None, endpoints=None):
        self.calls = []
        self.registry = registry
        self.endpoints = list(endpoints or [])
        self.job = {
            "job_id": "cr_v1_1_test",
            "ticker": "NVDA",
            "requested_start": "2025-09-08",
            "requested_end": "2026-09-08",
            "status": "queued",
        }
        self.result = {"job_id": "cr_v1_1_test", "status": "queued"}
        self.search_attempts = []
        self.active_adapters = {}

    def connect(self, db_path=None):
        self.calls.append("connect")
        return object()

    def create_job(self, connection, request, company=None, now=None):
        self.calls.append("create")
        self.job.update({"ticker": request["ticker"], "mode": request.get("mode", "research"), "status": "queued"})
        return dict(self.job)

    def start_job(self, connection, job_id, started_at):
        self.calls.append("start")
        self.job["status"] = "running"

    def update_resolved_company(self, connection, job_id, company):
        self.calls.append("company")
        return dict(self.job)

    def load_company_registry(self, connection, ticker):
        self.calls.append("load_registry")
        return self.registry

    def load_source_endpoints(self, connection, ticker):
        self.calls.append("load_endpoints")
        return list(self.endpoints)

    def load_active_adapter(self, connection, ticker, source_type):
        self.calls.append(f"load_adapter:{source_type}")
        return self.active_adapters.get(source_type)

    def load_latest_gap_search_at(self, connection, ticker, channel):
        self.calls.append(f"gap_at:{channel}")
        return None

    def record_search_attempt(self, connection, attempt):
        self.calls.append("record_search_attempt")
        self.search_attempts.append(dict(attempt))
        return "csa_gap_1"

    def save_company_registry(self, connection, registry):
        self.calls.append("save_registry")
        self.registry = dict(registry)
        return dict(registry)

    def upsert_source_endpoint(self, connection, endpoint):
        self.calls.append("upsert_endpoint")
        return dict(endpoint)

    def record_endpoint_check(self, connection, check):
        self.calls.append("record_check")

    def update_endpoint_health(self, connection, endpoint_id, state):
        self.calls.append("update_health")

    def save_source(self, connection, source):
        self.calls.append(f"source:{source['source_type']}")
        return {**source, "source_id": f"source_{source['source_type']}"}

    def save_finalized_observations(self, connection, job_id, events, classifications):
        self.calls.append("save_observations")
        self.saved_events = list(events)

    def finalize_job(self, connection, job_id, result):
        self.calls.append("finalize")
        self.job["status"] = result["status"]
        self.result = {**self.result, **result, "status": result["status"]}

    def finalize_job_with_observations(self, connection, job_id, events, classifications, result):
        self.save_finalized_observations(connection, job_id, events, classifications)
        self.finalize_job(connection, job_id, result)

    def fail_job(self, connection, job_id, error_summary, **kwargs):
        self.calls.append("fail")
        self.job["status"] = "failed"
        self.result = {**self.result, "status": "failed", "error_summary": error_summary}

    def load_job_result(self, connection, job_id):
        self.calls.append("load_result")
        return {
            **self.result,
            "schema_version": RESULT_SCHEMA_VERSION,
            "observation_count": len(getattr(self, "saved_events", []) or []),
            "job_id": job_id,
        }


def mode_dependencies(calls, repository=None, **overrides):
    async def resolve(request, **kwargs):
        calls.append("resolve")
        return {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "cik": 1045810}

    async def discover_registry(company, **kwargs):
        calls.append("dep:discover_registry")
        return {
            "status": "accepted",
            "registry": v1_1_registry(),
            "endpoints": [v1_1_endpoint()],
            "warnings": [],
            "next_actions": [],
            "provider_provenance": [],
        }

    async def run_historical_backfill(company, request, *, endpoints, config, dependencies):
        calls.append("dep:run_historical_backfill")
        assert company["official_domains"]
        return {
            "ticker": "NVDA",
            "requested_window": {"start": "2025-09-08", "end": "2026-09-08"},
            "channels": {
                "press_releases": v1_1_channel_payload([v1_1_event()]),
                "events_presentations": v1_1_channel_payload([]),
                "earnings_results": v1_1_channel_payload([]),
            },
            "warnings": [],
        }

    async def run_daily_update(company, *, registry, endpoints, as_of, config, dependencies):
        calls.append("dep:run_daily_update")
        assert company["official_domains"]
        return {"as_of": as_of.isoformat(), "plan": {"items": []}, "feeds": [], "gaps": []}

    async def classify(events, **kwargs):
        calls.append("classify")
        return {
            "events": [{**event, "earnings_state": "non_earnings", "classification_method": "rule_v1"} for event in events],
            "llm_call_count": 0,
            "provenance": [],
        }

    def stats(events, sources, requested_window):
        calls.append("stats")
        return {"total": len(events)}

    def progress(stage, **details):
        calls.append(stage)

    dependencies = {
        "repository": repository or FakeRegistryRepository(),
        "llm_client": object(),
        "models": {"registry_selection": "registry-model", "classification": "classification-model"},
        "search_router": _UnavailableSearchRouter(),
        "resolver": resolve,
        "discover_registry": discover_registry,
        "run_historical_backfill": run_historical_backfill,
        "run_daily_update": run_daily_update,
        "classify_observations": classify,
        "calculate_statistics": stats,
        "progress": progress,
        "clock": datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        "collection_config": dict(V1_1_COLLECTION_CONFIG),
    }
    dependencies.update(overrides)
    return dependencies


@pytest.mark.parametrize(
    ("mode", "expected_stage"),
    [("research", "historical_backfill"), ("update", "daily_update"), ("rediscover", "rediscover")],
)
def test_run_research_dispatches_v1_1_mode(mode, expected_stage):
    calls = []
    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": mode},
            dependencies=mode_dependencies(calls, repository),
        )
    )
    assert expected_stage in calls
    assert result["schema_version"] == RESULT_SCHEMA_VERSION
    assert result["status"] in {"completed", "completed_partial", "unsupported"}


def test_research_without_registry_discovers_once_and_backfills_without_adapters():
    calls = []
    repository = FakeRegistryRepository(registry=None, endpoints=[])
    dependencies = mode_dependencies(calls, repository)
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            dependencies=dependencies,
        )
    )
    assert calls.count("discover_registry") == 1
    assert calls.count("historical_backfill") == 1
    assert not [call for call in repository.calls if call.startswith("load_adapter:")]
    assert result["call_counts"]["adapter_generation"] == 0
    assert result["status"] == "completed_partial"
    assert result["observation_count"] == 1


def test_research_with_healthy_registry_skips_discovery():
    calls = []
    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            dependencies=mode_dependencies(calls, repository),
        )
    )
    assert "discover_registry" not in calls
    assert calls.count("historical_backfill") == 1


def test_update_with_healthy_registry_makes_zero_discovery_calls():
    calls = []
    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "update"},
            dependencies=mode_dependencies(calls, repository),
        )
    )
    assert "discover_registry" not in calls
    assert "historical_backfill" not in calls
    assert calls.count("daily_update") == 1
    assert result["call_counts"]["discovery"] == 0
    assert result["call_counts"]["adapter_generation"] == 0


def test_update_without_registry_is_unsupported_with_source_review_action():
    calls = []
    repository = FakeRegistryRepository(registry=None, endpoints=[])
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "update"},
            dependencies=mode_dependencies(calls, repository),
        )
    )
    assert result["status"] == "unsupported"
    assert "daily_update" not in calls
    assert result["next_actions"]


def test_rediscovery_failure_preserves_registry_and_prior_dataset(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "rediscover.sqlite"
    connection = repository.connect(db_path)
    registry = repository.save_company_registry(connection, v1_1_registry())
    repository.upsert_source_endpoint(connection, v1_1_endpoint())
    prior = repository.create_job(connection, {"ticker": "NVDA", "years": 1, "mode": "research"}, {"company_name": "NVIDIA Corporation", "cik": "1045810"}, datetime(2026, 9, 1, tzinfo=UTC))
    repository.start_job(connection, prior["job_id"], "2026-09-01T00:01:00+00:00")
    prior_source = repository.save_source(
        connection,
        {
            "job_id": prior["job_id"],
            "ticker": "NVDA",
            "source_type": "press_releases",
            "url": "https://nvidianews.nvidia.com/news",
            "acceptance_status": "accepted",
            "extraction_status": "complete",
        },
    )
    prior_event = {
        "source_id": prior_source["source_id"],
        "ticker": "NVDA",
        "source_type": "press_releases",
        "title": "NVIDIA prior release",
        "published_date": "2026-08-01",
        "count_date": "2026-08-01",
        "url": "https://nvidianews.nvidia.com/news/prior",
    }
    repository.finalize_job_with_observations(
        connection,
        prior["job_id"],
        [prior_event],
        [{"id": 1, "earnings_state": "non_earnings", "classification_method": "rule_v1"}],
        {"status": "completed", "statistics": {"total": 1}, "execution_paths": {}, "call_counts": {}},
    )
    connection.close()

    calls = []

    async def failing_discovery(company, **kwargs):
        calls.append("discover_registry")
        return {
            "status": "insufficient",
            "registry": None,
            "endpoints": [],
            "warnings": ["search provider chain is unavailable"],
            "next_actions": ["provide a verified official source override"],
            "provider_provenance": [],
        }

    dependencies = mode_dependencies(calls, repository, **{"discover_registry": failing_discovery})
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "rediscover"},
            db_path=db_path,
            dependencies=dependencies,
        )
    )
    assert result["status"] == "completed_partial"
    connection = repository.connect(db_path)
    try:
        assert connection.execute("select count(*) from catalyst_ir_events where job_id = ?", (prior["job_id"],)).fetchone()[0] == 1
        assert connection.execute("select count(*) from catalyst_ir_events where job_id = ?", (result["job_id"],)).fetchone()[0] == 0
        preserved = repository.load_company_registry(connection, "NVDA")
        assert preserved["registry_version"] == registry["registry_version"]
        assert preserved["official_domains"] == registry["official_domains"]
    finally:
        connection.close()


def test_rediscovery_success_increments_registry_version(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "rediscover_ok.sqlite"
    connection = repository.connect(db_path)
    registry = repository.save_company_registry(connection, v1_1_registry())
    repository.upsert_source_endpoint(connection, v1_1_endpoint())
    connection.close()
    calls = []

    async def rediscover(company, **kwargs):
        calls.append("discover_registry")
        existing = repository.load_company_registry(kwargs["connection"], "NVDA")
        saved = repository.save_company_registry(
            kwargs["connection"],
            {**v1_1_registry(), "official_domains": [*existing["official_domains"], "news.nvidia.com"], "registry_version": existing["registry_version"] + 1},
        )
        return {
            "status": "accepted",
            "registry": saved,
            "endpoints": [v1_1_endpoint()],
            "warnings": [],
            "next_actions": [],
            "provider_provenance": [],
        }

    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "rediscover"},
            db_path=db_path,
            dependencies=mode_dependencies(calls, repository, **{"discover_registry": rediscover}),
        )
    )
    assert result["status"] == "completed"
    connection = repository.connect(db_path)
    try:
        updated = repository.load_company_registry(connection, "NVDA")
        assert updated["registry_version"] == registry["registry_version"] + 1
        assert "news.nvidia.com" in updated["official_domains"]
    finally:
        connection.close()


def test_v1_1_partial_feed_events_finalize_atomically_once():
    calls = []
    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            dependencies=mode_dependencies(calls, repository),
        )
    )
    assert result["status"] == "completed_partial"
    assert repository.calls.count("save_observations") == 1
    assert repository.saved_events[0]["earnings_state"] == "non_earnings"
    finalize_index = repository.calls.index("finalize")
    assert repository.calls[finalize_index - 1] == "save_observations"


def test_v1_1_ambiguous_classification_downgrades_status():
    calls = []

    async def classify(events, **kwargs):
        calls.append("classify")
        return {
            "events": [{**event, "earnings_state": "ambiguous", "classification_method": "llm_v1"} for event in events],
            "llm_call_count": 1,
            "provenance": [],
        }

    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            dependencies=mode_dependencies(calls, repository, **{"classify_observations": classify}),
        )
    )
    assert result["status"] == "completed_partial"
    assert "classification_ambiguous" in result["warnings"]


def test_v1_1_manual_review_candidates_keep_job_partial():
    calls = []

    async def run_historical_backfill(company, request, *, endpoints, config, dependencies):
        calls.append("historical_backfill")
        payload = v1_1_channel_payload([v1_1_event()])
        payload["warnings"] = ["manual_review_required"]
        return {
            "ticker": "NVDA",
            "requested_window": {"start": "2025-09-08", "end": "2026-09-08"},
            "channels": {
                "press_releases": payload,
                "events_presentations": v1_1_channel_payload([]),
                "earnings_results": v1_1_channel_payload([]),
            },
            "warnings": ["manual_review_required"],
        }

    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            dependencies=mode_dependencies(calls, repository, **{"run_historical_backfill": run_historical_backfill}),
        )
    )
    assert result["status"] == "completed_partial"
    assert "manual_review_required" in result["warnings"]


def test_v1_1_firecrawl_absence_does_not_fail_job_and_builds_one_router(tmp_path):
    ingestion = __import__("app.agents.catalyst_research.ingestion", fromlist=["ingestion"])
    backfill = __import__("app.agents.catalyst_research.backfill", fromlist=["backfill"])
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "firecrawl_absent.sqlite"
    connection = repository.connect(db_path)
    repository.save_company_registry(connection, v1_1_registry())
    repository.upsert_source_endpoint(connection, v1_1_endpoint())
    connection.close()

    routers = []

    real_ingest = ingestion.ingest_candidates

    async def recording_ingest(candidates, **kwargs):
        routers.append(kwargs["extraction_router"])
        return await real_ingest(candidates, **kwargs)

    async def fetch_feed(endpoint, *, http_client=None, approved_domains=None):
        return {
            "format": "rss",
            "items": [
                {
                    "external_guid": "guid-1",
                    "title": "NVIDIA announces launch",
                    "url": "https://nvidianews.nvidia.com/news/launch",
                    "published_at": "2026-08-15T12:00:00+00:00",
                    "summary": "summary",
                    "discovery_method": "rss",
                    "endpoint_id": endpoint["endpoint_id"],
                }
            ],
            "item_count": 1,
            "newest_item_at": "2026-08-15T12:00:00+00:00",
            "content_hash": "hash-1",
            "final_url": endpoint["url"],
        }

    calls = []
    dependencies = mode_dependencies(
        calls,
        repository,
        **{
            "run_historical_backfill": backfill.run_historical_backfill,
            "ingest_candidates": recording_ingest,
            "fetch_feed": fetch_feed,
            "collection_config": {**V1_1_COLLECTION_CONFIG, "archive_enrichment_enabled": False},
        },
    )
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            db_path=db_path,
            dependencies=dependencies,
        )
    )
    assert result["status"] == "completed_partial"
    assert len(routers) == 3
    assert len({id(router) for router in routers}) == 1
    assert result["observation_count"] == 1


def test_v1_1_optional_adapter_failure_cannot_discard_feed_events(tmp_path):
    backfill = __import__("app.agents.catalyst_research.backfill", fromlist=["backfill"])
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "adapter_failure.sqlite"
    connection = repository.connect(db_path)
    repository.save_company_registry(connection, v1_1_registry())
    repository.upsert_source_endpoint(connection, v1_1_endpoint())
    connection.close()

    async def failing_adapter(*, channel, company, request):
        raise RuntimeError("adapter exploded")

    async def fetch_feed(endpoint, *, http_client=None, approved_domains=None):
        return {
            "format": "rss",
            "items": [
                {
                    "external_guid": "guid-1",
                    "title": "NVIDIA announces launch",
                    "url": "https://nvidianews.nvidia.com/news/launch",
                    "published_at": "2026-08-15T12:00:00+00:00",
                    "summary": "summary",
                    "discovery_method": "rss",
                    "endpoint_id": endpoint["endpoint_id"],
                }
            ],
            "item_count": 1,
            "newest_item_at": "2026-08-15T12:00:00+00:00",
            "content_hash": "hash-1",
            "final_url": endpoint["url"],
        }

    calls = []
    dependencies = mode_dependencies(
        calls,
        repository,
        **{
            "run_historical_backfill": backfill.run_historical_backfill,
            "adapter": failing_adapter,
            "fetch_feed": fetch_feed,
            "collection_config": {**V1_1_COLLECTION_CONFIG, "archive_enrichment_enabled": True},
        },
    )
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            db_path=db_path,
            dependencies=dependencies,
        )
    )
    assert result["status"] == "completed_partial"
    assert result["observation_count"] == 1
    assert "archive_adapter_failed" in result["warnings"]


def test_v1_1_hot_adapter_enrichment_still_executes_when_enabled(tmp_path):
    backfill = __import__("app.agents.catalyst_research.backfill", fromlist=["backfill"])
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "adapter_enrichment.sqlite"
    connection = repository.connect(db_path)
    repository.save_company_registry(connection, v1_1_registry())
    repository.upsert_source_endpoint(connection, v1_1_endpoint())
    connection.close()

    async def healthy_adapter(*, channel, company, request):
        if channel != "press_releases":
            return {"status": "complete", "events": [], "source": None}
        connection = repository.connect(db_path)
        try:
            source = repository.save_source(
                connection,
                {
                    "job_id": request["job_id"],
                    "ticker": "NVDA",
                    "source_type": channel,
                    "url": "https://nvidianews.nvidia.com/news",
                    "acceptance_status": "accepted",
                    "extraction_status": "complete",
                    "execution_path": "hot",
                },
            )
        finally:
            connection.close()
        return {
            "status": "complete",
            "boundary_reached": True,
            "events": [
                {
                    "source_type": channel,
                    "title": "NVIDIA archived release",
                    "published_date": "2026-07-01",
                    "count_date": "2026-07-01",
                    "url": "https://nvidianews.nvidia.com/news/archived",
                }
            ],
            "source": source,
        }

    async def fetch_feed(endpoint, *, http_client=None, approved_domains=None):
        return {
            "format": "rss",
            "items": [
                {
                    "external_guid": "guid-1",
                    "title": "NVIDIA announces launch",
                    "url": "https://nvidianews.nvidia.com/news/launch",
                    "published_at": "2026-08-15T12:00:00+00:00",
                    "summary": "summary",
                    "discovery_method": "rss",
                    "endpoint_id": endpoint["endpoint_id"],
                }
            ],
            "item_count": 1,
            "newest_item_at": "2026-08-15T12:00:00+00:00",
            "content_hash": "hash-1",
            "final_url": endpoint["url"],
        }

    calls = []
    dependencies = mode_dependencies(
        calls,
        repository,
        **{
            "run_historical_backfill": backfill.run_historical_backfill,
            "adapter": healthy_adapter,
            "fetch_feed": fetch_feed,
            "collection_config": {**V1_1_COLLECTION_CONFIG, "archive_enrichment_enabled": True},
        },
    )
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            db_path=db_path,
            dependencies=dependencies,
        )
    )
    assert result["status"] == "completed_partial"
    assert result["observation_count"] == 2


def test_v1_1_unexpected_persistence_failure_fails_with_sanitized_summary(tmp_path, monkeypatch):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "persist_failure.sqlite"
    original = repository.finalize_job_with_observations

    def fail_finalize(*args, **kwargs):
        raise RuntimeError("insert failed api_key=secret-token")

    monkeypatch.setattr(repository, "finalize_job_with_observations", fail_finalize)
    calls = []
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            db_path=db_path,
            dependencies=mode_dependencies(calls, repository),
        )
    )
    assert result["status"] == "failed"
    assert "secret-token" not in str(result)
    connection = repository.connect(db_path)
    try:
        assert connection.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0
        assert connection.execute("select status from catalyst_research_jobs").fetchone()[0] == "failed"
    finally:
        connection.close()
    assert original is not None


def test_v1_1_interrupted_run_leaves_no_promoted_event_rows(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "interrupted.sqlite"
    calls = []

    async def classify(events, **kwargs):
        raise RuntimeError("classification crashed")

    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            db_path=db_path,
            dependencies=mode_dependencies(calls, repository, **{"classify_observations": classify}),
        )
    )
    assert result["status"] == "failed"
    connection = repository.connect(db_path)
    try:
        assert connection.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0
    finally:
        connection.close()


def test_v1_1_update_gap_search_records_incremental_gap_attempts(tmp_path):
    repository = __import__("app.agents.catalyst_research.persistence.repository", fromlist=["repository"])
    db_path = tmp_path / "gap_attempts.sqlite"
    connection = repository.connect(db_path)
    repository.save_company_registry(connection, v1_1_registry())
    repository.upsert_source_endpoint(
        connection,
        v1_1_endpoint({"status": "failing", "consecutive_failures": 3, "last_checked_at": "2026-09-08T00:00:00+00:00"}),
    )
    connection.close()

    async def execute_query(query):
        return [
            {
                "url": "https://nvidianews.nvidia.com/news/gap-item",
                "title": "NVIDIA gap item",
                "snippet": "NVIDIA announces",
                "published_date": "2026-09-07",
                "provider_rank": 1,
            }
        ]

    class ManualRouter:
        def extract(self, candidate, *, company, approved_domains):
            return {"status": "manual_review_required", "url": candidate["url"], "extraction_provider": "manual"}

    calls = []
    dependencies = mode_dependencies(
        calls,
        repository,
        **{
            "run_daily_update": __import__("app.agents.catalyst_research.scheduler", fromlist=["scheduler"]).run_daily_update,
            "execute_query": execute_query,
            "extraction_router": ManualRouter(),
        },
    )
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "update"},
            db_path=db_path,
            dependencies=dependencies,
        )
    )
    assert result["status"] in {"completed", "completed_partial"}
    connection = repository.connect(db_path)
    try:
        attempts = connection.execute(
            "select search_purpose, completed_at, outcome from catalyst_search_attempts where job_id = ?",
            (result["job_id"],),
        ).fetchall()
        assert attempts
        assert all(attempt[0] == "incremental_gap_check" for attempt in attempts)
        assert all(attempt[1] for attempt in attempts)
        assert repository.load_latest_gap_search_at(connection, "NVDA", "press_releases") is not None
    finally:
        connection.close()


def test_v1_1_research_real_statistics_accept_multiple_sources_per_channel():
    calls = []
    first = v1_1_event(title="NVIDIA announces launch")
    second = v1_1_event(title="NVIDIA announces partnership")
    second.update(
        {
            "published_date": "2026-08-20",
            "count_date": "2026-08-20",
            "url": "https://nvidianews.nvidia.com/news/partnership",
            "canonical_url": "https://nvidianews.nvidia.com/news/partnership",
            "source_id": "source_press_releases_2",
        }
    )

    async def run_backfill(company, request, *, endpoints, config, dependencies):
        calls.append("dep:run_historical_backfill")
        press_payload = v1_1_channel_payload([first, second])
        press_payload["sources"] = [
            {
                "source_type": "press_releases",
                "source_id": "source_press_releases_1",
                "url": first["url"],
                "extraction_status": "complete",
            },
            {
                "source_type": "press_releases",
                "source_id": "source_press_releases_2",
                "url": second["url"],
                "extraction_status": "complete",
            },
        ]
        return {
            "ticker": "NVDA",
            "requested_window": {"start": "2025-09-08", "end": "2026-09-08"},
            "channels": {
                "press_releases": press_payload,
                "events_presentations": v1_1_channel_payload([]),
                "earnings_results": v1_1_channel_payload([]),
            },
            "warnings": [],
        }

    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=[v1_1_endpoint()])
    dependencies = mode_dependencies(
        calls,
        repository,
        **{"run_historical_backfill": run_backfill, "calculate_statistics": catalyst_statistics.calculate_statistics},
    )
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "research"},
            dependencies=dependencies,
        )
    )
    assert result["status"] == "completed_partial"
    statistics = result["statistics"]
    assert statistics["press_releases"]["coverage_status"] == "observed_partial"
    assert statistics["press_releases"]["observed_total"] == 2
    assert statistics["press_releases"]["observed_non_earnings"] == 2
    assert statistics["press_releases"]["observed_start"] == "2026-08-15"
    assert statistics["press_releases"]["observed_end"] == "2026-08-20"
    assert "observed_total" in statistics["events_presentations"]
    assert statistics["events_presentations"]["coverage_status"] == "unsupported"
    assert statistics["events_presentations"]["observed_total"] == 0


def test_v1_1_update_real_statistics_describe_run_observation():
    calls = []

    async def fetch_feed(endpoint, **kwargs):
        if endpoint.get("channel") == "press_releases":
            return {
                "items": [
                    {
                        "url": "https://nvidianews.nvidia.com/news/daily-item",
                        "title": "NVIDIA daily item",
                        "published_date": "2026-09-07",
                    }
                ],
                "newest_item_at": "2026-09-07T00:00:00+00:00",
            }
        return {"items": []}

    async def ingest_candidates(candidates, **kwargs):
        channel = kwargs.get("channel")
        events = []
        sources = []
        for index, candidate in enumerate(candidates):
            url = candidate.get("url")
            events.append(
                {
                    "ticker": "NVDA",
                    "source_type": channel,
                    "title": candidate.get("title"),
                    "published_date": candidate.get("published_date"),
                    "count_date": candidate.get("published_date"),
                    "url": url,
                    "canonical_url": url,
                    "discovery_method": "rss",
                    "discovery_methods": ["rss"],
                }
            )
            sources.append(
                {
                    "source_type": channel,
                    "source_id": f"source_{channel}_{index}",
                    "url": url,
                    "extraction_status": "complete",
                }
            )
        return {"events": events, "sources": sources}

    endpoints = [
        v1_1_endpoint({"endpoint_id": "ep_press"}),
        v1_1_endpoint(
            {
                "endpoint_id": "ep_events",
                "channel": "events_presentations",
                "url": "https://nvidia.com/events/rss",
                "domain": "nvidia.com",
            }
        ),
    ]
    repository = FakeRegistryRepository(registry=v1_1_registry(), endpoints=endpoints)
    dependencies = mode_dependencies(
        calls,
        repository,
        **{
            "run_daily_update": catalyst_scheduler.run_daily_update,
            "fetch_feed": fetch_feed,
            "ingest_candidates": ingest_candidates,
            "record_endpoint_check": lambda check: repository.calls.append("record_check"),
            "update_endpoint_health": lambda endpoint_id, health: repository.calls.append("update_health"),
            "calculate_statistics": catalyst_statistics.calculate_statistics,
        },
    )
    result = asyncio.run(
        run_research(
            {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "update"},
            dependencies=dependencies,
        )
    )
    assert result["status"] == "completed"
    statistics = result["statistics"]
    press = statistics["press_releases"]
    assert press["coverage_status"] == "observed_partial"
    assert press["observed_total"] == 1
    assert press["observed_start"] == "2026-09-07"
    assert press["observed_end"] == "2026-09-07"
    assert press["discovery_methods"] == ["rss"]
    events_channel = statistics["events_presentations"]
    assert events_channel["coverage_status"] == "missing"
    assert events_channel["observed_total"] == 0
    assert events_channel["coverage_warning"]


def test_v1_1_explicit_mode_requires_registry_persistence():
    class LegacyRepository(FakeRegistryRepository):
        load_company_registry = None
        load_source_endpoints = None

    calls = []
    with pytest.raises(ValueError, match="registry persistence"):
        asyncio.run(
            run_research(
                {"ticker": "NVDA", "years": 1, "as_of": "2026-09-08", "mode": "update"},
                dependencies=mode_dependencies(calls, LegacyRepository()),
            )
        )
