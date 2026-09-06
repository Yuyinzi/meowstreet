import asyncio

import pytest

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.native_search import NativeSearchProvider


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.responses = FakeResponses(response, error)


def test_native_search_requires_explicit_capability_for_custom_endpoint():
    provider = NativeSearchProvider(
        client=FakeClient(),
        model="search-model",
        base_url="https://gateway.example/v1",
        native_search_supported="auto",
    )

    assert provider.ready is False


def test_native_search_sends_tool_and_normalizes_citations_and_sources():
    response = {
        "id": "resp-1",
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "type": "search",
                    "sources": [
                        {"title": "IR home", "url": "https://investor.example.com"},
                        {"title": "IR news", "url": "https://investor.example.com/news"},
                    ],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "IR home and archive",
                        "annotations": [
                            {"type": "url_citation", "url": "https://investor.example.com", "title": "IR home"},
                            {"type": "url_citation", "url": "https://investor.example.com/news", "title": "IR news"},
                        ],
                    }
                ],
            },
        ],
    }
    client = FakeClient(response=response)
    provider = NativeSearchProvider(
        client=client,
        model="search-model",
        base_url=None,
        native_search_supported="auto",
    )

    rows = asyncio.run(provider.search("NVIDIA investor relations", limit=2))

    assert client.responses.calls == [
        {
            "model": "search-model",
            "input": "NVIDIA investor relations",
            "tools": [{"type": "web_search"}],
        }
    ]
    assert rows[0]["title"] == "IR home"
    assert rows[0]["url"] == "https://investor.example.com"
    assert rows[0]["provider_rank"] == 1
    assert rows[1]["snippet"] == "IR home and archive"
    assert provider.last_request_id == "resp-1"


def test_native_unsupported_tool_disables_provider():
    client = FakeClient(error=RuntimeError("unsupported tool web_search"))
    provider = NativeSearchProvider(
        client=client,
        model="search-model",
        native_search_supported=True,
    )

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "unsupported_tool"
    assert error.value.disable_provider is True
    assert provider.last_request_id is None
