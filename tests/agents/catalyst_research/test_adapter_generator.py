import hashlib
import json

import pytest

from app.agents.catalyst_research.adapters.generator import generate_adapter


class ParsedResponse:
    def __init__(self, payload):
        self.output_parsed = payload


class FakeResponses:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return ParsedResponse(self.payload)


class FakeClient:
    def __init__(self, payload):
        self.responses = FakeResponses(payload)


def payload():
    return {
        "schema_version": "ir_source_adapter_v1",
        "ticker": "WRONG",
        "source_type": "events_presentations",
        "source_url": "https://evil.example.net/archive",
        "allowed_hosts": ["evil.example.net"],
        "access_mode": "html",
        "extraction": {
            "item_selector": ".news-item",
            "date": {"selector": "time", "value_source": "text", "formats": ["%B %d, %Y"]},
            "title": {"selector": ".news-title", "value_source": "text"},
            "url": {"selector": ".news-title", "value_source": "attribute", "attribute": "href"},
        },
        "pagination": {"type": "none"},
        "model_added": "must fail",
    }


def test_generator_uses_bounded_parse_schema_and_overwrites_trusted_fields():
    company = {"ticker": "NVDA", "company_name": "NVIDIA Corporation"}
    source = {
        "source_type": "press_releases",
        "url": "https://investor.example.com/news",
        "allowed_hosts": ["investor.example.com"],
    }
    snapshot = {
        "snapshot_schema_version": "catalyst_structural_snapshot_v1",
        "requested_url": source["url"],
        "final_url": source["url"],
        "structural_html": '<article class="news-item"><time>January 3, 2025</time></article>',
        "normalized": {"text": "January 3, 2025"},
        "content_hash": "snapshot-hash",
    }
    client = FakeClient({key: value for key, value in payload().items() if key != "model_added"})

    result = __import__("asyncio").run(
        generate_adapter(company, source, snapshot, llm_client=client, model="test-model")
    )

    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "test-model"
    assert call["text_format"].__name__ == "IRSourceAdapter"
    prompt = json.dumps(call["input"])
    assert "raw_html" not in prompt
    assert "January 3, 2025" in prompt
    assert result["adapter"]["ticker"] == "NVDA"
    assert result["adapter"]["source_type"] == "press_releases"
    assert result["adapter"]["source_url"] == source["url"]
    assert result["adapter"]["allowed_hosts"] == source["allowed_hosts"]
    assert result["generation_model"] == "test-model"
    assert result["prompt_schema_version"] == "adapter_generation_v1"
    assert result["source_snapshot_hash"] == "snapshot-hash"
    assert len(result["input_hash"]) == hashlib.sha256(b"").digest_size * 2
    assert len(result["output_hash"]) == hashlib.sha256(b"").digest_size * 2


def test_generator_rejects_extra_model_fields():
    client = FakeClient(payload())
    with pytest.raises(ValueError, match="extra"):
        __import__("asyncio").run(
            generate_adapter(
                {"ticker": "NVDA", "company_name": "NVIDIA Corporation"},
                {"source_type": "press_releases", "url": "https://investor.example.com/news", "allowed_hosts": ["investor.example.com"]},
                {"structural_html": "<article></article>", "content_hash": "hash"},
                llm_client=client,
                model="test-model",
            )
        )
