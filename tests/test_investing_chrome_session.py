import httpx
import pytest

from app.data_sources import investing_chrome
from app.http_client import HttpClient
from app.services import investing_chrome_session


def test_existing_chrome_is_reused_without_launch(monkeypatch):
    def unexpected_launch(**kwargs):
        pytest.fail("existing Chrome must not launch a duplicate")

    monkeypatch.setattr(investing_chrome, "start_investing_chrome", unexpected_launch)
    client = HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    assert investing_chrome_session.ensure_investing_chrome(client, "http://127.0.0.1:9222", 1) == []


def test_missing_chrome_starts_interactive_session_and_waits(monkeypatch):
    launched = []
    requests = []

    def response(request):
        requests.append(request)
        if not launched:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=[{"type": "page"}])

    monkeypatch.setattr(investing_chrome, "start_investing_chrome", lambda **kwargs: launched.append(kwargs))
    client = HttpClient(transport=httpx.MockTransport(response), max_attempts=1)
    assert investing_chrome_session.ensure_investing_chrome(client, "http://127.0.0.1:9333", 1) == [{"type": "page"}]
    assert launched == [{"cdp_port": 9333, "headless": False}]
    assert len(requests) == 2
    assert requests[0].url.path == "/json"


def test_startup_timeout_is_bounded_and_launches_once(monkeypatch):
    launched = []
    ticks = iter([0, 0, 0, 2])
    monkeypatch.setattr(investing_chrome_session, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(investing_chrome_session, "sleep", lambda seconds: None)
    monkeypatch.setattr(investing_chrome, "start_investing_chrome", lambda **kwargs: launched.append(kwargs))
    client = HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)), max_attempts=1)
    with pytest.raises(ValueError, match="did not become ready"):
        investing_chrome_session.ensure_investing_chrome(client, "http://127.0.0.1:9222", 1)
    assert len(launched) == 1


def test_unavailable_remote_endpoint_does_not_launch_local_chrome(monkeypatch):
    def unexpected_launch(**kwargs):
        pytest.fail("remote CDP must not launch local Chrome")

    monkeypatch.setattr(investing_chrome, "start_investing_chrome", unexpected_launch)
    client = HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)), max_attempts=1)
    with pytest.raises(ValueError, match="remote"):
        investing_chrome_session.ensure_investing_chrome(client, "http://chrome.example:9222", 1)
