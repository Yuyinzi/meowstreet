import hashlib
import secrets
from copy import deepcopy
from datetime import datetime
from datetime import timezone

from app.db.market_assistant import connect
from app.db.market_assistant import load_snapshot
from app.db.market_assistant import save_answer_bundle
from app.services.market_assistant_exploration import EXPLORATION_SCHEMA_VERSION
from app.services.market_assistant_exploration import execute_exploration
from app.services.market_assistant_research import acquire_research
from app.services.market_assistant_research import build_research_provider
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_answers import DraftValidationError
from app.tools.market_assistant_answers import build_validation_report
from app.tools.market_assistant_answers import collect_citations
from app.tools.market_assistant_answers import render_answer
from app.tools.market_assistant_answers import render_fallback
from app.tools.market_assistant_answers import validate_answer_draft
from app.tools.market_assistant_artifacts import build_object_index
from app.tools.market_assistant_artifacts import validate_artifact
from app.tools.market_assistant_knowledge import load_knowledge_catalog
from app.tools.market_assistant_plans import deterministic_plan
from app.tools.market_assistant_research import RESEARCH_SCHEMA_VERSION
from app.tools.market_setup_explanation_snapshot import build_semantic_delta
from app.tools.market_setup_explanation_snapshot import canonical_json

PROMPT_VERSION = "market_assistant_prompt_v1"
ASSISTANT_POLICY_VERSION = "market_assistant_policy_v1"
ARTIFACT_SCHEMA_VERSION = "market_assistant_artifact_v1"

TOOL_SCHEMA_VERSIONS = {
    "artifact_envelope": ARTIFACT_SCHEMA_VERSION,
    "exploration": EXPLORATION_SCHEMA_VERSION,
    "research": RESEARCH_SCHEMA_VERSION,
}

_RESULT_LAYERS = (
    "macro_regime",
    "market_confirmation",
    "market_setup",
    "portfolio_posture",
)

_KNOWLEDGE_OBJECT_TYPE = {
    "get_indicator_definition": "indicator_definition",
    "get_indicator_method": "indicator_method",
    "get_indicator_source": "indicator_source",
}

_KNOWLEDGE_INDICATOR_ALIASES = {
    ("vix", "indicator_definition"): "vix_level",
    ("vix", "indicator_method"): "vix_level",
    ("vix", "indicator_source"): "vix_level",
    ("m2_money_stock", "indicator_definition"): "m2_liquidity",
    ("m2_money_stock", "indicator_method"): "m2_liquidity",
    ("m2_money_stock", "indicator_source"): "m2_liquidity",
    ("sp500_close", "indicator_definition"): "sp500_market_phase",
    ("sp500_close", "indicator_method"): "sp500_market_phase",
    ("sp500_close", "indicator_source"): "sp500_market_phase",
    ("ism_manufacturing_pmi", "indicator_source"): "ism_surveys",
    ("initial_claims_sa", "indicator_definition"): "jobless_claims",
    ("initial_claims_sa", "indicator_method"): "jobless_claims",
    ("initial_claims_sa", "indicator_source"): "jobless_claims",
    ("continuing_claims_sa", "indicator_definition"): "jobless_claims",
    ("continuing_claims_sa", "indicator_method"): "jobless_claims",
    ("continuing_claims_sa", "indicator_source"): "jobless_claims",
    ("credit_conditions", "indicator_definition"): "credit_conditions",
    ("credit_conditions", "indicator_method"): "credit_conditions",
    ("credit_conditions", "indicator_source"): "credit_conditions",
}

_EXPLORATION_QUERY_KIND = {
    "get_indicator_current": "indicator_current",
    "query_indicator_history": "indicator_history",
    "compare_indicator_periods": "period_comparison",
    "query_release_history": "release_history",
}

_RESEARCH_TIER = {
    "research_focused": "focused",
    "research_standard": "standard",
    "research_deep": "deep",
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
    "acquire_research": acquire_research,
    "build_research_provider": build_research_provider,
    "exploration": execute_exploration,
    "load_knowledge_catalog": load_knowledge_catalog,
    "save_bundle": save_answer_bundle,
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


async def answer_question(request, *, dependencies):
    deps = dependencies
    db_path = _dependency(deps, "db_path")
    resolution = _resolve_request_context(request, deps, db_path)
    plan, plan_attempts = await _plan_or_fallback(request, resolution, deps)
    artifacts, unsupported_operation_id = await _acquire_registered_artifacts(
        request, plan, resolution, deps
    )
    frozen_artifacts = deepcopy(artifacts)
    draft = None
    if unsupported_operation_id is None:
        draft = await _synthesize(request, plan, resolution, frozen_artifacts, deps)
    (
        validated,
        generation_status,
        attempts,
        validation_error_codes,
    ) = await _validate_or_repair_once(
        request, plan, resolution, frozen_artifacts, draft, deps
    )
    attempts["plan"] = plan_attempts
    if validated is not None:
        answer_text = render_answer(validated, frozen_artifacts, [])
        citations = collect_citations(validated, frozen_artifacts)
    else:
        answer_text = render_fallback(plan=plan, artifacts=frozen_artifacts, notices=[])
        citations = []
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
    return {
        "resolution": resolution["resolution"],
        "answer_text": answer_text,
        "citations": citations,
        "generation_status": generation_status,
        "answer_trace_id": trace["answer_trace_id"],
    }


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
    }


async def _plan_or_fallback(request, resolution, deps):
    question = request["question"]
    context_summary = _context_summary(request, resolution)
    attempts = {"plan": 0}
    try:
        plan = await _dependency(deps, "plan_llm")(
            question=question, context_summary=context_summary
        )
        attempts["plan"] += 1
        return plan, attempts["plan"]
    except ValueError as exc:
        attempts["plan"] += 1
        report = _plan_validation_report(exc)
    except Exception:
        attempts["plan"] += 1
        return _dependency(deps, "deterministic_plan")(question), attempts["plan"]
    try:
        plan = await _dependency(deps, "plan_llm")(
            question=question,
            context_summary={**context_summary, "plan_validation_report": report},
        )
        attempts["plan"] += 1
        return plan, attempts["plan"]
    except Exception:
        return _dependency(deps, "deterministic_plan")(question), attempts["plan"]


def _plan_validation_report(exc):
    return {
        "valid": False,
        "error_count": 1,
        "errors": [{"code": "PLAN_INVALID", "message": str(exc)}],
    }


async def _acquire_registered_artifacts(request, plan, resolution, deps):
    artifacts = {}
    unsupported_operation_id = None
    for operation in plan.get("operations") or []:
        operation_id = operation["operation_id"]
        if operation_id == "resolve_current_explanation":
            artifact = _snapshot_artifact(resolution["snapshot"])
        elif operation_id == "get_historical_snapshot":
            artifact = _historical_snapshot_artifact(operation, resolution, deps)
        elif operation_id == "get_snapshot_object":
            artifact = _snapshot_object_artifact(operation, resolution)
        elif operation_id == "get_counterfactuals":
            artifact = _counterfactuals_artifact(operation, resolution, deps)
        elif operation_id == "compare_snapshots":
            artifact = _compare_snapshots_artifact(operation, resolution, deps)
        elif operation_id in _KNOWLEDGE_OBJECT_TYPE:
            artifact = _knowledge_artifact(operation, deps)
        elif operation_id in _EXPLORATION_QUERY_KIND:
            artifact = _exploration_artifact(operation, deps)
        elif operation_id in _RESEARCH_TIER:
            artifact = await _research_artifact(request, operation, deps)
        else:
            unsupported_operation_id = operation_id
            break
        if artifact is None:
            unsupported_operation_id = operation_id
            break
        artifacts[artifact["artifact_id"]] = artifact
    if unsupported_operation_id is not None:
        snapshot_artifact = _snapshot_artifact(resolution["snapshot"])
        artifacts[snapshot_artifact["artifact_id"]] = snapshot_artifact
    return artifacts, unsupported_operation_id


def _load_snapshot_by_context_id(deps, context_id):
    con = _dependency(deps, "connect")(_dependency(deps, "db_path"))
    try:
        return _dependency(deps, "load_snapshot")(con, context_id)
    finally:
        con.close()


def _historical_snapshot_artifact(operation, resolution, deps):
    context_id = operation["parameters"]["context_id"]
    snapshot = resolution["snapshot"]
    if snapshot.get("context_id") != context_id:
        return None
    return _snapshot_artifact(snapshot)


def _snapshot_object_artifact(operation, resolution):
    object_type = operation["parameters"]["object_type"]
    object_id = operation["parameters"]["object_id"]
    snapshot = resolution["snapshot"]
    object_entry = _find_snapshot_object(snapshot, object_type, object_id)
    if object_entry is None:
        return None
    envelope = {
        "artifact_id": f"{snapshot['context_id']}_{object_type}_{object_id}",
        "artifact_kind": "explanation_snapshot",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": snapshot,
        "object_index": build_object_index([object_entry]),
    }
    return _finalize_envelope(envelope)


def _find_snapshot_object(snapshot, object_type, object_id):
    for candidate in _snapshot_objects(snapshot):
        if (
            candidate["object_type"] == object_type
            and candidate["object_id"] == object_id
        ):
            return candidate
    return None


def _counterfactuals_artifact(operation, resolution, deps):
    context_id = operation["parameters"]["context_id"]
    snapshot = resolution["snapshot"]
    if snapshot.get("context_id") != context_id:
        return None
    objects = [
        _artifact_object(
            counterfactual["object_type"],
            counterfactual["object_id"],
            "decision_fact",
            counterfactual,
        )
        for counterfactual in snapshot.get("counterfactuals") or []
    ]
    if not objects:
        return None
    envelope = {
        "artifact_id": f"{snapshot['context_id']}_counterfactuals",
        "artifact_kind": "explanation_snapshot",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": snapshot,
        "object_index": build_object_index(objects),
    }
    return _finalize_envelope(envelope)


def _compare_snapshots_artifact(operation, resolution, deps):
    context_a_id = operation["parameters"]["context_a_id"]
    context_b_id = operation["parameters"]["context_b_id"]
    resolution_context_id = resolution["snapshot"]["context_id"]
    if resolution_context_id not in (context_a_id, context_b_id):
        return None
    snapshot_a = (
        resolution["snapshot"]
        if context_a_id == resolution_context_id
        else _load_snapshot_by_context_id(deps, context_a_id)
    )
    snapshot_b = (
        resolution["snapshot"]
        if context_b_id == resolution_context_id
        else _load_snapshot_by_context_id(deps, context_b_id)
    )
    if snapshot_a is None or snapshot_b is None:
        return None
    delta = build_semantic_delta(snapshot_a, snapshot_b)
    artifact_id = f"cmp_{context_a_id}_{context_b_id}"
    envelope = {
        "artifact_id": artifact_id,
        "artifact_kind": "explanation_snapshot",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": {
            "context_a_id": context_a_id,
            "context_b_id": context_b_id,
            "delta": delta,
        },
        "object_index": build_object_index(
            [_artifact_object("snapshot_delta", artifact_id, "decision_fact", delta)]
        ),
    }
    return _finalize_envelope(envelope)


def _snapshot_artifact(snapshot):
    envelope = {
        "artifact_id": snapshot["context_id"],
        "artifact_kind": "explanation_snapshot",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": snapshot,
        "object_index": build_object_index(_snapshot_objects(snapshot)),
    }
    return _finalize_envelope(envelope)


def _snapshot_objects(snapshot):
    objects = []
    results = snapshot.get("results") or {}
    for layer_id in _RESULT_LAYERS:
        result = results.get(layer_id)
        if result is not None:
            objects.append(
                _artifact_object(
                    "market_setup_result", layer_id, "decision_fact", result
                )
            )
    for fact in snapshot.get("evidence") or []:
        objects.append(
            _artifact_object("evidence_fact", fact["fact_id"], "decision_fact", fact)
        )
    methods = (snapshot.get("method_contracts") or {}).get("methods") or {}
    for method_id, method in methods.items():
        objects.append(
            _artifact_object("method_contract", method_id, "method_knowledge", method)
        )
    for counterfactual in snapshot.get("counterfactuals") or []:
        objects.append(
            _artifact_object(
                counterfactual["object_type"],
                counterfactual["object_id"],
                "decision_fact",
                counterfactual,
            )
        )
    return objects


def _artifact_object(object_type, object_id, authority, payload):
    return {
        "object_type": object_type,
        "object_id": object_id,
        "authority": authority,
        "payload": payload,
    }


def _finalize_envelope(envelope):
    envelope["integrity_hash"] = _hash_excluding(envelope, "integrity_hash")
    return validate_artifact(envelope)


def _hash_excluding(payload, excluded_key):
    projection = {key: value for key, value in payload.items() if key != excluded_key}
    return hashlib.sha256(canonical_json(projection)).hexdigest()


def _knowledge_artifact(operation, deps):
    indicator_id = operation["parameters"]["indicator_id"]
    object_type = _KNOWLEDGE_OBJECT_TYPE[operation["operation_id"]]
    catalog = _dependency(deps, "load_knowledge_catalog")()
    record = _resolve_knowledge_record(catalog, indicator_id, object_type)
    if record is None:
        return None
    envelope = {
        "artifact_id": record["record_id"],
        "artifact_kind": "knowledge_record",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "method_knowledge",
        "market_setup_relation": "non_decision",
        "payload": record,
        "object_index": build_object_index(
            [
                _artifact_object(
                    object_type, record["record_id"], "method_knowledge", record
                )
            ]
        ),
    }
    return _finalize_envelope(envelope)


def _resolve_knowledge_record(catalog, indicator_id, object_type):
    matches = _knowledge_matches(catalog, indicator_id, object_type)
    if not matches:
        alias_id = _KNOWLEDGE_INDICATOR_ALIASES.get((indicator_id, object_type))
        if alias_id is not None:
            matches = _knowledge_matches(catalog, alias_id, object_type)
    if not matches:
        return None
    return max(matches, key=lambda record: record["version"])


def _knowledge_matches(catalog, indicator_id, object_type):
    return [
        record
        for record in catalog.get("records") or []
        if record.get("indicator_id") == indicator_id
        and record.get("object_type") == object_type
    ]


def _exploration_artifact(operation, deps):
    query = _exploration_query(operation)
    result_id = _new_id("expl_")
    created_at = _now_iso()
    con = _dependency(deps, "connect")(_dependency(deps, "db_path"))
    try:
        result = _dependency(deps, "exploration")(
            con, query, result_id=result_id, created_at=created_at
        )
    except ValueError:
        return None
    finally:
        con.close()
    envelope = {
        "artifact_id": result["exploration_result_id"],
        "artifact_kind": "exploration_result",
        "schema_version": result["artifact_schema_version"],
        "primary_authority": result["authority"],
        "market_setup_relation": result["market_setup_relation"],
        "payload": result,
        "object_index": build_object_index(result["object_index"]),
    }
    return _finalize_envelope(envelope)


def _exploration_query(operation):
    parameters = operation["parameters"]
    query_kind = _EXPLORATION_QUERY_KIND[operation["operation_id"]]
    query = {
        "query_kind": query_kind,
        "indicator_id": parameters["indicator_id"],
        "statistics": parameters.get("statistics", []),
    }
    if query_kind == "indicator_history":
        query["start"] = parameters["start"]
        query["end"] = parameters["end"]
    elif query_kind == "period_comparison":
        query["period_a"] = parameters["period_a"]
        query["period_b"] = parameters["period_b"]
    elif query_kind == "release_history":
        query["start"] = parameters["start"]
        query["end"] = parameters["end"]
    return query


async def _research_artifact(request, operation, deps):
    parameters = operation["parameters"]
    tier = _RESEARCH_TIER[operation["operation_id"]]
    result_id = _new_id("res_")
    searched_at = _now_iso()
    if tier == "deep" and not request.get("deep_research_requested"):
        return _research_unavailable_artifact(
            result_id, searched_at, "deep_research_not_requested"
        )
    task = {
        "purpose": parameters["purpose"],
        "depth_tier": tier,
        "queries": parameters["queries"],
        "expected_source_class": parameters["expected_source_class"],
    }
    if parameters.get("approved_domains") is not None:
        task["approved_domains"] = parameters["approved_domains"]
    if parameters.get("time_window") is not None:
        task["time_window"] = parameters["time_window"]
    try:
        provider = _dependency(deps, "build_research_provider")(_runtime_config(deps))
    except Exception:
        return _research_unavailable_artifact(
            result_id, searched_at, "configuration_unavailable"
        )
    result = await _dependency(deps, "acquire_research")(
        provider,
        task,
        result_id=result_id,
        searched_at=searched_at,
        explicit_deep=(tier == "deep" and bool(request.get("deep_research_requested"))),
    )
    if result.get("status") == "research_unavailable":
        return _research_unavailable_artifact(
            result_id, searched_at, result.get("reason_code")
        )
    envelope = {
        "artifact_id": result["research_result_id"],
        "artifact_kind": "research_result",
        "schema_version": result["artifact_schema_version"],
        "primary_authority": result["authority"],
        "market_setup_relation": result["market_setup_relation"],
        "payload": result,
        "object_index": build_object_index(result["object_index"]),
    }
    return _finalize_envelope(envelope)


def _research_unavailable_artifact(result_id, searched_at, reason_code):
    payload = {
        "research_result_id": result_id,
        "status": "research_unavailable",
        "reason_code": reason_code,
        "searched_at": searched_at,
    }
    envelope = {
        "artifact_id": result_id,
        "artifact_kind": "research_result",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "external_research",
        "market_setup_relation": "non_decision",
        "payload": payload,
        "object_index": build_object_index(
            [
                _artifact_object(
                    "research_unavailable", result_id, "external_research", payload
                )
            ]
        ),
    }
    return _finalize_envelope(envelope)


async def _synthesize(request, plan, resolution, artifacts, deps):
    try:
        return await _dependency(deps, "synthesize_llm")(
            question=request["question"],
            plan=plan,
            context_summary=_context_summary(request, resolution),
            artifacts=artifacts,
        )
    except Exception:
        return None


async def _validate_or_repair_once(request, plan, resolution, artifacts, draft, deps):
    attempts = {"draft": 0, "repair": 0}
    validation_error_codes = []
    if draft is None:
        return None, "fallback", attempts, validation_error_codes
    attempts["draft"] += 1
    try:
        validated = validate_answer_draft(draft, artifacts)
        return validated, "validated_first_pass", attempts, validation_error_codes
    except DraftValidationError as exc:
        validation_error_codes = sorted({error["code"] for error in exc.errors})
        report = build_validation_report(exc.errors)
    attempts["repair"] += 1
    try:
        repaired = await _dependency(deps, "repair_llm")(
            question=request["question"],
            plan=plan,
            context_summary=_context_summary(request, resolution),
            artifacts=artifacts,
            draft=draft,
            validation_report=report,
        )
    except Exception:
        return None, "fallback", attempts, validation_error_codes
    if repaired is None:
        return None, "fallback", attempts, validation_error_codes
    attempts["draft"] += 1
    try:
        validated = validate_answer_draft(repaired, artifacts)
        return validated, "validated_after_repair", attempts, validation_error_codes
    except DraftValidationError as exc:
        validation_error_codes = sorted({error["code"] for error in exc.errors})
        return None, "fallback", attempts, validation_error_codes


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
        "research_model": config.get("research_model"),
        "tool_schema_versions": TOOL_SCHEMA_VERSIONS,
        "assistant_policy_version": ASSISTANT_POLICY_VERSION,
        "prompt_version": PROMPT_VERSION,
    }
