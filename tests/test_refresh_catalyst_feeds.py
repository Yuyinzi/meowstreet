import pytest

from jobs import refresh_catalyst_feeds


def test_batch_records_partial_coverage_without_reporting_a_failure(monkeypatch):
    from app.db import job_notifications

    install_fakes(monkeypatch, ["NVDA", "AMD"], {"NVDA": {"status": "completed_partial"}, "AMD": {"status": "unsupported"}})
    assert refresh_catalyst_feeds.main([]) == 0
    con = job_notifications.connect()
    runs = job_notifications.list_runs(con)["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "completed_partial"
    assert [child["status"] for child in job_notifications.load_run(con, runs[0]["run_id"])["children"]] == ["unsupported", "completed_partial"]
    con.close()


def test_batch_setup_failure_is_recorded_and_preserved(monkeypatch):
    from app.db import job_notifications

    def unavailable(*args, **kwargs):
        raise ValueError("private repository failure")

    monkeypatch.setattr(refresh_catalyst_feeds.repository, "connect", unavailable)
    with pytest.raises(ValueError, match="private repository failure"):
        refresh_catalyst_feeds.main([])
    con = job_notifications.connect()
    assert job_notifications.list_runs(con)["runs"][0]["status"] == "failed"
    con.close()


def test_actual_shared_workflow_is_suppressed_under_feed_batch(monkeypatch):
    from app.agents.catalyst_research import workflow
    from app.db import job_notifications

    install_fakes(monkeypatch, ["NVDA", "AMD"], {})

    async def operation(request, **kwargs):
        kwargs["dependencies"]["progress"]("ingest_candidate", url="private")
        return {"status": "completed", "job_id": "cr_feed"}

    monkeypatch.setattr(workflow, "_run_research", operation)
    monkeypatch.setattr(refresh_catalyst_feeds, "run_research", workflow.run_research)
    assert refresh_catalyst_feeds.main([]) == 0
    con = job_notifications.connect()
    runs = job_notifications.list_runs(con)["runs"]
    assert len(runs) == 1
    assert runs[0]["job_id"] == "catalyst_feed_refresh"
    assert [child["status"] for child in job_notifications.load_run(con, runs[0]["run_id"])["children"]] == ["ok", "ok"]
    con.close()


class FakeConnection:
    def __init__(self, tickers):
        self.tickers = tickers
        self.closed = False

    def close(self):
        self.closed = True


class FakeHttpClient:
    instances = []

    def __init__(self):
        self.entered = False
        self.exited = False
        FakeHttpClient.instances.append(self)

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.exited = True
        return False


def install_fakes(monkeypatch, tickers, results):
    FakeHttpClient.instances = []
    connection = FakeConnection(tickers)
    calls = []

    async def fake_run_research(request, *, db_path=None, http_client=None, dependencies=None):
        calls.append((dict(request), db_path, http_client))
        outcome = results.get(request["ticker"], {"status": "completed"})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(refresh_catalyst_feeds.repository, "connect", lambda db_path: connection)
    monkeypatch.setattr(refresh_catalyst_feeds.repository, "list_feed_tickers", lambda con: list(con.tickers))
    monkeypatch.setattr(refresh_catalyst_feeds, "run_research", fake_run_research)
    monkeypatch.setattr(refresh_catalyst_feeds, "HttpClient", FakeHttpClient)
    return connection, calls


def test_main_refreshes_all_feed_tickers_in_order(monkeypatch, capsys):
    connection, calls = install_fakes(monkeypatch, ["AAPL", "NVDA"], {})
    exit_code = refresh_catalyst_feeds.main([])
    assert exit_code == 0
    assert connection.closed
    assert [request["ticker"] for request, _, _ in calls] == ["AAPL", "NVDA"]
    assert all(request["mode"] == "update" and request["years"] == 1 for request, _, _ in calls)
    assert all(http_client.entered for _, _, http_client in calls)
    assert FakeHttpClient.instances[0].exited
    out = capsys.readouterr().out
    assert "ticker AAPL: completed" in out
    assert "catalyst feed refresh completed: ok=2 unsupported=0 failed=0" in out


def test_main_ticker_flag_restricts_refresh(monkeypatch, capsys):
    _, calls = install_fakes(monkeypatch, ["AAPL", "NVDA"], {})
    exit_code = refresh_catalyst_feeds.main(["--ticker", "nvda"])
    assert exit_code == 0
    assert [request["ticker"] for request, _, _ in calls] == ["NVDA"]
    assert "catalyst feed refresh completed: ok=1 unsupported=0 failed=0" in capsys.readouterr().out


@pytest.mark.parametrize("status", ["completed", "completed_partial"])
def test_main_counts_partial_and_unsupported_as_non_failures(monkeypatch, capsys, status):
    install_fakes(monkeypatch, ["NVDA", "AMD"], {"NVDA": {"status": status}, "AMD": {"status": "unsupported"}})
    exit_code = refresh_catalyst_feeds.main([])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ticker AMD: unsupported" in out
    assert "catalyst feed refresh completed: ok=1 unsupported=1 failed=0" in out


def test_main_continues_after_failure_and_exits_nonzero(monkeypatch, capsys):
    _, calls = install_fakes(monkeypatch, ["AAPL", "NVDA"], {"AAPL": ValueError("boom")})
    exit_code = refresh_catalyst_feeds.main([])
    assert exit_code == 1
    assert [request["ticker"] for request, _, _ in calls] == ["AAPL", "NVDA"]
    captured = capsys.readouterr()
    assert "ticker AAPL: failed - boom" in captured.err
    assert "catalyst feed refresh completed: ok=1 unsupported=0 failed=1" in captured.out


def test_main_failed_status_exits_nonzero(monkeypatch, capsys):
    install_fakes(monkeypatch, ["NVDA"], {"NVDA": {"status": "failed"}})
    exit_code = refresh_catalyst_feeds.main([])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "ticker NVDA: failed - status failed" in captured.err
    assert "catalyst feed refresh completed: ok=0 unsupported=0 failed=1" in captured.out


def test_main_empty_ticker_list_exits_zero(monkeypatch, capsys):
    _, calls = install_fakes(monkeypatch, [], {})
    exit_code = refresh_catalyst_feeds.main([])
    assert exit_code == 0
    assert calls == []
    assert "catalyst feed refresh completed: ok=0 unsupported=0 failed=0" in capsys.readouterr().out
