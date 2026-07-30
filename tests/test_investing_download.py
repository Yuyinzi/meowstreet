import json
from pathlib import Path

import httpx
import pytest

from app.data_sources.chrome_cdp import ChromeCDP
from app.data_sources.investing_download import (
    DOWNLOAD_DIR,
    download_commodity_csv,
    wait_for_completed_csv,
)


def _market(**overrides):
    m = {
        "price_page_url": "https://www.investing.com/commodities/copper-historical-data",
        "display_name": "Copper (COMEX)",
        "instrument_id": 8831,
    }
    m.update(overrides)
    return m


def _cdp_targets_client(version_payload=None, targets=None):
    if version_payload is None:
        version_payload = {
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"
        }
    if targets is None:
        targets = [
            {
                "type": "page",
                "url": "https://www.investing.com/commodities/copper-historical-data",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
            }
        ]

    def handler(request):
        if request.url.path == "/json/version":
            return httpx.Response(200, json=version_payload)
        if request.url.path == "/json":
            return httpx.Response(200, json=targets)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


class _FakeSocket:
    def __init__(self, messages=None):
        self.sent = []
        self.closed = False
        self._messages = messages or []

    def send(self, msg):
        self.sent.append(msg)

    def recv(self):
        return json.dumps(self._messages.pop(0))

    def close(self):
        self.closed = True


def _result_msg(result_id, value):
    return {"id": result_id, "result": {"result": {"type": "object", "value": value}}}


def _page_that_navigates_and_returns_ready(
    tmp_path, csv_filename="download.csv", click_success=True, create_csv_on_click=False
):
    csv_path = tmp_path / csv_filename
    messages = [
        {"id": 1, "result": {"data": "ok"}},  # Browser.setDownloadBehavior
        {"id": 2, "result": {}},  # Page.navigate
        {"id": 3, "result": {"result": {"type": "string", "value": "complete"}}},
    ]
    if click_success:
        messages.append(
            {
                "id": 4,
                "result": {
                    "result": {
                        "type": "object",
                        "value": {"clicked": True, "tag": "A", "text": "Download Data"},
                    }
                },
            }
        )
    socket = _FakeSocket(messages)

    class FakePageCDP(ChromeCDP):
        def __init__(self, url, **kwargs):
            super().__init__(url, websocket_factory=lambda u, **kw: socket)

        def evaluate(self, expression):
            result = super().evaluate(expression)
            if create_csv_on_click and "download data" in expression.lower():
                csv_path.write_text("Date,Price\n2026-07-30,4.5\n", encoding="utf-8")
            return result

    return FakePageCDP, socket, csv_path


class _FakeBrowserCDP:
    def __init__(self, url, **kwargs):
        self.methods = []
        self.closed = False
        self._url = url

    def command(self, method, params=None):
        self.methods.append(method)
        return {"data": "ok"}

    def close(self):
        self.closed = True


class _FakePageCDPNoNav:
    def __init__(self, url, **kwargs):
        self.closed = False
        self.methods = []
        self._url = url
        self._messages = []

    def command(self, method, params=None):
        self.methods.append(method)
        return {}

    def evaluate(self, expression):
        return {"ready": True}

    def close(self):
        self.closed = True


# --- wait_for_completed_csv tests ---


def test_download_wait_rejects_unfinished_crdownload(tmp_path):
    (tmp_path / "commodity.csv.crdownload").write_text("partial", encoding="utf-8")
    result = wait_for_completed_csv(tmp_path, before_names=set(), timeout_seconds=0)
    assert result is None


def test_download_wait_returns_only_new_completed_csv(tmp_path):
    (tmp_path / "old.csv").write_text("old", encoding="utf-8")
    new_path = tmp_path / "new.csv"
    new_path.write_text("Date,Price\n2026-07-30,4.5\n", encoding="utf-8")
    result = wait_for_completed_csv(
        tmp_path, before_names={"old.csv"}, timeout_seconds=0
    )
    assert result == new_path


def test_download_wait_returns_none_when_no_new_file(tmp_path):
    (tmp_path / "existing.csv").write_text("data", encoding="utf-8")
    result = wait_for_completed_csv(
        tmp_path, before_names={"existing.csv"}, timeout_seconds=0
    )
    assert result is None


# --- download_commodity_csv tests ---


def test_download_reuses_existing_page_and_closes_only_websockets(tmp_path):
    page_cdp_cls, socket, csv_path = _page_that_navigates_and_returns_ready(
        tmp_path, create_csv_on_click=True
    )

    browser_instance = _FakeBrowserCDP("ws://127.0.0.1:9222/devtools/browser/1")
    result = download_commodity_csv(
        _market(),
        http_client=_cdp_targets_client(),
        browser_cdp_factory=lambda url, **kw: browser_instance,
        page_cdp_factory=page_cdp_cls,
        download_dir=tmp_path,
        timeout_seconds=5,
    )
    assert result["status"] == "ok"
    assert "Browser.close" not in browser_instance.methods
    assert "Target.createTarget" not in browser_instance.methods


def test_download_returns_reauth_when_no_investing_page(tmp_path):
    client = _cdp_targets_client(
        targets=[],
        version_payload={
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"
        },
    )
    result = download_commodity_csv(
        _market(),
        http_client=client,
        download_dir=tmp_path,
        timeout_seconds=1,
    )
    assert result["status"] == "session_reauth_required"
    assert "No Investing.com page found" in result["message"]


def test_download_returns_reauth_when_chrome_unreachable(tmp_path):
    def unreachable(request):
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(unreachable))
    result = download_commodity_csv(
        _market(),
        http_client=client,
        download_dir=tmp_path,
        timeout_seconds=1,
    )
    assert result["status"] == "session_reauth_required"
    assert "503" in result["message"]


def test_download_fails_when_csv_not_created_in_time(tmp_path):
    page_cdp_cls, socket, _ = _page_that_navigates_and_returns_ready(tmp_path)

    browser_instance = _FakeBrowserCDP("ws://127.0.0.1:9222/devtools/browser/1")
    result = download_commodity_csv(
        _market(),
        http_client=_cdp_targets_client(),
        browser_cdp_factory=lambda url, **kw: browser_instance,
        page_cdp_factory=page_cdp_cls,
        download_dir=tmp_path,
        timeout_seconds=0,
    )
    assert result["status"] == "download_failed"
    assert (
        "timed out" in result["message"].lower()
        or "no new csv" in result["message"].lower()
    )
