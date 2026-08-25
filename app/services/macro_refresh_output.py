import io
import sys
import threading
from contextlib import contextmanager, redirect_stderr, redirect_stdout


class ThreadLocalTextRouter:
    def __init__(self, base_stream):
        self._base_stream = base_stream
        self._local = threading.local()

    def write(self, text):
        return self._active_stream().write(text)

    def flush(self):
        return self._active_stream().flush()

    def isatty(self):
        return self._stream_attribute("isatty")()

    @property
    def encoding(self):
        return self._stream_attribute("encoding")

    @property
    def closed(self):
        return self._stream_attribute("closed")

    def fileno(self):
        return self._stream_attribute("fileno")()

    def _active_stream(self):
        return getattr(self._local, "target", self._base_stream)

    def _stream_attribute(self, name):
        target = self._active_stream()
        try:
            return getattr(target, name)
        except AttributeError:
            return getattr(self._base_stream, name)

    def __getattr__(self, name):
        return self._stream_attribute(name)

    @contextmanager
    def capture(self):
        if getattr(self._local, "target", None) is not None:
            raise ValueError("macro refresh output capture is already active")
        target = io.StringIO()
        self._local.target = target
        try:
            yield target
        finally:
            del self._local.target


@contextmanager
def install_output_routers(stdout=None, stderr=None):
    base_stdout = sys.stdout if stdout is None else stdout
    base_stderr = sys.stderr if stderr is None else stderr
    stdout_router = ThreadLocalTextRouter(base_stdout)
    stderr_router = ThreadLocalTextRouter(base_stderr)
    with redirect_stdout(stdout_router), redirect_stderr(stderr_router):
        yield {
            "stdout": stdout_router,
            "stderr": stderr_router,
            "base_stdout": base_stdout,
            "base_stderr": base_stderr,
        }
