from asyncio import CancelledError
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction, signature
from re import fullmatch
from sys import argv as process_argv
from uuid import uuid4

from app.services import job_notifications as notifications


_SCOPE = ContextVar("notification_task_scope", default=None)


def _safe_target(value):
    normalized = str(value or "").strip().upper()
    return normalized if fullmatch(r"[A-Z0-9^$][A-Z0-9.^$=_-]{0,31}", normalized) else None


class TaskScope:
    def __init__(self, task_id, origin, target):
        parent = notifications.current_run()
        self.nested = parent is not None
        self.parent_scope = _SCOPE.get()
        self.child_statuses = []
        self.suppressed = self.nested and parent.job_id == "macro_refresh"
        self.handle = parent or notifications.start_run(task_id, origin=origin, target=_safe_target(target))
        self.child_id = f"task_{uuid4().hex}"
        self.label = notifications.JOBS[task_id]["name"]
        safe = _safe_target(target)
        if safe:
            self.label += f" · {safe}"
        self.done = False
        if self.nested and not self.suppressed:
            self.handle.report_child(self.child_id, "running", "Task started", label=self.label)

    def finish(self, status=None, *, exit_code=None):
        if self.done or self.suppressed:
            return
        self.done = True
        limited = any(status in {"failed", "blocked", "completed_partial", "unsupported", "interrupted"} for status in self.child_statuses)
        status = status or ("completed_partial" if limited else "succeeded")
        summary = {"succeeded": "Task completed", "completed_partial": "Task completed with limitations; review its result",
                   "failed": "Task did not complete; review its result or command output", "interrupted": "Task was interrupted"}[status]
        if self.nested:
            self.handle.report_child(self.child_id, "ok" if status == "succeeded" else status, summary, label=self.label)
            if self.parent_scope is not None:
                self.parent_scope.child_statuses.append(status)
        else:
            self.handle.complete(status, summary, exit_code=exit_code)


@contextmanager
def task(task_id, *, origin="background", target=None):
    scope = TaskScope(task_id, origin, target)
    token = _SCOPE.set(scope)
    try:
        with notifications.bind_run(scope.handle):
            try:
                yield scope
            except (CancelledError, KeyboardInterrupt):
                scope.finish("interrupted")
                raise
            except BaseException:
                scope.finish("failed")
                raise
            else:
                scope.finish()
    finally:
        _SCOPE.reset(token)


def track_task(task_id, *, origin="manual", target_parameter=None, failed_when=None):
    def decorate(operation):
        bound_signature = signature(operation)

        def target(args, kwargs):
            if target_parameter is None:
                return None
            return bound_signature.bind_partial(*args, **kwargs).arguments.get(target_parameter)

        if iscoroutinefunction(operation):
            @wraps(operation)
            async def wrapped(*args, **kwargs):
                with task(task_id, origin=origin, target=target(args, kwargs)) as scope:
                    result = await operation(*args, **kwargs)
                    if failed_when is not None and failed_when(result):
                        scope.finish("failed")
                    return result
        else:
            @wraps(operation)
            def wrapped(*args, **kwargs):
                with task(task_id, origin=origin, target=target(args, kwargs)) as scope:
                    result = operation(*args, **kwargs)
                    if failed_when is not None and failed_when(result):
                        scope.finish("failed")
                    return result
        return wrapped
    return decorate


def report_failure(task_id):
    if notifications.current_run() is not None:
        TaskScope(task_id, "background", None).finish("failed")


def record_cli_task(task_id):
    def decorate(operation):
        @wraps(operation)
        def wrapped(*args, **kwargs):
            command_args = kwargs.get("argv", args[0] if args else None)
            command_args = process_argv[1:] if command_args is None else command_args
            if "--help" in command_args or "-h" in command_args:
                return operation(*args, **kwargs)
            with task(task_id, origin="command_line") as scope:
                try:
                    result = operation(*args, **kwargs)
                except KeyboardInterrupt:
                    scope.finish("interrupted", exit_code=130)
                    raise
                except SystemExit as exc:
                    code = exc.code if type(exc.code) is int else 0 if exc.code is None else 1
                    scope.finish("failed" if code else None, exit_code=code)
                    raise
                code = result if type(result) is int else 0
                scope.finish("interrupted" if code == 130 else "failed" if code else None, exit_code=code)
                return result
        return wrapped
    return decorate
