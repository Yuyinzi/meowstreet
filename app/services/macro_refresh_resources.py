from contextlib import contextmanager
import threading
import time
from urllib.parse import urlparse


class RefreshInterruptedError(RuntimeError):
    pass


class FredRateLimiter:
    def __init__(
        self,
        min_interval_seconds=0.6,
        monotonic=None,
        sleep=None,
        cancel_event=None,
    ):
        if min_interval_seconds < 0:
            raise ValueError("fred limiter interval must not be negative")
        if monotonic is None:
            monotonic = time.monotonic
        if sleep is None:
            sleep = time.sleep
        self._min_interval_seconds = float(min_interval_seconds)
        self._monotonic = monotonic
        self._sleep = sleep
        self._cancel_event = cancel_event
        self._lock = threading.Lock()
        self._last_start = None

    def wait(self):
        with self._lock:
            self._raise_if_interrupted()
            now = self._monotonic()
            if self._last_start is not None:
                delay = self._last_start + self._min_interval_seconds - now
                if delay > 0:
                    if self._cancel_event is None:
                        self._sleep(delay)
                    elif self._cancel_event.wait(delay):
                        raise RefreshInterruptedError("refresh interrupted")
            self._raise_if_interrupted()
            self._last_start = self._monotonic()

    def _raise_if_interrupted(self):
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise RefreshInterruptedError("refresh interrupted")


class RequestCoordinator:
    def __init__(self, fred_limiter):
        self._fred_limiter = fred_limiter

    def before_request(self, method, url):
        if _is_fred_url(url):
            self._fred_limiter.wait()


class SQLiteWriterGate:
    def __init__(self, lock=None):
        self._lock = lock or threading.Lock()

    @contextmanager
    def acquire(self, timeout=60):
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"sqlite writer gate timed out after {timeout} seconds"
            )
        try:
            yield
        finally:
            self._lock.release()


class ArtifactStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._values = {}

    def put(self, key, value):
        with self._lock:
            self._values[key] = value

    def get(self, key):
        with self._lock:
            if key not in self._values:
                raise ValueError(f"macro refresh artifact is missing: {key}")
            return self._values[key]

    def pop(self, key):
        with self._lock:
            if key not in self._values:
                raise ValueError(f"macro refresh artifact is missing: {key}")
            return self._values.pop(key)


def _is_fred_url(url):
    return urlparse(str(url)).hostname == "fred.stlouisfed.org"
