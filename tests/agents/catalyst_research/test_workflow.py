import asyncio
from datetime import UTC, datetime

from app.agents.catalyst_research.workflow import run_research


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

    def save_finalized_observations(self, connection, job_id, events, classifications):
        self.calls.append("save_observations")
        assert events
        self.saved_events = events

    def finalize_job(self, connection, job_id, result):
        self.calls.append("finalize")
        self.job["status"] = result["status"]
        self.result = {**self.result, **result, "status": result["status"]}

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
    assert repository.calls[-2:] == ["finalize", "load_result"]


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
        return {"requested_url": url, "final_url": url, "html": f"<html><body>Acme {purpose}</body></html>"}

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
    assert "fetch:https://ir.acme.example/news" in calls
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
