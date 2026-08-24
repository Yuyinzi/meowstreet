from pathlib import Path

import httpx
import pytest

from app.http_client import DEFAULT_USER_AGENT, HttpClient
from app.http_client import use_request_coordinator


def test_request_adds_user_agent_and_forwards_params():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["user_agent"] = request.headers["User-Agent"]
        return httpx.Response(200, content=b"ok")

    response = HttpClient(transport=httpx.MockTransport(handler)).request(
        "GET", "https://example.test/items", params={"page": 2}
    )

    assert response.content == b"ok"
    assert captured["url"] == "https://example.test/items?page=2"
    assert captured["user_agent"] == DEFAULT_USER_AGENT


def test_follows_redirect_to_final_response():
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"Location": "https://example.test/final"},
                request=request,
            )
        return httpx.Response(200, content=b"final content", request=request)

    response = HttpClient(transport=httpx.MockTransport(handler)).request(
        "GET", "https://example.test/start"
    )

    assert response.content == b"final content"
    assert requested_urls == [
        "https://example.test/start",
        "https://example.test/final",
    ]


def test_retries_read_timeout_then_succeeds():
    calls = []
    delays = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("timed out", request=request)

    def fake_sleep(seconds):
        delays.append(seconds)

    handler_called = 0

    def handler_success(request):
        nonlocal handler_called
        handler_called += 1
        if handler_called < 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler_success),
        sleep=fake_sleep,
        jitter=lambda lower, upper: 0.0,
        max_attempts=3,
    )
    response = client.request("GET", "https://example.test/items")

    assert response.content == b"ok"
    assert handler_called == 3
    assert delays == [1.0, 2.0]


def test_retries_429_then_succeeds():
    calls = []
    delays = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, content=b"too many")

    def fake_sleep(seconds):
        delays.append(seconds)

    handler_called = 0

    def handler_429_then_ok(request):
        nonlocal handler_called
        handler_called += 1
        if handler_called < 3:
            return httpx.Response(429, content=b"too many")
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler_429_then_ok),
        sleep=fake_sleep,
        max_attempts=3,
    )
    response = client.request("GET", "https://example.test/items")

    assert response.content == b"ok"
    assert handler_called == 3


def test_retries_503_then_succeeds():
    delays = []

    def fake_sleep(seconds):
        delays.append(seconds)

    handler_called = 0

    def handler(request):
        nonlocal handler_called
        handler_called += 1
        if handler_called < 3:
            return httpx.Response(503, content=b"unavailable")
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        jitter=lambda lower, upper: 0.0,
        max_attempts=3,
    )
    response = client.request("GET", "https://example.test/items")

    assert response.content == b"ok"
    assert handler_called == 3


def test_404_raises_immediately():
    def handler(request):
        return httpx.Response(404, content=b"not found")

    client = HttpClient(transport=httpx.MockTransport(handler), max_attempts=3)
    with pytest.raises(httpx.HTTPStatusError):
        client.request("GET", "https://example.test/items")


def test_final_503_raises_after_three_attempts():
    delays = []

    def fake_sleep(seconds):
        delays.append(seconds)

    handler_called = 0

    def handler(request):
        nonlocal handler_called
        handler_called += 1
        return httpx.Response(503, content=b"unavailable")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        jitter=lambda lower, upper: 0.0,
        max_attempts=3,
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.request("GET", "https://example.test/items")
    assert handler_called == 3


def test_retry_after_on_429_supplies_delay():
    delays = []

    def fake_sleep(seconds):
        delays.append(seconds)

    handler_called = 0

    def handler(request):
        nonlocal handler_called
        handler_called += 1
        if handler_called < 3:
            return httpx.Response(
                429, content=b"too many", headers={"Retry-After": "5"}
            )
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        max_attempts=3,
    )
    response = client.request("GET", "https://example.test/items")
    assert response.content == b"ok"
    assert delays == [5.0, 5.0]


def test_default_delays_are_one_then_two_seconds():
    delays = []

    def fake_sleep(seconds):
        delays.append(seconds)

    handler_called = 0

    def handler(request):
        nonlocal handler_called
        handler_called += 1
        if handler_called < 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        jitter=lambda lower, upper: 0.0,
        max_attempts=3,
    )
    client.request("GET", "https://example.test/items")
    assert delays == [1.0, 2.0]


def test_form_data_reaches_server():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["body"] = request.read()
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, content=b"ok")

    client = HttpClient(transport=httpx.MockTransport(handler))
    client.request(
        "POST",
        "https://example.test/submit",
        data={"table": "1", "year": "1978"},
    )
    assert captured["method"] == "POST"
    assert b"table=1" in captured["body"]
    assert b"year=1978" in captured["body"]
    assert captured["content_type"] == "application/x-www-form-urlencoded"


def test_json_body_reaches_server():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["json"] = request.read()
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, content=b"ok")

    client = HttpClient(transport=httpx.MockTransport(handler))
    client.request(
        "POST",
        "https://example.test/api",
        json={"app_name": "sbet", "params": []},
    )
    assert captured["method"] == "POST"
    assert b"app_name" in captured["json"]
    assert captured["content_type"] == "application/json"


def test_caller_accept_header_merges_with_default_user_agent():
    captured = {}

    def handler(request):
        captured["user_agent"] = request.headers.get("User-Agent")
        captured["accept"] = request.headers.get("Accept")
        return httpx.Response(200, content=b"ok")

    client = HttpClient(transport=httpx.MockTransport(handler))
    client.request(
        "GET",
        "https://example.test/data",
        headers={"Accept": "application/json"},
    )
    assert captured["user_agent"] == DEFAULT_USER_AGENT
    assert captured["accept"] == "application/json"


def test_caller_timeout_overrides_default():
    captured = {}

    def handler(request):
        captured["called"] = True
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        default_timeout=30.0,
    )
    response = client.request("GET", "https://example.test/items", timeout=60.0)
    assert response.content == b"ok"


def test_transport_error_after_exhaustion_raises_original_exception():
    handler_called = 0

    def handler(request):
        nonlocal handler_called
        handler_called += 1
        raise httpx.ReadTimeout("Connection timed out", request=request)

    client = HttpClient(transport=httpx.MockTransport(handler), max_attempts=3)
    with pytest.raises(httpx.ReadTimeout, match="Connection timed out"):
        client.request("GET", "https://example.test/items")
    assert handler_called == 3


def test_request_coordinator_runs_before_each_retry_attempt():
    attempts = []
    sleeps = []

    class RecordingCoordinator:
        def __init__(self):
            self.urls = []

        def before_request(self, method, url):
            self.urls.append((method, url))

    coordinator = RecordingCoordinator()

    def handler(request):
        attempts.append(request.url)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"}, content=b"busy")
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        jitter=lambda lower, upper: 0.25,
        max_attempts=2,
    )
    url = "https://fred.stlouisfed.org/example"
    with use_request_coordinator(coordinator):
        response = client.request("GET", url)

    assert coordinator.urls == [("GET", url), ("GET", url)]
    assert sleeps == [3.0]
    assert response.status_code == 200


def test_exponential_retry_delay_uses_injected_jitter():
    sleeps = []
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        jitter=lambda lower, upper: 0.25,
        max_attempts=2,
    )

    client.request("GET", "https://example.test/items")

    assert sleeps == [1.25]


def test_context_managed_client_reuses_underlying_client(monkeypatch):
    constructed = []

    class RecordingClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = []
            self.closed = False
            constructed.append(self)

        def request(self, method, url, **kwargs):
            self.calls.append((method, url))
            return httpx.Response(200, content=b"ok")

        def close(self):
            self.closed = True

    monkeypatch.setattr("app.http_client.httpx.Client", RecordingClient)
    with HttpClient() as client:
        client.request("GET", "https://example.test/one")
        client.request("GET", "https://example.test/two")

    assert len(constructed) == 1
    assert constructed[0].calls == [
        ("GET", "https://example.test/one"),
        ("GET", "https://example.test/two"),
    ]
    assert constructed[0].closed is True


def test_one_shot_client_closes_underlying_client(monkeypatch):
    constructed = []

    class RecordingClient:
        def __init__(self, **kwargs):
            self.closed = False
            constructed.append(self)

        def request(self, method, url, **kwargs):
            return httpx.Response(200, content=b"ok")

        def close(self):
            self.closed = True

    monkeypatch.setattr("app.http_client.httpx.Client", RecordingClient)
    response = HttpClient().request("GET", "https://example.test/one")

    assert response.content == b"ok"
    assert len(constructed) == 1
    assert constructed[0].closed is True


MIGRATED_FILES = [
    "app/data_sources/fred.py",
    "app/data_sources/cftc_cot.py",
    "app/data_sources/census_nrc.py",
    "app/data_sources/michigan_consumer_sentiment.py",
    "app/data_sources/nfib_sbet.py",
    "app/data_sources/nfib_sbet_api.py",
    "app/data_sources/oil.py",
    "app/tools/market_data.py",
    "scripts/fetch_fomc_documents.py",
    "scripts/fetch_ism_official_reports.py",
]

_URLLIB_BYPASS_EXCLUDES = frozenset({"scripts/extract_ism_report_ai.py"})


def test_no_direct_urllib_in_app_and_scripts():
    root = Path(__file__).resolve().parents[1]
    for dirname in ("app", "scripts"):
        for path in sorted((root / dirname).rglob("*.py")):
            relative = path.relative_to(root)
            if str(relative) in _URLLIB_BYPASS_EXCLUDES:
                continue
            text = path.read_text()
            assert "urlopen" not in text, f"{relative} uses urlopen"
            assert "urlretrieve" not in text, f"{relative} uses urlretrieve"
            assert '"curl"' not in text, f"{relative} shells out to curl"
