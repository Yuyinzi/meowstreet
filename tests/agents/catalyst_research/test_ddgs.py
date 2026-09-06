import asyncio

import pytest

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.ddgs import DDGSSearchProvider


class FakeDDGS:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.calls = []

    def text(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.error is not None:
            raise self.error
        return self.rows


def test_ddgs_runs_sync_sdk_in_thread_and_normalizes_results():
    client = FakeDDGS(
        rows=[
            {"title": "NVIDIA IR", "href": "https://investor.example.com", "body": "Official site"},
            {"title": "NVIDIA news", "url": "https://investor.example.com/news", "snippet": "Archive"},
        ]
    )
    provider = DDGSSearchProvider(client=client)

    rows = asyncio.run(provider.search("NVIDIA investor relations", limit=2))

    assert client.calls == [("NVIDIA investor relations", {"max_results": 2})]
    assert rows[0] == {
        "title": "NVIDIA IR",
        "url": "https://investor.example.com",
        "snippet": "Official site",
        "provider_rank": 1,
        "provider_metadata": {},
    }
    assert provider.ready is True
    assert provider.last_request_id is None


def test_ddgs_requires_no_credential_and_maps_timeout_without_leaking_response():
    provider = DDGSSearchProvider(client=FakeDDGS(error=TimeoutError("private response")))

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "timeout"
    assert error.value.retryable is True
    assert "private response" not in str(error.value)


def test_ddgs_empty_results_have_stable_error():
    provider = DDGSSearchProvider(client=FakeDDGS(rows=[]))

    with pytest.raises(SearchProviderError) as error:
        asyncio.run(provider.search("NVIDIA", limit=1))

    assert error.value.reason_code == "empty_results"
    assert error.value.retryable is False
