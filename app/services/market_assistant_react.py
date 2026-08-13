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
    "get_indicator_current": "querying_history",
    "query_indicator_history": "querying_history",
    "compare_snapshots": "comparing_evidence",
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
    "Answer in the user's language. Do not invent facts, thresholds, or causality "
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


def _model_tool_ids(request, route):
    if route["route_id"] == "react":
        tool_ids = list(_REACT_TOOL_IDS)
    else:
        tool_ids = list(route.get("supplementary_tools") or [])
    tool_ids.extend(_authorized_research_tools(request))
    seen = set()
    unique = []
    for tool_id in tool_ids:
        if tool_id not in seen:
            seen.add(tool_id)
            unique.append(tool_id)
    return tuple(unique)


def _authorized_research_tools(request):
    if not request.get("external_search_requested"):
        return []
    tier = request.get("research_tier")
    if tier is None:
        tier = "deep" if request.get("deep_research_requested") else "standard"
    if tier not in _RESEARCH_TOOL_IDS:
        raise ValueError("research tier is unknown")
    return list(_RESEARCH_TOOL_IDS[tier])


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
    tool_ids = _model_tool_ids(request, route)
    tool_id_set = set(tool_ids)
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
    deadline = monotonic() + budget["deadline_seconds"]
    stream_state = {"text_parts": [], "has_output": False}
    generation_status = None
    answer_text = ""
    initial_tools_seconds = 0.0
    observer = _turn_observer(stream_state, event_sink)

    initial_calls = _translated_initial_calls(route)
    initial_records = []
    if initial_calls:
        await _emit(event_sink, {"type": "initial_tools_started"})
        initial_started_at = monotonic()
        initial_records = await execute_batch(
            initial_calls,
            request=request,
            resolution=resolution,
            dependencies=dependencies,
            created_at=created_at,
        )
        _merge_records(artifacts, initial_records, tool_trace, "initial")
        initial_tools_seconds = round(monotonic() - initial_started_at, 4)
        await _emit(event_sink, {"type": "initial_tools_completed"})
    if route["route_id"] == "react":
        _seed_snapshot_anchor(artifacts, resolution)
    view = build_view(route, artifacts, question=request["question"])
    input_items = _initial_input_items(request["question"], initial_records, view)
    tools = definitions(list(tool_ids))

    while True:
        if round_number >= budget["max_rounds"]:
            generation_status = "budget_exhausted"
            break
        if monotonic() > deadline:
            generation_status = "budget_exhausted"
            break
        if call_count >= budget["max_tool_calls"]:
            generation_status = "budget_exhausted"
            break
        round_number += 1
        await _emit(event_sink, {"type": "model_turn_started"})
        if round_number > 1 or initial_calls:
            await _emit_progress(event_sink, "writing_answer", request)
        try:
            turn = await stream_turn(
                client,
                model=model,
                input_items=input_items,
                instructions=instructions,
                tools=tools,
                reasoning_effort=reasoning_effort,
                observer=observer,
            )
        except Exception:
            if stream_state["has_output"]:
                generation_status = "narration_interrupted"
            else:
                generation_status = "narration_unavailable"
            break
        if turn["tool_calls"]:
            accepted, rejected = _classify_calls(
                turn["tool_calls"],
                tool_id_set,
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
                    generation_status = "budget_exhausted"
                    break
                await _emit_batch_progress(event_sink, accepted, request)
                records = await execute_batch(
                    accepted,
                    request=request,
                    resolution=resolution,
                    dependencies=dependencies,
                    created_at=created_at,
                )
                _merge_records(artifacts, records, tool_trace, "optional")
                seen_calls.update(_call_keys(normalize_key, accepted))
                result_bytes += _result_bytes(measure, records)
                if result_bytes > budget["max_tool_result_bytes"]:
                    generation_status = "budget_exhausted"
                    break
            call_count += len(accepted) + len(rejected)
            executed_calls += len(records)
            input_items = _next_input_items(
                input_items,
                next_items(turn),
                _output_items(accepted, records, rejected),
                build_view(route, artifacts, question=request["question"]),
            )
        else:
            answer_text = turn["output_text"]
            if answer_text.strip():
                generation_status = "answered"
            else:
                generation_status = "narration_unavailable"
            break

    if generation_status == "answered":
        pass
    elif generation_status == "narration_interrupted":
        answer_text = "".join(stream_state["text_parts"])
    elif stream_state["has_output"]:
        answer_text = "".join(stream_state["text_parts"])
    else:
        answer_text = _fallback_answer(request)
    view = build_view(route, artifacts, question=request["question"])
    return {
        "answer_text": answer_text,
        "artifacts": artifacts,
        "view": view,
        "tool_trace": tool_trace,
        "route": route,
        "timings": {
            "initial_tools_seconds": initial_tools_seconds,
            "optional_rounds": round_number,
            "executed_calls": executed_calls,
            "total_seconds": round(monotonic() - started_at, 4),
        },
        "generation_status": generation_status,
    }


def _view_text(view):
    return json.dumps({"explanation_view": view}, ensure_ascii=False, sort_keys=True)


def _message_with_view(message, view):
    content = list(message["content"])
    content[1] = {"type": "input_text", "text": _view_text(view)}
    return {**message, "content": content}


def _initial_input_items(question, records, view):
    items = [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": question},
                {"type": "input_text", "text": _view_text(view)},
            ],
        }
    ]
    for record in records:
        items.append(
            {
                "type": "function_call",
                "call_id": record["call_id"],
                "name": record["tool_name"],
                "arguments": json.dumps(
                    record["arguments"], ensure_ascii=False, sort_keys=True
                ),
            }
        )
        items.append(
            {
                "type": "function_call_output",
                "call_id": record["call_id"],
                "output": _provider_tool_output(record),
            }
        )
    return items


def _next_input_items(input_items, response_items, output_items, view):
    items = list(input_items)
    items.extend(response_items)
    items.extend(output_items)
    items[0] = _message_with_view(items[0], view)
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
    tool_id_set,
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
            validated = validate_call(call, tool_id_set)
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


def _turn_observer(stream_state, event_sink):
    async def observer(event):
        if event["type"] == "output_delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                stream_state["text_parts"].append(delta)
                stream_state["has_output"] = True
        await _emit(event_sink, event)

    return observer


def _fallback_answer(request):
    return _FALLBACK_ANSWERS[_question_language(request["question"])]


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


async def _emit_progress(event_sink, stage, request):
    language = _question_language(request["question"])
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
