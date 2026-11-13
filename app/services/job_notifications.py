from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from uuid import uuid4

from app.db import job_notifications as repository
from app.runtime_logging import get_runtime_logger
from app.services.task_notification_catalog import TASKS


LOGGER = get_runtime_logger(__name__)
JOBS = TASKS
STATUS_LABELS = {"running": "Last reported: running", "succeeded": "Succeeded", "partially_failed": "Partially failed", "failed": "Failed", "interrupted": "Interrupted", "completed_partial": "Completed with limitations", "unsupported": "Unsupported"}
_CHILD_LABELS = {"running": "Last reported: running", "ok": "Succeeded", "skipped": "Skipped", "blocked": "Blocked", "failed": "Failed", "completed_partial": "Completed with limitations", "unsupported": "Unsupported", "interrupted": "Interrupted"}
_CURRENT_RUN = ContextVar("notification_run", default=None)


def _timestamp():
    return datetime.now(UTC).isoformat()


class RunRecorder:
    def __init__(self, run_id, db_path, job_id=None):
        self.job_id = job_id
        self.run_id = run_id
        self.db_path = db_path
        self.results = {}

    def _write(self, operation, *args):
        try:
            con = repository.connect(self.db_path)
            try:
                return operation(con, *args)
            finally:
                con.close()
        except Exception:
            LOGGER.warning("job notification recording unavailable run_id=%s", self.run_id)
            return None

    def record_event(self, event):
        if event.get("type") not in {"task_started", "task_finished"}:
            return
        source = event.get("result") if event["type"] == "task_finished" else event["task"]
        status = source.get("status", "running")
        if status not in _CHILD_LABELS:
            status = "failed"
        child = {
            "name": event["task"]["name"], "status": status, "status_label": _CHILD_LABELS[status],
            "updated_at": _timestamp(),
            "summary": "See job log for details" if status in {"failed", "blocked"} else _CHILD_LABELS[status],
        }
        if event["type"] == "task_finished":
            self.results[child["name"]] = child
        self._write(repository.update_child, self.run_id, child)

    def report_child(self, name, status, summary, *, label=None):
        if status not in _CHILD_LABELS:
            raise ValueError("notification child status is invalid")
        child = {"name": name, "status": status, "status_label": _CHILD_LABELS[status], "summary": summary, "updated_at": _timestamp()}
        if label is not None:
            child["label"] = label
        if status != "running":
            self.results[name] = child
        self._write(repository.update_child, self.run_id, child)

    def complete(self, status, summary, *, exit_code=None, details=None):
        if status not in repository.TERMINAL_STATUSES:
            raise ValueError("notification terminal status is invalid")
        stamp = _timestamp()
        self._write(repository.finish_run, self.run_id, {"status": status, "status_label": STATUS_LABELS[status],
                    "summary": summary, "ended_at": stamp, "updated_at": stamp, "exit_code": exit_code, "details": details or {}})

    def finish(self, exit_code, results=None):
        if results is not None:
            for result in results:
                self.record_event({"type": "task_finished", "task": {"name": result["name"]}, "result": result})
        counts = {status: sum(child["status"] == status for child in self.results.values()) for status in ("ok", "skipped", "failed", "blocked")}
        if exit_code == 130:
            status = "interrupted"
        elif counts["failed"] or counts["blocked"]:
            status = "partially_failed" if counts["ok"] else "failed"
        else:
            status = "succeeded" if not exit_code else "failed"
        summary = "Refresh completed" if status == "succeeded" else "See job log for details"
        if counts and self.results:
            summary = f"{counts['ok']} succeeded · {counts['skipped']} skipped · {counts['failed']} failed · {counts['blocked']} blocked"
        stamp = _timestamp()
        self._write(repository.finish_run, self.run_id, {
            "status": status, "status_label": STATUS_LABELS[status], "summary": summary,
            "ended_at": stamp, "updated_at": stamp, "exit_code": int(exit_code or 0), "counts": counts,
        })

    def fail(self):
        stamp = _timestamp()
        self._write(repository.finish_run, self.run_id, {"status": "failed", "status_label": STATUS_LABELS["failed"],
                    "summary": "Refresh did not complete; see job log for details", "ended_at": stamp, "updated_at": stamp, "exit_code": 1})

    def interrupt(self):
        self.finish(130)


def start_run(job_id, *, target=None, origin="command_line", db_path=None):
    if job_id not in JOBS:
        raise ValueError("notification job is invalid")
    if origin not in {"command_line", "manual", "background"}:
        raise ValueError("notification origin is invalid")
    handle = RunRecorder(uuid4().hex, db_path, job_id)
    stamp = _timestamp()
    handle._write(repository.create_run, {
        "run_id": handle.run_id, "job_id": job_id, **JOBS[job_id], "origin": origin,
        "origin_label": {"manual": "Manual", "command_line": "Command line", "background": "Background"}[origin],
        "target": target, "started_at": stamp, "updated_at": stamp, "ended_at": None,
        "status": "running", "status_label": STATUS_LABELS["running"],
        "summary": "Completion has not been reported", "exit_code": None,
    })
    return handle


def record_event(event):
    handle = _CURRENT_RUN.get()
    if handle is not None:
        handle.record_event(event)


def record_job(job_id):
    def decorate(operation):
        @wraps(operation)
        def wrapped(*args, **kwargs):
            handle = start_run(job_id)
            token = _CURRENT_RUN.set(handle)
            try:
                code = operation(*args, **kwargs)
            except KeyboardInterrupt:
                handle.interrupt()
                raise
            except SystemExit as exc:
                handle.finish(exc.code if isinstance(exc.code, int) else 1)
                raise
            except Exception:
                handle.fail()
                raise
            else:
                handle.finish(code)
                return code
            finally:
                _CURRENT_RUN.reset(token)
        return wrapped
    return decorate


def read(operation, *args, **kwargs):
    con = repository.connect()
    try:
        return operation(con, *args, **kwargs)
    finally:
        con.close()


def get_snapshot():
    return {**read(repository.notification_snapshot),
            "jobs": [{"job_id": key, "name": value["name"]} for key, value in JOBS.items()],
            "statuses": [{"status": key, "label": value} for key, value in STATUS_LABELS.items()]}


def get_events(after, limit=100):
    return read(repository.events_after, after, limit)


def get_history(*, job_id=None, status=None, before=None, limit=25):
    if job_id is not None and job_id not in JOBS:
        raise ValueError("notification job is invalid")
    if status is not None and status not in STATUS_LABELS:
        raise ValueError("notification status is invalid")
    return read(repository.list_runs, job_id=job_id, status=status, before=before, limit=limit)


def get_run(run_id):
    return read(repository.load_run, run_id)


def mark_read(event_ids):
    return read(repository.mark_read, event_ids)


def mark_all_read(through):
    return read(repository.mark_all_read, through)


def clear_notifications(through):
    return read(repository.clear_notifications, through)


def current_run():
    return _CURRENT_RUN.get()


@contextmanager
def bind_run(handle):
    token = _CURRENT_RUN.set(handle)
    try:
        yield
    finally:
        _CURRENT_RUN.reset(token)
