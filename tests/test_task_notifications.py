import asyncio

import pytest

from app.db import job_notifications as db
from app.services import task_notifications as tasks


def test_nested_operations_create_one_run_and_distinct_child_records():
    @tasks.track_task("portfolio_analysis")
    def operation():
        for _ in range(2):
            with tasks.task("ticker_fundamentals", target="NVDA"):
                pass
        return {"classification": "reject"}

    assert operation()["classification"] == "reject"
    con = db.connect()
    runs = db.list_runs(con)["runs"]
    assert len(runs) == 1
    detail = db.load_run(con, runs[0]["run_id"])
    assert detail["status"] == "succeeded"
    assert len(detail["children"]) == 2
    assert len(db.events_after(con, 0)["events"]) == 2
    con.close()


def test_handled_child_failure_is_visible_without_changing_return():
    @tasks.track_task("portfolio_analysis")
    def operation():
        try:
            with tasks.task("ticker_fundamentals"):
                raise ValueError("private provider payload")
        except ValueError:
            return {"status": "insufficient_data"}

    assert operation() == {"status": "insufficient_data"}
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "completed_partial"
    assert "private" not in str(db.load_run(con, run["run_id"]))
    con.close()


def test_failed_sibling_does_not_change_a_successful_child_state():
    with tasks.task("portfolio_analysis"):
        try:
            with tasks.task("ticker_fundamentals"):
                raise ValueError("unavailable")
        except ValueError:
            pass
        with tasks.task("ticker_profile"):
            pass
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    children = db.load_run(con, run["run_id"])["children"]
    assert sorted(child["status"] for child in children) == ["failed", "ok"]
    con.close()


def test_async_cancellation_is_recorded_without_a_process_exit_code():
    @tasks.track_task("market_assistant")
    async def operation():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(operation())
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "interrupted"
    assert run["exit_code"] is None
    con.close()


@pytest.mark.parametrize("code,status", [(None, "succeeded"), (0, "succeeded"), (2, "failed")])
def test_cli_returns_and_process_codes_are_preserved(code, status):
    @tasks.record_cli_task("cli_import_oil")
    def operation(argv=None):
        return code

    assert operation([]) is code
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == status
    assert run["exit_code"] == (code or 0)
    con.close()


def test_help_does_not_create_a_task():
    @tasks.record_cli_task("cli_import_oil")
    def operation(argv=None):
        raise SystemExit(0)

    with pytest.raises(SystemExit):
        operation(["--help"])
    con = db.connect()
    assert db.list_runs(con)["runs"] == []
    con.close()


def test_unsafe_targets_are_not_persisted():
    with tasks.task("ticker_fundamentals", target="https://private?token=secret"):
        pass
    con = db.connect()
    assert "secret" not in str(db.notification_snapshot(con))
    con.close()


def test_storage_failure_preserves_sync_and_async_work(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(db, "connect", unavailable)

    @tasks.track_task("portfolio_analysis")
    def operation():
        return 13

    assert operation() == 13


def test_fundamentals_cache_hit_creates_no_task_but_actual_fetch_does(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from app.db import ticker_context
    from app.services import ticker_quant_context

    con = ticker_context.connect(tmp_path / "ticker.sqlite")
    monkeypatch.setattr(ticker_quant_context.yahoo_asset_profile, "fetch_quote_fundamentals", lambda symbol, **kwargs: {
        "symbol": symbol, "provider": "yahoo", "company_name": "Test", "forward_pe": 10,
        "fetched_at": datetime.now(UTC).isoformat(),
    })
    ticker_quant_context._load_fundamentals(con, "NVDA", None)
    ticker_quant_context._load_fundamentals(con, "NVDA", None)
    con.close()
    notification_con = db.connect()
    runs = db.list_runs(notification_con)["runs"]
    assert len(runs) == 1
    assert runs[0]["job_id"] == "ticker_fundamentals"
    notification_con.close()


def test_macro_worker_context_suppresses_duplicate_cli_notifications():
    from app.services import job_notifications
    from app.services.macro_refresh_executor import execute_tasks
    from app.services.macro_refresh_plan import make_task

    @tasks.record_cli_task("cli_import_oil")
    def provider(argv=None):
        return 0

    @job_notifications.record_job("macro_refresh")
    def macro():
        results = execute_tasks([make_task("oil", "energy", "fetch", provider)])
        assert results[0]["status"] == "ok"
        return 0

    assert macro() == 0
    con = db.connect()
    runs = db.list_runs(con)["runs"]
    assert len(runs) == 1
    assert runs[0]["job_id"] == "macro_refresh"
    con.close()


def test_price_collection_failure_is_visible_under_analysis(tmp_path):
    from app.tools import market_data

    def unavailable(*args):
        raise ValueError("private source error")

    with tasks.task("portfolio_analysis"):
        with pytest.raises(ValueError):
            market_data.fetch_market_data("NVDA", fetch_json=unavailable, db_path=tmp_path / "prices.sqlite")
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "completed_partial"
    assert db.load_run(con, run["run_id"])["children"][0]["status"] == "failed"
    con.close()


def test_external_research_failure_is_visible_under_answer():
    from app.services.market_assistant_research import acquire_research

    class Provider:
        async def search(self, request):
            raise RuntimeError("private query contents")

    async def operation():
        with tasks.task("market_assistant"):
            result = await acquire_research(Provider(), {"purpose": "current_events", "depth_tier": "focused", "queries": ["private query"], "expected_source_class": "official_publication"}, result_id="research_test", searched_at="2026-11-13T00:00:00Z")
            assert result["status"] == "research_unavailable"

    asyncio.run(operation())
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "completed_partial"
    assert "private" not in str(db.load_run(con, run["run_id"]))
    con.close()


def test_forecast_parse_failure_is_not_a_successful_collection(tmp_path, monkeypatch):
    from app.db import ticker_context
    from app.services import ticker_quant_context

    con = ticker_context.connect(tmp_path / "ticker.sqlite")
    monkeypatch.setattr(ticker_quant_context.stockanalysis_screener, "fetch_forecast_document", lambda *args, **kwargs: "invalid document")

    def invalid(*args, **kwargs):
        raise ValueError("private document contents")

    monkeypatch.setattr(ticker_quant_context.stockanalysis_screener, "parse_forecast_data", invalid)
    monkeypatch.setattr(ticker_quant_context.stockanalysis_screener, "parse_analyst_ratings", invalid)
    ticker_quant_context._load_forecast_data(con, "NVDA", None)
    con.close()
    notification_con = db.connect()
    run = db.list_runs(notification_con)["runs"][0]
    assert run["status"] == "completed_partial"
    assert "private" not in str(db.load_run(notification_con, run["run_id"]))
    notification_con.close()
