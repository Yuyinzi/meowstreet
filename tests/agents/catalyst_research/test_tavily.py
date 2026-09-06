import asyncio

import httpx
import pytest
from tavily.errors import InvalidAPIKeyError
from tavily.errors import UsageLimitExceededError

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.tavily import TavilySearchProvider


class FakeTavilyClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def test_tavily_search_uses_exact_bounded_request_and_normalizes_results():
    client = FakeTavilyClient(
        {
            "request_id": "tv-request-1",
            "results": [
                {"title": "NVIDIA Investor Relations", "url": "https://investor.example.com", "content": "Official archive", "score": 0.9},
                {"title": "NVIDIA News", "url": "https://investor.example.com/news", "content": "Press releases"},
            ],
        }
    )
    provider = TavilySearchProvider(api_key="secret-key", client=client)

    rows = asyncio.run(provider.search("NVIDIA investor relations", limit=2))

    assert client.calls == [
        {
            "query": "NVIDIA investor relations",
            "max_results": 2,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
    ]
    assert rows == [
        {
            "title": "NVIDIA Investor Relations",
            "url": "https://investor.example.com",
            "snippet": "Official archive",
            "provider_rank": 1,
            "provider_metadata": {"score": 0.9},
        },
        {
            "title": "NVIDIA News",
            "url": "https://investor.example.com/news",
            "snippet": "Press releases",
            "provider_rank": 2,
            "provider_metadata": {},
        },
    ]
    assert provider.last_request_id == "tv-request-1"


def test_tavily_authentication_error_is_stable_and_redacts_secret():
    client = FakeTavilyClient(error=InvalidAPIKeyError("secret-key full provider payload"))
    provider = TavilySearchProvider(api_key="secret-key", client=client)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "authentication_failed"
    assert error.value.disable_provider is True
    assert error.value.retryable is False
    assert "secret-key" not in str(error.value)
    assert "full provider payload" not in str(error.value)
    assert provider.last_request_id is None
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_tavily_usage_limit_is_rate_limited_without_retry():
    client = FakeTavilyClient(error=UsageLimitExceededError("private usage payload"))
    provider = TavilySearchProvider(api_key="key", client=client)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "rate_limited"
    assert error.value.retryable is True
    assert len(client.calls) == 1
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_tavily_http_5xx_retries_once_and_returns_provider_error_without_chaining():
    request = httpx.Request("GET", "https://api.tavily.com/search")
    response = httpx.Response(503, request=request)
    first = httpx.HTTPStatusError("raw secret response", request=request, response=response)
    client = FakeTavilyClient(error=first)
    provider = TavilySearchProvider(api_key="key", client=client)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "provider_error"
    assert error.value.retryable is True
    assert len(client.calls) == 2
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.parametrize(
    ("status", "reason", "disable", "retryable"),
    [
        (401, "authentication_failed", True, False),
        (403, "authentication_failed", True, False),
        (429, "rate_limited", False, True),
    ],
)
def test_tavily_http_status_errors_use_stable_reason_codes(status, reason, disable, retryable):
    request = httpx.Request("GET", "https://api.tavily.com/search")
    response = httpx.Response(status, request=request, json={"secret": "payload"})
    client = FakeTavilyClient(error=httpx.HTTPStatusError("private payload", request=request, response=response))
    provider = TavilySearchProvider(api_key="key", client=client)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == reason
    assert error.value.disable_provider is disable
    assert error.value.retryable is retryable
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_tavily_rejects_invalid_inputs_before_calling_client():
    client = FakeTavilyClient(response={"results": []})
    provider = TavilySearchProvider(api_key="key", client=client)

    with pytest.raises(ValueError, match="query is required"):
        asyncio.run(provider.search("  ", limit=1))
    with pytest.raises(ValueError, match="limit must be between"):
        asyncio.run(provider.search("NVIDIA", limit=0))
    assert client.calls == []


@pytest.mark.parametrize("rows", [None, [{"title": "missing-url"}], ["not-a-row"]])
def test_tavily_malformed_rows_are_stable_and_bounded(rows):
    provider = TavilySearchProvider(api_key="key", client=FakeTavilyClient(response={"results": rows}))

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "malformed_response"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_tavily_does_not_republish_injected_provider_error_payload():
    client = FakeTavilyClient(error=SearchProviderError("raw_reason", "secret raw response"))
    provider = TavilySearchProvider(api_key="key", client=client)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "provider_error"
    assert "secret raw response" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
