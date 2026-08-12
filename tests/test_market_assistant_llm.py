import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.services.market_assistant_llm import complete_structured
from app.services.market_assistant_llm import plan_question


class DummyStructured(BaseModel):
    value: str


class FakeParsed:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self, *, mode):
        return self._payload


class FakeResponse:
    def __init__(self, output_parsed=None, output_text=""):
        self.output_parsed = output_parsed
        self.output_text = output_text


class FakeResponses:
    def __init__(self, client):
        self.client = client

    async def parse(self, **kwargs):
        self.client.calls.append(kwargs)
        return FakeResponse(self.client.output_parsed)

    async def create(self, **kwargs):
        self.client.calls.append(kwargs)
        if self.client.stream_events is not None:
            stream = FakeStream(self.client.stream_events)
            self.client.last_stream = stream
            return stream
        return FakeResponse(output_text=self.client.output_text)


class FakeClient:
    def __init__(self, output_parsed=None, output_text="", stream_events=None):
        self.output_parsed = output_parsed
        self.output_text = output_text
        self.stream_events = stream_events
        self.calls = []
        self.last_stream = None

    @property
    def responses(self):
        return FakeResponses(self)


class FakeStream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self.events:
            yield event

    async def aclose(self):
        self.closed = True


def valid_plan_payload(**overrides):
    plan = {
        "intent": "definition",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "get_indicator_definition",
                "parameters": {"indicator_id": "vix"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    plan.update(overrides)
    return plan


@pytest.mark.asyncio
async def test_complete_structured_records_kwargs_and_returns_json_dump():
    client = FakeClient(output_parsed=DummyStructured(value="hello"))
    prompt = [{"role": "user", "content": "hello"}]

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=prompt,
        schema_type=DummyStructured,
    )

    assert client.calls == [
        {
            "model": "assistant-model",
            "input": prompt,
            "text_format": DummyStructured,
            "reasoning": {"effort": "low"},
        }
    ]
    assert result == {"value": "hello"}


@pytest.mark.asyncio
async def test_complete_structured_unavailable_parsed_raises():
    client = FakeClient(output_parsed=None)

    with pytest.raises(ValueError, match="structured response is unavailable"):
        await complete_structured(
            client,
            model="assistant-model",
            prompt=[],
            schema_type=DummyStructured,
        )


@pytest.mark.asyncio
async def test_complete_structured_json_object_streams_and_validates_locally(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta='{"value":'),
            SimpleNamespace(type="response.output_text.delta", delta='"hello"}'),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(output_text='{"value":"hello"}'),
            ),
        ]
    )
    prompt = [{"role": "user", "content": "hello"}]

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=prompt,
        schema_type=DummyStructured,
        structured_output_mode="json_object",
    )

    assert client.calls[0]["model"] == "assistant-model"
    assert client.calls[0]["text"] == {"format": {"type": "json_object"}}
    assert client.calls[0]["stream"] is True
    assert client.calls[0]["reasoning"] == {"effort": "low"}
    assert client.calls[0]["input"][-1] == prompt[-1]
    assert "value" in client.calls[0]["input"][0]["content"]
    assert result == {"value": "hello"}
    assert "market assistant response stream started" in caplog.text
    assert "market assistant response stream completed" in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_json_object_rejects_unvalidated_provider_text():
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.output_text.delta", delta='{"value":42}'),
            SimpleNamespace(type="response.completed", response=None),
        ]
    )

    with pytest.raises(ValueError, match="structured response is invalid"):
        await complete_structured(
            client,
            model="assistant-model",
            prompt=[],
            schema_type=DummyStructured,
            structured_output_mode="json_object",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_type", ["response.incomplete", "response.failed"])
async def test_complete_structured_json_object_rejects_unsuccessful_stream(
    terminal_type,
):
    client = FakeClient(
        stream_events=[SimpleNamespace(type=terminal_type, response=None)]
    )

    with pytest.raises(ValueError, match="structured response stream did not complete"):
        await complete_structured(
            client,
            model="assistant-model",
            prompt=[],
            schema_type=DummyStructured,
            structured_output_mode="json_object",
        )


@pytest.mark.asyncio
async def test_plan_question_returns_validated_plan():
    payload = valid_plan_payload()
    client = FakeClient(output_parsed=FakeParsed(payload))

    plan = await plan_question(
        client,
        model="assistant-model",
        question="What is the VIX?",
        context_summary={},
    )

    assert plan == payload
    assert isinstance(plan["operations"][0], dict)


@pytest.mark.asyncio
async def test_plan_question_invalid_payload_raises_for_repair():
    payload = valid_plan_payload(
        intent="decision_explanation", context_mode="historical"
    )
    client = FakeClient(output_parsed=FakeParsed(payload))

    with pytest.raises(
        ValueError, match="historical context requires historical intent"
    ):
        await plan_question(
            client,
            model="assistant-model",
            question="Why is the current setup Mild Risk-Off?",
            context_summary={},
        )


@pytest.mark.asyncio
async def test_plan_question_prompt_mentions_only_registered_operations():
    client = FakeClient(output_parsed=FakeParsed(valid_plan_payload()))

    await plan_question(
        client,
        model="assistant-model",
        question="What is the VIX?",
        context_summary={"mode": "current"},
    )

    prompt = client.calls[0]["input"]
    assert isinstance(prompt, list) and prompt
    assert all(
        isinstance(message, dict) and "role" in message and "content" in message
        for message in prompt
    )
    combined = " ".join(message["content"] for message in prompt)
    assert "resolve_current_explanation" in combined
    assert "research_deep" in combined
    assert "run_sql" not in combined


@pytest.mark.asyncio
async def test_plan_question_passes_reasoning_effort_to_complete_structured():
    client = FakeClient(output_parsed=FakeParsed(valid_plan_payload()))

    await plan_question(
        client,
        model="assistant-model",
        question="What is the VIX?",
        context_summary={},
        reasoning_effort="high",
    )

    assert client.calls[0]["reasoning"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_complete_structured_json_object_logs_usage_metrics(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.reasoning_text.delta", delta="thinking"),
            SimpleNamespace(type="response.output_text.delta", delta='{"value":'),
            SimpleNamespace(type="response.output_text.delta", delta='"hello"}'),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text='{"value":"hello"}',
                    usage=SimpleNamespace(
                        input_tokens=10,
                        output_tokens=5,
                        input_tokens_details=SimpleNamespace(cached_tokens=3),
                        output_tokens_details=SimpleNamespace(reasoning_tokens=2),
                    ),
                ),
            ),
        ]
    )

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[{"role": "user", "content": "hello"}],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
    )

    assert result == {"value": "hello"}
    assert "input_tokens=10" in caplog.text
    assert "cached_tokens=3" in caplog.text
    assert "output_tokens=5" in caplog.text
    assert "reasoning_tokens=2" in caplog.text
    assert "first_reasoning_seconds=" in caplog.text
    assert "first_output_seconds=" in caplog.text
    assert "thinking" not in caplog.text
    assert "hello" not in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_json_object_logs_usage_from_dict_events(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            {"type": "response.output_text.delta", "delta": '{"value":"hi"}'},
            {
                "type": "response.completed",
                "response": {
                    "output_text": '{"value":"hi"}',
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "input_tokens_details": {"cached_tokens": 40},
                        "output_tokens_details": {"reasoning_tokens": 8},
                    },
                },
            },
        ]
    )

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
    )

    assert result == {"value": "hi"}
    assert "input_tokens=100" in caplog.text
    assert "cached_tokens=40" in caplog.text
    assert "output_tokens=20" in caplog.text
    assert "reasoning_tokens=8" in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_logs_missing_token_subfields_as_none(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.output_text.delta", delta='{"value":"hi"}'),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text='{"value":"hi"}',
                    usage=SimpleNamespace(
                        input_tokens=100,
                        output_tokens=20,
                    ),
                ),
            ),
        ]
    )

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
    )

    assert result == {"value": "hi"}
    assert "input_tokens=100" in caplog.text
    assert "cached_tokens=none" in caplog.text
    assert "output_tokens=20" in caplog.text
    assert "reasoning_tokens=none" in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_observer_gets_reasoning_started_only(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(
                type="response.reasoning_text.delta", delta="deep thinking here"
            ),
            SimpleNamespace(type="response.reasoning_text.delta", delta=" keep going"),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text='{"answer_text":"hi","value":"ok"}'
                ),
            ),
        ]
    )
    events = []

    def observer(event):
        events.append(event)

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
        stream_observer=observer,
    )

    assert result == {"value": "ok"}
    assert events == [{"type": "reasoning_started"}]
    assert "deep thinking here" not in json.dumps(events)
    assert "deep thinking here" not in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_observer_gets_answer_deltas_from_extractor(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(
                type="response.reasoning_text.delta", delta="deep thinking here"
            ),
            SimpleNamespace(type="response.output_text.delta", delta='{"answer_'),
            SimpleNamespace(type="response.output_text.delta", delta='text":"当前'),
            SimpleNamespace(
                type="response.output_text.delta", delta='市场","value":"x"}'
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text='{"answer_text":"当前市场","value":"x"}',
                    usage=SimpleNamespace(
                        input_tokens=10,
                        output_tokens=5,
                        input_tokens_details=SimpleNamespace(cached_tokens=3),
                        output_tokens_details=SimpleNamespace(reasoning_tokens=2),
                    ),
                ),
            ),
        ]
    )
    events = []

    def observer(event):
        events.append(event)

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
        stream_observer=observer,
    )

    assert result == {"value": "x"}
    assert events == [
        {"type": "reasoning_started"},
        {"type": "answer_delta", "delta": "当前"},
        {"type": "answer_delta", "delta": "市场"},
    ]
    assert "deep thinking here" not in json.dumps(events)
    assert "deep thinking here" not in caplog.text
    assert "reasoning_tokens=2" in caplog.text
    assert "当前" not in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_missing_streamed_answer_text_is_best_effort(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.output_text.delta", delta='{"value":"ok"}'),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(output_text='{"value":"ok"}'),
            ),
        ]
    )
    events = []

    def observer(event):
        events.append(event)

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
        stream_observer=observer,
    )

    assert result == {"value": "ok"}
    assert events == []
    assert "answer_text missing" in caplog.text


@pytest.mark.asyncio
async def test_complete_structured_observer_error_closes_stream_and_reraises():
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.reasoning_text.delta", delta="thinking"),
            SimpleNamespace(type="response.output_text.delta", delta='{"value":'),
            SimpleNamespace(type="response.output_text.delta", delta='"ok"}'),
        ]
    )

    def observer(event):
        raise RuntimeError("observer exploded")

    with pytest.raises(RuntimeError, match="observer exploded"):
        await complete_structured(
            client,
            model="assistant-model",
            prompt=[],
            schema_type=DummyStructured,
            structured_output_mode="json_object",
            stream_observer=observer,
        )

    assert client.last_stream.closed is True


@pytest.mark.asyncio
async def test_complete_structured_supports_async_observer():
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.output_text.delta", delta='{"answer_'),
            SimpleNamespace(
                type="response.output_text.delta", delta='text":"hi","value":"ok"}'
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text='{"answer_text":"hi","value":"ok"}'
                ),
            ),
        ]
    )
    events = []

    async def observer(event):
        events.append(event)

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
        stream_observer=observer,
    )

    assert result == {"value": "ok"}
    assert events == [{"type": "answer_delta", "delta": "hi"}]


@pytest.mark.asyncio
async def test_complete_structured_without_observer_keeps_existing_behavior(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.output_text.delta", delta='{"value":'),
            SimpleNamespace(type="response.output_text.delta", delta='"hi"}'),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(output_text='{"value":"hi"}'),
            ),
        ]
    )

    result = await complete_structured(
        client,
        model="assistant-model",
        prompt=[],
        schema_type=DummyStructured,
        structured_output_mode="json_object",
    )

    assert result == {"value": "hi"}
    assert "market assistant response stream started" in caplog.text
