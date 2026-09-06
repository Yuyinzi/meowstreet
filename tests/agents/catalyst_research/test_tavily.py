import asyncio

import pytest

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
    client = FakeTavilyClient(error=RuntimeError("401 secret-key full provider payload"))
    provider = TavilySearchProvider(api_key="secret-key", client=client)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "authentication"
    assert error.value.disable_provider is True
    assert error.value.retryable is False
    assert "secret-key" not in str(error.value)
    assert "full provider payload" not in str(error.value)
    assert provider.last_request_id is None


def test_tavily_rejects_invalid_inputs_before_calling_client():
    client = FakeTavilyClient(response={"results": []})
    provider = TavilySearchProvider(api_key="key", client=client)

    with pytest.raises(ValueError, match="query is required"):
        asyncio.run(provider.search("  ", limit=1))
    with pytest.raises(ValueError, match="limit must be between"):
        asyncio.run(provider.search("NVIDIA", limit=0))
    assert client.calls == []
