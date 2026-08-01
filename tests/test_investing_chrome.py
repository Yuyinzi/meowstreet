import json
from pathlib import Path

import httpx
import pytest

from app.data_sources import investing_chrome
from app.data_sources.investing_chrome import (
    fetch_investing_history,
    start_investing_chrome,
)


def _market():
    return {
        "instrument_id": 8831,
        "price_page_url": "https://www.investing.com/commodities/copper-historical-data",
    }


def _targets_response(targets):
    def handler(request):
        return httpx.Response(200, json=targets)

    return handler


_INVESTING_TARGET = [
    {
        "type": "page",
        "url": "https://www.investing.com/commodities/copper-historical-data",
        "webSocketDebuggerUrl": "ws://localhost/investing",
    },
]


def _cdp_factory_for(_socket):
    class FakeCDP:
        def __init__(self, url, websocket_factory=None):
            self.url = url
            self.closed = False
            self.evaluation_count = 0

        def evaluate(self, expr):
            self.evaluation_count += 1
            return {
                "status": 200,
                "contentType": "application/json",
                "body": json.dumps(
                    {
                        "data": [{"rowDate": "2026-07-29", "last_close": 4.5}],
                    }
                ),
            }

        def close(self):
            self.closed = True

    return FakeCDP


def _noop_factory(api_result):
    class FakeCDP:
        def __init__(self, url, websocket_factory=None):
            self.closed = False

        def evaluate(self, expr):
            return api_result

        def close(self):
            self.closed = True

    return FakeCDP


def test_fetch_reuses_one_existing_investing_target_for_all_ranges():
    transport = httpx.MockTransport(_targets_response(_INVESTING_TARGET))
    client = httpx.Client(transport=transport)

    result = fetch_investing_history(
        _market(),
        "2020-01-01",
        "2026-07-30",
        http_client=client,
        cdp_factory=_cdp_factory_for(None),
    )
    assert result["status"] == "ok"
    assert result["payload"]["data"] == [{"rowDate": "2026-07-29", "last_close": 4.5}]
    assert result["retrieved_at"] is not None


def test_fetch_requires_an_open_verified_investing_page():
    transport = httpx.MockTransport(_targets_response([]))
    client = httpx.Client(transport=transport)

    result = fetch_investing_history(
        _market(),
        http_client=client,
        cdp_factory=_cdp_factory_for(None),
    )
    assert result["status"] == "session_reauth_required"
    assert "leave it open" in result["message"]


def test_fetch_closes_the_cdp_websocket_in_finally():
    transport = httpx.MockTransport(_targets_response(_INVESTING_TARGET))
    client = httpx.Client(transport=transport)

    result = fetch_investing_history(
        _market(),
        "2026-07-01",
        "2026-07-30",
        http_client=client,
        cdp_factory=_cdp_factory_for(None),
    )
    assert result["status"] == "ok"


def test_fetch_reports_missing_cdp_endpoint():
    def handler(request):
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    result = fetch_investing_history(
        _market(),
        http_client=client,
        cdp_factory=_cdp_factory_for(None),
    )
    assert result["status"] == "session_reauth_required"
    assert "503" in result["message"]


def test_fetch_reports_websocket_connection_rejection():
    transport = httpx.MockTransport(_targets_response(_INVESTING_TARGET))
    client = httpx.Client(transport=transport)

    class FailingCDP:
        def __init__(self, websocket_url):
            raise RuntimeError("Handshake status 403 Forbidden")

    result = fetch_investing_history(
        _market(),
        "2026-07-01",
        "2026-07-30",
        http_client=client,
        cdp_factory=FailingCDP,
    )

    assert result["status"] == "session_reauth_required"
    assert "WebSocket" in result["message"]


def test_start_chrome_allows_the_local_cdp_websocket_origin(monkeypatch, tmp_path):
    command = []

    def fake_popen(args, **kwargs):
        command.extend(args)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    start_investing_chrome(profile_dir=tmp_path / "chrome", cdp_port=9222)

    assert "--remote-allow-origins=http://127.0.0.1:9222" in command


def test_fetch_reports_api_http_error():
    transport = httpx.MockTransport(_targets_response(_INVESTING_TARGET))
    client = httpx.Client(transport=transport)

    result = fetch_investing_history(
        _market(),
        "2026-07-01",
        "2026-07-30",
        http_client=client,
        cdp_factory=_noop_factory(
            {"status": 403, "contentType": "text/html", "body": "Forbidden"}
        ),
    )
    assert result["status"] == "session_reauth_required"
    assert "403" in result["message"]


def test_fetch_reports_non_json_response():
    transport = httpx.MockTransport(_targets_response(_INVESTING_TARGET))
    client = httpx.Client(transport=transport)

    result = fetch_investing_history(
        _market(),
        "2026-07-01",
        "2026-07-30",
        http_client=client,
        cdp_factory=_noop_factory(
            {"status": 200, "contentType": "text/html", "body": "<html></html>"}
        ),
    )
    assert result["status"] == "session_reauth_required"
    assert "instead of JSON" in result["message"]


def test_investing_fetch_does_not_depend_on_playwright_or_create_pages():
    source = Path("app/data_sources/investing_chrome.py").read_text(encoding="utf-8")
    assert "sync_playwright" not in source
    assert "new_page(" not in source
    assert "page.close(" not in source


def test_start_chrome_headless_adds_headless_flag_and_accepts_config(
    monkeypatch, tmp_path
):
    command = []

    def fake_popen(args, **kwargs):
        command.extend(args)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    start_investing_chrome(
        profile_dir=tmp_path / "headless",
        cdp_port=9333,
        headless=True,
        initial_url="https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data",
    )

    assert "--headless=new" in command
    assert "--remote-debugging-port=9333" in command
    assert "--remote-allow-origins=http://127.0.0.1:9333" in command
    assert f"--user-data-dir={tmp_path / 'headless'}" in command
    assert (
        command[-1]
        == "https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data"
    )


def test_start_chrome_interactive_omits_headless_flag(monkeypatch, tmp_path):
    command = []

    def fake_popen(args, **kwargs):
        command.extend(args)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    start_investing_chrome(profile_dir=tmp_path / "chrome", cdp_port=9222)

    assert "--headless=new" not in command
    assert "--remote-debugging-port=9222" in command
    assert "--remote-allow-origins=http://127.0.0.1:9222" in command
    assert f"--user-data-dir={tmp_path / 'chrome'}" in command
    assert command[-1] == "https://www.investing.com/commodities/copper-historical-data"


def test_start_chrome_returns_the_launched_process(monkeypatch, tmp_path):
    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.args = args

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    proc = start_investing_chrome(profile_dir=tmp_path / "chrome", cdp_port=9222)
    assert isinstance(proc, FakeProcess)


def test_start_chrome_rejects_invalid_cdp_port(monkeypatch, tmp_path):
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    with pytest.raises(ValueError, match="invalid cdp port"):
        start_investing_chrome(profile_dir=tmp_path / "chrome", cdp_port=99999)


def test_start_chrome_rejects_zero_cdp_port(monkeypatch, tmp_path):
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    with pytest.raises(ValueError, match="invalid cdp port"):
        start_investing_chrome(profile_dir=tmp_path / "chrome", cdp_port=0)


def test_start_chrome_rejects_non_numeric_cdp_port(monkeypatch, tmp_path):
    monkeypatch.setattr(investing_chrome, "_find_chrome", lambda: "google-chrome")

    with pytest.raises(ValueError, match="invalid cdp port"):
        start_investing_chrome(profile_dir=tmp_path / "chrome", cdp_port="not-a-port")


def test_start_chrome_raises_value_error_when_chrome_missing(monkeypatch, tmp_path):
    def missing_chrome():
        raise ValueError("Chrome not found")

    monkeypatch.setattr(investing_chrome, "_find_chrome", missing_chrome)

    with pytest.raises(ValueError, match="Chrome not found"):
        start_investing_chrome(profile_dir=tmp_path / "chrome")
