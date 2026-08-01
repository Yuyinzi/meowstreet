import fcntl

import httpx
import pytest

from app.db import macro_indicators
from app.services.investing_rendered_refresh import (
    _acquire_lock,
    _wait_for_cdp,
    refresh_investing_rendered,
)


class FakeProc:
    def __init__(self):
        self.terminated = 0
        self.waited = 0

    def terminate(self):
        self.terminated += 1

    def wait(self):
        self.waited += 1


def _ready_wait(client, endpoint, timeout):
    return [
        {
            "type": "page",
            "url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/1",
        }
    ]


def _importer_result():
    return {
        "series": 1,
        "observations": 2,
        "ranges": {
            "iron_ore_62_cfr_china": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            }
        },
        "no_new_data": [],
    }


def _noop_importer_result():
    return {
        "series": 0,
        "observations": 0,
        "ranges": {},
        "no_new_data": ["iron_ore_62_cfr_china"],
    }


def test_refresh_success_launches_waits_imports_and_terminates(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    launched = FakeProc()
    started = {}

    def fake_start_chrome(**kwargs):
        started.update(kwargs)
        return launched

    wait_calls = []

    def fake_wait(client, endpoint, timeout):
        wait_calls.append((endpoint, timeout))

    import_calls = []

    def fake_importer(con, **kwargs):
        import_calls.append(kwargs)
        return _importer_result()

    result = refresh_investing_rendered(
        con,
        lock_path=tmp_path / "refresh.lock",
        profile_dir=tmp_path / "profile",
        cdp_port=9223,
        readiness_timeout=30,
        start_chrome=fake_start_chrome,
        wait_for_cdp=fake_wait,
        importer=fake_importer,
    )

    assert started["headless"] is True
    assert started["cdp_port"] == 9223
    assert started["profile_dir"] == tmp_path / "profile"
    assert wait_calls == [("http://127.0.0.1:9223", 30)]
    assert import_calls == [
        {
            "markets": ["iron_ore_62_cfr_china"],
            "cdp_endpoint": "http://127.0.0.1:9223",
        }
    ]
    assert result["status"] == "ok"
    assert result["observations"] == 2
    assert result["cdp_endpoint"] == "http://127.0.0.1:9223"
    assert result["profile_dir"] == str(tmp_path / "profile")
    assert launched.terminated == 1
    assert launched.waited == 1


def test_refresh_noop_returns_zero_observations_and_cleans_up(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    launched = FakeProc()

    result = refresh_investing_rendered(
        con,
        lock_path=tmp_path / "refresh.lock",
        start_chrome=lambda **kwargs: launched,
        wait_for_cdp=_ready_wait,
        importer=lambda con, **kwargs: _noop_importer_result(),
    )

    assert result["status"] == "ok"
    assert result["observations"] == 0
    assert result["no_new_data"] == ["iron_ore_62_cfr_china"]
    assert launched.terminated == 1
    assert launched.waited == 1


def test_refresh_reports_cdp_never_ready_and_cleans_up(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    launched = FakeProc()

    def never_ready(client, endpoint, timeout):
        raise ValueError(f"Chrome CDP endpoint at {endpoint} did not become ready")

    with pytest.raises(ValueError, match="did not become ready"):
        refresh_investing_rendered(
            con,
            lock_path=tmp_path / "refresh.lock",
            start_chrome=lambda **kwargs: launched,
            wait_for_cdp=never_ready,
            importer=lambda con, **kwargs: _importer_result(),
        )
    assert launched.terminated == 1
    assert launched.waited == 1


def test_refresh_propagates_import_failure_and_cleans_up(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    launched = FakeProc()

    def failing_importer(con, **kwargs):
        raise ValueError("rendered history fetch failed")

    with pytest.raises(ValueError, match="rendered history fetch failed"):
        refresh_investing_rendered(
            con,
            lock_path=tmp_path / "refresh.lock",
            start_chrome=lambda **kwargs: launched,
            wait_for_cdp=_ready_wait,
            importer=failing_importer,
        )
    assert launched.terminated == 1
    assert launched.waited == 1


def test_refresh_raises_when_lock_already_held_without_starting_chrome(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    lock_path = tmp_path / "refresh.lock"
    lock_file = open(lock_path, "w")
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        started = []

        def fake_start_chrome(**kwargs):
            started.append(kwargs)
            return FakeProc()

        with pytest.raises(ValueError, match="already running"):
            refresh_investing_rendered(
                con,
                lock_path=lock_path,
                start_chrome=fake_start_chrome,
                wait_for_cdp=_ready_wait,
                importer=lambda con, **kwargs: _importer_result(),
            )
        assert started == []
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def test_cleanup_terminates_only_the_process_the_service_launched(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    launched = FakeProc()
    preexisting = FakeProc()

    def failing_importer(con, **kwargs):
        raise ValueError("import failed")

    with pytest.raises(ValueError, match="import failed"):
        refresh_investing_rendered(
            con,
            lock_path=tmp_path / "refresh.lock",
            start_chrome=lambda **kwargs: launched,
            wait_for_cdp=_ready_wait,
            importer=failing_importer,
        )
    assert launched.terminated == 1
    assert launched.waited == 1
    assert preexisting.terminated == 0
    assert preexisting.waited == 0


def test_refresh_converts_browser_start_oserror_to_value_error(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")

    def failing_start_chrome(**kwargs):
        raise OSError("profile directory is locked")

    with pytest.raises(ValueError, match="failed to start headless Chrome"):
        refresh_investing_rendered(
            con,
            lock_path=tmp_path / "refresh.lock",
            profile_dir=tmp_path / "profile",
            start_chrome=failing_start_chrome,
            wait_for_cdp=_ready_wait,
            importer=lambda con, **kwargs: _importer_result(),
        )


def test_refresh_browser_start_failure_releases_lock(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    lock_path = tmp_path / "refresh.lock"

    def failing_start_chrome(**kwargs):
        raise OSError("profile directory is locked")

    with pytest.raises(ValueError, match="failed to start headless Chrome"):
        refresh_investing_rendered(
            con,
            lock_path=lock_path,
            start_chrome=failing_start_chrome,
            wait_for_cdp=_ready_wait,
            importer=lambda con, **kwargs: _importer_result(),
        )

    launched = FakeProc()
    result = refresh_investing_rendered(
        con,
        lock_path=lock_path,
        start_chrome=lambda **kwargs: launched,
        wait_for_cdp=_ready_wait,
        importer=lambda con, **kwargs: _importer_result(),
    )
    assert result["status"] == "ok"
    assert launched.terminated == 1


def test_acquire_lock_converts_mkdir_failure_to_value_error(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot create lock file"):
        _acquire_lock(blocker / "refresh.lock")


def test_wait_for_cdp_returns_targets_when_reachable():
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {
                    "type": "page",
                    "url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data",
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/1",
                }
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    targets = _wait_for_cdp(client, "http://127.0.0.1:9223", 5)
    assert targets[0]["type"] == "page"


def test_wait_for_cdp_reports_timeout_descriptively():
    class FailingClient:
        def request(self, method, url, **kwargs):
            raise RuntimeError("connection refused")

    with pytest.raises(ValueError, match="did not become ready"):
        _wait_for_cdp(FailingClient(), "http://127.0.0.1:9223", 0.01)
