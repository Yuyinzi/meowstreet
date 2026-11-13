import json
from pathlib import Path
from sqlite3 import Row, connect as sqlite_connect


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "job_notifications.sqlite"
TERMINAL_STATUSES = {"succeeded", "partially_failed", "failed", "interrupted", "completed_partial", "unsupported"}

_SCHEMA = """
create table if not exists job_notification_runs (
    sequence integer primary key autoincrement,
    run_id text not null unique,
    job_id text not null,
    status text not null,
    payload text not null
);
create index if not exists job_runs_filter on job_notification_runs(job_id, status, sequence);
create table if not exists job_notification_children (
    run_id text not null references job_notification_runs(run_id),
    name text not null,
    payload text not null,
    primary key (run_id, name)
);
create table if not exists job_notification_events (
    event_id integer primary key autoincrement,
    run_id text not null references job_notification_runs(run_id),
    payload text not null,
    read_at text
);
create index if not exists job_events_run on job_notification_events(run_id, event_id);
create index if not exists job_events_unread on job_notification_events(event_id) where read_at is null;
create table if not exists job_notification_preferences (
    setting_key text primary key,
    value integer not null
);
"""


def connect(db_path=None):
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite_connect(path, timeout=5)
    con.row_factory = Row
    try:
        con.execute("pragma journal_mode=wal")
        con.execute("pragma foreign_keys=on")
        con.executescript(_SCHEMA)
    except Exception:
        con.close()
        raise
    return con


def _insert_event(con, run):
    con.execute(
        "insert into job_notification_events(run_id, payload) values (?, ?)",
        (run["run_id"], json.dumps(run)),
    )


def create_run(con, run):
    if run["status"] != "running":
        raise ValueError("initial status must be running")
    with con:
        con.execute(
            "insert into job_notification_runs(run_id, job_id, status, payload) values (?, ?, ?, ?)",
            (run["run_id"], run["job_id"], run["status"], json.dumps(run)),
        )
        _insert_event(con, run)


def update_child(con, run_id, child):
    with con:
        row = con.execute("select status, payload from job_notification_runs where run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("notification run does not exist")
        if row["status"] != "running":
            return
        con.execute(
            "insert into job_notification_children(run_id, name, payload) values (?, ?, ?) "
            "on conflict(run_id, name) do update set payload=excluded.payload",
            (run_id, child["name"], json.dumps(child)),
        )
        if child.get("updated_at"):
            run = json.loads(row["payload"])
            run["updated_at"] = child["updated_at"]
            con.execute("update job_notification_runs set payload=? where run_id=?", (json.dumps(run), run_id))


def finish_run(con, run_id, outcome):
    if outcome["status"] not in TERMINAL_STATUSES:
        raise ValueError("notification terminal status is invalid")
    with con:
        con.execute("begin immediate")
        row = con.execute("select payload, status from job_notification_runs where run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("notification run does not exist")
        if row["status"] != "running":
            return
        run = {**json.loads(row["payload"]), **outcome}
        con.execute("update job_notification_runs set status=?, payload=? where run_id=?", (run["status"], json.dumps(run), run_id))
        _insert_event(con, run)


def _event(row):
    return {**json.loads(row["payload"]), "event_id": row["event_id"], "read": row["read_at"] is not None}


def _unread(con):
    return con.execute("select count(*) from job_notification_events where read_at is null").fetchone()[0]


def _notification_state(con):
    values = {row["setting_key"]: row["value"] for row in con.execute("select * from job_notification_preferences").fetchall()}
    return {"cleared_through": values.get("cleared_through", 0), "read_through": values.get("read_through", 0)}


def _inbox_events(con, cleared_through, limit=25):
    rows = con.execute("select * from job_notification_events where event_id>? and read_at is null order by event_id desc limit ?", (cleared_through, limit)).fetchall()
    return [_event(row) for row in rows]


def notification_snapshot(con, limit=25):
    with con:
        con.execute("begin")
        state = _notification_state(con)
        cursor = con.execute("select coalesce(max(event_id), 0) from job_notification_events").fetchone()[0]
        return {"events": _inbox_events(con, state["cleared_through"], limit), "next_cursor": cursor, "unread_count": _unread(con), "has_more": False, **state}


def events_after(con, after, limit=100):
    with con:
        con.execute("begin")
        state = _notification_state(con)
        cursor = max(after, state["cleared_through"])
        rows = con.execute("select * from job_notification_events where event_id>? order by event_id limit ?", (cursor, limit + 1)).fetchall()
        selected = rows[:limit]
        inbox_cursor = con.execute("select coalesce(max(event_id), 0) from job_notification_events").fetchone()[0]
        return {"events": [_event(r) for r in selected], "next_cursor": selected[-1]["event_id"] if selected else cursor,
                "has_more": len(rows) > limit, "unread_count": _unread(con),
                "inbox_events": _inbox_events(con, state["cleared_through"]), "inbox_cursor": inbox_cursor, **state}


def load_run(con, run_id):
    row = con.execute("select payload from job_notification_runs where run_id=?", (run_id,)).fetchone()
    if row is None:
        return None
    children = con.execute("select payload from job_notification_children where run_id=? order by name", (run_id,)).fetchall()
    return {**json.loads(row["payload"]), "children": [json.loads(child["payload"]) for child in children]}


def list_runs(con, *, job_id=None, status=None, before=None, limit=25):
    clauses = []
    args = []
    for column, value, operator in [("job_id", job_id, "="), ("status", status, "="), ("sequence", before, "<")]:
        if value is not None:
            clauses.append(f"{column}{operator}?")
            args.append(value)
    where = " where " + " and ".join(clauses) if clauses else ""
    with con:
        con.execute("begin")
        snapshot_cursor = con.execute("select coalesce(max(event_id), 0) from job_notification_events").fetchone()[0]
        rows = con.execute(f"select sequence, run_id, payload from job_notification_runs{where} order by sequence desc limit ?", [*args, limit + 1]).fetchall()
        selected = rows[:limit]
        event_ids = [r[0] for row in selected for r in con.execute("select event_id from job_notification_events where run_id=? and event_id<=?", (row["run_id"], snapshot_cursor)).fetchall()]
        return {"runs": [json.loads(r["payload"]) for r in selected], "displayed_event_ids": event_ids,
                "next_cursor": selected[-1]["sequence"] if selected else None, "has_more": len(rows) > limit}


def mark_read(con, event_ids):
    if len(event_ids) > 200 or any(type(value) is not int or value <= 0 for value in event_ids):
        raise ValueError("notification event ids must be up to 200 positive integers")
    with con:
        con.executemany("update job_notification_events set read_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') where event_id=? and read_at is null", [(value,) for value in event_ids])
    return {"unread_count": _unread(con)}


def _bulk_action(con, through, *, clear):
    if type(through) is not int or through < 0:
        raise ValueError("notification cursor must be a nonnegative integer")
    with con:
        con.execute("begin immediate")
        latest = con.execute("select coalesce(max(event_id), 0) from job_notification_events").fetchone()[0]
        cursor = min(through, latest)
        con.execute("update job_notification_events set read_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') where event_id<=? and read_at is null", (cursor,))
        for key in (["read_through", "cleared_through"] if clear else ["read_through"]):
            con.execute("insert into job_notification_preferences(setting_key, value) values (?, ?) on conflict(setting_key) do update set value=max(value, excluded.value)", (key, cursor))
        return {"unread_count": _unread(con), **_notification_state(con)}


def mark_all_read(con, through):
    return _bulk_action(con, through, clear=False)


def clear_notifications(con, through):
    return _bulk_action(con, through, clear=True)
