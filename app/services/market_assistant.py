import asyncio
import hashlib
import logging
import secrets
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from time import monotonic

from app.db.market_assistant import connect
from app.db.market_assistant import append_conversation_message
from app.db.market_assistant import append_conversation_turn
from app.db.market_assistant import load_snapshot
from app.db.market_assistant import load_conversation_history
from app.db.market_assistant import save_conversation_checkpoint
from app.db.market_assistant import save_answer_bundle
from app.services import market_assistant_tool_runtime
from app.services.market_assistant_exploration import EXPLORATION_SCHEMA_VERSION
from app.services.market_assistant_react import run_hybrid_narration
from app.services.market_assistant_tool_runtime import ARTIFACT_SCHEMA_VERSION
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_claim_audit import AuditValidationError
from app.tools.market_assistant_claim_audit import build_audit_validation_report
from app.tools.market_assistant_claim_audit import validate_claim_audit
from app.tools.market_assistant_conversation import build_checkpoint
from app.tools.market_assistant_conversation import CHECKPOINT_SCHEMA_VERSION
from app.tools.market_assistant_conversation import should_compact
from app.tools.market_assistant_research import RESEARCH_SCHEMA_VERSION
from app.tools.market_assistant_routes import route_question
from app.tools.market_setup_explanation_snapshot import canonical_json

PROMPT_VERSION = "market_assistant_prompt_v2"
ASSISTANT_POLICY_VERSION = "market_assistant_policy_v1"
ARTIFACT_SCHEMA_VERSION = "market_assistant_artifact_v1"
LLM_ATTEMPT_TIMEOUT_SECONDS = 900.0
AUDIT_TIMEOUT_SECONDS = 120.0

LOGGER = logging.getLogger(__name__)
STREAM_LOGGER = logging.getLogger("uvicorn.error")

TOOL_SCHEMA_VERSIONS = {
    "artifact_envelope": ARTIFACT_SCHEMA_VERSION,
    "exploration": EXPLORATION_SCHEMA_VERSION,
    "research": RESEARCH_SCHEMA_VERSION,
}

_DEPENDENCY_DEFAULTS = {
    "resolve_current_explanation": resolve_current_explanation,
    "connect": connect,
    "load_snapshot": load_snapshot,
    "load_conversation_history": load_conversation_history,
    "append_conversation_message": append_conversation_message,
    "append_conversation_turn": append_conversation_turn,
    "save_conversation_checkpoint": save_conversation_checkpoint,
    "save_bundle": save_answer_bundle,
}

_ENGLISH_LANGUAGE_REQUESTS = (
    "answer in english",
    "respond in english",
    "use english",
    "用英文",
    "英文回答",
)

_CHINESE_LANGUAGE_REQUESTS = (
    "answer in chinese",
    "respond in chinese",
    "use chinese",
    "用中文",
    "中文回答",
)


def _dependency(dependencies, name, default=None):
    if default is None:
        default = _DEPENDENCY_DEFAULTS.get(name)
    if isinstance(dependencies, dict):
        value = dependencies.get(name, default)
    else:
        value = getattr(dependencies, name, None)
        if value is None:
            value = default
    if value is None:
        raise ValueError(f"dependency is missing: {name}")
    return value


def _optional_dependency(dependencies, name):
    if isinstance(dependencies, dict):
        return dependencies.get(name)
    return getattr(dependencies, name, None)


def _runtime_config(dependencies):
    config = _dependency(dependencies, "config", default=None)
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


def _new_id(prefix):
    return f"{prefix}{secrets.token_hex(8)}"


def _request_id(deps):
    request_id = _optional_dependency(deps, "request_id")
    if request_id:
        return request_id
    return _new_id("req_")


def _prepare_conversation_request(request, deps, db_path):
    prepared = dict(request)
    conversation_id = str(prepared.get("conversation_id") or "").strip()
    if not conversation_id:
        return prepared
    con = _dependency(deps, "connect")(db_path)
    try:
        history = _dependency(deps, "load_conversation_history")(con, conversation_id)
        if not history.get("messages") and prepared.get("conversation_bootstrap"):
            _bootstrap_conversation(
                con,
                conversation_id=conversation_id,
                messages=prepared["conversation_bootstrap"],
                question=prepared["question"],
                deps=deps,
            )
            history = _dependency(deps, "load_conversation_history")(
                con, conversation_id
            )
        _maybe_compact_conversation(
            con,
            history=history,
            conversation_id=conversation_id,
            question=prepared["question"],
            deps=deps,
        )
        history = _dependency(deps, "load_conversation_history")(con, conversation_id)
    finally:
        con.close()
    language = _conversation_language(
        prepared["question"], history.get("preferred_language")
    )
    prepared["conversation_id"] = conversation_id
    prepared["message_id"] = str(prepared.get("message_id") or "").strip() or _new_id(
        "msg_"
    )
    prepared["answer_language"] = language
    provider_history = _provider_history_with_checkpoint(history)
    checkpoint = history.get("checkpoint") or {}
    prepared["provider_history"] = provider_history
    prepared["conversation_context"] = {
        "conversation_id": conversation_id,
        "checkpoint_hash": checkpoint.get("checkpoint_hash"),
        "checkpoint_through_sequence": checkpoint.get("through_sequence", 0),
        "provider_history_item_count": len(provider_history),
        "provider_history_hash": hashlib.sha256(
            canonical_json({"provider_history": provider_history})
        ).hexdigest(),
    }
    return prepared


def _bootstrap_conversation(con, *, conversation_id, messages, question, deps):
    preferred_language = _bootstrap_language(messages)
    preferred_language = _conversation_language(question, preferred_language)
    created_at = _now_iso()
    stored_messages = []
    for index, message in enumerate(messages):
        role = message.get("role")
        text = str(message.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        content_type = "input_text" if role == "user" else "output_text"
        stored_messages.append(
            {
                "message_id": f"bootstrap_{index:04d}",
                "created_at": created_at,
                "display": {
                    "role": role,
                    "text": text,
                    "source": "local_display_bootstrap",
                },
                "provider_items": [
                    {
                        "type": "message",
                        "role": role,
                        "content": [{"type": content_type, "text": text}],
                    }
                ],
            }
        )
    if not stored_messages:
        return
    _dependency(deps, "append_conversation_turn")(
        con,
        conversation_id=conversation_id,
        messages=stored_messages,
        preferred_language=preferred_language,
    )


def _bootstrap_language(messages):
    for message in reversed(messages):
        text = str(message.get("text") or "")
        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return "zh"
    return "en"


def _maybe_compact_conversation(con, *, history, conversation_id, question, deps):
    if not history.get("messages"):
        return
    projected_items = _provider_history_with_checkpoint(history)
    projected_items.append(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": question}],
        }
    )
    config = _runtime_config(deps)
    context_window_tokens = config.get("context_window_tokens", 1000000)
    threshold_ratio = config.get("conversation_compaction_ratio", 0.8)
    if not should_compact(
        projected_items,
        context_window_tokens=context_window_tokens,
        threshold_ratio=threshold_ratio,
    ):
        return
    language = history.get("preferred_language") or _conversation_language(
        question, None
    )
    checkpoint = build_checkpoint(
        messages=history["messages"],
        preferred_language=language,
        created_at=_now_iso(),
    )
    save_checkpoint = _dependency(deps, "save_conversation_checkpoint")
    save_checkpoint(
        con,
        conversation_id=conversation_id,
        through_sequence=checkpoint["through_sequence"],
        checkpoint=checkpoint,
    )


def _conversation_language(question, preferred_language):
    normalized = str(question or "").strip()
    lowered = normalized.lower()
    if any(phrase in lowered for phrase in _ENGLISH_LANGUAGE_REQUESTS):
        return "en"
    if any(phrase in lowered for phrase in _CHINESE_LANGUAGE_REQUESTS):
        return "zh"
    if any("\u4e00" <= char <= "\u9fff" for char in normalized):
        return "zh"
    if preferred_language in {"en", "zh"}:
        return preferred_language
    return "en"


def _provider_history_with_checkpoint(history):
    items = []
    checkpoint = history.get("checkpoint")
    if isinstance(checkpoint, dict):
        payload = checkpoint.get("payload")
        if isinstance(payload, dict):
            items.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Conversation checkpoint: "
                            + canonical_json(payload).decode("utf-8"),
                        }
                    ],
                }
            )
    items.extend(history.get("provider_items") or [])
    return items


def _persist_conversation(request, narration, answer_text, trace, deps, db_path):
    conversation_id = request.get("conversation_id")
    if not conversation_id:
        return
    current_user_item = narration.get("current_user_item")
    if not isinstance(current_user_item, dict):
        current_user_item = {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": request["question"]},
                {
                    "type": "input_text",
                    "text": "Answer language: "
                    + (
                        "Chinese"
                        if request.get("answer_language") == "zh"
                        else "English"
                    ),
                },
            ],
        }
    user_items = [current_user_item]
    assistant_items = list(narration.get("generated_provider_items") or [])
    if trace["generation_status"] == "answer_unavailable":
        assistant_items = [
            item for item in assistant_items if item.get("type") != "message"
        ]
    elif not any(
        item.get("type") == "message" and item.get("role") == "assistant"
        for item in assistant_items
    ):
        assistant_items = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": answer_text}],
            }
        ]
    created_at = trace["generated_time"]
    con = _dependency(deps, "connect")(db_path)
    try:
        append_turn = _dependency(deps, "append_conversation_turn")
        append_turn(
            con,
            conversation_id=conversation_id,
            preferred_language=request.get("answer_language") or "en",
            messages=[
                {
                    "message_id": trace["message_id"],
                    "created_at": created_at,
                    "display": {"role": "user", "text": request["question"]},
                    "provider_items": user_items,
                },
                {
                    "message_id": f"assistant_{trace['message_id']}",
                    "created_at": created_at,
                    "display": {"role": "assistant", "text": answer_text},
                    "provider_items": assistant_items,
                },
            ],
        )
    finally:
        con.close()


class _StageRecorder:
    def __init__(self, request_id, started_at):
        self._request_id = request_id
        self._started_at = started_at
        self._recorded = set()

    def record(self, stage):
        if stage in self._recorded:
            return
        self._recorded.add(stage)
        STREAM_LOGGER.info(
            "market assistant stage stage=%s request_id=%s elapsed_seconds=%.2f",
            stage,
            self._request_id,
            monotonic() - self._started_at,
        )


async def answer_question(request, *, dependencies, event_sink=None):
    deps = dependencies
    db_path = _dependency(deps, "db_path")
    request = _prepare_conversation_request(request, deps, db_path)
    request_id = _request_id(deps)
    request_started_at = monotonic()
    recorder = _StageRecorder(request_id, request_started_at)
    resolution = _resolve_request_context(request, deps, db_path)
    recorder.record("resolution_completed")
    await _emit(
        event_sink,
        {
            "type": "resolution",
            "resolution": resolution["resolution"],
            "request_id": request_id,
        },
    )
    result = await _answer_hybrid(
        request,
        resolution,
        deps,
        event_sink,
        recorder=recorder,
        request_id=request_id,
    )
    recorder.record("request_completed")
    return result


class _AnswerDeltaSink:
    def __init__(self, event_sink, recorder=None):
        self._event_sink = event_sink
        self._recorder = recorder

    async def send(self, event):
        self._record_stage(event)
        if event.get("type") == "output_delta":
            event = {"type": "answer_delta", "delta": event.get("delta")}
        await _emit(self._event_sink, event)

    def _record_stage(self, event):
        if self._recorder is None:
            return
        event_type = event.get("type")
        if event_type == "initial_tools_completed":
            self._recorder.record("initial_tools_completed")
        elif event_type == "model_turn_started":
            self._recorder.record("narration_request_started")
            self._recorder.record("react_round_started")
        elif event_type == "optional_round_completed":
            self._recorder.record("react_round_completed")
        elif event_type == "reasoning_started":
            self._recorder.record("first_reasoning_delta")
        elif event_type == "output_delta":
            self._recorder.record("first_output_text_delta")
            delta = event.get("delta")
            if isinstance(delta, str) and any(not char.isspace() for char in delta):
                self._recorder.record("first_user_visible_delta")


async def _answer_hybrid(
    request, resolution, deps, event_sink=None, recorder=None, request_id=None
):
    started_at = monotonic()
    await _emit(event_sink, {"type": "status", "status": "thinking"})
    route = _route_for_request(request, deps)
    if recorder is not None:
        recorder.record("route_selected")
    narration = await run_hybrid_narration(
        request,
        route=route,
        resolution=resolution,
        dependencies=deps,
        event_sink=_AnswerDeltaSink(event_sink, recorder=recorder),
    )
    if recorder is not None:
        recorder.record("narration_completed")
    outcome, answer_text = _narration_outcome(narration)
    LOGGER.info(
        "market assistant narration outcome outcome=%s generation_status=%s answer_length=%d",
        outcome,
        narration["generation_status"],
        len(answer_text),
    )
    frozen_artifacts = deepcopy(narration["artifacts"])
    claim_audit = None
    validation_report = None
    validation_error_codes = []
    audit_seconds = None
    attempts = {"narration": 1, "audit": 0}
    if outcome == "answered":
        await _emit(event_sink, {"type": "status", "status": "validating"})
        (
            validation_status,
            generation_status,
            claim_audit,
            validation_report,
            validation_error_codes,
            audit_seconds,
        ) = await _run_claim_audit(narration, frozen_artifacts, deps)
        if validation_status != "disabled":
            attempts["audit"] = 1
            if recorder is not None:
                recorder.record("audit_completed")
        await _emit_validation(event_sink, validation_status, validation_error_codes)
    else:
        generation_status = "answer_unavailable"
        answer_text = ""
        await _emit(event_sink, {"type": "answer_failed"})
    generated_at = _now_iso()
    trace = _build_hybrid_trace(
        request=request,
        resolution=resolution,
        route=route,
        narration=narration,
        generation_status=generation_status,
        attempts=attempts,
        validation_error_codes=validation_error_codes,
        claim_audit=claim_audit,
        validation_report=validation_report,
        audit_seconds=audit_seconds,
        answer_text=answer_text,
        generated_at=generated_at,
        started_at=started_at,
        runtime_config=_runtime_config(deps),
    )
    _persist_bundle(
        deps, _dependency(deps, "db_path"), list(narration["artifacts"].values()), trace
    )
    _persist_conversation(
        request,
        narration,
        answer_text,
        trace,
        deps,
        _dependency(deps, "db_path"),
    )
    await _emit(
        event_sink,
        {
            "type": "complete",
            "resolution": resolution["resolution"],
            "generation_status": generation_status,
            "answer_trace_id": trace["answer_trace_id"],
            "citations": [],
            "request_id": request_id or _request_id(deps),
        },
    )
    return {
        "resolution": resolution["resolution"],
        "answer_text": answer_text,
        "citations": [],
        "generation_status": generation_status,
        "answer_trace_id": trace["answer_trace_id"],
    }


async def _run_claim_audit(narration, frozen_artifacts, deps):
    if not _runtime_config(deps).get("claim_validation_enabled", True):
        return (
            "disabled",
            "narration_validation_disabled",
            None,
            None,
            [],
            None,
        )
    artifact_projection = _audit_artifact_projection(frozen_artifacts)
    audit_started_at = monotonic()
    try:
        audit_payload = await _bounded_llm_call(
            deps,
            "claim_audit_llm",
            timeout=_audit_timeout_seconds(deps),
            answer_text=narration["answer_text"],
            explanation_view=narration["view"],
            artifact_projection=artifact_projection,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.warning("market assistant claim audit failed", exc_info=True)
        return (
            "unavailable",
            "narration_validation_unavailable",
            None,
            None,
            [],
            round(monotonic() - audit_started_at, 4),
        )
    audit_seconds = round(monotonic() - audit_started_at, 4)
    try:
        validate_claim_audit(
            audit_payload,
            answer_text=narration["answer_text"],
            artifacts=frozen_artifacts,
        )
    except AuditValidationError as exc:
        report = build_audit_validation_report(exc.errors)
        error_codes = [error["code"] for error in report["errors"]]
        return (
            "failed",
            "narration_validation_failed",
            audit_payload,
            report,
            error_codes,
            audit_seconds,
        )
    return (
        "passed",
        "narration_validated",
        audit_payload,
        {"valid": True, "error_count": 0, "errors": []},
        [],
        audit_seconds,
    )


def _route_for_request(request, deps):
    router = _optional_dependency(deps, "route_question") or route_question
    return router(
        request["question"], deep_analysis=bool(request.get("deep_analysis_requested"))
    )


def _narration_outcome(narration):
    if narration["generation_status"] == "answered":
        return "answered", narration["answer_text"]
    return "failed", ""


def _audit_timeout_seconds(deps):
    timeout = _optional_dependency(deps, "audit_timeout_seconds")
    if timeout is not None:
        return timeout
    return _runtime_config(deps).get("audit_timeout_seconds", AUDIT_TIMEOUT_SECONDS)


def _audit_artifact_projection(artifacts):
    return {
        artifact_id: {
            "artifact_id": artifact["artifact_id"],
            "artifact_kind": artifact["artifact_kind"],
            "primary_authority": artifact["primary_authority"],
            "market_setup_relation": artifact["market_setup_relation"],
            "object_index": artifact["object_index"],
        }
        for artifact_id, artifact in artifacts.items()
    }


def _request_controls(request):
    return {
        "mode": request.get("mode") or "current",
        "deep_analysis_requested": bool(request.get("deep_analysis_requested")),
        "deep_research_requested": bool(request.get("deep_research_requested")),
        "external_search_requested": bool(request.get("external_search_requested")),
    }


def _view_projection(view):
    return {
        "view_version": view.get("view_version"),
        "view_hash": hashlib.sha256(canonical_json(view)).hexdigest(),
    }


def _build_hybrid_trace(
    *,
    request,
    resolution,
    route,
    narration,
    generation_status,
    attempts,
    validation_error_codes,
    claim_audit,
    validation_report,
    audit_seconds,
    answer_text,
    generated_at,
    started_at,
    runtime_config,
):
    return {
        "answer_trace_id": _new_id("trc_"),
        "message_id": request.get("message_id") or _new_id("msg_"),
        "conversation_context": request.get("conversation_context"),
        "resolution": resolution["resolution"],
        "explanation_context_id": resolution["snapshot"]["context_id"],
        "request_controls": _request_controls(request),
        "route": route,
        "tool_trace": narration["tool_trace"],
        "budget": route["budget"],
        "explanation_view": _view_projection(narration["view"]),
        "knowledge_references": _artifact_ids_by_kind(
            narration["artifacts"], "knowledge_record"
        ),
        "snapshot_artifact_ids": _artifact_ids_by_kind(
            narration["artifacts"], "explanation_snapshot"
        ),
        "exploration_result_ids": _artifact_ids_by_kind(
            narration["artifacts"], "exploration_result"
        ),
        "research_result_ids": _artifact_ids_by_kind(
            narration["artifacts"], "research_result"
        ),
        "plan": None,
        "structured_claims": None,
        "generation_status": generation_status,
        "narration_status": narration["generation_status"],
        "attempts": attempts,
        "validation_error_codes": sorted(validation_error_codes),
        "prompt": {
            "version": PROMPT_VERSION,
            "hash": _prompt_hash(request, route, resolution),
        },
        "model_configuration_fingerprint": _model_configuration_fingerprint(
            runtime_config
        ),
        "tool_schema_versions": TOOL_SCHEMA_VERSIONS,
        "answer_text": answer_text,
        "answer_text_hash": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
        "claim_audit": {
            "audit": claim_audit,
            "validation": validation_report,
        },
        "timings": {
            "narration": narration["timings"],
            "audit_seconds": audit_seconds,
            "total_seconds": round(monotonic() - started_at, 4),
        },
        "generated_time": generated_at,
    }


async def _emit(event_sink, event):
    if event_sink is not None:
        await event_sink.send(event)


async def _emit_validation(event_sink, status, error_codes):
    await _emit(
        event_sink,
        {"type": "validation", "status": status, "error_codes": sorted(error_codes)},
    )


class _QueueEventSink:
    def __init__(self, queue):
        self._queue = queue

    async def send(self, event):
        await self._queue.put(event)


async def stream_answer_question(request, *, dependencies):
    queue = asyncio.Queue(maxsize=100)
    sink = _QueueEventSink(queue)
    worker = asyncio.create_task(_stream_worker(request, dependencies, sink))
    try:
        while True:
            event = await queue.get()
            yield event
            if event["type"] in ("complete", "error"):
                break
    finally:
        if not worker.done():
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass


async def _stream_worker(request, dependencies, sink):
    try:
        await answer_question(request, dependencies=dependencies, event_sink=sink)
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.warning("market assistant stream failed", exc_info=True)
        await sink.send(
            {"type": "error", "message": "market assistant service is unavailable"}
        )


def _resolve_request_context(request, deps, db_path):
    mode = request.get("mode") or "current"
    if mode == "current":
        return _dependency(deps, "resolve_current_explanation")(
            db_path,
            previous_context_id=request.get("previous_context_id"),
            resolved_at=_now_iso(),
        )
    if mode == "historical":
        context_id = request.get("context_id")
        if not context_id:
            raise ValueError("historical context id is required")
        con = _dependency(deps, "connect")(db_path)
        try:
            snapshot = _dependency(deps, "load_snapshot")(con, context_id)
        finally:
            con.close()
        if snapshot is None:
            raise ValueError("historical context is not available")
        return {
            "resolution": {
                "mode": "historical",
                "resolved_at": _now_iso(),
                "previous_context_id": request.get("previous_context_id"),
                "current_context_id": context_id,
                "context_changed": (request.get("previous_context_id") != context_id),
                "evidence_through": snapshot.get("evidence_through"),
            },
            "delta": {"results_changed": False, "changes": []},
            "snapshot": snapshot,
        }
    raise ValueError("request mode is unknown")


async def _bounded_llm_call(deps, dependency_name, *, timeout=None, **kwargs):
    if timeout is None:
        timeout = _dependency(
            deps, "llm_attempt_timeout", default=LLM_ATTEMPT_TIMEOUT_SECONDS
        )
    task = asyncio.create_task(_dependency(deps, dependency_name)(**kwargs))
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
    except asyncio.CancelledError:
        task.cancel()
        task.add_done_callback(_consume_llm_task)
        raise
    if task not in done:
        task.cancel()
        task.add_done_callback(_consume_llm_task)
        raise TimeoutError("market assistant LLM attempt timed out")
    return task.result()


def _consume_llm_task(task):
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        LOGGER.warning("market assistant timed-out LLM task failed", exc_info=True)


def _persist_bundle(deps, db_path, artifacts, trace):
    explanation_context_id = trace["explanation_context_id"]
    durable_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["artifact_kind"] != "explanation_snapshot"
        or artifact["artifact_id"] != explanation_context_id
    ]
    con = _dependency(deps, "connect")(db_path)
    try:
        _dependency(deps, "save_bundle")(
            con, artifacts=durable_artifacts, answer_trace=trace
        )
    except Exception as exc:
        raise ValueError("answer trace persistence failed") from exc
    finally:
        con.close()


def _artifact_ids_by_kind(artifacts, kind):
    return sorted(
        artifact["artifact_id"]
        for artifact in artifacts.values()
        if artifact["artifact_kind"] == kind
    )


def _prompt_hash(request, plan, resolution):
    projection = {
        "question": request.get("question"),
        "plan": plan,
        "context_summary": resolution["resolution"],
    }
    return hashlib.sha256(canonical_json(projection)).hexdigest()


def _model_configuration_fingerprint(config):
    return {
        "provider": config.get("provider"),
        "model": config.get("model"),
        "structured_output_mode": config.get("structured_output_mode"),
        "claim_validation_enabled": config.get("claim_validation_enabled", True),
        "research_model": config.get("research_model"),
        "reasoning_effort": config.get("reasoning_effort", "low"),
        "tool_schema_versions": TOOL_SCHEMA_VERSIONS,
        "assistant_policy_version": ASSISTANT_POLICY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "conversation_checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "conversation_context_window_size": config.get(
            "context_window_tokens", 1000000
        ),
        "conversation_compaction_ratio": config.get(
            "conversation_compaction_ratio", 0.8
        ),
    }
