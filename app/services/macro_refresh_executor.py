from contextlib import ExitStack, contextmanager, nullcontext
from datetime import datetime
import io
from queue import Empty, Queue
import threading
from concurrent.futures import ThreadPoolExecutor
import time

from app.http_client import use_request_coordinator
from app.services.macro_refresh_output import install_output_routers
from app.services.macro_refresh_plan import group_tasks_by_lane
from app.services.macro_refresh_plan import make_blocked_result
from app.services.macro_refresh_plan import validate_tasks


def execute_tasks(
    tasks,
    *,
    serial=False,
    stop_on_error=False,
    request_coordinator=None,
    writer_gate=None,
    writer_timeout=60,
    on_event=None,
    cancel_event=None,
    stdout_router=None,
    stderr_router=None,
):
    planned = validate_tasks(tasks)
    if not planned:
        return []

    event_queue = Queue()
    state = _ExecutionState(planned, cancel_event, event_queue)
    lanes = group_tasks_by_lane(planned)
    worker_rows = [planned] if serial else list(lanes.values())
    max_workers = 1 if serial else len(worker_rows)
    worker_func = _run_serial_plan if serial else _run_lane
    watcher = None
    watcher_done = threading.Event()
    if cancel_event is not None:
        watcher = threading.Thread(
            target=_watch_cancellation,
            args=(cancel_event, watcher_done, state),
            daemon=True,
        )
        watcher.start()

    router_context = (
        install_output_routers(stdout=stdout_router, stderr=stderr_router)
        if stdout_router is None or stderr_router is None
        else nullcontext({"stdout": stdout_router, "stderr": stderr_router})
    )
    try:
        with router_context as streams:
            stdout_router = streams["stdout"]
            stderr_router = streams["stderr"]
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [
                    pool.submit(
                        worker_func,
                        rows,
                        state=state,
                        stop_on_error=stop_on_error,
                        request_coordinator=request_coordinator,
                        writer_gate=writer_gate,
                        writer_timeout=writer_timeout,
                        stdout_router=stdout_router,
                        stderr_router=stderr_router,
                    )
                    for rows in worker_rows
                ]
                try:
                    _consume_events_until_complete(
                        event_queue,
                        expected_finished=len(planned),
                        on_event=on_event,
                        state=state,
                        futures=futures,
                    )
                except KeyboardInterrupt:
                    state.interrupt()
                    raise
                for future in futures:
                    future.result()
            return state.ordered_results()
    finally:
        watcher_done.set()
        if watcher is not None:
            watcher.join(timeout=0.2)


class _ExecutionState:
    def __init__(self, tasks, cancel_event, event_queue):
        self._tasks_by_name = {task["name"]: task for task in tasks}
        self._ordered_tasks = list(tasks)
        self._cancel_event = cancel_event or threading.Event()
        self._event_queue = event_queue
        self._condition = threading.Condition()
        self._results = {}
        self._started = set()
        self._ordering_dependencies = {}
        for lane_tasks in group_tasks_by_lane(tasks).values():
            for predecessor, task in zip(lane_tasks, lane_tasks[1:]):
                self._ordering_dependencies[task["name"]] = predecessor["name"]

    def dependency_status(self, task):
        dependencies = list(task["dependencies"])
        predecessor = self._ordering_dependencies.get(task["name"])
        if predecessor is not None and predecessor not in dependencies:
            dependencies.append(predecessor)
        unresolved = [name for name in dependencies if name not in self._results]
        if unresolved:
            return False, (), unresolved
        accepted = set(task["accepted_dependency_statuses"])
        rejected = [
            name
            for name in task["dependencies"]
            if self._results[name]["status"] not in accepted
        ]
        if rejected:
            return False, rejected, []
        return True, (), []

    def wait_for_dependencies(self, task):
        with self._condition:
            while True:
                if self._cancel_event.is_set():
                    return False, (), "refresh interrupted"
                ready, rejected, unresolved = self.dependency_status(task)
                if unresolved:
                    self._condition.wait()
                    continue
                if rejected:
                    return False, rejected, "required dependency failed"
                return True, (), ""

    def mark_started(self, task):
        with self._condition:
            self._started.add(task["name"])
            self._event_queue.put(
                {
                    "type": "task_started",
                    "name": task["name"],
                    "lane": task["lane"],
                    "task": task,
                }
            )

    def record(self, result, task):
        with self._condition:
            self._results[result["name"]] = result
            self._event_queue.put(
                {
                    "type": "task_finished",
                    "name": task["name"],
                    "lane": task["lane"],
                    "task": task,
                    "result": result,
                }
            )
            self._condition.notify_all()

    def block_remaining(self, tasks, reason):
        for task in tasks:
            with self._condition:
                if task["name"] in self._results:
                    continue
            self.record(make_blocked_result(task, (), reason), task)

    def interrupt(self):
        self._cancel_event.set()
        with self._condition:
            self._condition.notify_all()

    def compact(self, name):
        with self._condition:
            result = self._results.get(name)
            if result is not None:
                result["stdout"] = ""
                result["stderr"] = ""

    def terminal_count(self):
        with self._condition:
            return len(self._results)

    def ordered_results(self):
        with self._condition:
            return [self._results[task["name"]] for task in self._ordered_tasks]


def _run_lane(tasks, **kwargs):
    failed_name = None
    for index, task in enumerate(tasks):
        if kwargs["stop_on_error"] and failed_name is not None:
            result = make_blocked_result(
                task,
                (),
                f"refresh stopped after task failure: {failed_name}",
            )
            kwargs["state"].record(result, task)
            continue
        result = _run_one_task(task, **kwargs)
        if result["status"] == "failed":
            failed_name = task["name"]


def _run_serial_plan(tasks, **kwargs):
    pending = list(tasks)
    failed_lanes = set()
    failed_names = {}
    while pending:
        state = kwargs["state"]
        if state._cancel_event.is_set():
            state.block_remaining(pending, "refresh interrupted")
            return
        selected = None
        for task in pending:
            lane = task["lane"]
            ready, rejected, unresolved = _dependency_status(state, task)
            if lane in failed_lanes:
                if not unresolved:
                    selected = task
                    break
            elif ready or rejected:
                selected = task
                break
        if selected is None:
            state.block_remaining(
                pending,
                "required dependency could not be scheduled",
            )
            return
        pending.remove(selected)
        lane = selected["lane"]
        if kwargs["stop_on_error"] and lane in failed_lanes:
            result = make_blocked_result(
                selected,
                (),
                f"refresh stopped after task failure: {failed_names[lane]}",
            )
            state.record(result, selected)
            continue
        result = _run_one_task(selected, **kwargs)
        if result["status"] == "failed":
            failed_lanes.add(lane)
            failed_names[lane] = selected["name"]


def _run_one_task(
    task,
    *,
    state,
    stop_on_error,
    request_coordinator,
    writer_gate,
    writer_timeout,
    stdout_router,
    stderr_router,
):
    ready, dependency_names, blocked_reason = state.wait_for_dependencies(task)
    if not ready:
        result = make_blocked_result(task, dependency_names, blocked_reason)
        state.record(result, task)
        return result

    state.mark_started(task)
    result = _execute_task(
        task,
        request_coordinator=request_coordinator,
        writer_gate=writer_gate,
        writer_timeout=writer_timeout,
        stdout_router=stdout_router,
        stderr_router=stderr_router,
    )
    state.record(result, task)
    return result


def _execute_task(
    task,
    *,
    request_coordinator,
    writer_gate,
    writer_timeout,
    stdout_router,
    stderr_router,
):
    started_at = _timestamp()
    started_monotonic = time.monotonic()
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    try:
        with ExitStack() as stack:
            stdout_buffer = stack.enter_context(_capture_stream(stdout_router))
            stderr_buffer = stack.enter_context(_capture_stream(stderr_router))
            stack.enter_context(_coordinator_context(request_coordinator))
            if "sqlite_writer" in task["resources"] and writer_gate is not None:
                stack.enter_context(writer_gate.acquire(timeout=writer_timeout))
            if task["skip_reason"]:
                status = "skipped"
                exit_code = 0
                error = task["skip_reason"]
            else:
                exit_code = int(task["func"](task["argv"]) or 0)
                status = "ok" if exit_code == 0 else "failed"
                error = "" if status == "ok" else f"exit code {exit_code}"
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        status = "failed"
        exit_code = 1
        error = str(exc)
    finished_at = _timestamp()
    return {
        "name": task["name"],
        "lane": task["lane"],
        "status": status,
        "exit_code": exit_code,
        "error": error,
        "stdout": stdout_buffer.getvalue(),
        "stderr": stderr_buffer.getvalue(),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": time.monotonic() - started_monotonic,
    }


@contextmanager
def _capture_stream(router):
    with router.capture() as buffer:
        yield buffer


@contextmanager
def _coordinator_context(coordinator):
    if coordinator is None:
        yield
        return
    with use_request_coordinator(coordinator):
        yield


def _consume_events_until_complete(
    event_queue,
    *,
    expected_finished,
    on_event,
    state,
    futures,
):
    finished = 0
    while finished < expected_finished:
        try:
            event = event_queue.get(timeout=0.1)
        except Empty:
            for future in futures:
                if future.done():
                    exception = future.exception()
                    if isinstance(exception, KeyboardInterrupt):
                        state.interrupt()
                        raise exception
            if all(future.done() for future in futures) and state.terminal_count() < expected_finished:
                raise RuntimeError(
                    "macro refresh executor stopped before all tasks completed"
                )
            continue
        if on_event is not None:
            on_event(event)
            if event["type"] == "task_finished":
                state.compact(event["name"])
        if event["type"] == "task_finished":
            finished += 1


def _dependency_status(state, task):
    with state._condition:
        return state.dependency_status(task)


def _watch_cancellation(cancel_event, done_event, state):
    while not done_event.is_set():
        if cancel_event.wait(0.05):
            state.interrupt()
            return


def _timestamp():
    return datetime.now().isoformat()
