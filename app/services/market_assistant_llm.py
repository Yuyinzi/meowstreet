import inspect
import json
import logging
from time import monotonic
from typing import Awaitable

from pydantic import BaseModel

from app.tools.market_assistant_plans import TaskPlanSchema
from app.tools.market_assistant_plans import registered_operation_ids
from app.tools.market_assistant_plans import validate_task_plan
from app.tools.market_assistant_stream import AnswerTextStreamExtractor


LOGGER = logging.getLogger(__name__)
STREAM_LOGGER = logging.getLogger("uvicorn.error")


async def complete_structured(
    client,
    *,
    model: str,
    prompt: list[dict],
    schema_type: type[BaseModel],
    structured_output_mode: str = "json_schema",
    reasoning_effort: str = "low",
    stream_observer=None,
) -> Awaitable[dict]:
    if structured_output_mode == "json_object":
        request_started_at = monotonic()
        STREAM_LOGGER.info("market assistant response stream request started")
        stream = await client.responses.create(
            model=model,
            input=_json_object_prompt(prompt, schema_type),
            text={"format": {"type": "json_object"}},
            reasoning={"effort": reasoning_effort},
            stream=True,
        )
        STREAM_LOGGER.info(
            "market assistant response stream connected elapsed_seconds=%.2f",
            monotonic() - request_started_at,
        )
        output_text = await _collect_response_stream(stream, stream_observer)
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
        reasoning={"effort": reasoning_effort},
    )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("structured response is unavailable")
    return parsed.model_dump(mode="json")


async def _collect_response_stream(stream, stream_observer=None):
    started_at = monotonic()
    event_counts = {}
    output_parts = []
    completed_response = None
    completed = False
    first_event_received = False
    first_reasoning_at = None
    first_output_at = None
    reasoning_started_emitted = False
    extractor = None
    if stream_observer is not None:
        extractor = AnswerTextStreamExtractor()
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
        if event_type == "response.reasoning_text.delta":
            if first_reasoning_at is None:
                first_reasoning_at = monotonic() - started_at
            if extractor is not None and not reasoning_started_emitted:
                reasoning_started_emitted = True
                await _notify_observer(
                    stream, stream_observer, {"type": "reasoning_started"}
                )
        if event_type == "response.output_text.delta":
            if first_output_at is None:
                first_output_at = monotonic() - started_at
            delta = _event_value(event, "delta")
            if isinstance(delta, str):
                output_parts.append(delta)
                if extractor is not None:
                    delta_text = extractor.feed(delta)
                    if delta_text:
                        await _notify_observer(
                            stream,
                            stream_observer,
                            {"type": "answer_delta", "delta": delta_text},
                        )
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
    if extractor is not None and not output_parts:
        extractor.feed(output_text)
    if extractor is not None:
        extractor.finish()
    elapsed_seconds = monotonic() - started_at
    _log_stream_usage(
        completed_response, elapsed_seconds, first_reasoning_at, first_output_at
    )
    STREAM_LOGGER.info(
        "market assistant response stream completed elapsed_seconds=%.2f event_counts=%s",
        elapsed_seconds,
        event_counts,
    )
    return output_text


async def _notify_observer(stream, stream_observer, event):
    try:
        result = stream_observer(event)
        if inspect.isawaitable(result):
            await result
    except Exception:
        aclose = getattr(stream, "aclose", None)
        if callable(aclose):
            await aclose()
        raise


def _log_stream_usage(
    completed_response, elapsed_seconds, first_reasoning_at, first_output_at
):
    usage = _event_value(completed_response, "usage")
    if usage is None:
        return
    STREAM_LOGGER.info(
        "market assistant response usage "
        "input_tokens=%s cached_tokens=%s output_tokens=%s reasoning_tokens=%s "
        "elapsed_seconds=%.2f first_reasoning_seconds=%s first_output_seconds=%s",
        _token_label(_nested_value(usage, "input_tokens")),
        _token_label(_nested_value(usage, "input_tokens_details", "cached_tokens")),
        _token_label(_nested_value(usage, "output_tokens")),
        _token_label(_nested_value(usage, "output_tokens_details", "reasoning_tokens")),
        elapsed_seconds,
        _elapsed_label(first_reasoning_at),
        _elapsed_label(first_output_at),
    )


def _token_label(value):
    if value is None:
        return "none"
    return value


def _nested_value(payload, *path):
    value = payload
    for part in path:
        if value is None:
            return None
        value = _event_value(value, part)
    return value


def _elapsed_label(seconds):
    if seconds is None:
        return "none"
    return f"{seconds:.2f}"


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


async def stream_response_turn(
    client,
    *,
    model: str,
    input_items: list,
    instructions: str,
    tools: list[dict],
    reasoning_effort: str,
    observer=None,
):
    request_started_at = monotonic()
    STREAM_LOGGER.info("market assistant response turn request started")
    stream = await client.responses.create(
        model=model,
        instructions=instructions,
        input=input_items,
        tools=tools,
        reasoning={"effort": reasoning_effort},
        stream=True,
    )
    STREAM_LOGGER.info(
        "market assistant response turn connected elapsed_seconds=%.2f",
        monotonic() - request_started_at,
    )
    return await _collect_response_turn(
        stream, observer=observer, started_at=request_started_at
    )


async def _collect_response_turn(stream, *, observer, started_at):
    event_counts = {}
    output_parts = []
    tool_calls = []
    response_items = []
    argument_buffers = {}
    parsed_arguments = {}
    completed_response = None
    completed = False
    first_event_received = False
    first_reasoning_at = None
    first_output_at = None
    first_visible_at = None
    reasoning_started_emitted = False
    STREAM_LOGGER.info("market assistant response turn started")
    async for event in stream:
        event_type = _event_value(event, "type") or "unknown"
        if not first_event_received:
            first_event_received = True
            STREAM_LOGGER.info(
                "market assistant response turn first event event_type=%s elapsed_seconds=%.2f",
                event_type,
                monotonic() - started_at,
            )
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type == "response.reasoning_text.delta":
            if first_reasoning_at is None:
                first_reasoning_at = monotonic() - started_at
            if observer is not None and not reasoning_started_emitted:
                reasoning_started_emitted = True
                await _notify_observer(stream, observer, {"type": "reasoning_started"})
        if event_type == "response.output_text.delta":
            if first_output_at is None:
                first_output_at = monotonic() - started_at
            delta = _event_value(event, "delta")
            if isinstance(delta, str):
                output_parts.append(delta)
                if first_visible_at is None and any(
                    not char.isspace() for char in delta
                ):
                    first_visible_at = monotonic() - started_at
                if observer is not None:
                    await _notify_observer(
                        stream, observer, {"type": "output_delta", "delta": delta}
                    )
        if event_type == "response.output_item.added":
            item = _event_value(event, "item")
            if _event_value(item, "type") == "function_call":
                call_id = _event_value(item, "call_id")
                argument_buffers.setdefault(call_id, [])
                if observer is not None:
                    await _notify_observer(
                        stream,
                        observer,
                        {
                            "type": "provider_tool_call_started",
                            "call_id": call_id,
                            "tool_name": _event_value(item, "name"),
                        },
                    )
        if event_type == "response.function_call_arguments.delta":
            call_id = _event_value(event, "item_id")
            delta = _event_value(event, "delta")
            if call_id is not None and isinstance(delta, str):
                argument_buffers.setdefault(call_id, []).append(delta)
        if event_type == "response.function_call_arguments.done":
            call_id = _event_value(event, "item_id")
            arguments_text = _event_value(event, "arguments")
            if not isinstance(arguments_text, str):
                arguments_text = "".join(argument_buffers.get(call_id, []))
            parsed_arguments[call_id] = _parse_arguments(arguments_text, call_id)
        if event_type == "response.output_item.done":
            item = _event_value(event, "output")
            if item is None:
                item = _event_value(event, "item")
            if item is not None:
                response_items.append(_to_plain_dict(item))
                if _event_value(item, "type") == "function_call":
                    tool_calls.append(
                        _normalized_tool_call(item, parsed_arguments, argument_buffers)
                    )
        if event_type == "response.completed":
            completed = True
            completed_response = _event_value(event, "response")
            break
        if event_type in {"response.incomplete", "response.failed"}:
            LOGGER.warning(
                "market assistant response turn terminated event_type=%s elapsed_seconds=%.2f event_counts=%s",
                event_type,
                monotonic() - started_at,
                event_counts,
            )
            raise ValueError("response stream did not complete")
    if not completed:
        raise ValueError("response stream did not complete")
    output_text = "".join(output_parts)
    elapsed_seconds = monotonic() - started_at
    _log_stream_usage(
        completed_response, elapsed_seconds, first_reasoning_at, first_output_at
    )
    STREAM_LOGGER.info(
        "market assistant response turn completed "
        "first_reasoning_seconds=%s first_output_seconds=%s "
        "first_visible_delta_seconds=%s completed_seconds=%.2f event_counts=%s",
        _elapsed_label(first_reasoning_at),
        _elapsed_label(first_output_at),
        _elapsed_label(first_visible_at),
        elapsed_seconds,
        event_counts,
    )
    return {
        "output_text": output_text,
        "tool_calls": tool_calls,
        "response_items": response_items,
        "usage": _to_plain_dict(_event_value(completed_response, "usage")),
        "timings": {
            "first_reasoning_seconds": first_reasoning_at,
            "first_output_seconds": first_output_at,
            "first_visible_delta_seconds": first_visible_at,
            "completed_seconds": elapsed_seconds,
        },
    }


def response_items_for_next_turn(turn):
    return list(turn["response_items"])


def _normalized_tool_call(item, parsed_arguments, argument_buffers):
    call_id = _event_value(item, "call_id")
    arguments = parsed_arguments.get(call_id)
    if arguments is None:
        arguments_text = _event_value(item, "arguments")
        if not isinstance(arguments_text, str):
            arguments_text = "".join(argument_buffers.get(call_id, []))
        arguments = _parse_arguments(arguments_text, call_id)
    return {
        "call_id": call_id,
        "tool_name": _event_value(item, "name"),
        "arguments": arguments,
    }


def _parse_arguments(arguments_text, call_id):
    if not isinstance(arguments_text, str):
        raise ValueError(f"function call {call_id} arguments are invalid")
    try:
        return json.loads(arguments_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"function call {call_id} arguments are invalid") from exc


def _to_plain_dict(value):
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return value


async def plan_question(
    client,
    *,
    model: str,
    question: str,
    context_summary: dict,
    structured_output_mode: str = "json_schema",
    reasoning_effort: str = "low",
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
        reasoning_effort=reasoning_effort,
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
