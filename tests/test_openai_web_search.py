import pytest
from openai import APITimeoutError
from openai import OpenAIError

from app.data_sources.openai_web_search import OpenAIWebSearchError
from app.data_sources.openai_web_search import OpenAIWebSearchProvider


def focused_task():
    return {
        "purpose": "current_events",
        "depth_tier": "focused",
        "queries": ["latest federal funds rate"],
        "expected_source_class": "official_publication",
    }


class FakeSearchSource:
    def __init__(self, url):
        self.type = "web_search"
        self.url = url


class FakeSearchAction:
    def __init__(self, query, sources):
        self.type = "search"
        self.query = query
        self.sources = sources


class FakeWebSearchCall:
    def __init__(self, call_id, query, sources):
        self.type = "web_search_call"
        self.id = call_id
        self.action = FakeSearchAction(query, sources)


class FakeURLCitation:
    def __init__(self, url, title, start_index, end_index):
        self.type = "url_citation"
        self.url = url
        self.title = title
        self.start_index = start_index
        self.end_index = end_index


class FakeOutputText:
    def __init__(self, text, annotations):
        self.type = "output_text"
        self.text = text
        self.annotations = annotations


class FakeMessage:
    def __init__(self, message_id, content):
        self.type = "message"
        self.id = message_id
        self.content = content


class FakeResponse:
    def __init__(self, output, response_id="resp_1"):
        self.id = response_id
        self.output = output


class FakeResponsesClient:
    def __init__(self, response):
        self.response = response
        self.kwargs = {}
        self.calls = []

    @property
    def responses(self):
        return self._Responses(self)

    class _Responses:
        def __init__(self, client):
            self.client = client

        async def create(self, **kwargs):
            self.client.kwargs = kwargs
            self.client.calls.append(kwargs)
            return self.client.response


def response_with_search_call_and_citations():
    text = "The Federal Reserve reported a rate decision."
    start = text.index("reported")
    end = text.index("rate decision")
    return FakeResponse(
        output=[
            FakeWebSearchCall(
                "sc_1",
                "latest federal funds rate",
                [FakeSearchSource("https://example.test/report")],
            ),
            FakeMessage(
                "msg_1",
                [
                    FakeOutputText(
                        text,
                        [
                            FakeURLCitation(
                                "https://example.test/report",
                                "Federal Reserve Report",
                                start,
                                end,
                            )
                        ],
                    )
                ],
            ),
        ]
    )


def response_with_two_sources():
    text = "The Federal Reserve reported a rate decision."
    start = text.index("reported")
    end = text.index("rate decision")
    return FakeResponse(
        output=[
            FakeWebSearchCall(
                "sc_1",
                "latest federal funds rate",
                [
                    FakeSearchSource("https://www.federalreserve.gov/press.htm"),
                    FakeSearchSource("https://example.test/rates"),
                ],
            ),
            FakeMessage(
                "msg_1",
                [
                    FakeOutputText(
                        text,
                        [
                            FakeURLCitation(
                                "https://www.federalreserve.gov/press.htm",
                                "Federal Reserve Press",
                                start,
                                end,
                            ),
                            FakeURLCitation(
                                "https://example.test/rates",
                                "Example Rates",
                                start,
                                end,
                            ),
                        ],
                    )
                ],
            ),
        ]
    )


@pytest.mark.asyncio
async def test_provider_requests_sources_and_normalizes_citations():
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    payload = await provider.search(focused_task())

    assert client.kwargs["tools"] == [
        {"type": "web_search", "search_context_size": "low"}
    ]
    assert client.kwargs["include"] == ["web_search_call.action.sources"]
    assert payload["sources"][0]["url"] == "https://example.test/report"


@pytest.mark.asyncio
async def test_provider_passes_allowed_domains_in_request_filters():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["approved_domains"] = ["federalreserve.gov"]

    await provider.search(task)

    assert client.kwargs["tools"] == [
        {
            "type": "web_search",
            "search_context_size": "low",
            "filters": {"allowed_domains": ["federalreserve.gov"]},
        }
    ]


@pytest.mark.asyncio
async def test_provider_filters_findings_when_all_cited_sources_dropped():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["approved_domains"] = ["not-allowed.test"]

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        await provider.search(task)

    assert excinfo.value.reason_code == "missing_sources"


@pytest.mark.asyncio
async def test_provider_drops_dropped_source_from_finding_citations():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["approved_domains"] = ["federalreserve.gov"]

    payload = await provider.search(task)

    assert len(payload["sources"]) == 1
    assert all(
        citation["url"] == "https://www.federalreserve.gov/press.htm"
        for finding in payload["findings"]
        for citation in finding["citations"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tier", "size"),
    [("focused", "low"), ("standard", "medium"), ("deep", "high")],
)
async def test_provider_maps_search_context_size_per_tier(tier, size):
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["depth_tier"] = tier

    await provider.search(task)

    assert client.kwargs["tools"] == [
        {"type": "web_search", "search_context_size": size}
    ]


@pytest.mark.asyncio
async def test_provider_makes_one_request_per_query():
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["queries"] = ["first query", "second query"]

    await provider.search(task)

    assert len(client.calls) == 2
    assert client.calls[0]["input"] == "first query (official publication)"
    assert client.calls[1]["input"] == "second query (official publication)"


@pytest.mark.asyncio
async def test_provider_passes_model_through():
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    await provider.search(focused_task())

    assert client.kwargs["model"] == "research-model"


@pytest.mark.asyncio
async def test_provider_does_not_enable_background_mode():
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    await provider.search(focused_task())

    assert "background" not in client.kwargs


@pytest.mark.asyncio
async def test_provider_normalizes_search_calls_sources_and_findings():
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    payload = await provider.search(focused_task())

    assert payload["search_calls"][0]["search_call_id"] == "sc_1"
    assert payload["search_calls"][0]["query"] == (
        "latest federal funds rate (official publication)"
    )
    source = payload["sources"][0]
    assert source["title"] == "Federal Reserve Report"
    assert source["cited_spans"] == ["reported a"]
    finding = payload["findings"][0]
    assert finding["statement"] == "The Federal Reserve reported a rate decision."
    assert finding["purpose"] == "current_events"
    assert finding["framing"] == "reported"
    assert finding["citations"] == [
        {"url": "https://example.test/report", "span": "reported a"}
    ]


@pytest.mark.asyncio
async def test_provider_metadata_has_no_credentials():
    client = FakeResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    payload = await provider.search(focused_task())

    metadata = payload["provider_metadata"]
    assert metadata["provider_id"] == "openai_responses_web_search"
    assert metadata["model"] == "research-model"
    assert metadata["request_id"] == "resp_1"
    assert set(metadata) == {"provider_id", "model", "request_id"}


@pytest.mark.asyncio
async def test_provider_raises_stable_error_when_sources_missing():
    response = FakeResponse(output=[FakeMessage("msg_1", [])])
    client = FakeResponsesClient(response)
    provider = OpenAIWebSearchProvider(client, "research-model")

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        await provider.search(focused_task())

    assert excinfo.value.reason_code == "missing_sources"


@pytest.mark.asyncio
async def test_provider_filters_sources_outside_approved_domains():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["approved_domains"] = ["federalreserve.gov"]

    payload = await provider.search(task)

    assert [source["url"] for source in payload["sources"]] == [
        "https://www.federalreserve.gov/press.htm"
    ]


@pytest.mark.asyncio
async def test_provider_raises_missing_sources_when_all_domains_filtered():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["approved_domains"] = ["not-allowed.test"]

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        await provider.search(task)

    assert excinfo.value.reason_code == "missing_sources"


@pytest.mark.asyncio
async def test_provider_translates_time_window_into_query_qualifier():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["time_window"] = {"start": "2026-08-01", "end": "2026-08-31"}

    payload = await provider.search(task)

    assert client.calls[0]["input"] == (
        "latest federal funds rate "
        "(official publication, between 2026-08-01 and 2026-08-31)"
    )
    assert [source["url"] for source in payload["sources"]] == [
        "https://example.test/rates",
        "https://www.federalreserve.gov/press.htm",
    ]


@pytest.mark.asyncio
async def test_provider_does_not_drop_sources_for_time_window():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["time_window"] = {"start": "2026-08-01", "end": "2026-08-31"}

    payload = await provider.search(task)

    assert len(payload["sources"]) == 2
    assert payload["search_calls"][0]["query"] == (
        "latest federal funds rate "
        "(official publication, between 2026-08-01 and 2026-08-31)"
    )


@pytest.mark.asyncio
async def test_provider_translates_expected_source_class_into_query():
    client = FakeResponsesClient(response_with_two_sources())
    provider = OpenAIWebSearchProvider(client, "research-model")
    task = focused_task()
    task["expected_source_class"] = "academic"

    payload = await provider.search(task)

    assert client.calls[0]["input"] == "latest federal funds rate (academic)"
    assert len(payload["sources"]) == 2


@pytest.mark.asyncio
async def test_provider_raises_stable_error_when_citations_missing():
    text = "No citation annotations here."
    response = FakeResponse(
        output=[
            FakeWebSearchCall(
                "sc_1",
                "latest federal funds rate",
                [FakeSearchSource("https://example.test/report")],
            ),
            FakeMessage("msg_1", [FakeOutputText(text, [])]),
        ]
    )
    client = FakeResponsesClient(response)
    provider = OpenAIWebSearchProvider(client, "research-model")

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        await provider.search(focused_task())

    assert excinfo.value.reason_code == "missing_citations"


@pytest.mark.asyncio
async def test_provider_translates_timeout_to_stable_error():
    class FlakyResponsesClient(FakeResponsesClient):
        @property
        def responses(self):
            return self._FlakyResponses(self)

        class _FlakyResponses:
            def __init__(self, client):
                self.client = client

            def create(self, **kwargs):
                raise APITimeoutError("Request timed out.")

    client = FlakyResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        await provider.search(focused_task())

    assert excinfo.value.reason_code == "timeout"


@pytest.mark.asyncio
async def test_provider_translates_provider_error_to_stable_error():
    class BrokenResponsesClient(FakeResponsesClient):
        @property
        def responses(self):
            return self._BrokenResponses(self)

        class _BrokenResponses:
            def __init__(self, client):
                self.client = client

            def create(self, **kwargs):
                raise OpenAIError("Provider exploded.")

    client = BrokenResponsesClient(response_with_search_call_and_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        await provider.search(focused_task())

    assert excinfo.value.reason_code == "provider_error"
