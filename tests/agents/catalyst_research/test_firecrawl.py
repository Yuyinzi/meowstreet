import sys

import pytest

from app.agents.catalyst_research.providers.firecrawl import FirecrawlExtractProvider
from app.agents.catalyst_research.providers.firecrawl import FirecrawlProviderError
from app.agents.catalyst_research.providers.firecrawl import build_firecrawl_provider


URL = "https://investor.example.com/news/nvidia-update"


class FakeFirecrawlClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def scrape(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


class StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"private upstream payload status {status_code}")
        self.status_code = status_code


class FakeDocument:
    def model_dump(self):
        return {
            "markdown": "# SDK body",
            "metadata": {
                "url": URL,
                "title": "SDK title",
                "published_time": "2026-09-01T00:00:00Z",
                "scrape_id": "fc-scrape-1",
            },
        }


def test_firecrawl_extract_calls_scrape_for_one_url_only():
    client = FakeFirecrawlClient(
        result={"markdown": "# NVIDIA update", "metadata": {"sourceURL": URL, "title": "NVIDIA update"}}
    )
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    result = provider.extract(URL)

    assert client.calls == [(URL, {"formats": ["markdown", "html"]})]
    assert result == {
        "url": URL,
        "final_url": URL,
        "title": "NVIDIA update",
        "markdown": "# NVIDIA update",
        "html": None,
        "published_at": None,
        "request_id": None,
        "provider": "firecrawl",
    }


def test_firecrawl_provider_exposes_no_expansion_methods():
    provider = FirecrawlExtractProvider(api_key="fc-test", client=FakeFirecrawlClient())

    for name in ("search", "crawl", "map", "interact", "batch_scrape", "agent", "browser"):
        assert not hasattr(provider, name)


def test_firecrawl_normalizes_sdk_object_results():
    client = FakeFirecrawlClient(result=FakeDocument())
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    result = provider.extract(URL)

    assert client.calls == [(URL, {"formats": ["markdown", "html"]})]
    assert result["final_url"] == URL
    assert result["title"] == "SDK title"
    assert result["markdown"] == "# SDK body"
    assert result["published_at"] == "2026-09-01T00:00:00Z"
    assert result["request_id"] == "fc-scrape-1"
    assert result["provider"] == "firecrawl"


def test_firecrawl_final_url_defaults_to_requested_url():
    client = FakeFirecrawlClient(result={"markdown": "body", "metadata": {"title": "t"}})
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    result = provider.extract(URL)

    assert result["final_url"] == URL


def test_firecrawl_not_configured_without_key():
    provider = FirecrawlExtractProvider()

    assert provider.ready is False
    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "not_configured"
    assert error.value.disable_provider is False


def test_firecrawl_missing_sdk_is_stable_configuration_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, "firecrawl.v2", None)

    with pytest.raises(FirecrawlProviderError) as error:
        FirecrawlExtractProvider(api_key="fc-test")

    assert error.value.reason_code == "not_configured"
    assert error.value.disable_provider is False


@pytest.mark.parametrize(
    ("status", "reason", "disabled"),
    [
        (401, "authentication_failed", True),
        (403, "authentication_failed", True),
        (402, "payment_required", True),
        (429, "rate_limited", False),
        (500, "provider_error", False),
    ],
)
def test_firecrawl_errors_are_stable(status, reason, disabled):
    provider = FirecrawlExtractProvider(api_key="fc-test", client=FakeFirecrawlClient(error=StatusError(status)))

    with pytest.raises(FirecrawlProviderError) as excinfo:
        provider.extract(URL)

    assert excinfo.value.reason_code == reason
    assert excinfo.value.disable_provider is disabled
    assert "private upstream payload" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


def test_firecrawl_timeout_is_stable_retryable_and_redacted():
    client = FakeFirecrawlClient(error=TimeoutError("private upstream payload"))
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "timeout"
    assert error.value.disable_provider is False
    assert error.value.retryable is True
    assert "private upstream payload" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_firecrawl_retryable_errors_retry_once_then_degrade():
    client = FakeFirecrawlClient(error=StatusError(503))
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "provider_error"
    assert error.value.retryable is True
    assert len(client.calls) == 2


def test_firecrawl_authentication_errors_do_not_retry():
    client = FakeFirecrawlClient(error=StatusError(401))
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "authentication_failed"
    assert len(client.calls) == 1


def test_firecrawl_generic_error_is_not_retryable():
    client = FakeFirecrawlClient(error=Exception("private upstream payload"))
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "provider_error"
    assert error.value.retryable is False
    assert len(client.calls) == 1
    assert "private upstream payload" not in str(error.value)


@pytest.mark.parametrize(
    "result",
    [None, {}, {"metadata": {"title": "t"}}, {"markdown": 123}, "not-a-mapping", 42],
)
def test_firecrawl_malformed_results_are_rejected(result):
    provider = FirecrawlExtractProvider(api_key="fc-test", client=FakeFirecrawlClient(result=result))

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "malformed_response"
    assert error.value.disable_provider is False


def test_firecrawl_empty_markdown_is_rejected():
    client = FakeFirecrawlClient(result={"markdown": "   ", "metadata": {"sourceURL": URL}})
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "empty_content"
    assert error.value.disable_provider is False


@pytest.mark.parametrize("final_url", ["javascript:alert(1)", "data:text/html,hi", "not-a-url"])
def test_firecrawl_unsafe_final_url_is_rejected(final_url):
    client = FakeFirecrawlClient(result={"markdown": "body", "metadata": {"sourceURL": final_url}})
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(FirecrawlProviderError) as error:
        provider.extract(URL)

    assert error.value.reason_code == "unsafe_final_url"
    assert error.value.disable_provider is False


def test_firecrawl_rejects_invalid_inputs_before_calling_client():
    client = FakeFirecrawlClient(result={"markdown": "body"})
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    with pytest.raises(ValueError, match="url is required"):
        provider.extract("  ")
    with pytest.raises(ValueError, match="url must be an http or https url"):
        provider.extract("ftp://example.com/report.pdf")

    assert client.calls == []


def test_build_firecrawl_provider_returns_none_without_key():
    assert build_firecrawl_provider({}) is None
    assert build_firecrawl_provider({"firecrawl_api_key": None}) is None
    assert build_firecrawl_provider({"firecrawl_api_key": "   "}) is None


def test_build_firecrawl_provider_constructs_configured_provider():
    provider = build_firecrawl_provider(
        {"firecrawl_api_key": "fc-test", "firecrawl_base_url": "https://firecrawl.example.com"}
    )

    assert isinstance(provider, FirecrawlExtractProvider)
    assert provider.ready is True


def test_extract_retains_html_payload_when_present():
    client = FakeFirecrawlClient(result={"markdown": "Article body text", "html": "<html><body>Article</body></html>", "metadata": {}})
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    result = provider.extract(URL)

    assert result["html"] == "<html><body>Article</body></html>"


def test_extract_drops_non_string_or_blank_html():
    client = FakeFirecrawlClient(result={"markdown": "Article body text", "html": "   ", "metadata": {}})
    provider = FirecrawlExtractProvider(api_key="fc-test", client=client)

    assert provider.extract(URL)["html"] is None
