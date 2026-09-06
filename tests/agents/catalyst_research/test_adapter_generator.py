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


def source():
    return {
        "source_type": "press_releases",
        "url": "https://investor.example.com/news",
        "allowed_hosts": ["investor.example.com"],
        "untrusted": "x" * 100_000,
    }


def company():
    return {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "untrusted": "x" * 100_000}


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
    company_data = company()
    source_data = source()
    snapshot = {
        "snapshot_schema_version": "catalyst_structural_snapshot_v1",
        "requested_url": source_data["url"],
        "final_url": source_data["url"],
        "structural_html": '<article class="news-item"><time>January 3, 2025</time></article>',
        "normalized": {"text": "January 3, 2025"},
        "content_hash": "snapshot-hash",
    }
    client = FakeClient({key: value for key, value in payload().items() if key != "model_added"})

    result = __import__("asyncio").run(
        generate_adapter(company_data, source_data, snapshot, llm_client=client, model="test-model")
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
    assert result["adapter"]["source_url"] == source_data["url"]
    assert result["adapter"]["allowed_hosts"] == source_data["allowed_hosts"]
    assert result["generation_model"] == "test-model"
    assert result["prompt_schema_version"] == "adapter_generation_v1"
    assert result["source_snapshot_hash"] == hashlib.sha256(snapshot["structural_html"].encode()).hexdigest()
    assert len(result["input_hash"]) == hashlib.sha256(b"").digest_size * 2
    assert len(result["output_hash"]) == hashlib.sha256(b"").digest_size * 2


def test_generator_rejects_extra_model_fields():
    client = FakeClient(payload())
    with pytest.raises(ValueError, match="extra"):
        __import__("asyncio").run(
            generate_adapter(
                company(),
                source(),
                {"structural_html": "<article></article>", "content_hash": "hash"},
                llm_client=client,
                model="test-model",
            )
        )


def test_generator_bounds_aggregate_prompt_and_normalized_shapes_and_recomputes_invalid_hash():
    normalized = {
        "title": "T" * 10_000,
        "text": "X" * 100_000,
        "headings": [{"level": 1, "text": "H" * 10_000, "extra": "x" * 10_000}] * 1_000,
        "links": [{"href": "https://investor.example.com/" + "x" * 10_000, "text": "L" * 10_000, "extra": "x"}] * 1_000,
    }
    snapshot = {
        "snapshot_schema_version": "catalyst_structural_snapshot_v1",
        "requested_url": "https://investor.example.com/news",
        "final_url": "https://investor.example.com/news",
        "structural_html": "<article class='news-item'>" + ("x" * 200_000) + "</article>",
        "normalized": normalized,
        "content_hash": "not-a-sha256",
    }
    client = FakeClient({key: value for key, value in payload().items() if key != "model_added"})
    result = __import__("asyncio").run(
        generate_adapter(company(), source(), snapshot, llm_client=client, model="test-model")
    )

    prompt_text = json.dumps(client.responses.calls[0]["input"], ensure_ascii=False)
    assert len(prompt_text) <= 125_000
    assert "\"untrusted\"" not in prompt_text
    assert len(result["source_snapshot_hash"]) == 64
    assert result["source_snapshot_hash"] == hashlib.sha256(result["adapter"]["source_url"].encode()).hexdigest() or result["source_snapshot_hash"] != "not-a-sha256"


def test_generator_missing_parsed_response_is_bounded_error():
    class EmptyResponses:
        async def parse(self, **kwargs):
            return ParsedResponse(None)

    class EmptyClient:
        responses = EmptyResponses()

    with pytest.raises(ValueError, match="response is missing"):
        __import__("asyncio").run(
            generate_adapter(
                company(), source(), {"structural_html": "<article></article>"}, llm_client=EmptyClient(), model="test-model"
            )
        )


def test_generator_hashes_are_stable_for_identical_bounded_inputs():
    snapshot = {
        "structural_html": "<article class='news-item'><time>January 3, 2025</time></article>",
        "content_hash": "bad",
    }
    first_client = FakeClient({key: value for key, value in payload().items() if key != "model_added"})
    second_client = FakeClient({key: value for key, value in payload().items() if key != "model_added"})
    first = __import__("asyncio").run(generate_adapter(company(), source(), snapshot, llm_client=first_client, model="test-model"))
    second = __import__("asyncio").run(generate_adapter(company(), source(), snapshot, llm_client=second_client, model="test-model"))

    assert first["input_hash"] == second["input_hash"]
    assert first["output_hash"] == second["output_hash"]
    assert first["source_snapshot_hash"] == second["source_snapshot_hash"]
