from contextlib import contextmanager
from threading import Barrier, Event, Lock, Thread
import sys
import time

import pytest

from app.services.macro_refresh_executor import execute_tasks
from app.services.macro_refresh_plan import make_task
from app.services.macro_refresh_output import install_output_routers
from app.services.macro_refresh_resources import SQLiteWriterGate


def _task(name, lane, func, *, stage="fetch", argv=(), dependencies=(), resources=(), skip_reason=None, plan_index=0, accepted=("ok",)):
    return make_task(
        name,
        lane,
        stage,
        func,
        argv=argv,
        dependencies=dependencies,
        resources=resources,
        skip_reason=skip_reason,
        plan_index=plan_index,
        accepted_dependency_statuses=accepted,
    )


def test_independent_lanes_overlap_but_each_lane_stays_serial():
    yahoo_started = Event()
    fred_started = Event()
    release = Event()
    calls = []

    def wait_task(label, own, other):
        def run(argv):
            calls.append(f"{label}:start")
            own.set()
            assert other.wait(1)
            assert release.wait(1)
            calls.append(f"{label}:end")
            return 0

        return run

    tasks = [
        _task(
            "fred_fetch",
            "fred_macro",
            wait_task("fred", fred_started, yahoo_started),
            plan_index=0,
        ),
        _task(
            "fred_import",
            "fred_macro",
            lambda argv: calls.append("fred:import") or 0,
            stage="persist",
            dependencies=["fred_fetch"],
            plan_index=1,
        ),
        _task(
            "yahoo_fetch",
            "yahoo",
            wait_task("yahoo", yahoo_started, fred_started),
            plan_index=2,
        ),
    ]

    timer = Thread(target=lambda: (fred_started.wait(1), yahoo_started.wait(1), release.set()))
    timer.start()
    results = execute_tasks(tasks)
    timer.join()

    assert [result["name"] for result in results] == [
        "fred_fetch",
        "fred_import",
        "yahoo_fetch",
    ]
    assert calls.index("fred:end") < calls.index("fred:import")


def test_four_independent_lanes_reach_barrier_before_release():
    barrier = Barrier(5)
    release = Event()
    reached = []

    def run(argv):
        reached.append(argv[0])
        barrier.wait(timeout=1)
        assert release.wait(1)
        return 0

    tasks = [
        _task(f"fetch_{i}", f"lane_{i}", run, argv=[f"lane_{i}"], plan_index=i)
        for i in range(4)
    ]

    def open_gate():
        barrier.wait(timeout=1)
        release.set()

    gate = Thread(target=open_gate)
    gate.start()
    results = execute_tasks(tasks)
    gate.join()

    assert len(reached) == 4
    assert all(result["status"] == "ok" for result in results)


def test_empty_plan_returns_without_workers():
    assert execute_tasks([]) == []


def test_failed_dependency_blocks_child_and_unrelated_lane_completes():
    called = []
    tasks = [
        _task("fetch", "fred_macro", lambda argv: 1, plan_index=0),
        _task(
            "import",
            "fred_macro",
            lambda argv: called.append("import") or 0,
            stage="persist",
            dependencies=["fetch"],
            plan_index=1,
        ),
        _task("yahoo", "yahoo", lambda argv: called.append("yahoo") or 0, plan_index=2),
    ]

    results = execute_tasks(tasks)

    by_name = {result["name"]: result for result in results}
    assert by_name["fetch"]["status"] == "failed"
    assert by_name["import"]["status"] == "blocked"
    assert by_name["import"]["error"] == "required dependency failed: fetch"
    assert by_name["yahoo"]["status"] == "ok"
    assert called == ["yahoo"]


def test_stop_on_error_blocks_only_later_tasks_in_failed_lane():
    called = []
    tasks = [
        _task("a1", "a", lambda argv: 1, plan_index=0),
        _task("a2", "a", lambda argv: called.append("a2") or 0, plan_index=1),
        _task("b1", "b", lambda argv: called.append("b1") or 0, plan_index=2),
    ]

    results = execute_tasks(tasks, stop_on_error=True)
    by_name = {result["name"]: result for result in results}

    assert by_name["a2"]["status"] == "blocked"
    assert by_name["b1"]["status"] == "ok"
    assert called == ["b1"]


def test_explicitly_accepted_skipped_dependency_allows_child():
    called = []
    tasks = [
        _task("optional", "lane", lambda argv: called.append("optional"), skip_reason="missing key", plan_index=0),
        _task(
            "child",
            "lane",
            lambda argv: called.append("child") or 0,
            dependencies=["optional"],
            accepted=("ok", "skipped"),
            plan_index=1,
        ),
    ]

    results = execute_tasks(tasks)

    assert [result["status"] for result in results] == ["skipped", "ok"]
    assert called == ["child"]


def test_dependency_resolution_precedes_skip_reason():
    tasks = [
        _task("core", "lane_a", lambda argv: 1, plan_index=0),
        _task(
            "enrichment",
            "lane_b",
            lambda argv: pytest.fail("blocked enrichment was executed"),
            dependencies=["core"],
            skip_reason="OPENAI_API_KEY is not configured",
            plan_index=1,
        ),
    ]

    result = execute_tasks(tasks)[1]
    assert result["status"] == "blocked"
    assert "core" in result["error"]


def test_results_are_sorted_by_plan_index_not_completion_order():
    release = Event()
    tasks = [
        _task("slow", "slow", lambda argv: (release.wait(1), 0)[1], plan_index=1),
        _task("fast", "fast", lambda argv: 0, plan_index=0),
    ]

    results = execute_tasks(tasks)
    release.set()

    assert [result["name"] for result in results] == ["fast", "slow"]


def test_on_event_runs_only_on_caller_thread():
    caller = __import__("threading").get_ident()
    event_threads = []
    events = []

    def on_event(event):
        event_threads.append(__import__("threading").get_ident())
        events.append(event["type"])

    execute_tasks([_task("one", "lane", lambda argv: 0)], on_event=on_event)

    assert event_threads
    assert set(event_threads) == {caller}
    assert events.count("task_started") == 1
    assert events.count("task_finished") == 1


def test_writer_gate_serializes_persist_tasks_in_separate_lanes():
    gate = SQLiteWriterGate()
    active = 0
    maximum = 0
    lock = Lock()

    def persist(argv):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return 0

    tasks = [
        _task("persist_a", "a", persist, stage="persist", resources=["sqlite_writer"], plan_index=0),
        _task("persist_b", "b", persist, stage="persist", resources=["sqlite_writer"], plan_index=1),
    ]

    results = execute_tasks(tasks, writer_gate=gate)

    assert maximum == 1
    assert all(result["status"] == "ok" for result in results)


class _NeverLock:
    def acquire(self, timeout):
        return False

    def release(self):
        raise AssertionError("writer lock must not be released after timeout")


def test_writer_gate_timeout_fails_only_declared_persist_task():
    gate = SQLiteWriterGate(lock=_NeverLock())
    task = _task("persist", "lane", lambda argv: 0, stage="persist", resources=["sqlite_writer"])

    result = execute_tasks([task], writer_gate=gate, writer_timeout=60)[0]

    assert result["status"] == "failed"
    assert result["error"] == "sqlite writer gate timed out after 60 seconds"


def test_cancel_event_blocks_tasks_that_have_not_started():
    started = Event()
    cancel = Event()
    calls = []

    def first(argv):
        calls.append("first")
        started.set()
        assert cancel.wait(1)
        return 0

    tasks = [
        _task("first", "lane", first, plan_index=0),
        _task("second", "lane", lambda argv: calls.append("second") or 0, plan_index=1),
        _task(
            "other",
            "other",
            lambda argv: calls.append("other") or 0,
            dependencies=["first"],
            plan_index=2,
        ),
    ]

    def cancel_after_start():
        assert started.wait(1)
        cancel.set()

    canceller = Thread(target=cancel_after_start)
    canceller.start()
    results = execute_tasks(tasks, cancel_event=cancel)
    canceller.join()

    by_name = {result["name"]: result for result in results}
    assert by_name["first"]["status"] == "ok"
    assert by_name["second"]["error"] == "refresh interrupted"
    assert by_name["other"]["error"] == "refresh interrupted"
    assert calls == ["first"]


def test_request_coordinator_context_wraps_each_task():
    active = []

    @contextmanager
    def coordinator_context():
        active.append("enter")
        try:
            yield
        finally:
            active.append("exit")

    class Coordinator:
        pass

    coordinator = Coordinator()
    tasks = [_task("one", "a", lambda argv: 0), _task("two", "b", lambda argv: 0, plan_index=1)]
    from app.services import macro_refresh_executor

    original = macro_refresh_executor.use_request_coordinator
    macro_refresh_executor.use_request_coordinator = lambda value: coordinator_context()
    try:
        execute_tasks(tasks, request_coordinator=coordinator)
    finally:
        macro_refresh_executor.use_request_coordinator = original

    assert active.count("enter") == 2
    assert active.count("exit") == 2


def test_task_output_is_captured_per_lane():
    def write(argv):
        print(argv[0])
        return 0

    with install_output_routers() as streams:
        results = execute_tasks(
            [_task("one", "lane", write, argv=["captured"])],
            stdout_router=streams["stdout"],
            stderr_router=streams["stderr"],
        )

    assert results[0]["stdout"] == "captured\n"


def test_serial_mode_preserves_result_and_lane_failure_semantics():
    calls = []
    tasks = [
        _task("a1", "a", lambda argv: calls.append("a1") or 1, plan_index=0),
        _task("b1", "b", lambda argv: calls.append("b1") or 0, plan_index=1),
        _task("a2", "a", lambda argv: calls.append("a2") or 0, plan_index=2),
    ]

    results = execute_tasks(tasks, serial=True, stop_on_error=True)

    assert calls == ["a1", "b1"]
    assert [result["status"] for result in results] == ["failed", "ok", "blocked"]


def test_serial_mode_runs_later_cross_lane_dependency_before_dependent_task():
    calls = []
    tasks = [
        _task(
            "dependent",
            "dependent_lane",
            lambda argv: calls.append("dependent") or 0,
            dependencies=["prerequisite"],
            plan_index=0,
        ),
        _task(
            "prerequisite",
            "prerequisite_lane",
            lambda argv: calls.append("prerequisite") or 0,
            plan_index=1,
        ),
    ]

    results = execute_tasks(tasks, serial=True)

    assert calls == ["prerequisite", "dependent"]
    assert [result["name"] for result in results] == ["dependent", "prerequisite"]
    assert all(result["status"] == "ok" for result in results)


def test_default_output_capture_isolated_and_restored_for_concurrent_tasks(monkeypatch):
    barrier = Barrier(2)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    from app.services import macro_refresh_executor

    install_calls = []
    original_install = macro_refresh_executor.install_output_routers

    def track_install(*args, **kwargs):
        install_calls.append((args, kwargs))
        return original_install(*args, **kwargs)

    monkeypatch.setattr(macro_refresh_executor, "install_output_routers", track_install)

    def write(argv):
        print(f"{argv[0]}-before")
        print(f"{argv[0]}-error", file=sys.stderr)
        barrier.wait(timeout=1)
        print(f"{argv[0]}-after")
        print(f"{argv[0]}-error-after", file=sys.stderr)
        return 0

    results = execute_tasks(
        [
            _task("first", "first_lane", write, argv=["first"], plan_index=0),
            _task("second", "second_lane", write, argv=["second"], plan_index=1),
        ]
    )

    by_name = {result["name"]: result for result in results}
    assert by_name["first"]["stdout"] == "first-before\nfirst-after\n"
    assert by_name["second"]["stdout"] == "second-before\nsecond-after\n"
    assert by_name["first"]["stderr"] == "first-error\nfirst-error-after\n"
    assert by_name["second"]["stderr"] == "second-error\nsecond-error-after\n"
    assert len(install_calls) == 1
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr


def test_system_exit_is_failed_task_with_terminal_event():
    events = []

    def stop(argv):
        raise SystemExit("terminated")

    results = execute_tasks(
        [_task("stop", "lane", stop)],
        on_event=events.append,
    )

    assert results[0]["status"] == "failed"
    assert results[0]["exit_code"] == 1
    assert results[0]["error"] == "terminated"
    finished = [event for event in events if event["type"] == "task_finished"]
    assert len(finished) == 1
    assert finished[0]["result"]["status"] == "failed"


def test_worker_keyboard_interrupt_cancels_other_lanes_and_propagates():
    cancelled = Event()

    def interrupt(argv):
        raise KeyboardInterrupt

    def wait_for_interrupt(argv):
        assert cancelled.wait(1)
        return 0

    with pytest.raises(KeyboardInterrupt):
        execute_tasks(
            [
                _task("interrupt", "interrupt_lane", interrupt, plan_index=0),
                _task("wait", "wait_lane", wait_for_interrupt, plan_index=1),
            ],
            cancel_event=cancelled,
        )
