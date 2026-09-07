import asyncio
from datetime import UTC, datetime

import httpx

from app.agents.catalyst_research.workflow import _javascript_archive_shell, run_research
from app.agents.catalyst_research.extraction.pages import fetch_html_page
from app.http_client import HttpClient


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

    async def fetch(url, **kwargs):
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
