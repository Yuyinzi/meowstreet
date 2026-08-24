from contextlib import contextmanager
import threading
import time
from urllib.parse import urlparse


class FredRateLimiter:
    def __init__(self, min_interval_seconds=0.6, monotonic=None, sleep=None):
        if min_interval_seconds < 0:
            raise ValueError("fred limiter interval must not be negative")
        if monotonic is None:
            monotonic = time.monotonic
        if sleep is None:
            sleep = time.sleep
        self._min_interval_seconds = float(min_interval_seconds)
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_start = None

    def wait(self):
        with self._lock:
            now = self._monotonic()
            if self._last_start is not None:
                delay = self._last_start + self._min_interval_seconds - now
                if delay > 0:
                    self._sleep(delay)
            self._last_start = self._monotonic()


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
