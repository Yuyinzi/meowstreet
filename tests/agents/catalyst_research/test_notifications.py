import asyncio
import json

import pytest

from app.agents.catalyst_research import notifications
from app.db import job_notifications as db


@pytest.mark.parametrize("status,expected", [
    ("completed", "succeeded"), ("completed_partial", "completed_partial"),
    ("unsupported", "unsupported"), ("failed", "failed"), ("queued", "failed"), (None, "failed"),
])
def test_research_result_preserves_coverage_semantics(status, expected):
    async def operation(request, **kwargs):
        kwargs["dependencies"]["progress"]("ingest_candidate", url="https://private/token", index=1)
        return {"status": status, "job_id": "cr_test", "observation_count": 3, "error_summary": "private-token"}

    result = asyncio.run(notifications.run_with_notifications(operation, {"ticker": "nvda", "years": 1, "mode": "research"}))
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    detail = db.load_run(con, run["run_id"])
    assert result["status"] == status
    assert run["target"] == "NVDA"
    assert run["status"] == expected
    assert run["details"]["research_job_id"] == "cr_test"
    assert "private" not in json.dumps(detail)
    assert all(child["status"] != "running" for child in detail["children"])
    assert len(db.events_after(con, 0)["events"]) == 2
    con.close()


def test_existing_progress_callback_and_background_origin_are_preserved():
    stages = []

    def progress(stage, **details):
        stages.append((stage, details))

    async def operation(request, **kwargs):
        kwargs["dependencies"]["progress"]("historical_backfill", channels="press_releases")
        return {"status": "completed"}

    with notifications.background_origin():
        asyncio.run(notifications.run_with_notifications(operation, {"ticker": "AAPL"}, dependencies={"progress": progress}))
    assert stages == [("historical_backfill", {"channels": "press_releases"})]
    con = db.connect()
    assert db.list_runs(con)["runs"][0]["origin"] == "background"
    con.close()


@pytest.mark.parametrize("exception,expected", [(ValueError("private failure"), "failed"), (asyncio.CancelledError(), "interrupted"), (KeyboardInterrupt(), "interrupted")])
def test_exception_is_recorded_and_reraised(exception, expected):
    async def operation(request, **kwargs):
        raise exception

    with pytest.raises(type(exception)):
        asyncio.run(notifications.run_with_notifications(operation, {"ticker": "NVDA"}))
    con = db.connect()
    assert db.list_runs(con)["runs"][0]["status"] == expected
    assert "private failure" not in json.dumps(db.notification_snapshot(con))
    con.close()


def test_invalid_request_does_not_create_a_run():
    async def operation(request, **kwargs):
        raise AssertionError("must not run")

    with pytest.raises(ValueError):
        asyncio.run(notifications.run_with_notifications(operation, {"ticker": ""}))
    con = db.connect()
    assert db.list_runs(con)["runs"] == []
    con.close()


def test_notification_failure_does_not_change_research(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(db, "connect", unavailable)

    async def operation(request, **kwargs):
        kwargs["dependencies"]["progress"]("ingest_candidate", url="private")
        return {"status": "completed_partial"}

    assert asyncio.run(notifications.run_with_notifications(operation, {"ticker": "NVDA"}))["status"] == "completed_partial"


def test_background_runner_records_once_with_background_origin(monkeypatch):
    from app.agents.catalyst_research import run_trigger, workflow

    async def operation(request, **kwargs):
        return {"status": "completed", "job_id": "cr_background"}

    monkeypatch.setattr(workflow, "_run_research", operation)
    asyncio.run(run_trigger._run_and_release("NVDA", 1, workflow.run_research, None))
    con = db.connect()
    runs = db.list_runs(con)["runs"]
    assert len(runs) == 1
    assert runs[0]["origin"] == "background"
    assert runs[0]["status"] == "succeeded"
    con.close()


def test_actual_cli_uses_shared_notification_boundary(monkeypatch, capsys):
    from app.agents.catalyst_research import __main__ as cli
    from app.agents.catalyst_research import workflow

    async def operation(request, **kwargs):
        kwargs["dependencies"]["progress"]("feeds", count=1)
        return {"status": "completed_partial", "job_id": "cr_cli", "sources": []}

    monkeypatch.setattr(workflow, "_run_research", operation)
    assert cli.main(["NVDA", "--years", "1", "--mode", "research"]) == 0
    assert "stage feeds count=1" in capsys.readouterr().err
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["origin"] == "command_line"
    assert run["status"] == "completed_partial"
    con.close()


@pytest.mark.parametrize("status", ["completed", "completed_partial", "unsupported", "failed"])
def test_async_result_does_not_invent_a_process_exit_code(status):
    async def operation(request, **kwargs):
        return {"status": status}

    asyncio.run(notifications.run_with_notifications(operation, {"ticker": "NVDA"}))
    con = db.connect()
    assert db.list_runs(con)["runs"][0]["exit_code"] is None
    con.close()


def test_cli_report_failure_does_not_rewrite_research_completion(monkeypatch, tmp_path):
    from app.agents.catalyst_research import __main__ as cli
    from app.agents.catalyst_research import workflow

    async def operation(request, **kwargs):
        return {"status": "completed", "sources": []}

    monkeypatch.setattr(workflow, "_run_research", operation)
    monkeypatch.setattr(cli, "render_report", lambda result: "report")
    assert cli.main(["NVDA", "--report", str(tmp_path / "missing" / "report.md")]) == 2
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "succeeded"
    assert run["exit_code"] is None
    con.close()


def test_notification_only_ticker_filter_preserves_research_input():
    ticker = "https://example.test/?token=private"
    seen = []

    async def operation(request, **kwargs):
        seen.append(request["ticker"])
        kwargs["dependencies"]["progress"]("ingest_candidate", url=ticker)
        return {"status": "completed"}

    asyncio.run(notifications.run_with_notifications(operation, {"ticker": ticker}))
    assert seen == [ticker]
    con = db.connect()
    assert "PRIVATE" not in json.dumps(db.notification_snapshot(con))
    assert "private" not in json.dumps(db.load_run(con, db.list_runs(con)["runs"][0]["run_id"]))
    con.close()


def test_batch_unknown_tickers_are_safe_and_keep_distinct_children():
    @notifications.record_feed_batch
    def batch():
        notifications.record_feed_result("https://example.test/private-one", {"status": "failed"})
        notifications.record_feed_result("https://example.test/private-two", {"status": "failed"})
        return 1

    batch()
    con = db.connect()
    detail = db.load_run(con, db.list_runs(con)["runs"][0]["run_id"])
    assert len(detail["children"]) == 2
    assert "private" not in json.dumps(detail).lower()
    con.close()


@pytest.mark.parametrize("statuses,code,expected", [
    ([], 0, "succeeded"), (["unsupported"], 0, "unsupported"),
    (["completed_partial"], 0, "completed_partial"), (["completed", "unsupported"], 0, "completed_partial"),
    (["completed", "failed"], 1, "partially_failed"), (["failed"], 1, "failed"),
])
def test_feed_batch_has_one_notification_with_ticker_details(statuses, code, expected):
    @notifications.record_feed_batch
    def batch():
        for index, status in enumerate(statuses):
            ticker = f"TEST{index}"

            async def operation(request, **kwargs):
                return {"status": status}

            asyncio.run(notifications.run_with_notifications(operation, {"ticker": ticker, "mode": "update"}))
            notifications.record_feed_result(ticker, {"status": status})
        return code

    assert batch() == code
    con = db.connect()
    runs = db.list_runs(con)["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == expected
    assert len(db.load_run(con, runs[0]["run_id"])["children"]) == len(statuses)
    assert len(db.events_after(con, 0)["events"]) == 2
    con.close()
