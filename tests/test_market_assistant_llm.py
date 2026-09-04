import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.services.market_assistant_llm import complete_structured
from app.services.market_assistant_llm import plan_question
from app.services.market_assistant_llm import response_items_for_next_turn
from app.services.market_assistant_llm import stream_response_turn


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


class FakeOutputItem:
    def __init__(self, **fields):
        self._fields = fields
        for key, value in fields.items():
            setattr(self, key, value)

    def model_dump(self, *, mode):
        return self._fields


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
    caplog,
):
    client = FakeClient(
        stream_events=[SimpleNamespace(type=terminal_type, response=None)]
    )

    with caplog.at_level(logging.INFO):
        with pytest.raises(
            ValueError, match="structured response stream did not complete"
        ):
            await complete_structured(
                client,
                model="assistant-model",
                prompt=[],
                schema_type=DummyStructured,
                structured_output_mode="json_object",
            )

    record = next(
        record
        for record in caplog.records
        if "response stream terminated" in record.getMessage()
    )
    assert record.levelno == logging.ERROR


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
async def test_complete_structured_missing_streamed_answer_text_raises():
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

    with pytest.raises(ValueError, match="answer_text missing"):
        await complete_structured(
            client,
            model="assistant-model",
            prompt=[],
            schema_type=DummyStructured,
            structured_output_mode="json_object",
            stream_observer=observer,
        )

    assert events == []


@pytest.mark.asyncio
async def test_complete_structured_duplicate_answer_text_raises():
    client = FakeClient(
        stream_events=[
            SimpleNamespace(
                type="response.output_text.delta",
                delta='{"answer_text":"first","answer_text":"second","value":"ok"}',
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text='{"answer_text":"first","answer_text":"second","value":"ok"}'
                ),
            ),
        ]
    )
    events = []

    def observer(event):
        events.append(event)

    with pytest.raises(ValueError, match="duplicate top-level answer_text"):
        await complete_structured(
            client,
            model="assistant-model",
            prompt=[],
            schema_type=DummyStructured,
            structured_output_mode="json_object",
            stream_observer=observer,
        )

    assert events == [{"type": "answer_delta", "delta": "first"}]


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


def tool_call_kwargs():
    return {
        "model": "assistant-model",
        "input_items": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "what is the vix?"}],
            }
        ],
        "instructions": "narrate the current market",
        "tools": [
            {
                "type": "function",
                "name": "query_indicator_history",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "indicator_id": {"type": "string"},
                        "window": {"type": "string"},
                    },
                    "required": ["indicator_id", "window"],
                },
            }
        ],
        "reasoning_effort": "medium",
    }


def function_call_stream_events():
    return [
        SimpleNamespace(type="response.created"),
        {
            "type": "response.output_item.added",
            "item": {
                "type": "function_call",
                "call_id": "call_vix",
                "name": "query_indicator_history",
            },
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "call_vix",
            "delta": '{"indicator_id":',
        },
        SimpleNamespace(
            type="response.function_call_arguments.delta",
            item_id="call_vix",
            delta='"vix","window":"6m"}',
        ),
        SimpleNamespace(
            type="response.function_call_arguments.done",
            item_id="call_vix",
            arguments='{"indicator_id":"vix","window":"6m"}',
        ),
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call_vix",
                "name": "query_indicator_history",
                "arguments": '{"indicator_id":"vix","window":"6m"}',
            },
        },
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(output_text="", usage=None),
        ),
    ]


@pytest.mark.asyncio
async def test_stream_response_turn_parses_function_call_from_mixed_event_forms():
    client = FakeClient(stream_events=function_call_stream_events())

    result = await stream_response_turn(client, **tool_call_kwargs())

    assert result["tool_calls"] == [
        {
            "call_id": "call_vix",
            "tool_name": "query_indicator_history",
            "arguments": {"indicator_id": "vix", "window": "6m"},
        }
    ]
    assert result["output_text"] == ""
    assert result["response_items"] == [
        {
            "type": "function_call",
            "call_id": "call_vix",
            "name": "query_indicator_history",
            "arguments": '{"indicator_id":"vix","window":"6m"}',
        }
    ]
    assert result["usage"] is None
    assert client.calls[0]["input"] == tool_call_kwargs()["input_items"]
    assert client.calls[0]["instructions"] == tool_call_kwargs()["instructions"]
    assert client.calls[0]["tools"] == tool_call_kwargs()["tools"]
    assert client.calls[0]["reasoning"] == {"effort": "medium"}
    assert client.calls[0]["stream"] is True


@pytest.mark.asyncio
async def test_stream_response_turn_preserves_sdk_output_item_with_model_dump():
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.created"),
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(
                    type="function_call",
                    call_id="call_vix",
                    name="query_indicator_history",
                ),
            ),
            SimpleNamespace(
                type="response.function_call_arguments.delta",
                item_id="call_vix",
                delta='{"indicator_id":"vix","window":"6m"}',
            ),
            SimpleNamespace(
                type="response.function_call_arguments.done",
                item_id="call_vix",
                arguments='{"indicator_id":"vix","window":"6m"}',
            ),
            SimpleNamespace(
                type="response.output_item.done",
                output=FakeOutputItem(
                    type="function_call",
                    id="fc_1",
                    call_id="call_vix",
                    name="query_indicator_history",
                    arguments='{"indicator_id":"vix","window":"6m"}',
                ),
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(output_text="", usage=None),
            ),
        ]
    )

    result = await stream_response_turn(client, **tool_call_kwargs())

    assert result["tool_calls"] == [
        {
            "call_id": "call_vix",
            "tool_name": "query_indicator_history",
            "arguments": {"indicator_id": "vix", "window": "6m"},
        }
    ]
    assert result["response_items"] == [
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_vix",
            "name": "query_indicator_history",
            "arguments": '{"indicator_id":"vix","window":"6m"}',
        }
    ]


def test_response_items_for_next_turn_returns_preserved_items():
    turn = {
        "response_items": [
            {
                "type": "function_call",
                "call_id": "call_vix",
                "name": "query_indicator_history",
            }
        ]
    }

    assert response_items_for_next_turn(turn) == [
        {
            "type": "function_call",
            "call_id": "call_vix",
            "name": "query_indicator_history",
        }
    ]


@pytest.mark.asyncio
async def test_stream_response_turn_narrates_deltas_to_observer_and_hides_reasoning(
    caplog,
):
    caplog.set_level(logging.INFO)
    reasoning_text = "deep thinking not shown"
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.reasoning_text.delta", delta="deep"),
            SimpleNamespace(
                type="response.reasoning_text.delta", delta=" thinking not shown"
            ),
            SimpleNamespace(type="response.output_text.delta", delta="现在的市场"),
            SimpleNamespace(type="response.output_text.delta", delta="偏积极。"),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(output_text="现在的市场偏积极。", usage=None),
            ),
        ]
    )
    events = []

    def observer(event):
        events.append(event)

    result = await stream_response_turn(
        client,
        observer=observer,
        **tool_call_kwargs(),
    )

    assert result["output_text"] == "现在的市场偏积极。"
    assert result["tool_calls"] == []
    assert events == [
        {"type": "reasoning_started"},
        {"type": "output_delta", "delta": "现在的市场"},
        {"type": "output_delta", "delta": "偏积极。"},
    ]
    assert reasoning_text not in result["output_text"]
    assert reasoning_text not in json.dumps(events)
    assert reasoning_text not in caplog.text


@pytest.mark.asyncio
async def test_stream_response_turn_notifies_provider_tool_call_started():
    client = FakeClient(stream_events=function_call_stream_events())
    events = []

    def observer(event):
        events.append(event)

    result = await stream_response_turn(
        client,
        observer=observer,
        **tool_call_kwargs(),
    )

    assert events == [
        {
            "type": "provider_tool_call_started",
            "call_id": "call_vix",
            "tool_name": "query_indicator_history",
        }
    ]
    assert result["tool_calls"][0]["call_id"] == "call_vix"


@pytest.mark.asyncio
async def test_stream_response_turn_returns_tool_calls_when_provider_adds_preamble_text():
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.output_text.delta", delta="some narration"),
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "call_id": "call_vix",
                    "name": "query_indicator_history",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "call_vix",
                "delta": "{}",
            },
            {
                "type": "response.function_call_arguments.done",
                "item_id": "call_vix",
                "arguments": "{}",
            },
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "call_id": "call_vix",
                    "name": "query_indicator_history",
                    "arguments": "{}",
                },
            },
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(output_text="some narration", usage=None),
            ),
        ]
    )

    result = await stream_response_turn(client, **tool_call_kwargs())

    assert result["output_text"] == "some narration"
    assert result["tool_calls"] == [
        {
            "call_id": "call_vix",
            "tool_name": "query_indicator_history",
            "arguments": {},
        }
    ]


@pytest.mark.asyncio
async def test_stream_response_turn_rejects_malformed_function_arguments():
    client = FakeClient(
        stream_events=[
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "call_id": "call_vix",
                    "name": "query_indicator_history",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "call_vix",
                "delta": "{not json",
            },
            {
                "type": "response.function_call_arguments.done",
                "item_id": "call_vix",
                "arguments": "{not json",
            },
        ]
    )

    with pytest.raises(
        ValueError, match="function call call_vix arguments are invalid"
    ):
        await stream_response_turn(client, **tool_call_kwargs())


@pytest.mark.asyncio
async def test_stream_response_turn_rejects_uncompleted_stream(caplog):
    client = FakeClient(
        stream_events=[SimpleNamespace(type="response.incomplete", response=None)]
    )

    with caplog.at_level(logging.INFO):
        with pytest.raises(ValueError, match="response stream did not complete"):
            await stream_response_turn(client, **tool_call_kwargs())

    record = next(
        record
        for record in caplog.records
        if "response turn terminated" in record.getMessage()
    )
    assert record.levelno == logging.ERROR


@pytest.mark.asyncio
async def test_stream_response_turn_logs_and_returns_four_timings(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient(
        stream_events=[
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.reasoning_text.delta", delta="thinking"),
            SimpleNamespace(type="response.output_text.delta", delta=" "),
            SimpleNamespace(type="response.output_text.delta", delta="answer"),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output_text=" answer",
                    usage={
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "input_tokens_details": {"cached_tokens": 3},
                        "output_tokens_details": {"reasoning_tokens": 2},
                    },
                ),
            ),
        ]
    )

    result = await stream_response_turn(
        client,
        instructions="narrate with credential sk-abc123",
        input_items=[{"type": "message", "role": "user", "content": "secret question"}],
        model="assistant-model",
        tools=[{"type": "function", "name": "query_indicator_history"}],
        reasoning_effort="medium",
    )

    timings = result["timings"]
    assert set(timings) == {
        "first_reasoning_seconds",
        "first_output_seconds",
        "first_visible_delta_seconds",
        "completed_seconds",
    }
    assert isinstance(timings["first_reasoning_seconds"], float)
    assert isinstance(timings["first_output_seconds"], float)
    assert isinstance(timings["first_visible_delta_seconds"], float)
    assert isinstance(timings["completed_seconds"], float)
    assert timings["first_output_seconds"] <= timings["first_visible_delta_seconds"]
    assert result["output_text"] == " answer"
    assert result["usage"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "input_tokens_details": {"cached_tokens": 3},
        "output_tokens_details": {"reasoning_tokens": 2},
    }
    assert "first_reasoning_seconds=" in caplog.text
    assert "first_output_seconds=" in caplog.text
    assert "first_visible_delta_seconds=" in caplog.text
    assert "completed_seconds=" in caplog.text
    assert "input_tokens=10" in caplog.text
    assert "cached_tokens=3" in caplog.text
    assert "sk-abc123" not in caplog.text
    assert "secret question" not in caplog.text
    assert "thinking" not in caplog.text
    assert "answer" not in caplog.text
