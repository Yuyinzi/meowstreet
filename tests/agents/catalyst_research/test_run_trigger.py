import asyncio
from datetime import UTC, datetime

import pytest

from app.agents.catalyst_research import run_trigger
from app.agents.catalyst_research.persistence import repository


@pytest.fixture(autouse=True)
def _clear_in_flight():
    run_trigger._IN_FLIGHT.clear()
    yield
    run_trigger._IN_FLIGHT.clear()


def _patched_connect(tmp_path, monkeypatch):
    db_path = tmp_path / "market_data.sqlite"
    original_connect = repository.connect
    monkeypatch.setattr(
        run_trigger.repository, "connect", lambda *args, **kwargs: original_connect(db_path)
    )
    return original_connect(db_path)


def _job(con, ticker="INTC", status="queued", now=None):
    created = now or datetime.now(UTC)
    job = repository.create_job(con, {"ticker": ticker, "years": 4, "mode": "research"}, now=created)
    if status == "running":
        repository.start_job(con, job["job_id"], created.isoformat())
    elif status == "failed":
        repository.start_job(con, job["job_id"], created.isoformat())
        repository.fail_job(con, job["job_id"], "boom", completed_at=created.isoformat())
    return job


def test_load_active_job_returns_latest_nonterminal_job(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    try:
        job = _job(con, status="running")
        active = repository.load_active_job(con, "intc")
        assert active is not None
        assert active["job_id"] == job["job_id"]
        assert active["status"] == "running"
        assert active["started_at"] is not None
    finally:
        con.close()


def test_load_active_job_ignores_terminal_jobs(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    try:
        _job(con, status="failed")
        assert repository.load_active_job(con, "INTC") is None
    finally:
        con.close()


def test_load_active_job_ignores_stale_jobs(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    try:
        created = datetime(2026, 9, 15, tzinfo=UTC)
        job = _job(con, status="running", now=created)
        fresh = datetime(2026, 9, 15, 0, 30, tzinfo=UTC)
        assert repository.load_active_job(con, "INTC", now=fresh)["job_id"] == job["job_id"]
        stale = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
        assert repository.load_active_job(con, "INTC", now=stale) is None
    finally:
        con.close()


def test_load_active_job_validates_max_age(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    try:
        with pytest.raises(ValueError, match="max age minutes must be a positive integer"):
            repository.load_active_job(con, "INTC", max_age_minutes=0)
    finally:
        con.close()


def test_research_trigger_state_ready_when_nothing_exists(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    try:
        assert run_trigger.research_trigger_state(con, "intc") == {
            "ticker": "INTC",
            "run_status": "ready",
        }
    finally:
        con.close()


def test_research_trigger_state_already_running(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    try:
        job = _job(con, status="running")
        state = run_trigger.research_trigger_state(con, "INTC")
        assert state["run_status"] == "already_running"
        assert state["job_id"] == job["job_id"]
    finally:
        con.close()


def test_research_trigger_state_already_researched(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    monkeypatch.setattr(
        run_trigger.repository, "load_latest_result", lambda con, ticker: {"job_id": "cr_1"}
    )
    try:
        assert run_trigger.research_trigger_state(con, "INTC")["run_status"] == "already_researched"
    finally:
        con.close()


def test_launch_research_starts_background_run(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    requests = []

    async def fake_runner(request):
        requests.append(request)

    async def scenario():
        result = await run_trigger.launch_research("intc", runner=fake_runner)
        assert result == {"ticker": "INTC", "run_status": "started"}
        assert "INTC" in run_trigger._IN_FLIGHT
        await asyncio.sleep(0.05)
        assert requests == [{"ticker": "INTC", "years": 4, "mode": "research"}]
        assert "INTC" not in run_trigger._IN_FLIGHT

    try:
        asyncio.run(scenario())
    finally:
        con.close()


def test_launch_research_dedupes_in_flight_ticker(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    calls = []

    async def scenario():
        release = asyncio.Event()

        async def blocking_runner(request):
            calls.append(request)
            await release.wait()

        first = await run_trigger.launch_research("INTC", runner=blocking_runner)
        second = await run_trigger.launch_research("INTC", runner=blocking_runner)
        assert first["run_status"] == "started"
        assert second == {"ticker": "INTC", "run_status": "already_running"}
        release.set()
        await asyncio.sleep(0.05)
        assert len(calls) == 1
        assert "INTC" not in run_trigger._IN_FLIGHT

    try:
        asyncio.run(scenario())
    finally:
        con.close()


def test_launch_research_short_circuits_when_already_researched(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    monkeypatch.setattr(
        run_trigger.repository, "load_latest_result", lambda con, ticker: {"job_id": "cr_1"}
    )
    calls = []

    async def fake_runner(request):
        calls.append(request)

    async def scenario():
        result = await run_trigger.launch_research("INTC", runner=fake_runner)
        assert result == {"ticker": "INTC", "run_status": "already_researched"}
        await asyncio.sleep(0.05)
        assert calls == []

    try:
        asyncio.run(scenario())
    finally:
        con.close()


def test_launch_research_runner_failure_releases_in_flight(tmp_path, monkeypatch):
    con = _patched_connect(tmp_path, monkeypatch)
    attempts = []

    async def failing_runner(request):
        attempts.append(request)
        raise RuntimeError("provider down")

    async def scenario():
        result = await run_trigger.launch_research("INTC", runner=failing_runner)
        assert result["run_status"] == "started"
        await asyncio.sleep(0.05)
        assert "INTC" not in run_trigger._IN_FLIGHT
        retry = await run_trigger.launch_research("INTC", runner=failing_runner)
        assert retry["run_status"] == "started"
        await asyncio.sleep(0.05)
        assert len(attempts) == 2

    try:
        asyncio.run(scenario())
    finally:
        con.close()


@pytest.mark.parametrize(
    "ticker, years",
    [("", 4), ("   ", 4), ("INTC", 0), ("INTC", 5), ("INTC", True)],
)
def test_launch_research_validates_inputs(tmp_path, monkeypatch, ticker, years):
    _patched_connect(tmp_path, monkeypatch)

    async def scenario():
        with pytest.raises(ValueError):
            await run_trigger.launch_research(ticker, years=years, runner=None)

    asyncio.run(scenario())
