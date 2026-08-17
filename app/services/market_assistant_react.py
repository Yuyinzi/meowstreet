import asyncio
import inspect
import json
import re
from datetime import datetime
from datetime import timezone
from time import monotonic

from app.services.market_assistant_llm import response_items_for_next_turn
from app.services.market_assistant_llm import stream_response_turn
from app.services.market_assistant_tool_runtime import execute_tool_batch
from app.services.market_assistant_tool_runtime import snapshot_artifact
from app.tools.market_assistant_tools import ALL_TOOL_IDS
from app.tools.market_assistant_tools import normalized_tool_call_key
from app.tools.market_assistant_tools import tool_definitions
from app.tools.market_assistant_tools import validate_tool_call
from app.tools.market_assistant_views import build_explanation_view
from app.tools.market_setup_explanation_snapshot import canonical_json

_REACT_TOOL_IDS = (
    "get_setup_overview",
    "get_macro_regime_explanation",
    "get_confirmation_test",
    "get_confirmation_tests",
    "get_posture_explanation",
    "get_approved_counterfactuals",
    "get_indicator_knowledge",
    "query_indicator_history",
    "compare_snapshots",
)

_RESEARCH_TOOL_IDS = {
    "focused": ("research_focused",),
    "standard": ("research_focused", "research_standard"),
    "deep": ("research_focused", "research_standard", "research_deep"),
}

_TEST_ID_BY_INDICATOR = {
    "vix": "vix",
    "sp500_close": "equity",
    "sp500_market_phase": "equity",
    "credit_conditions": "credit",
}

_CONFIRMATION_TEST_IDS = ("equity", "credit", "vix")

_STAGE_BY_TOOL = {
    "get_setup_overview": "reading_setup",
    "get_macro_regime_explanation": "reading_setup",
    "get_posture_explanation": "reading_setup",
    "get_approved_counterfactuals": "reading_setup",
    "get_confirmation_test": "checking_confirmation",
    "get_confirmation_tests": "checking_confirmation",
    "get_indicator_knowledge": "reading_setup",
    "get_indicator_definition": "reading_setup",
    "get_indicator_method": "reading_setup",
    "get_indicator_current": "querying_history",
    "query_indicator_history": "querying_history",
    "get_evidence_detail": "reading_setup",
    "compare_snapshots": "comparing_evidence",
    "research_focused": "querying_history",
    "research_standard": "querying_history",
    "research_deep": "querying_history",
}

_STAGE_ORDER = (
    "reading_setup",
    "checking_confirmation",
    "querying_history",
    "comparing_evidence",
)

_PROGRESS_MESSAGES = {
    "zh": {
        "reading_setup": "正在读取当前 Market Setup…",
        "checking_confirmation": "正在检查股票、信贷与波动率信号…",
        "querying_history": "正在查询本地历史数据…",
        "comparing_evidence": "正在比较证据…",
        "writing_answer": "正在整理回答…",
    },
    "en": {
        "reading_setup": "Reading the current Market Setup…",
        "checking_confirmation": "Checking equity, credit, and volatility signals…",
        "querying_history": "Querying local history…",
        "comparing_evidence": "Comparing evidence…",
        "writing_answer": "Writing the answer…",
    },
}

_FALLBACK_ANSWERS = {
    "zh": "当前市场证据已收集，但回答生成暂不可用。",
    "en": "Market evidence was collected, but answer generation is currently unavailable.",
}

_INSTRUCTIONS = (
    "You are the Market Setup narration assistant. "
    "Narrate the current market setup, confirmation evidence, and portfolio posture "
    "from the tool evidence provided in this conversation. "
    "Answer in the language required by the newest user message. Some relevant evidence "
    "has already been fetched and is shown in this conversation. You may call any of "
    "the available tools if you need additional evidence. Do not invent facts, "
    "thresholds, or causality "
    "that the evidence does not support. When evidence is unavailable, say it is "
    "unavailable rather than guessing."
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_DEPENDENCY_DEFAULTS = {
    "stream_turn": stream_response_turn,
    "narration_instructions": _INSTRUCTIONS,
    "response_items_for_next_turn": response_items_for_next_turn,
    "execute_tool_batch": execute_tool_batch,
    "build_explanation_view": build_explanation_view,
    "validate_tool_call": validate_tool_call,
    "tool_definitions": tool_definitions,
    "normalized_tool_call_key": normalized_tool_call_key,
    "canonical_json": canonical_json,
}


def _dependency(dependencies, name):
    if isinstance(dependencies, dict):
        value = dependencies.get(name)
        if value is None:
            value = _DEPENDENCY_DEFAULTS.get(name)
    else:
        value = getattr(dependencies, name, None)
        if value is None:
            value = _DEPENDENCY_DEFAULTS.get(name)
    if value is None:
        raise ValueError(f"dependency is missing: {name}")
    return value


def _optional_dependency(dependencies, name):
    if isinstance(dependencies, dict):
        return dependencies.get(name)
    return getattr(dependencies, name, None)


def _runtime_config(dependencies):
    config = _optional_dependency(dependencies, "config")
    if config is not None:
        return config
    build_config = _dependency(dependencies, "build_config")
    config = build_config()
    if not isinstance(config, dict):
        raise ValueError("runtime config is invalid")
    return config


def _now_iso():
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _model(dependencies):
    model = _optional_dependency(dependencies, "model")
    if model is not None:
        return model
    config = _runtime_config(dependencies)
    model = config.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model is required")
    return model


def _reasoning_effort(dependencies):
    effort = _optional_dependency(dependencies, "reasoning_effort")
    if effort is not None:
        return effort
    config = _runtime_config(dependencies)
    return config.get("reasoning_effort", "low")


def _question_language(question):
    return "zh" if _CJK_RE.search(question) else "en"


def _translate_initial_operation(operation):
    operation_id = operation["operation_id"]
    indicator_id = operation.get("indicator_id")
    if operation_id == "get_indicator_confirmation":
        test_id = _TEST_ID_BY_INDICATOR.get(indicator_id, indicator_id)
        return {
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": test_id},
        }
    if operation_id == "get_indicator_definition":
        return {
            "tool_name": "get_indicator_knowledge",
            "arguments": {"indicator_id": indicator_id, "topic": "definition"},
        }
    if operation_id == "get_indicator_method":
        return {
            "tool_name": "get_indicator_knowledge",
            "arguments": {"indicator_id": indicator_id, "topic": "method"},
        }
    if operation_id == "get_confirmation_tests":
        return {
            "tool_name": "get_confirmation_tests",
            "arguments": {"test_ids": list(_CONFIRMATION_TEST_IDS)},
        }
    return {"tool_name": operation_id, "arguments": {}}


def _translated_initial_calls(route):
    calls = []
    for operation in route.get("initial_operations") or []:
        call = _translate_initial_operation(operation)
        call["call_id"] = f"initial_{operation['operation_id']}"
        calls.append(call)
    return calls


def _available_tool_ids():
    return tuple(ALL_TOOL_IDS)


def _validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("request is required")
    question = request.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")


def _validate_route(route):
    if not isinstance(route, dict):
        raise ValueError("route is required")
    route_id = route.get("route_id")
    if not isinstance(route_id, str) or not route_id:
        raise ValueError("route id is required")
    budget = route.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("route budget is required")


async def run_hybrid_narration(
    request, *, route, resolution, dependencies, event_sink=None
):
    _validate_request(request)
    _validate_route(route)
    if event_sink is None:
        event_sink = _optional_dependency(dependencies, "event_sink")
    budget = route["budget"]
    tool_ids = _available_tool_ids()
    client = _dependency(dependencies, "client")
    model = _model(dependencies)
    reasoning_effort = _reasoning_effort(dependencies)
    stream_turn = _dependency(dependencies, "stream_turn")
    instructions = _dependency(dependencies, "narration_instructions")
    if callable(instructions):
        instructions = instructions()
    execute_batch = _dependency(dependencies, "execute_tool_batch")
    definitions = _dependency(dependencies, "tool_definitions")
    validate_call = _dependency(dependencies, "validate_tool_call")
    normalize_key = _dependency(dependencies, "normalized_tool_call_key")
    next_items = _dependency(dependencies, "response_items_for_next_turn")
    build_view = _dependency(dependencies, "build_explanation_view")
    measure = _dependency(dependencies, "canonical_json")
    started_at = monotonic()
    created_at = _now_iso()
    artifacts = {}
    tool_trace = []
    seen_calls = set()
    call_count = 0
    executed_calls = 0
    result_bytes = 0
    round_number = 0
    turn_count = 0
    deadline = monotonic() + budget["deadline_seconds"]
    stream_state = {"text_parts": [], "has_output": False}
    generation_status = None
    answer_text = ""
    initial_tools_seconds = 0.0

    initial_calls = _translated_initial_calls(route)
    initial_records = []
    if initial_calls:
        await _emit(event_sink, {"type": "initial_tools_started"})
        initial_started_at = monotonic()
        try:
            initial_records = await _await_within_budget(
                lambda: execute_batch(
                    initial_calls,
                    request=request,
                    resolution=resolution,
                    dependencies=dependencies,
                    created_at=created_at,
                ),
                deadline,
            )
        except _DeadlineExceeded:
            generation_status = "deadline_exceeded"
            return _narration_result(
                answer_text="",
                artifacts=artifacts,
                route=route,
                generation_status=generation_status,
                initial_tools_seconds=round(monotonic() - initial_started_at, 4),
                optional_rounds=0,
                executed_calls=executed_calls,
                started_at=started_at,
                view=build_view(
                    route,
                    artifacts,
                    question=request["question"],
                    answer_language=request.get("answer_language"),
                ),
                tool_trace=tool_trace,
            )
        _merge_records(artifacts, initial_records, tool_trace, "initial")
        initial_tools_seconds = round(monotonic() - initial_started_at, 4)
        await _emit(event_sink, {"type": "initial_tools_completed"})
    if route["route_id"] == "react":
        _seed_snapshot_anchor(artifacts, resolution)
    view = build_view(
        route,
        artifacts,
        question=request["question"],
        answer_language=request.get("answer_language"),
    )
    history_items = request.get("provider_history") or []
    input_items = _initial_input_items(
        request["question"],
        view,
        history_items,
        answer_language=request.get("answer_language")
        or _question_language(request["question"]),
        available_tool_ids=tool_ids,
    )
    current_user_item = input_items[-1]
    new_provider_items = [current_user_item]
    generated_provider_items = []
    tools = definitions(list(ALL_TOOL_IDS))

    while True:
        if monotonic() > deadline:
            generation_status = "deadline_exceeded"
            break
        await _emit(event_sink, {"type": "model_turn_started"})
        if turn_count > 0 or initial_calls:
            await _emit_progress(event_sink, "writing_answer", request)
        turn_stream = {"output_events": [], "has_tool_call": False}
        observer = _turn_observer(turn_stream, event_sink)
        try:
            turn = await _await_within_budget(
                lambda: stream_turn(
                    client,
                    model=model,
                    input_items=input_items,
                    instructions=instructions,
                    tools=tools,
                    reasoning_effort=reasoning_effort,
                    observer=observer,
                ),
                deadline,
            )
        except _DeadlineExceeded:
            if not turn_stream["has_tool_call"]:
                await _flush_turn_output(turn_stream, stream_state, event_sink)
            if stream_state["has_output"]:
                generation_status = "narration_interrupted"
            else:
                generation_status = "deadline_exceeded"
            break
        except asyncio.TimeoutError:
            if not turn_stream["has_tool_call"]:
                await _flush_turn_output(turn_stream, stream_state, event_sink)
            if stream_state["has_output"]:
                generation_status = "narration_interrupted"
            else:
                generation_status = "narration_unavailable"
            break
        except Exception:
            if not turn_stream["has_tool_call"]:
                await _flush_turn_output(turn_stream, stream_state, event_sink)
            if stream_state["has_output"]:
                generation_status = "narration_interrupted"
            else:
                generation_status = "narration_unavailable"
            break
        if turn["tool_calls"]:
            if (
                round_number >= budget["max_rounds"]
                or call_count >= budget["max_tool_calls"]
            ):
                generation_status = "budget_exhausted"
                break
            round_number += 1
            accepted, rejected = _classify_calls(
                turn["tool_calls"],
                validate_call,
                normalize_key,
                seen_calls,
                budget,
                call_count,
            )
            if any(item["reason"] == "duplicate_tool_call" for item in rejected):
                generation_status = "duplicate_tool_call"
                break
            _record_rejected(tool_trace, rejected, "optional")
            records = []
            if accepted:
                if monotonic() > deadline:
                    generation_status = "deadline_exceeded"
                    break
                await _emit_batch_progress(event_sink, accepted, request)
                try:
                    records = await _await_within_budget(
                        lambda: execute_batch(
                            accepted,
                            request=request,
                            resolution=resolution,
                            dependencies=dependencies,
                            created_at=created_at,
                        ),
                        deadline,
                    )
                except _DeadlineExceeded:
                    generation_status = "deadline_exceeded"
                    break
                _merge_records(artifacts, records, tool_trace, "optional")
                seen_calls.update(_call_keys(normalize_key, accepted))
                result_bytes += _result_bytes(measure, records)
                if result_bytes > budget["max_tool_result_bytes"]:
                    generation_status = "budget_exhausted"
                    break
                await _emit(event_sink, {"type": "optional_round_completed"})
            call_count += len(accepted) + len(rejected)
            executed_calls += len(records)
            input_items = _next_input_items(
                input_items,
                next_items(turn),
                _output_items(accepted, records, rejected),
            )
            new_provider_items.extend(next_items(turn))
            new_provider_items.extend(_output_items(accepted, records, rejected))
            generated_provider_items.extend(next_items(turn))
            generated_provider_items.extend(_output_items(accepted, records, rejected))
        else:
            await _flush_turn_output(turn_stream, stream_state, event_sink)
            answer_text = turn["output_text"]
            new_provider_items.extend(next_items(turn))
            generated_provider_items.extend(next_items(turn))
            if answer_text.strip():
                generation_status = "answered"
            else:
                generation_status = "narration_unavailable"
            break
        turn_count += 1

    if generation_status == "answered":
        pass
    elif generation_status == "narration_interrupted":
        answer_text = "".join(stream_state["text_parts"])
    elif stream_state["has_output"]:
        answer_text = "".join(stream_state["text_parts"])
    else:
        answer_text = _fallback_answer(request)
    view = build_view(
        route,
        artifacts,
        question=request["question"],
        answer_language=request.get("answer_language"),
    )
    return _narration_result(
        answer_text=answer_text,
        artifacts=artifacts,
        view=view,
        tool_trace=tool_trace,
        route=route,
        generation_status=generation_status,
        initial_tools_seconds=initial_tools_seconds,
        optional_rounds=round_number,
        executed_calls=executed_calls,
        started_at=started_at,
        provider_items=new_provider_items,
        current_user_item=current_user_item,
        generated_provider_items=generated_provider_items,
    )


def _narration_result(
    *,
    answer_text,
    artifacts,
    view,
    tool_trace,
    route,
    generation_status,
    initial_tools_seconds,
    optional_rounds,
    executed_calls,
    started_at,
    provider_items=None,
    current_user_item=None,
    generated_provider_items=None,
):
    return {
        "answer_text": answer_text,
        "artifacts": artifacts,
        "view": view,
        "tool_trace": tool_trace,
        "route": route,
        "timings": {
            "initial_tools_seconds": initial_tools_seconds,
            "optional_rounds": optional_rounds,
            "executed_calls": executed_calls,
            "total_seconds": round(monotonic() - started_at, 4),
        },
        "generation_status": generation_status,
        "provider_items": list(provider_items or []),
        "current_user_item": current_user_item,
        "generated_provider_items": list(generated_provider_items or []),
    }


def _view_text(view):
    return json.dumps({"explanation_view": view}, ensure_ascii=False, sort_keys=True)


def _initial_input_items(
    question,
    view,
    history_items=None,
    answer_language=None,
    available_tool_ids=(),
):
    items = list(history_items or [])
    items.append(
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": question},
                {"type": "input_text", "text": _view_text(view)},
                {
                    "type": "input_text",
                    "text": "Answer language: "
                    + ("Chinese" if answer_language == "zh" else "English"),
                },
                {
                    "type": "input_text",
                    "text": "Pre-fetched evidence is shown above. You may call any "
                    "of the available tools if you need more evidence.",
                },
            ],
        }
    )
    return items


def _next_input_items(input_items, response_items, output_items):
    items = list(input_items)
    items.extend(response_items)
    items.extend(output_items)
    return items


def _seed_snapshot_anchor(artifacts, resolution):
    snapshot = (resolution or {}).get("snapshot")
    if not isinstance(snapshot, dict):
        return
    envelope = snapshot_artifact(snapshot)
    artifacts.setdefault(envelope["artifact_id"], envelope)


def _provider_tool_output(record):
    artifact = record["artifact"]
    if artifact is None:
        return json.dumps(
            {
                "tool_name": record["tool_name"],
                "status": "unavailable",
                "arguments": record["arguments"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    return json.dumps(
        {
            "tool_name": record["tool_name"],
            "status": "available",
            "artifact_id": artifact["artifact_id"],
            "artifact_kind": artifact["artifact_kind"],
            "schema_version": artifact["schema_version"],
            "primary_authority": artifact["primary_authority"],
            "market_setup_relation": artifact["market_setup_relation"],
            "payload": artifact["payload"],
            "object_index": artifact["object_index"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _rejected_output(reason):
    return json.dumps(
        {"status": "rejected", "reason": reason}, ensure_ascii=False, sort_keys=True
    )


def _output_items(accepted, records, rejected):
    items = []
    for call, record in zip(accepted, records):
        items.append(
            {
                "type": "function_call_output",
                "call_id": call["call_id"],
                "output": _provider_tool_output(record),
            }
        )
    for item in rejected:
        call = item["call"]
        items.append(
            {
                "type": "function_call_output",
                "call_id": call.get("call_id", ""),
                "output": _rejected_output(item["reason"]),
            }
        )
    return items


def _classify_calls(
    turn_calls,
    validate_call,
    normalize_key,
    seen_calls,
    budget,
    call_count,
):
    rejected = []
    accepted = []
    round_keys = set()
    for call in turn_calls:
        try:
            validated = validate_call(call)
        except ValueError:
            rejected.append({"call": call, "reason": "tool_call_invalid"})
            continue
        key = normalize_key(validated)
        if key in seen_calls or key in round_keys:
            rejected.append({"call": validated, "reason": "duplicate_tool_call"})
            continue
        round_keys.add(key)
        accepted.append(validated)
    if len(accepted) > budget["max_parallel_calls"]:
        rejected.extend(
            {"call": call, "reason": "parallel_call_limit"}
            for call in accepted[budget["max_parallel_calls"] :]
        )
        accepted = accepted[: budget["max_parallel_calls"]]
    remaining = budget["max_tool_calls"] - call_count
    if len(accepted) > remaining:
        rejected.extend(
            {"call": call, "reason": "tool_call_budget"}
            for call in accepted[remaining:]
        )
        accepted = accepted[:remaining]
    return accepted, rejected


def _call_keys(normalize_key, calls):
    return {normalize_key(call) for call in calls}


def _result_bytes(measure, records):
    total = 0
    for record in records:
        artifact = record["artifact"]
        if artifact is not None:
            total += len(measure(artifact))
    return total


def _merge_records(artifacts, records, tool_trace, phase):
    for record in records:
        artifact = record["artifact"]
        if artifact is not None:
            artifacts[artifact["artifact_id"]] = artifact
        tool_trace.append(
            {
                "phase": phase,
                "call_id": record["call_id"],
                "tool_name": record["tool_name"],
                "arguments": record["arguments"],
                "status": "executed" if artifact is not None else "unavailable",
                "artifact_id": artifact["artifact_id"]
                if artifact is not None
                else None,
            }
        )


def _record_rejected(tool_trace, rejected, phase):
    for item in rejected:
        call = item["call"]
        tool_trace.append(
            {
                "phase": phase,
                "call_id": call.get("call_id", ""),
                "tool_name": call.get("tool_name"),
                "arguments": call.get("arguments", {}),
                "status": "rejected",
                "reason": item["reason"],
                "artifact_id": None,
            }
        )


def _turn_observer(turn_stream, event_sink):
    async def observer(event):
        if event["type"] == "output_delta":
            turn_stream["output_events"].append(event)
            return
        if event["type"] == "provider_tool_call_started":
            turn_stream["has_tool_call"] = True
        await _emit(event_sink, event)

    return observer


async def _flush_turn_output(turn_stream, stream_state, event_sink):
    for event in turn_stream["output_events"]:
        delta = event.get("delta")
        if isinstance(delta, str):
            stream_state["text_parts"].append(delta)
            stream_state["has_output"] = True
        await _emit(event_sink, event)
    turn_stream["output_events"] = []


def _fallback_answer(request):
    language = request.get("answer_language") or _question_language(request["question"])
    return _FALLBACK_ANSWERS[language]


async def _emit(event_sink, event):
    if event_sink is None:
        return
    send = getattr(event_sink, "send", None)
    if callable(send):
        result = send(event)
    else:
        result = event_sink(event)
    if inspect.isawaitable(result):
        await result


class _DeadlineExceeded(asyncio.TimeoutError):
    pass


async def _await_within_budget(coro_factory, deadline):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise _DeadlineExceeded()
    task = asyncio.create_task(coro_factory())
    try:
        done, _ = await asyncio.wait({task}, timeout=remaining)
    except asyncio.CancelledError:
        task.cancel()
        task.add_done_callback(_consume_deadlined_task)
        raise
    if task not in done:
        task.cancel()
        task.add_done_callback(_consume_deadlined_task)
        raise _DeadlineExceeded()
    return task.result()


def _consume_deadlined_task(task):
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        pass


async def _emit_progress(event_sink, stage, request):
    language = request.get("answer_language") or _question_language(request["question"])
    message = _PROGRESS_MESSAGES[language][stage]
    await _emit(event_sink, {"type": "progress", "stage": stage, "message": message})


async def _emit_batch_progress(event_sink, calls, request):
    stages = set()
    for call in calls:
        stage = _STAGE_BY_TOOL.get(call["tool_name"])
        if stage is not None:
            stages.add(stage)
    for stage in _STAGE_ORDER:
        if stage in stages:
            await _emit_progress(event_sink, stage, request)
