import pytest

from app.data_sources.openai_web_search import OpenAIWebSearchError
from app.data_sources.openai_web_search import OpenAIWebSearchProvider
from app.services import market_assistant_research as research_service
from app.tools.market_assistant_research import build_research_result


def valid_task(tier="focused", **overrides):
    task = {
        "purpose": "current_events",
        "depth_tier": tier,
        "queries": ["latest federal funds rate"],
        "expected_source_class": "official_publication",
    }
    task.update(overrides)
    return task


def valid_provider_payload(**overrides):
    payload = {
        "provider_metadata": {
            "provider_id": "openai_responses_web_search",
            "model": "research-model",
        },
        "search_calls": [
            {
                "search_call_id": "sc_1",
                "query": "latest federal funds rate",
            }
        ],
        "sources": [
            {
                "url": "https://www.federalreserve.gov/press-release.htm",
                "title": "Federal Reserve Press Release",
                "cited_spans": ["The Federal Reserve announced a rate decision."],
            }
        ],
        "findings": [
            {
                "statement": "The Federal Reserve reported a rate decision.",
                "purpose": "current_events",
                "framing": "reported",
                "citations": [
                    {
                        "url": "https://www.federalreserve.gov/press-release.htm",
                        "span": "The Federal Reserve announced a rate decision.",
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


class FakeProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.search_calls = 0

    async def search(self, task):
        self.search_calls += 1
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.mark.asyncio
async def test_acquire_research_returns_frozen_result():
    provider = FakeProvider(payload=valid_provider_payload())

    result = await research_service.acquire_research(
        provider,
        valid_task(),
        result_id="res_1",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert provider.search_calls == 1
    assert result["authority"] == "external_research"
    assert result["market_setup_relation"] == "non_decision"
    assert result["research_result_id"] == "res_1"
    assert result["searched_at"] == "2026-08-10T02:00:00Z"
    assert "status" not in result
    assert result["findings"][0]["framing"] == "reported"


@pytest.mark.asyncio
async def test_acquire_research_invalid_task_returns_unavailable():
    provider = FakeProvider(payload=valid_provider_payload())

    result = await research_service.acquire_research(
        provider,
        valid_task(purpose="unregulated"),
        result_id="res_bad",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert provider.search_calls == 0
    assert result["status"] == "research_unavailable"
    assert result["reason_code"] == "invalid_task"
    assert result["research_result_id"] == "res_bad"


@pytest.mark.asyncio
async def test_acquire_research_deep_without_explicit_intent_returns_unavailable():
    provider = FakeProvider(payload=valid_provider_payload())

    result = await research_service.acquire_research(
        provider,
        valid_task(tier="deep"),
        result_id="res_deep",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert provider.search_calls == 0
    assert result["status"] == "research_unavailable"
    assert result["reason_code"] == "invalid_task"


@pytest.mark.asyncio
async def test_acquire_research_deep_with_explicit_intent_executes():
    provider = FakeProvider(payload=valid_provider_payload())

    result = await research_service.acquire_research(
        provider,
        valid_task(tier="deep"),
        result_id="res_deep_ok",
        searched_at="2026-08-10T02:00:00Z",
        explicit_deep=True,
    )

    assert provider.search_calls == 1
    assert result["research_result_id"] == "res_deep_ok"
    assert result["authority"] == "external_research"
    assert result["task"]["depth_tier"] == "deep"
    assert "status" not in result


@pytest.mark.asyncio
async def test_acquire_research_provider_error_returns_unavailable():
    provider = FakeProvider(error=RuntimeError("boom"))

    result = await research_service.acquire_research(
        provider,
        valid_task(),
        result_id="res_err",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert result["status"] == "research_unavailable"
    assert result["reason_code"] == "provider_error"


@pytest.mark.asyncio
async def test_acquire_research_timeout_returns_unavailable():
    provider = FakeProvider(error=OpenAIWebSearchError("timeout", "timed out"))

    result = await research_service.acquire_research(
        provider,
        valid_task(),
        result_id="res_to",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert result["status"] == "research_unavailable"
    assert result["reason_code"] == "timeout"


@pytest.mark.asyncio
async def test_acquire_research_config_unavailable_returns_unavailable():
    config = {
        "api_key": "test-key",
        "research_model": "research-model",
        "research_enabled": False,
        "supports_web_search": True,
    }

    result = await research_service.acquire_research_from_config(
        config,
        valid_task(),
        result_id="res_cfg",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert result["status"] == "research_unavailable"
    assert result["reason_code"] == "configuration_unavailable"


@pytest.mark.asyncio
async def test_acquire_research_from_config_happy_path():
    class FakeConfigProvider:
        async def search(self, task):
            return valid_provider_payload()

    config = {
        "api_key": "test-key",
        "research_model": "research-model",
        "research_enabled": True,
        "supports_web_search": True,
        "base_url": None,
    }
    original_build = research_service.build_research_provider
    research_service.build_research_provider = lambda cfg: FakeConfigProvider()
    try:
        result = await research_service.acquire_research_from_config(
            config,
            valid_task(),
            result_id="res_cfg_ok",
            searched_at="2026-08-10T02:00:00Z",
        )
    finally:
        research_service.build_research_provider = original_build

    assert result["research_result_id"] == "res_cfg_ok"
    assert result["authority"] == "external_research"


@pytest.mark.asyncio
async def test_acquire_research_never_calls_ingestion(monkeypatch):
    provider = FakeProvider(payload=valid_provider_payload())

    def fail_ingestion(*args, **kwargs):
        raise AssertionError("ingestion must not be called")

    from app.db import market_assistant as market_assistant_db

    monkeypatch.setattr(market_assistant_db, "save_answer_bundle", fail_ingestion)

    result = await research_service.acquire_research(
        provider,
        valid_task(),
        result_id="res_noingest",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert result["research_result_id"] == "res_noingest"
    assert result["authority"] == "external_research"


@pytest.mark.asyncio
async def test_acquire_research_calls_only_provider_and_build(monkeypatch):
    provider = FakeProvider(payload=valid_provider_payload())
    calls = []

    original_build = build_research_result

    def recording_build(**kwargs):
        calls.append("build")
        return original_build(**kwargs)

    monkeypatch.setattr(research_service, "build_research_result", recording_build)

    result = await research_service.acquire_research(
        provider,
        valid_task(),
        result_id="res_calls",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert provider.search_calls == 1
    assert calls == ["build"]
    assert result["research_result_id"] == "res_calls"


class ChainSearchSource:
    def __init__(self, url):
        self.type = "web_search"
        self.url = url


class ChainSearchAction:
    def __init__(self, query, sources):
        self.type = "search"
        self.query = query
        self.sources = sources


class ChainWebSearchCall:
    def __init__(self, call_id, query, sources):
        self.type = "web_search_call"
        self.id = call_id
        self.action = ChainSearchAction(query, sources)


class ChainURLCitation:
    def __init__(self, url, title, start_index, end_index):
        self.type = "url_citation"
        self.url = url
        self.title = title
        self.start_index = start_index
        self.end_index = end_index


class ChainOutputText:
    def __init__(self, text, annotations):
        self.type = "output_text"
        self.text = text
        self.annotations = annotations


class ChainMessage:
    def __init__(self, message_id, content):
        self.type = "message"
        self.id = message_id
        self.content = content


class ChainResponse:
    def __init__(self, output):
        self.id = "resp_chain"
        self.output = output


class ChainResponsesClient:
    def __init__(self, response):
        self.response = response

    @property
    def responses(self):
        return self._Responses(self)

    class _Responses:
        def __init__(self, client):
            self.client = client

        async def create(self, **kwargs):
            return self.client.response


def chain_task():
    return {
        "purpose": "current_events",
        "depth_tier": "focused",
        "queries": ["latest federal funds rate"],
        "expected_source_class": "official_publication",
    }


def chain_response_with_citations():
    text = "The Federal Reserve reported a rate decision."
    start = text.index("reported")
    end = text.index("rate decision")
    return ChainResponse(
        output=[
            ChainWebSearchCall(
                "sc_1",
                "latest federal funds rate",
                [ChainSearchSource("https://example.test/report")],
            ),
            ChainMessage(
                "msg_1",
                [
                    ChainOutputText(
                        text,
                        [
                            ChainURLCitation(
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


@pytest.mark.asyncio
async def test_acquire_research_full_chain_with_openai_provider():
    client = ChainResponsesClient(chain_response_with_citations())
    provider = OpenAIWebSearchProvider(client, "research-model")

    result = await research_service.acquire_research(
        provider,
        chain_task(),
        result_id="res_chain",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert result["research_result_id"] == "res_chain"
    assert result["authority"] == "external_research"
    assert result["market_setup_relation"] == "non_decision"
    assert result["sources"][0]["canonical_url"] == "https://example.test/report"
    assert result["findings"][0]["source_refs"] == ["src_1"]


@pytest.mark.asyncio
async def test_build_research_provider_requires_explicit_web_search_support():
    config = {
        "api_key": "test-key",
        "base_url": "https://compatible.test/v1",
        "research_model": "research-model",
        "research_enabled": True,
        "supports_web_search": False,
    }

    with pytest.raises(OpenAIWebSearchError) as excinfo:
        research_service.build_research_provider(config)

    assert excinfo.value.reason_code == "configuration_unavailable"


@pytest.mark.asyncio
async def test_acquire_research_unavailable_is_plain_dict_not_result():
    provider = FakeProvider(error=RuntimeError("boom"))

    result = await research_service.acquire_research(
        provider,
        valid_task(),
        result_id="res_plain",
        searched_at="2026-08-10T02:00:00Z",
    )

    assert isinstance(result, dict)
    assert "result_hash" not in result
    assert "artifact_schema_version" not in result
    assert result["status"] == "research_unavailable"
