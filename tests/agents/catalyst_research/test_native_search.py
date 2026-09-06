import asyncio

import httpx
import pytest
from openai import BadRequestError

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
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "Invalid value web_search; supported web_search_preview"}},
    )
    client = FakeClient(error=BadRequestError("Invalid value web_search; supported web_search_preview", response=response, body=response.json()))
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
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_native_arbitrary_bad_request_is_not_misclassified_as_unsupported_tool():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(400, request=request, json={"error": {"message": "invalid model"}})
    client = FakeClient(error=BadRequestError("invalid model", response=response, body=response.json()))
    provider = NativeSearchProvider(client=client, model="search-model", native_search_supported=True)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "provider_error"
    assert error.value.disable_provider is False
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ({"id": "missing-output"}, "malformed_response"),
        ({"id": "none-output", "output": None}, "malformed_response"),
        ({"id": "empty-output", "output": []}, "empty_results"),
        (
            {"output": [{"type": "web_search_call", "action": {"sources": {}}}]},
            "malformed_response",
        ),
        (
            {"output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}]},
            "empty_results",
        ),
    ],
)
def test_native_output_shape_has_stable_empty_or_malformed_reason(response, reason):
    provider = NativeSearchProvider(client=FakeClient(response=response), model="search-model", native_search_supported=True)

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == reason


def test_native_last_request_id_resets_on_sequential_call():
    client = FakeClient(response={"id": "first", "output": []})
    provider = NativeSearchProvider(client=client, model="search-model", native_search_supported=True)
    with pytest.raises(SearchProviderError):
        asyncio.run(provider.search("first", limit=1))
    assert provider.last_request_id == "first"
    client.responses.response = {"output": []}
    with pytest.raises(SearchProviderError):
        asyncio.run(provider.search("second", limit=1))
    assert provider.last_request_id is None


def test_native_accepts_tuple_sources_from_sdk_or_pydantic_shapes():
    provider = NativeSearchProvider(
        client=FakeClient(
            response={
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {"sources": ({"title": "IR", "url": "https://example.com"},)},
                    }
                ]
            }
        ),
        model="search-model",
        native_search_supported=True,
    )

    rows = asyncio.run(provider.search("NVIDIA", limit=1))

    assert rows[0]["url"] == "https://example.com"


@pytest.mark.parametrize("sources", ["https://example.com", {"url": "https://example.com"}])
def test_native_rejects_string_or_mapping_sources(sources):
    provider = NativeSearchProvider(
        client=FakeClient(
            response={"output": [{"type": "web_search_call", "action": {"sources": sources}}]}
        ),
        model="search-model",
        native_search_supported=True,
    )

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "malformed_response"
