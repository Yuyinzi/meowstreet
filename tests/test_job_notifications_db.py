import pytest

from app.db import job_notifications as db


def run_payload(run_id="run-one", job_id="macro_refresh"):
    return {
        "run_id": run_id, "job_id": job_id, "name": "Macro data refresh",
        "origin": "command_line", "target": None,
        "started_at": "2026-11-13T00:00:00+00:00", "updated_at": "2026-11-13T00:00:00+00:00",
        "ended_at": None, "status": "running", "status_label": "Last reported: running",
        "summary": "Completion has not been reported", "exit_code": None,
        "log_path": "logs/macro_refresh.log",
    }


def outcome(status="succeeded"):
    return {"status": status, "status_label": "Succeeded", "summary": "Refresh completed",
            "ended_at": "2026-11-13T00:01:00+00:00", "updated_at": "2026-11-13T00:01:00+00:00", "exit_code": 0}


def test_run_and_events_survive_reopen_and_finish_is_idempotent(tmp_path):
    path = tmp_path / "notifications.sqlite"
    con = db.connect(path)
    db.create_run(con, run_payload())
    db.update_child(con, "run-one", {"name": "prices", "status": "ok", "status_label": "Succeeded"})
    db.finish_run(con, "run-one", outcome())
    db.finish_run(con, "run-one", outcome())
    con.close()
    con = db.connect(path)
    detail = db.load_run(con, "run-one")
    assert detail["status"] == "succeeded"
    assert detail["children"][0]["name"] == "prices"
    events = db.events_after(con, 0)
    assert [event["status"] for event in events["events"]] == ["running", "succeeded"]
    assert events["unread_count"] == 2
    con.close()


def test_read_only_displayed_events_and_completion_stays_unread(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    db.create_run(con, run_payload())
    snapshot = db.notification_snapshot(con)
    db.create_run(con, run_payload("run-two"))
    db.mark_read(con, [event["event_id"] for event in snapshot["events"]])
    db.finish_run(con, "run-one", outcome())
    events = db.events_after(con, snapshot["next_cursor"])
    assert events["unread_count"] == 2
    assert [e["run_id"] for e in events["events"]] == ["run-two", "run-one"]
    con.close()


def test_event_cursor_does_not_skip_backlog(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    for i in range(5):
        db.create_run(con, run_payload(f"run-{i}"))
    first = db.events_after(con, 0, limit=2)
    second = db.events_after(con, first["next_cursor"], limit=2)
    third = db.events_after(con, second["next_cursor"], limit=2)
    assert [e["event_id"] for p in [first, second, third] for e in p["events"]] == [1, 2, 3, 4, 5]
    assert first["has_more"] is True
    assert third["has_more"] is False
    snapshot = db.notification_snapshot(con, limit=2)
    assert snapshot["next_cursor"] == 5
    assert [e["event_id"] for e in snapshot["events"]] == [5, 4]
    con.close()


def test_run_pagination_and_filters_exclude_unseen_events(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    db.create_run(con, run_payload("first"))
    db.create_run(con, run_payload("second", "investing_refresh"))
    db.finish_run(con, "first", outcome())
    page = db.list_runs(con, job_id="macro_refresh", status="succeeded", limit=1)
    assert [r["run_id"] for r in page["runs"]] == ["first"]
    db.mark_read(con, page["displayed_event_ids"])
    assert db.notification_snapshot(con)["unread_count"] == 1
    page = db.list_runs(con, limit=1)
    assert page["runs"][0]["run_id"] == "second"
    assert db.list_runs(con, before=page["next_cursor"], limit=1)["runs"][0]["run_id"] == "first"
    assert db.load_run(con, "unknown") is None
    con.close()


def test_invalid_terminal_state_cannot_change_run_or_create_event(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    db.create_run(con, run_payload())
    with pytest.raises(ValueError, match="terminal status"):
        db.finish_run(con, "run-one", outcome("running"))
    assert db.load_run(con, "run-one")["status"] == "running"
    assert len(db.events_after(con, 0)["events"]) == 1
    con.close()


def test_event_insert_failure_rolls_back_run_update(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    db.create_run(con, run_payload())
    con.execute("create trigger prevent_event before insert on job_notification_events begin select raise(abort, 'test failure'); end")
    with pytest.raises(Exception, match="test failure"):
        db.finish_run(con, "run-one", outcome())
    assert db.load_run(con, "run-one")["status"] == "running"
    con.close()


def test_clear_notifications_persists_without_deleting_task_history(tmp_path):
    path = tmp_path / "n.sqlite"
    con = db.connect(path)
    db.create_run(con, run_payload())
    db.finish_run(con, "run-one", outcome())
    snapshot = db.notification_snapshot(con)
    db.clear_notifications(con, snapshot["next_cursor"])
    con.close()
    con = db.connect(path)
    assert db.notification_snapshot(con)["events"] == []
    assert db.notification_snapshot(con)["unread_count"] == 0
    assert len(db.list_runs(con)["runs"]) == 1
    assert db.load_run(con, "run-one")["status"] == "succeeded"
    con.close()


def test_bulk_actions_preserve_new_events_and_future_completion(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    db.create_run(con, run_payload())
    cursor = db.notification_snapshot(con)["next_cursor"]
    db.finish_run(con, "run-one", outcome())
    db.mark_all_read(con, cursor)
    snapshot = db.notification_snapshot(con)
    assert snapshot["unread_count"] == 1
    assert len(snapshot["events"]) == 1
    db.clear_notifications(con, cursor)
    assert [e["status"] for e in db.events_after(con, 0)["events"]] == ["succeeded"]
    assert db.notification_snapshot(con)["unread_count"] == 1
    con.close()


def test_clear_cutoff_cannot_hide_future_events(tmp_path):
    con = db.connect(tmp_path / "n.sqlite")
    db.create_run(con, run_payload())
    db.clear_notifications(con, 9999)
    db.finish_run(con, "run-one", outcome())
    assert len(db.notification_snapshot(con)["events"]) == 1
    assert db.events_after(con, 0)["next_cursor"] == 2
    con.close()


def test_inbox_excludes_individually_read_events_and_poll_syncs_other_tabs(tmp_path):
    path = tmp_path / "n.sqlite"
    con = db.connect(path)
    db.create_run(con, run_payload())
    db.finish_run(con, "run-one", outcome())
    cursor = db.notification_snapshot(con)["next_cursor"]
    other = db.connect(path)
    db.mark_read(other, [cursor])
    assert [e["status"] for e in db.notification_snapshot(con)["events"]] == ["running"]
    assert [e["status"] for e in db.events_after(con, cursor)["inbox_events"]] == ["running"]
    db.mark_all_read(other, cursor)
    assert db.notification_snapshot(con)["events"] == []
    assert db.events_after(con, cursor)["inbox_events"] == []
    assert db.load_run(con, "run-one")["status"] == "succeeded"
    other.close()
    con.close()
