import fcntl

import httpx
import pytest

from app.db import macro_indicators
from app.services.investing_rendered_refresh import (
    _acquire_lock,
    _wait_for_cdp,
    refresh_investing_rendered,
)


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


def test_refresh_attaches_existing_interactive_chrome_without_starting_another(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    wait_calls = []

    def ready_wait(client, endpoint, timeout):
        wait_calls.append((endpoint, timeout))

    result = refresh_investing_rendered(
        con,
        lock_path=tmp_path / "refresh.lock",
        cdp_port=9222,
        readiness_timeout=30,
        wait_for_cdp=ready_wait,
        importer=lambda con, **kwargs: _importer_result(),
    )

    assert wait_calls == [("http://127.0.0.1:9222", 30)]
    assert result["status"] == "ok"
    assert result["cdp_endpoint"] == "http://127.0.0.1:9222"


def test_refresh_waits_for_existing_chrome_and_imports(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
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
        cdp_port=9222,
        readiness_timeout=30,
        wait_for_cdp=fake_wait,
        importer=fake_importer,
    )

    assert wait_calls == [("http://127.0.0.1:9222", 30)]
    assert import_calls == [
        {
            "markets": ["iron_ore_62_cfr_china"],
            "cdp_endpoint": "http://127.0.0.1:9222",
        }
    ]
    assert result["status"] == "ok"
    assert result["observations"] == 2
    assert result["cdp_endpoint"] == "http://127.0.0.1:9222"


def test_refresh_noop_returns_zero_observations(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")

    result = refresh_investing_rendered(
        con,
        lock_path=tmp_path / "refresh.lock",
        wait_for_cdp=lambda *args: None,
        importer=lambda con, **kwargs: _noop_importer_result(),
    )

    assert result["status"] == "ok"
    assert result["observations"] == 0
    assert result["no_new_data"] == ["iron_ore_62_cfr_china"]


def test_refresh_reports_unavailable_existing_chrome(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")

    def never_ready(client, endpoint, timeout):
        raise ValueError(f"Chrome CDP endpoint at {endpoint} did not become ready")

    with pytest.raises(ValueError, match="did not become ready"):
        refresh_investing_rendered(
            con,
            lock_path=tmp_path / "refresh.lock",
            wait_for_cdp=never_ready,
            importer=lambda con, **kwargs: _importer_result(),
        )


def test_refresh_propagates_import_failure(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")

    def failing_importer(con, **kwargs):
        raise ValueError("rendered history fetch failed")

    with pytest.raises(ValueError, match="rendered history fetch failed"):
        refresh_investing_rendered(
            con,
            lock_path=tmp_path / "refresh.lock",
            wait_for_cdp=lambda *args: None,
            importer=failing_importer,
        )


def test_refresh_raises_when_lock_already_held(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    lock_path = tmp_path / "refresh.lock"
    lock_file = open(lock_path, "w")
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(ValueError, match="already running"):
            refresh_investing_rendered(
                con,
                lock_path=lock_path,
                wait_for_cdp=lambda *args: None,
                importer=lambda con, **kwargs: _importer_result(),
            )
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


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
