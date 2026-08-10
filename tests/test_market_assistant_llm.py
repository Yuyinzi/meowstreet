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
    def __init__(self, output_parsed):
        self.output_parsed = output_parsed


class FakeResponses:
    def __init__(self, client):
        self.client = client

    async def parse(self, **kwargs):
        self.client.calls.append(kwargs)
        return FakeResponse(self.client.output_parsed)


class FakeClient:
    def __init__(self, output_parsed):
        self.output_parsed = output_parsed
        self.calls = []

    @property
    def responses(self):
        return FakeResponses(self)


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
        {"model": "assistant-model", "input": prompt, "text_format": DummyStructured}
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
