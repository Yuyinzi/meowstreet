from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import sys
from threading import Barrier

import pytest

from app.services import macro_refresh_output


def test_thread_local_router_keeps_concurrent_task_output_separate():
    barrier = Barrier(2)

    def write_lines(label, router):
        with router.capture() as buffer:
            print(f"{label}-before")
            barrier.wait()
            print(f"{label}-after")
        return buffer.getvalue()

    base_stdout = StringIO()
    with macro_refresh_output.install_output_routers(stdout=base_stdout) as streams:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(write_lines, "first", streams["stdout"])
            second = pool.submit(write_lines, "second", streams["stdout"])

    assert first.result() == "first-before\nfirst-after\n"
    assert second.result() == "second-before\nsecond-after\n"
    assert base_stdout.getvalue() == ""


def test_thread_local_router_keeps_stderr_capture_separate():
    router = macro_refresh_output.ThreadLocalTextRouter(StringIO())

    with router.capture() as buffer:
        print("diagnostic", file=router)

    assert buffer.getvalue() == "diagnostic\n"


def test_thread_local_router_rejects_nested_capture():
    router = macro_refresh_output.ThreadLocalTextRouter(StringIO())

    with router.capture():
        with pytest.raises(
            ValueError, match="macro refresh output capture is already active"
        ):
            with router.capture():
                pass


def test_install_output_routers_passes_main_thread_output_to_base_streams():
    base_stdout = StringIO()
    base_stderr = StringIO()

    with macro_refresh_output.install_output_routers(
        stdout=base_stdout, stderr=base_stderr
    ) as streams:
        print("main stdout")
        print("main stderr", file=streams["stderr"])

    assert base_stdout.getvalue() == "main stdout\n"
    assert base_stderr.getvalue() == "main stderr\n"


def test_install_output_routers_resolves_none_streams_when_entered(monkeypatch):
    base_stdout = StringIO()
    base_stderr = StringIO()
    monkeypatch.setattr("sys.stdout", base_stdout)
    monkeypatch.setattr("sys.stderr", base_stderr)

    with macro_refresh_output.install_output_routers() as streams:
        assert streams["base_stdout"] is base_stdout
        assert streams["base_stderr"] is base_stderr


def test_thread_local_router_delegates_stream_methods_and_attributes():
    base_stream = StringIO()
    router = macro_refresh_output.ThreadLocalTextRouter(base_stream)

    assert router.isatty() is False
    assert router.closed is False
    assert router.encoding == base_stream.encoding

    router.flush()
    with pytest.raises((OSError, ValueError)):
        router.fileno()


def test_thread_local_router_flushes_active_capture():
    router = macro_refresh_output.ThreadLocalTextRouter(StringIO())

    with router.capture() as buffer:
        router.write("before flush")
        router.flush()

    assert buffer.getvalue() == "before flush"


def test_output_routers_restore_original_streams_after_context():
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    with macro_refresh_output.install_output_routers(
        stdout=StringIO(), stderr=StringIO()
    ):
        assert sys.stdout is not original_stdout
        assert sys.stderr is not original_stderr

    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr
