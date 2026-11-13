import json

import pytest

from app.db import job_notifications as db
from app.services import job_notifications as service


@pytest.mark.parametrize("statuses,code,expected", [
    (["ok"], 0, "succeeded"), (["ok", "failed"], 1, "partially_failed"),
    (["ok", "blocked"], 1, "partially_failed"), (["failed", "skipped"], 1, "failed"),
    (["blocked"], 1, "failed"), (["skipped"], 0, "succeeded"),
    ([], 0, "succeeded"), (["ok"], 130, "interrupted"), ([], 1, "failed"),
])
def test_outcome_follows_child_results_without_inventing_success(tmp_path, statuses, code, expected):
    path = tmp_path / "n.sqlite"
    handle = service.start_run("macro_refresh", db_path=path)
    for i, status in enumerate(statuses):
        handle.record_event({"type": "task_finished", "task": {"name": f"task-{i}"},
                             "result": {"name": f"task-{i}", "status": status, "error": "secret-token", "stdout": "secret-token"}})
    handle.finish(code)
    con = db.connect(path)
    run = db.load_run(con, handle.run_id)
    assert run["status"] == expected
    assert "secret-token" not in json.dumps(run)
    assert run["counts"]["ok"] == statuses.count("ok")
    con.close()


def test_decorator_records_setup_exception_and_preserves_it(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", tmp_path / "n.sqlite")

    @service.record_job("macro_refresh")
    def operation():
        raise ValueError("private credential")

    with pytest.raises(ValueError, match="private credential"):
        operation()
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "failed"
    assert "private credential" not in json.dumps(db.notification_snapshot(con))
    con.close()


def test_recording_failure_does_not_change_operation_return(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(db, "connect", unavailable)

    @service.record_job("macro_refresh")
    def operation():
        service.record_event({"type": "task_started", "task": {"name": "prices"}})
        return 7

    assert operation() == 7


def test_keyboard_interrupt_is_persisted_then_reraised(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", tmp_path / "n.sqlite")

    @service.record_job("macro_refresh")
    def operation():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        operation()
    con = db.connect()
    assert db.list_runs(con)["runs"][0]["status"] == "interrupted"
    con.close()


def test_unfinished_run_does_not_claim_process_is_alive(tmp_path):
    path = tmp_path / "n.sqlite"
    handle = service.start_run("macro_refresh", db_path=path)
    con = db.connect(path)
    run = db.load_run(con, handle.run_id)
    assert run["status_label"] == "Last reported: running"
    assert run["summary"] == "Completion has not been reported"
    assert run["ended_at"] is None
    con.close()
