import json
import logging
from time import monotonic
from typing import Awaitable

from pydantic import BaseModel

from app.tools.market_assistant_plans import TaskPlanSchema
from app.tools.market_assistant_plans import registered_operation_ids
from app.tools.market_assistant_plans import validate_task_plan


LOGGER = logging.getLogger(__name__)
STREAM_LOGGER = logging.getLogger("uvicorn.error")


async def complete_structured(
    client,
    *,
    model: str,
    prompt: list[dict],
    schema_type: type[BaseModel],
    structured_output_mode: str = "json_schema",
) -> Awaitable[dict]:
    if structured_output_mode == "json_object":
        request_started_at = monotonic()
        STREAM_LOGGER.info("market assistant response stream request started")
        stream = await client.responses.create(
            model=model,
            input=_json_object_prompt(prompt, schema_type),
            text={"format": {"type": "json_object"}},
            stream=True,
        )
        STREAM_LOGGER.info(
            "market assistant response stream connected elapsed_seconds=%.2f",
            monotonic() - request_started_at,
        )
        output_text = await _collect_response_stream(stream)
        try:
            parsed = schema_type.model_validate_json(output_text)
        except (TypeError, ValueError) as exc:
            raise ValueError("structured response is invalid") from exc
        return parsed.model_dump(mode="json")
    if structured_output_mode != "json_schema":
        raise ValueError("structured output mode is invalid")
    response = await client.responses.parse(
        model=model,
        input=prompt,
        text_format=schema_type,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("structured response is unavailable")
    return parsed.model_dump(mode="json")


async def _collect_response_stream(stream):
    started_at = monotonic()
    event_counts = {}
    output_parts = []
    completed_response = None
    completed = False
    first_event_received = False
    STREAM_LOGGER.info("market assistant response stream started")
    async for event in stream:
        event_type = _event_value(event, "type") or "unknown"
        if not first_event_received:
            first_event_received = True
            STREAM_LOGGER.info(
                "market assistant response stream first event event_type=%s elapsed_seconds=%.2f",
                event_type,
                monotonic() - started_at,
            )
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type == "response.output_text.delta":
            delta = _event_value(event, "delta")
            if isinstance(delta, str):
                output_parts.append(delta)
        if event_type == "response.completed":
            completed = True
            completed_response = _event_value(event, "response")
            break
        if event_type in {"response.incomplete", "response.failed"}:
            LOGGER.warning(
                "market assistant response stream terminated event_type=%s elapsed_seconds=%.2f event_counts=%s",
                event_type,
                monotonic() - started_at,
                event_counts,
            )
            raise ValueError("structured response stream did not complete")
    if not completed:
        raise ValueError("structured response stream did not complete")
    output_text = "".join(output_parts)
    if not output_text:
        response_output_text = _event_value(completed_response, "output_text")
        if isinstance(response_output_text, str):
            output_text = response_output_text
    STREAM_LOGGER.info(
        "market assistant response stream completed elapsed_seconds=%.2f event_counts=%s",
        monotonic() - started_at,
        event_counts,
    )
    return output_text


def _event_value(event, field):
    if isinstance(event, dict):
        return event.get(field)
    return getattr(event, field, None)


def _json_object_prompt(prompt, schema_type):
    schema = json.dumps(
        schema_type.model_json_schema(), ensure_ascii=False, sort_keys=True
    )
    instruction = {
        "role": "system",
        "content": (
            "Return exactly one JSON object matching this JSON Schema. "
            "Do not use markdown or add fields. JSON Schema: " + schema
        ),
    }
    return [instruction, *prompt]


async def plan_question(
    client,
    *,
    model: str,
    question: str,
    context_summary: dict,
    structured_output_mode: str = "json_schema",
) -> Awaitable[dict]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    if not isinstance(context_summary, dict):
        raise ValueError("context summary is required")
    prompt = _planning_prompt(question, context_summary)
    payload = await complete_structured(
        client,
        model=model,
        prompt=prompt,
        schema_type=TaskPlanSchema,
        structured_output_mode=structured_output_mode,
    )
    return validate_task_plan(payload)


def _planning_prompt(question, context_summary):
    operations_text = ", ".join(sorted(registered_operation_ids()))
    system_content = (
        "You are the Market Setup assistant planner. "
        "You must select operations only from the registered read-only operation registry: "
        f"{operations_text}. "
        "Every operation must carry bounded parameters only. "
        "Never include sql, file paths, urls, provider names, or credentials. "
        "Return a structured task plan matching the supplied schema."
    )
    user_content = (
        f"question: {question}\n"
        f"context summary: {json.dumps(context_summary, ensure_ascii=False, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
