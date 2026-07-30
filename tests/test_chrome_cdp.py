import json
from pathlib import Path

import httpx
import pytest

from app.data_sources.chrome_cdp import (
    ChromeCDP,
    find_browser_target,
    find_page_target,
    load_chrome_targets,
    load_chrome_version,
)


def test_find_page_target_selects_existing_investing_page():
    target = find_page_target(
        [
            {
                "type": "page",
                "url": "https://www.investing.com/commodities/copper-historical-data",
                "webSocketDebuggerUrl": "ws://localhost/page/1",
            },
            {
                "type": "page",
                "url": "https://example.com",
                "webSocketDebuggerUrl": "ws://localhost/page/2",
            },
            {
                "type": "page",
                "url": "https://other.investing.com/page",
                "webSocketDebuggerUrl": "ws://localhost/page/3",
            },
        ],
        "www.investing.com",
    )
    assert target["webSocketDebuggerUrl"] == "ws://localhost/page/1"


def test_find_page_target_never_creates_a_target_when_none_matches():
    assert find_page_target([], "www.investing.com") is None


def test_find_page_target_ignores_non_page_targets():
    target = find_page_target(
        [
            {
                "type": "iframe",
                "url": "https://www.investing.com/commodities/copper-historical-data",
                "webSocketDebuggerUrl": "ws://localhost/page/1",
            },
        ],
        "www.investing.com",
    )
    assert target is None


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


def _error_msg(result_id, message):
    return {"id": result_id, "error": {"message": message}}


def test_evaluate_sends_runtime_evaluate_and_returns_value():
    socket = _FakeSocket(messages=[_result_msg(1, {"data": []})])
    client = ChromeCDP(
        "ws://localhost/page/1", websocket_factory=lambda url, timeout: socket
    )
    result = client.evaluate("({data: []})")
    assert result == {"data": []}
    sent = json.loads(socket.sent[0])
    assert sent["method"] == "Runtime.evaluate"


def test_close_closes_only_websocket():
    socket = _FakeSocket()
    client = ChromeCDP(
        "ws://localhost/page/1", websocket_factory=lambda url, timeout: socket
    )
    assert socket.closed is False
    client.close()
    assert socket.closed is True


def test_evaluate_reports_javascript_exception():
    socket = _FakeSocket(
        messages=[
            {
                "id": 1,
                "result": {
                    "result": {"type": "object", "value": {"status": "error"}},
                    "exceptionDetails": {"text": "ReferenceError: foo is not defined"},
                },
            }
        ]
    )
    client = ChromeCDP(
        "ws://localhost/page/1", websocket_factory=lambda url, timeout: socket
    )
    with pytest.raises(ValueError, match="JavaScript exception"):
        client.evaluate("foo.bar")


def test_load_chrome_targets_returns_targets():
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {
                    "type": "page",
                    "url": "https://www.investing.com/",
                    "webSocketDebuggerUrl": "ws://x/1",
                },
            ],
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    targets, error = load_chrome_targets(client, "http://127.0.0.1:9222")
    assert error is None
    assert isinstance(targets, list)
    assert targets[0]["type"] == "page"


def test_load_chrome_targets_reports_cdp_unreachable():
    def handler(request):
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    targets, error = load_chrome_targets(client, "http://127.0.0.1:9222")
    assert targets is None
    assert "503" in error


def test_find_browser_target_reads_browser_websocket_url():
    assert (
        find_browser_target(
            {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"}
        )
        == "ws://127.0.0.1:9222/devtools/browser/1"
    )


def test_find_browser_target_returns_none_when_missing():
    assert find_browser_target({}) is None
    assert find_browser_target({"webSocketDebuggerUrl": None}) is None


def test_load_chrome_version_returns_version_payload():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1",
                "Browser": "Chrome/126.0.0.0",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload, error = load_chrome_version(client, "http://127.0.0.1:9222")
    assert error is None
    assert payload["webSocketDebuggerUrl"] == "ws://127.0.0.1:9222/devtools/browser/1"


def test_load_chrome_version_reports_cdp_unreachable():
    def handler(request):
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload, error = load_chrome_version(client, "http://127.0.0.1:9222")
    assert payload is None
    assert "503" in error


def test_command_sends_generic_cdp_method_and_returns_result():
    socket = _FakeSocket(messages=[{"id": 1, "result": {"data": "ok"}}])
    client = ChromeCDP(
        "ws://localhost/browser/1", websocket_factory=lambda url, timeout: socket
    )
    result = client.command("Browser.setDownloadBehavior", {"behavior": "allow"})
    assert result == {"data": "ok"}
    sent = json.loads(socket.sent[0])
    assert sent["method"] == "Browser.setDownloadBehavior"


def test_command_raises_on_protocol_error():
    socket = _FakeSocket(messages=[{"id": 1, "error": {"message": "not allowed"}}])
    client = ChromeCDP(
        "ws://localhost/browser/1", websocket_factory=lambda url, timeout: socket
    )
    with pytest.raises(ValueError, match="not allowed"):
        client.command("Browser.close")


def test_command_id_does_not_conflict_with_evaluate_id():
    socket = _FakeSocket(
        messages=[
            _result_msg(1, "eval_result"),
            {"id": 2, "result": {"the_data": 42}},
        ]
    )
    client = ChromeCDP(
        "ws://localhost/browser/1", websocket_factory=lambda url, timeout: socket
    )
    assert client.evaluate("1+1") == "eval_result"
    result = client.command("Some.method")
    assert result == {"the_data": 42}


def test_local_investing_artifacts_are_ignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert "/data/private/investing_chrome_profile/" in gitignore
