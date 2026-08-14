import asyncio
import hashlib
import logging
import secrets
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from time import monotonic

from app.db.market_assistant import connect
from app.db.market_assistant import load_snapshot
from app.db.market_assistant import save_answer_bundle
from app.services import market_assistant_tool_runtime
from app.services.market_assistant_exploration import EXPLORATION_SCHEMA_VERSION
from app.services.market_assistant_react import run_hybrid_narration
from app.services.market_assistant_tool_runtime import ARTIFACT_SCHEMA_VERSION
from app.services.market_assistant_tool_runtime import acquire_registered_artifacts
from app.services.market_assistant_tool_runtime import snapshot_artifact
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_answers import DraftValidationError
from app.tools.market_assistant_answers import build_validation_report
from app.tools.market_assistant_answers import collect_citations
from app.tools.market_assistant_answers import detect_answer_language
from app.tools.market_assistant_answers import render_answer
from app.tools.market_assistant_answers import render_fallback
from app.tools.market_assistant_answers import render_unvalidated_debug_answer
from app.tools.market_assistant_answers import validate_answer_draft
from app.tools.market_assistant_answers import validate_answer_draft_schema
from app.tools.market_assistant_claim_audit import AuditValidationError
from app.tools.market_assistant_claim_audit import build_audit_validation_report
from app.tools.market_assistant_claim_audit import validate_claim_audit
from app.tools.market_assistant_plans import deterministic_plan
from app.tools.market_assistant_research import RESEARCH_SCHEMA_VERSION
from app.tools.market_assistant_routes import route_question
from app.tools.market_setup_explanation_snapshot import canonical_json

PROMPT_VERSION = "market_assistant_prompt_v1"
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

_DROPPED_EVIDENCE_FUNCTIONS = frozenset({"display_only", "watch_only"})

_KEPT_EVIDENCE_FIELDS = (
    "fact_id",
    "label",
    "accepted_values",
    "classifications",
    "data_status",
    "participation",
    "decision_result",
    "finding",
    "role",
)

_DELETED_LAYER_RESULT_FIELDS = {
    "macro_regime": frozenset({"source_periods"}),
    "market_confirmation": frozenset({"source_periods", "evidence"}),
    "market_setup": frozenset(),
    "portfolio_posture": frozenset(),
}

_FALLBACK_ARTIFACT_KINDS = {
    "decision_explanation": frozenset({"explanation_snapshot"}),
    "counterfactual": frozenset({"explanation_snapshot"}),
    "historical_snapshot": frozenset({"explanation_snapshot"}),
    "snapshot_comparison": frozenset({"explanation_snapshot"}),
    "current_evidence": frozenset({"explanation_snapshot"}),
    "method": frozenset({"explanation_snapshot"}),
    "definition": frozenset({"knowledge_record"}),
    "source": frozenset({"knowledge_record"}),
    "governance": frozenset({"knowledge_record"}),
    "local_current": frozenset({"exploration_result"}),
    "local_history": frozenset({"exploration_result"}),
    "local_comparison": frozenset({"exploration_result"}),
    "release_history": frozenset({"exploration_result"}),
    "external_research": frozenset({"explanation_snapshot"}),
    "illustration": frozenset(),
    "unsupported": frozenset(),
}

_DEPENDENCY_DEFAULTS = {
    "resolve_current_explanation": resolve_current_explanation,
    "connect": connect,
    "load_snapshot": load_snapshot,
    "deterministic_plan": deterministic_plan,
    "save_bundle": save_answer_bundle,
}

_FALLBACK_INTENT_BY_ROUTE = {
    "current_setup_overview": "decision_explanation",
    "why_macro_regime": "decision_explanation",
    "why_market_confirmation": "decision_explanation",
    "why_portfolio_posture": "decision_explanation",
    "indicator_confirmation": "decision_explanation",
    "indicator_definition": "definition",
    "indicator_method": "method",
    "react": "decision_explanation",
}


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
    if _optional_dependency(deps, "client") is None:
        result = await _answer_legacy(
            request, resolution, deps, event_sink, request_id=request_id
        )
    else:
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
    frozen_artifacts = deepcopy(narration["artifacts"])
    claim_audit = None
    validation_report = None
    validation_error_codes = []
    audit_seconds = None
    attempts = {"narration": 1, "audit": 0}
    if outcome == "fallback":
        generation_status = "deterministic_fallback"
        answer_text = render_fallback(
            plan=_fallback_plan(route),
            artifacts=_fallback_artifacts(resolution, frozen_artifacts),
            notices=[],
        )
        await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
        await _emit_validation(event_sink, "fallback", [])
    elif outcome == "interrupted":
        generation_status = "narration_interrupted"
        await _emit_validation(event_sink, "interrupted", [])
    else:
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


async def _answer_legacy(request, resolution, deps, event_sink=None, request_id=None):
    db_path = _dependency(deps, "db_path")
    await _emit(event_sink, {"type": "status", "status": "thinking"})
    plan, plan_attempts = await _plan_or_fallback(request, resolution, deps)
    artifacts, unsupported_operation_id = await _acquire_registered_artifacts(
        request, plan, resolution, deps
    )
    frozen_artifacts = deepcopy(artifacts)
    stream_state = {"streamed_delta": False}
    draft = None
    if unsupported_operation_id is None:
        draft = await _synthesize(
            request,
            plan,
            resolution,
            frozen_artifacts,
            deps,
            event_sink,
            stream_state,
        )
    await _emit(event_sink, {"type": "status", "status": "validating"})
    (
        validated,
        generation_status,
        attempts,
        validation_error_codes,
    ) = await _validate_or_repair_once(
        request, plan, resolution, frozen_artifacts, draft, deps, event_sink
    )
    attempts["plan"] = plan_attempts
    answer_language = detect_answer_language(request.get("question") or "")
    if generation_status == "unvalidated_debug":
        answer_text = validated.get("answer_text") or ""
        if not answer_text:
            answer_text = render_unvalidated_debug_answer(
                validated, language=answer_language
            )
        if not answer_text.strip():
            generation_status = "fallback"
            answer_text = render_fallback(
                plan=plan, artifacts=frozen_artifacts, notices=[]
            )
            validation_error_codes = sorted(
                set(validation_error_codes) | {"DISPLAY_FILTERED"}
            )
        citations = []
        if generation_status == "fallback":
            await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
            await _emit_validation(event_sink, "fallback", validation_error_codes)
        else:
            if not _body_streamed(event_sink, stream_state):
                await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
            await _emit_validation(event_sink, "disabled", [])
    elif generation_status == "validation_failed_visible":
        if validated is None:
            answer_text = render_fallback(
                plan=plan, artifacts=frozen_artifacts, notices=[]
            )
            citations = []
            await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
        else:
            answer_text = validated.get("answer_text") or render_answer(
                validated, frozen_artifacts, [], language=answer_language
            )
            citations = collect_citations(validated, frozen_artifacts)
            if not _body_streamed(event_sink, stream_state):
                await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
        await _emit_validation(event_sink, "failed", validation_error_codes)
    elif validated is not None:
        answer_text = render_answer(
            validated,
            frozen_artifacts,
            [],
            language=answer_language,
        )
        citations = collect_citations(validated, frozen_artifacts)
        if generation_status == "validated_first_pass":
            if not _body_streamed(event_sink, stream_state):
                await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
            await _emit_validation(event_sink, "passed", [])
        else:
            await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
            await _emit_validation(event_sink, "repaired_and_passed", [])
    else:
        answer_text = render_fallback(plan=plan, artifacts=frozen_artifacts, notices=[])
        citations = []
        await _emit(event_sink, {"type": "answer_replace", "text": answer_text})
        await _emit_validation(event_sink, "fallback", validation_error_codes)
    generated_at = _now_iso()
    referenced = _referenced_artifacts(plan, validated, frozen_artifacts)
    referenced_map = {artifact["artifact_id"]: artifact for artifact in referenced}
    trace = build_answer_trace(
        request=request,
        resolution=resolution,
        plan=plan,
        artifacts=referenced_map,
        draft=validated,
        generation_status=generation_status,
        attempts=attempts,
        validation_error_codes=validation_error_codes,
        answer_text=answer_text,
        generated_at=generated_at,
        runtime_config=_runtime_config(deps),
    )
    _persist_bundle(deps, db_path, referenced, trace)
    await _emit(
        event_sink,
        {
            "type": "complete",
            "resolution": resolution["resolution"],
            "generation_status": generation_status,
            "answer_trace_id": trace["answer_trace_id"],
            "citations": citations,
            "request_id": request_id or _request_id(deps),
        },
    )
    return {
        "resolution": resolution["resolution"],
        "answer_text": answer_text,
        "citations": citations,
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
    status = narration["generation_status"]
    if status == "answered":
        return "answered", narration["answer_text"]
    if status == "narration_interrupted":
        return "interrupted", narration["answer_text"]
    if status == "budget_exhausted" and narration["answer_text"].strip():
        return "interrupted", narration["answer_text"]
    return "fallback", ""


def _fallback_plan(route):
    intent = _FALLBACK_INTENT_BY_ROUTE.get(route["route_id"], "unsupported")
    return {"intent": intent}


def _fallback_artifacts(resolution, artifacts):
    snapshot = snapshot_artifact(resolution["snapshot"])
    return {snapshot["artifact_id"]: snapshot, **artifacts}


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
        "message_id": _new_id("msg_"),
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


def _context_summary(request, resolution):
    envelope = resolution["resolution"]
    return {
        "question": request.get("question"),
        "mode": envelope["mode"],
        "current_context_id": envelope["current_context_id"],
        "previous_context_id": envelope["previous_context_id"],
        "resolved_at": envelope["resolved_at"],
        "external_search_requested": bool(request.get("external_search_requested")),
        "deep_analysis_requested": bool(request.get("deep_analysis_requested")),
    }


async def _plan_or_fallback(request, resolution, deps):
    question = request["question"]
    context_summary = _context_summary(request, resolution)
    attempts = {"plan": 0}
    try:
        plan = await _bounded_llm_call(
            deps,
            "plan_llm",
            question=question,
            context_summary=context_summary,
        )
        attempts["plan"] += 1
        return plan, attempts["plan"]
    except ValueError as exc:
        attempts["plan"] += 1
        report = _plan_validation_report(exc)
    except Exception:
        LOGGER.warning("market assistant plan generation failed", exc_info=True)
        attempts["plan"] += 1
        return _dependency(deps, "deterministic_plan")(question), attempts["plan"]
    try:
        plan = await _bounded_llm_call(
            deps,
            "plan_llm",
            question=question,
            context_summary={**context_summary, "plan_validation_report": report},
        )
        attempts["plan"] += 1
        return plan, attempts["plan"]
    except Exception:
        LOGGER.warning("market assistant plan repair failed", exc_info=True)
        return _dependency(deps, "deterministic_plan")(question), attempts["plan"]


def _plan_validation_report(exc):
    return {
        "valid": False,
        "error_count": 1,
        "errors": [{"code": "PLAN_INVALID", "message": str(exc)}],
    }


async def _acquire_registered_artifacts(request, plan, resolution, deps):
    return await acquire_registered_artifacts(
        plan.get("operations") or [],
        request=request,
        resolution=resolution,
        dependencies=deps,
    )


async def _synthesize(
    request, plan, resolution, artifacts, deps, event_sink=None, stream_state=None
):
    kwargs = {
        "question": request["question"],
        "plan": plan,
        "context_summary": _context_summary(request, resolution),
        "artifacts": _llm_artifact_projection(artifacts, plan),
    }
    if event_sink is not None:
        kwargs["stream_observer"] = _synthesis_stream_observer(event_sink, stream_state)
    try:
        return await _bounded_llm_call(deps, "synthesize_llm", **kwargs)
    except Exception:
        LOGGER.warning("market assistant synthesis failed", exc_info=True)
        return None


def _synthesis_stream_observer(event_sink, stream_state):
    async def observer(event):
        if event["type"] == "reasoning_started":
            await event_sink.send({"type": "status", "status": "thinking"})
        elif event["type"] == "answer_delta":
            stream_state["streamed_delta"] = True
            await event_sink.send(event)

    return observer


def _body_streamed(event_sink, stream_state):
    if event_sink is None:
        return True
    return stream_state["streamed_delta"]


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


def _llm_artifact_projection(artifacts, plan):
    return {
        artifact_id: {
            "artifact_id": artifact["artifact_id"],
            "artifact_kind": artifact["artifact_kind"],
            "primary_authority": artifact["primary_authority"],
            "market_setup_relation": artifact["market_setup_relation"],
            "object_index": _projected_object_index(artifact["object_index"], plan),
        }
        for artifact_id, artifact in artifacts.items()
    }


def _projected_object_index(object_index, plan):
    if plan.get("intent") != "decision_explanation":
        return list(object_index)
    kept_counterfactual_ids = _kept_setup_counterfactual_ids(object_index)
    return [
        projected
        for item in object_index
        if _keeps_artifact_object(item, kept_counterfactual_ids)
        and (projected := _project_artifact_object_for_llm(item, plan)) is not None
    ]


def _keeps_artifact_object(item, kept_counterfactual_ids):
    return (
        not _is_setup_counterfactual(item)
        or item.get("object_id") in kept_counterfactual_ids
    )


def _is_setup_counterfactual(item):
    return (
        item.get("object_type") == "market_setup"
        and item.get("object_id") != "market_setup"
    )


def _kept_setup_counterfactual_ids(object_index):
    kept = []
    for item in object_index:
        if len(kept) == 2:
            break
        if _is_setup_counterfactual(item):
            kept.append(item["object_id"])
    return kept


def _project_artifact_object_for_llm(item, plan):
    if plan.get("intent") != "decision_explanation":
        return item
    object_type = item.get("object_type")
    if object_type == "method_contract":
        return None
    if object_type == "confirmation_test":
        return None
    if object_type == "evidence_fact":
        return _project_evidence_fact_for_llm(item)
    if object_type == "market_setup_result":
        return _project_layer_result_for_llm(item)
    return item


def _project_evidence_fact_for_llm(item):
    role = (item.get("payload") or {}).get("role") or {}
    if role.get("function") in _DROPPED_EVIDENCE_FUNCTIONS:
        return None
    payload = item["payload"]
    projected_payload = {
        key: payload[key] for key in _KEPT_EVIDENCE_FIELDS if key in payload
    }
    provenance = payload.get("provenance")
    source_period = (provenance or {}).get("source_period")
    if isinstance(provenance, dict) and source_period is not None:
        projected_payload["provenance"] = {"source_period": source_period}
    return {**item, "payload": projected_payload}


def _project_layer_result_for_llm(item):
    deleted_fields = _DELETED_LAYER_RESULT_FIELDS.get(item["object_id"], frozenset())
    projected_payload = {
        key: value
        for key, value in item["payload"].items()
        if key not in deleted_fields
    }
    return {**item, "payload": projected_payload}


async def _validate_or_repair_once(
    request, plan, resolution, artifacts, draft, deps, event_sink=None
):
    attempts = {"draft": 0, "repair": 0}
    validation_error_codes = []
    answer_language = detect_answer_language(request.get("question") or "")
    if draft is None:
        return None, "fallback", attempts, validation_error_codes
    attempts["draft"] += 1
    claim_validation_enabled = _runtime_config(deps).get(
        "claim_validation_enabled", True
    )
    if not claim_validation_enabled:
        try:
            normalized = validate_answer_draft_schema(draft)
        except DraftValidationError as exc:
            validation_error_codes = sorted({error["code"] for error in exc.errors})
            return None, "fallback", attempts, validation_error_codes
        return normalized, "unvalidated_debug", attempts, validation_error_codes
    initial_draft = None
    try:
        validated = validate_answer_draft(draft, artifacts, language=answer_language)
        return validated, "validated_first_pass", attempts, validation_error_codes
    except DraftValidationError as exc:
        validation_error_codes = sorted({error["code"] for error in exc.errors})
        report = build_validation_report(exc.errors)
        initial_draft = _normalized_draft_or_none(draft)
        await _emit_validation(event_sink, "failed_initial", validation_error_codes)
    attempts["repair"] += 1
    await _emit(event_sink, {"type": "status", "status": "repairing"})
    try:
        repaired = await _bounded_llm_call(
            deps,
            "repair_llm",
            question=request["question"],
            plan=plan,
            context_summary=_context_summary(request, resolution),
            artifacts=_llm_artifact_projection(artifacts, plan),
            draft=draft,
            validation_report=report,
        )
    except Exception:
        LOGGER.warning("market assistant answer repair failed", exc_info=True)
        return (
            initial_draft,
            "validation_failed_visible",
            attempts,
            validation_error_codes,
        )
    if repaired is None:
        return (
            initial_draft,
            "validation_failed_visible",
            attempts,
            validation_error_codes,
        )
    attempts["draft"] += 1
    try:
        validated = validate_answer_draft(repaired, artifacts, language=answer_language)
        return validated, "validated_after_repair", attempts, validation_error_codes
    except DraftValidationError as exc:
        validation_error_codes = sorted({error["code"] for error in exc.errors})
        return (
            initial_draft,
            "validation_failed_visible",
            attempts,
            validation_error_codes,
        )


def _normalized_draft_or_none(draft):
    try:
        return validate_answer_draft_schema(draft)
    except DraftValidationError:
        return None


def _referenced_artifacts(plan, validated, artifacts):
    if validated is not None:
        referenced_ids = set()
        for section in validated.get("sections") or []:
            for claim in section.get("claims") or []:
                _collect_claim_artifact_ids(claim, referenced_ids)
        return [
            artifact
            for artifact_id, artifact in artifacts.items()
            if artifact_id in referenced_ids
        ]
    kinds = _FALLBACK_ARTIFACT_KINDS.get(plan.get("intent")) or frozenset()
    return [
        artifact
        for artifact in artifacts.values()
        if artifact["artifact_kind"] in kinds
    ]


def _collect_claim_artifact_ids(claim, referenced_ids):
    for ref in claim.get("refs") or []:
        artifact_id = ref.get("artifact_id")
        if artifact_id:
            referenced_ids.add(artifact_id)
    for binding in (claim.get("bindings") or {}).values():
        if not isinstance(binding, dict):
            continue
        if binding.get("artifact_id"):
            referenced_ids.add(binding["artifact_id"])
        source = binding.get("source")
        if isinstance(source, dict) and source.get("artifact_id"):
            referenced_ids.add(source["artifact_id"])


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


def build_answer_trace(
    *,
    request,
    resolution,
    plan,
    artifacts,
    draft,
    generation_status,
    attempts,
    validation_error_codes,
    answer_text,
    generated_at,
    runtime_config,
):
    return {
        "answer_trace_id": _new_id("trc_"),
        "message_id": _new_id("msg_"),
        "resolution": resolution["resolution"],
        "explanation_context_id": resolution["snapshot"]["context_id"],
        "knowledge_references": _artifact_ids_by_kind(artifacts, "knowledge_record"),
        "snapshot_artifact_ids": _artifact_ids_by_kind(
            artifacts, "explanation_snapshot"
        ),
        "exploration_result_ids": _artifact_ids_by_kind(
            artifacts, "exploration_result"
        ),
        "research_result_ids": _artifact_ids_by_kind(artifacts, "research_result"),
        "plan": plan,
        "structured_claims": draft.get("sections") if draft is not None else None,
        "generation_status": generation_status,
        "attempts": attempts,
        "validation_error_codes": sorted(validation_error_codes),
        "prompt": {
            "version": PROMPT_VERSION,
            "hash": _prompt_hash(request, plan, resolution),
        },
        "model_configuration_fingerprint": _model_configuration_fingerprint(
            runtime_config
        ),
        "tool_schema_versions": TOOL_SCHEMA_VERSIONS,
        "answer_text": answer_text,
        "answer_text_hash": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
        "generated_time": generated_at,
    }


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
    }
