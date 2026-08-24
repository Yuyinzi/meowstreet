import threading

import pytest

from app.services.macro_refresh_resources import ArtifactStore
from app.services.macro_refresh_resources import FredRateLimiter
from app.services.macro_refresh_resources import RequestCoordinator
from app.services.macro_refresh_resources import SQLiteWriterGate


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeLock:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.timeouts = []
        self.releases = 0

    def acquire(self, timeout):
        self.timeouts.append(timeout)
        return self.acquired

    def release(self):
        self.releases += 1


def test_fred_limiter_serializes_two_lanes_on_one_budget():
    clock = FakeClock()
    limiter = FredRateLimiter(
        min_interval_seconds=0.6,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    limiter.wait()
    limiter.wait()
    limiter.wait()

    assert clock.sleeps == [0.6, 0.6]
    assert clock.now == pytest.approx(1.2)


def test_request_coordinator_limits_fred_urls_but_not_other_urls():
    clock = FakeClock()
    limiter = FredRateLimiter(
        min_interval_seconds=0.6,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    coordinator = RequestCoordinator(limiter)

    coordinator.before_request("GET", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL")
    coordinator.before_request("GET", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
    coordinator.before_request("GET", "https://example.test/data")

    assert clock.sleeps == [0.6]


def test_fred_limiter_shares_budget_between_threads():
    clock = FakeClock()
    limiter = FredRateLimiter(
        min_interval_seconds=0.6,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    barrier = threading.Barrier(2)
    calls = []

    def worker(lane):
        barrier.wait()
        limiter.wait()
        calls.append(lane)

    threads = [threading.Thread(target=worker, args=(lane,)) for lane in ("fred_macro", "credit")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(calls) == ["credit", "fred_macro"]
    assert clock.sleeps == [0.6]


def test_sqlite_writer_gate_reports_timeout():
    lock = FakeLock(acquired=False)
    gate = SQLiteWriterGate(lock=lock)

    with pytest.raises(TimeoutError, match="sqlite writer gate timed out after 60 seconds"):
        with gate.acquire(timeout=60):
            pass

    assert lock.timeouts == [60]
    assert lock.releases == 0


def test_sqlite_writer_gate_releases_after_context():
    lock = FakeLock(acquired=True)
    gate = SQLiteWriterGate(lock=lock)

    with gate.acquire(timeout=12):
        pass

    assert lock.timeouts == [12]
    assert lock.releases == 1


def test_artifact_store_rejects_missing_key():
    store = ArtifactStore()

    with pytest.raises(ValueError, match="macro refresh artifact is missing: m2"):
        store.get("m2")


def test_artifact_store_put_get_and_pop_are_thread_safe():
    store = ArtifactStore()
    store.put("m2", {"rows": 1})

    assert store.get("m2") == {"rows": 1}
    assert store.pop("m2") == {"rows": 1}
    with pytest.raises(ValueError, match="macro refresh artifact is missing: m2"):
        store.pop("m2")
