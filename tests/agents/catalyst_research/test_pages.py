from datetime import UTC, datetime

import httpx
import pytest

from app.agents.catalyst_research.extraction.pages import fetch_html_page
from app.http_client import HttpClient


def client_for(handler):
    transport = httpx.MockTransport(handler)
    return HttpClient(transport=transport, sleep=lambda _: None, max_attempts=1)


def test_fetch_html_page_uses_browser_headers_and_captures_canonical_final_url():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://cdn.example.com/page?utm_source=x"})
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, content=b"<main>Ready</main>")

    page = fetch_html_page(
        "https://example.com/start?utm_medium=email#top",
        http_client=client_for(handler),
        resolver={"example.com": ["93.184.216.34"], "cdn.example.com": ["93.184.216.35"]},
        allowed_hosts={"example.com", "cdn.example.com"},
    )

    assert requests[0].method == "GET"
    assert requests[0].headers["user-agent"].startswith("Mozilla/")
    assert requests[0].headers["accept"].startswith("text/html")
    assert page["requested_url"] == "https://example.com/start"
    assert page["final_url"] == "https://cdn.example.com/page"
    assert page["content_type"] == "text/html"
    assert page["html"] == "<main>Ready</main>"
    assert page["response_bytes"] == len(page["html"].encode())
    assert page["truncated"] is False
    datetime.fromisoformat(page["fetched_at"])


def test_fetch_html_page_revalidates_repeated_redirect_hosts_with_resolver():
    calls = []

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://example.com/next"})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<p>ok</p>")

    def resolver(host):
        calls.append(host)
        if len(calls) == 2:
            return ["192.168.1.8"]
        return ["93.184.216.34"]

    with pytest.raises(ValueError, match="url host is not public"):
        fetch_html_page("https://example.com/start", http_client=client_for(handler), resolver=resolver)

    assert calls == ["example.com", "example.com"]


def test_fetch_html_page_enforces_allowed_hosts_on_every_redirect_hop():
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "https://other.example.com/final"})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<p>ok</p>")

    with pytest.raises(ValueError, match="not allowed"):
        fetch_html_page(
            "https://example.com/start",
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            allowed_hosts={"example.com"},
        )


def test_fetch_html_page_bounds_response_bytes_and_marks_truncation():
    body = b"<main>" + b"x" * 100 + b"</main>"

    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=body)

    page = fetch_html_page(
        "https://example.com/page",
        http_client=client_for(handler),
        resolver=lambda host: ["93.184.216.34"],
        max_bytes=20,
    )

    assert page["response_bytes"] == 20
    assert len(page["html"].encode()) == 20
    assert page["truncated"] is True


@pytest.mark.parametrize(
    ("content_type", "body"),
    [("application/json", b"{}"), ("application/pdf", b"%PDF-1.7")],
)
def test_fetch_html_page_rejects_non_html_content_types(content_type, body):
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": content_type}, content=body)

    with pytest.raises(ValueError, match="content type"):
        fetch_html_page("https://example.com/page", http_client=client_for(handler), resolver=lambda host: ["93.184.216.34"])


def test_fetch_html_page_rejects_empty_html():
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b" \n\t")

    with pytest.raises(ValueError, match="html is empty"):
        fetch_html_page("https://example.com/page", http_client=client_for(handler), resolver=lambda host: ["93.184.216.34"])


def test_fetch_html_page_normalizes_timeout_and_http_errors():
    def timeout_handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ValueError, match="page request timed out"):
        fetch_html_page("https://example.com/page", http_client=client_for(timeout_handler), resolver=lambda host: ["93.184.216.34"])

    def error_handler(request):
        return httpx.Response(503, request=request)

    with pytest.raises(ValueError, match="page request failed"):
        fetch_html_page("https://example.com/page", http_client=client_for(error_handler), resolver=lambda host: ["93.184.216.34"])


@pytest.mark.parametrize("url", ["https://user:pass@example.com/page"])
def test_fetch_html_page_rejects_embedded_credentials(url):
    with pytest.raises(ValueError, match="credentials"):
        fetch_html_page(url, http_client=client_for(lambda request: httpx.Response(200)))


def test_fetch_html_page_rejects_private_redirect_target_before_returning_page():
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "http://192.168.1.10/private"})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<p>not reached</p>")

    with pytest.raises(ValueError, match="not public"):
        fetch_html_page("https://example.com/start", http_client=client_for(handler), resolver=lambda host: ["93.184.216.34"])
