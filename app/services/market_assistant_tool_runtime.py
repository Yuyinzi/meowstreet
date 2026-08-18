import asyncio
import hashlib
import secrets
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.db.market_assistant import connect
from app.db.market_assistant import load_snapshot
from app.services.market_assistant_exploration import execute_exploration
from app.services.market_assistant_research import acquire_research
from app.services.market_assistant_research import build_research_provider
from app.tools.market_assistant_artifacts import build_object_index
from app.tools.market_assistant_artifacts import validate_artifact
from app.tools.market_assistant_evidence_detail_registry import evidence_detail_record
from app.tools.market_assistant_evidence_detail_registry import (
    load_evidence_detail_registry,
)
from app.tools.market_assistant_evidence_details import project_evidence_detail
from app.tools.market_assistant_knowledge import load_knowledge_catalog
from app.tools.market_assistant_tools import ALL_TOOL_IDS
from app.tools.market_setup_explanation_snapshot import build_semantic_delta
from app.tools.market_setup_explanation_snapshot import canonical_json

ARTIFACT_SCHEMA_VERSION = "market_assistant_artifact_v1"

_RESULT_LAYERS = (
    "macro_regime",
    "market_confirmation",
    "market_setup",
    "portfolio_posture",
)

_CONFIRMATION_TEST_INDICATORS = {
    "equity": "sp500_close",
    "credit": "credit_conditions",
    "vix": "vix",
}

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

TOOL_RUNTIME_POLICIES = {
    "get_setup_overview": ("frozen_local", ()),
    "get_macro_regime_explanation": ("frozen_local", ()),
    "get_confirmation_test": ("frozen_local", ()),
    "get_confirmation_tests": ("frozen_local", ()),
    "get_posture_explanation": ("frozen_local", ()),
    "get_approved_counterfactuals": ("frozen_local", ()),
    "get_evidence_detail": ("frozen_local", ()),
    "get_indicator_knowledge": ("local_read", ()),
    "query_indicator_history": ("local_read", ()),
    "compare_snapshots": ("local_read", ()),
    "get_indicator_current": ("local_read", ()),
    "get_indicator_definition": ("local_read", ()),
    "get_indicator_method": ("local_read", ()),
    "research_focused": ("external_read", ("external_search_requested",)),
    "research_standard": ("external_read", ("external_search_requested",)),
    "research_deep": (
        "external_read",
        ("external_search_requested", "deep_research_requested"),
    ),
}

if set(TOOL_RUNTIME_POLICIES) != set(ALL_TOOL_IDS):
    raise ValueError("tool runtime policies must cover every registered tool")

_HISTORY_WINDOW_DAYS = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
}

_POSTURE_METHOD_ID = "posture_matrix"

_DEPENDENCY_DEFAULTS = {
    "connect": connect,
    "load_snapshot": load_snapshot,
    "load_knowledge_catalog": load_knowledge_catalog,
    "load_evidence_detail_registry": load_evidence_detail_registry,
    "exploration": execute_exploration,
    "acquire_research": acquire_research,
    "build_research_provider": build_research_provider,
}

_PROGRESS_LABELS = {
    "get_setup_overview": "reading the current market setup",
    "get_macro_regime_explanation": "reading the macro regime explanation",
    "get_confirmation_test": "checking a market confirmation test",
    "get_confirmation_tests": "checking market confirmation tests",
    "get_posture_explanation": "reading the portfolio posture explanation",
    "get_approved_counterfactuals": "reading approved counterfactuals",
    "get_indicator_knowledge": "reading approved indicator knowledge",
    "get_indicator_definition": "reading an approved indicator definition",
    "get_indicator_method": "reading an approved indicator method",
    "get_indicator_current": "reading the current indicator value",
    "query_indicator_history": "querying local indicator history",
    "compare_snapshots": "comparing market setup snapshots",
    "get_evidence_detail": "reading governed evidence detail",
    "research_focused": "running focused external research",
    "research_standard": "running standard external research",
    "research_deep": "running deep external research",
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


def _normalized_call(call):
    if not isinstance(call, dict):
        raise ValueError("tool call is invalid")
    tool_name = call.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool call is invalid")
    arguments = call.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("tool call is invalid")
    return tool_name, dict(arguments)


async def _frozen_snapshot(dependencies, resolution):
    loader = _optional_dependency(dependencies, "load_frozen_context")
    if loader is None:
        return resolution["snapshot"]
    loaded = loader(resolution)
    if asyncio.iscoroutine(loaded):
        return await loaded
    return loaded


async def execute_tool_call(call, *, request, resolution, dependencies, created_at):
    tool_name, arguments = _normalized_call(call)
    operation = {"operation_id": tool_name, "parameters": arguments}
    artifact = await acquire_operation_artifact(
        operation,
        request=request,
        resolution=resolution,
        dependencies=dependencies,
        created_at=created_at,
    )
    return {
        "call_id": call.get("call_id", ""),
        "tool_name": tool_name,
        "arguments": arguments,
        "artifact": artifact,
        "progress_label": _PROGRESS_LABELS.get(tool_name, "reading local evidence"),
    }


async def execute_tool_batch(calls, *, request, resolution, dependencies, created_at):
    tasks = [
        execute_tool_call(
            call,
            request=request,
            resolution=resolution,
            dependencies=dependencies,
            created_at=created_at,
        )
        for call in calls
    ]
    return list(await asyncio.gather(*tasks))


async def acquire_registered_artifacts(
    operations, *, request, resolution, dependencies, created_at=None
):
    if created_at is None:
        created_at = _now_iso()
    artifacts = {}
    unsupported_operation_id = None
    for operation in operations:
        operation_id = operation["operation_id"]
        artifact = await acquire_operation_artifact(
            operation,
            request=request,
            resolution=resolution,
            dependencies=dependencies,
            created_at=created_at,
        )
        if artifact is None:
            unsupported_operation_id = operation_id
            break
        artifacts[artifact["artifact_id"]] = artifact
    if unsupported_operation_id is not None:
        snapshot = await _frozen_snapshot(dependencies, resolution)
        snapshot_envelope = snapshot_artifact(snapshot)
        artifacts[snapshot_envelope["artifact_id"]] = snapshot_envelope
    return artifacts, unsupported_operation_id


async def acquire_operation_artifact(
    operation, *, request, resolution, dependencies, created_at
):
    operation_id = operation["operation_id"]
    parameters = operation.get("parameters") or {}
    if operation_id in TOOL_RUNTIME_POLICIES:
        missing_control = _missing_policy_control(operation_id, request)
        if missing_control is not None:
            return _policy_blocked_artifact(operation_id, missing_control, created_at)
    if operation_id == "resolve_current_explanation":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return snapshot_artifact(snapshot)
    if operation_id == "get_historical_snapshot":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _historical_snapshot_artifact(parameters, snapshot, dependencies)
    if operation_id == "get_snapshot_object":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _snapshot_object_artifact(parameters, snapshot)
    if operation_id == "get_counterfactuals":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _counterfactuals_artifact(parameters, snapshot)
    if operation_id == "compare_snapshots":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _compare_snapshots_artifact(parameters, snapshot, dependencies)
    if operation_id == "get_setup_overview":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _setup_overview_artifact(snapshot)
    if operation_id == "get_macro_regime_explanation":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _macro_regime_artifact(snapshot)
    if operation_id == "get_confirmation_test":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _confirmation_test_artifact(parameters, snapshot)
    if operation_id == "get_confirmation_tests":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _confirmation_tests_artifact(parameters, snapshot)
    if operation_id == "get_posture_explanation":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _posture_artifact(snapshot)
    if operation_id == "get_approved_counterfactuals":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _approved_counterfactuals_artifact(snapshot)
    if operation_id == "get_indicator_knowledge":
        object_type = _KNOWLEDGE_OBJECT_TYPE.get(
            f"get_indicator_{parameters.get('topic')}"
        )
        if object_type is None:
            return None
        return _knowledge_artifact(parameters, object_type, dependencies)
    if operation_id in _KNOWLEDGE_OBJECT_TYPE:
        return _knowledge_artifact(
            parameters, _KNOWLEDGE_OBJECT_TYPE[operation_id], dependencies
        )
    if operation_id == "get_evidence_detail":
        snapshot = await _frozen_snapshot(dependencies, resolution)
        return _evidence_detail_artifact(parameters, snapshot, dependencies)
    if operation_id in _EXPLORATION_QUERY_KIND:
        return _exploration_artifact(parameters, operation_id, dependencies, created_at)
    if operation_id in _RESEARCH_TIER:
        return await _research_artifact(
            request, operation_id, parameters, dependencies, created_at
        )
    return None


def _load_snapshot_by_context_id(dependencies, context_id):
    con = _dependency(dependencies, "connect")(_dependency(dependencies, "db_path"))
    try:
        return _dependency(dependencies, "load_snapshot")(con, context_id)
    finally:
        con.close()


def _historical_snapshot_artifact(parameters, snapshot, dependencies):
    context_id = parameters["context_id"]
    if snapshot.get("context_id") != context_id:
        return None
    return snapshot_artifact(snapshot)


def _snapshot_object_artifact(parameters, snapshot):
    object_type = parameters["object_type"]
    object_id = parameters["object_id"]
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


def _counterfactuals_artifact(parameters, snapshot):
    context_id = parameters["context_id"]
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


def _compare_snapshots_artifact(parameters, snapshot, dependencies):
    context_a_id = parameters["context_a_id"]
    context_b_id = parameters["context_b_id"]
    resolution_context_id = snapshot["context_id"]
    if resolution_context_id not in (context_a_id, context_b_id):
        return None
    snapshot_a = (
        snapshot
        if context_a_id == resolution_context_id
        else _load_snapshot_by_context_id(dependencies, context_a_id)
    )
    snapshot_b = (
        snapshot
        if context_b_id == resolution_context_id
        else _load_snapshot_by_context_id(dependencies, context_b_id)
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


def snapshot_artifact(snapshot):
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


def _knowledge_artifact(parameters, object_type, dependencies):
    indicator_id = parameters["indicator_id"]
    catalog = _dependency(dependencies, "load_knowledge_catalog")()
    record = _resolve_knowledge_record(catalog, indicator_id, object_type)
    if record is None:
        return None
    envelope = {
        "artifact_id": f"{record['record_id']}_{record['version']}",
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


def _exploration_artifact(parameters, operation_id, dependencies, created_at):
    if created_at is None:
        created_at = _now_iso()
    query = _exploration_query(operation_id, parameters, created_at)
    result_id = _new_id("expl_")
    con = _dependency(dependencies, "connect")(_dependency(dependencies, "db_path"))
    try:
        result = _dependency(dependencies, "exploration")(
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


def _exploration_query(operation_id, parameters, created_at):
    query_kind = _EXPLORATION_QUERY_KIND[operation_id]
    query = {
        "query_kind": query_kind,
        "indicator_id": parameters["indicator_id"],
        "statistics": parameters.get("statistics", []),
    }
    if query_kind == "indicator_history":
        if "window" in parameters:
            query["start"], query["end"] = _window_date_range(
                parameters["window"], created_at
            )
        else:
            query["start"] = parameters["start"]
            query["end"] = parameters["end"]
    elif query_kind == "period_comparison":
        query["period_a"] = parameters["period_a"]
        query["period_b"] = parameters["period_b"]
    elif query_kind == "release_history":
        query["start"] = parameters["start"]
        query["end"] = parameters["end"]
    return query


def _window_date_range(window, created_at):
    end = _window_end_date(created_at)
    start = end - timedelta(days=_HISTORY_WINDOW_DAYS[window])
    return start.isoformat(), end.isoformat()


def _window_end_date(created_at):
    if created_at:
        try:
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            return parsed.date()
    return date.today()


async def _research_artifact(
    request, operation_id, parameters, dependencies, created_at
):
    tier = _RESEARCH_TIER[operation_id]
    result_id = _new_id("res_")
    searched_at = created_at or _now_iso()
    if not request.get("external_search_requested"):
        return _research_unavailable_artifact(
            result_id, searched_at, "external_search_not_requested"
        )
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
        provider = _dependency(dependencies, "build_research_provider")(
            _runtime_config(dependencies)
        )
    except Exception:
        return _research_unavailable_artifact(
            result_id, searched_at, "configuration_unavailable"
        )
    result = await _dependency(dependencies, "acquire_research")(
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


def _missing_policy_control(tool_name, request):
    capability, controls = TOOL_RUNTIME_POLICIES[tool_name]
    for control in controls:
        if not request.get(control):
            return control
    return None


def _policy_blocked_artifact(tool_name, missing_control, created_at):
    if tool_name in _RESEARCH_TIER:
        return _research_unavailable_artifact(
            _new_id("res_"), created_at, _control_unavailable_reason(missing_control)
        )
    artifact_id = _new_id("cap_")
    payload = {
        "artifact_id": artifact_id,
        "tool_name": tool_name,
        "status": "capability_unavailable",
        "reason_code": _control_unavailable_reason(missing_control),
        "requested_at": created_at,
    }
    envelope = {
        "artifact_id": artifact_id,
        "artifact_kind": "exploration_result",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "local_observation",
        "market_setup_relation": "non_decision",
        "payload": payload,
        "object_index": build_object_index(
            [
                _artifact_object(
                    "capability_unavailable",
                    artifact_id,
                    "local_observation",
                    payload,
                )
            ]
        ),
    }
    return _finalize_envelope(envelope)


_CONTROL_UNAVAILABLE_REASON = {
    "external_search_requested": "external_search_not_requested",
    "deep_research_requested": "deep_research_not_requested",
}


def _control_unavailable_reason(missing_control):
    return _CONTROL_UNAVAILABLE_REASON.get(
        missing_control, f"{missing_control}_not_requested"
    )


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


def _focused_snapshot_envelope(snapshot, artifact_id, objects, extra=None):
    payload = {
        "context_id": snapshot["context_id"],
        "as_of": snapshot.get("as_of"),
        "evidence_through": snapshot.get("evidence_through"),
    }
    if extra:
        payload.update(extra)
    envelope = {
        "artifact_id": artifact_id,
        "artifact_kind": "explanation_snapshot",
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": payload,
        "object_index": build_object_index(objects),
    }
    return _finalize_envelope(envelope)


def _setup_overview_artifact(snapshot):
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
    for step in snapshot.get("decision_path") or []:
        objects.append(
            _artifact_object(
                "decision_path_step", step["step_id"], "decision_fact", step
            )
        )
    return _focused_snapshot_envelope(
        snapshot, f"{snapshot['context_id']}_overview", objects
    )


def _macro_regime_artifact(snapshot):
    objects = []
    result = (snapshot.get("results") or {}).get("macro_regime")
    if result is not None:
        objects.append(
            _artifact_object(
                "market_setup_result", "macro_regime", "decision_fact", result
            )
        )
    for fact in snapshot.get("evidence") or []:
        role = fact.get("role") or {}
        if (
            role.get("function") in ("selector", "contextual_relationship")
            and role.get("target_layer") == "macro_regime"
        ):
            objects.append(
                _artifact_object(
                    "evidence_fact", fact["fact_id"], "decision_fact", fact
                )
            )
    return _focused_snapshot_envelope(
        snapshot, f"{snapshot['context_id']}_macro_regime", objects
    )


def _confirmation_test_fact(snapshot, test_id):
    indicator_id = _CONFIRMATION_TEST_INDICATORS.get(test_id)
    if indicator_id is None:
        return None
    for fact in snapshot.get("evidence") or []:
        role = fact.get("role") or {}
        if (
            role.get("function") == "confirmation_test"
            and fact.get("indicator_id") == indicator_id
        ):
            return fact
    return None


def _confirmation_test_artifact(parameters, snapshot):
    test_id = parameters["test_id"]
    fact = _confirmation_test_fact(snapshot, test_id)
    if fact is None:
        return None
    objects = [
        _artifact_object("evidence_fact", fact["fact_id"], "decision_fact", fact)
    ]
    confirmation_result = (snapshot.get("results") or {}).get("market_confirmation")
    if confirmation_result is not None:
        objects.append(
            _artifact_object(
                "market_setup_result",
                "market_confirmation",
                "decision_fact",
                confirmation_result,
            )
        )
    return _focused_snapshot_envelope(
        snapshot,
        f"{snapshot['context_id']}_confirmation_test_{test_id}",
        objects,
        {"test_id": test_id},
    )


def _confirmation_tests_artifact(parameters, snapshot):
    test_ids = parameters["test_ids"]
    objects = []
    for test_id in test_ids:
        fact = _confirmation_test_fact(snapshot, test_id)
        if fact is not None:
            objects.append(
                _artifact_object(
                    "evidence_fact", fact["fact_id"], "decision_fact", fact
                )
            )
    if not objects:
        return None
    confirmation_result = (snapshot.get("results") or {}).get("market_confirmation")
    if confirmation_result is not None:
        objects.append(
            _artifact_object(
                "market_setup_result",
                "market_confirmation",
                "decision_fact",
                confirmation_result,
            )
        )
    return _focused_snapshot_envelope(
        snapshot,
        f"{snapshot['context_id']}_confirmation_tests",
        objects,
        {"test_ids": test_ids},
    )


def _posture_artifact(snapshot):
    objects = []
    result = (snapshot.get("results") or {}).get("portfolio_posture")
    if result is not None:
        objects.append(
            _artifact_object(
                "market_setup_result", "portfolio_posture", "decision_fact", result
            )
        )
    methods = (snapshot.get("method_contracts") or {}).get("methods") or {}
    posture_contract = methods.get(_POSTURE_METHOD_ID)
    if posture_contract is not None:
        objects.append(
            _artifact_object(
                "method_contract",
                _POSTURE_METHOD_ID,
                "method_knowledge",
                posture_contract,
            )
        )
    return _focused_snapshot_envelope(
        snapshot, f"{snapshot['context_id']}_posture", objects
    )


def _approved_counterfactuals_artifact(snapshot):
    objects = []
    for counterfactual in snapshot.get("counterfactuals") or []:
        if counterfactual.get("object_type") == "market_setup":
            objects.append(
                _artifact_object(
                    "market_setup",
                    counterfactual["object_id"],
                    "decision_fact",
                    counterfactual,
                )
            )
    if not objects:
        return None
    return _focused_snapshot_envelope(
        snapshot, f"{snapshot['context_id']}_approved_counterfactuals", objects
    )


def _evidence_detail_artifact(parameters, snapshot, dependencies):
    fact_id = parameters["fact_id"]
    topics = parameters["topics"]
    fact = _snapshot_evidence_fact(snapshot, fact_id)
    registry = _dependency(dependencies, "load_evidence_detail_registry")()
    record = evidence_detail_record(registry, fact_id)
    method_contracts = snapshot.get("method_contracts") or {}
    projection = project_evidence_detail(fact, record, topics, method_contracts)
    artifact_id = (
        f"{snapshot['context_id']}_evidence_detail_{fact_id}_{'_'.join(sorted(topics))}"
    )
    decision_payload = {
        key: value
        for key, value in projection.items()
        if key not in ("method", "source")
    }
    objects = [
        _artifact_object(
            "evidence_detail", artifact_id, "decision_fact", decision_payload
        )
    ]
    source = projection.get("source")
    if source is not None:
        objects.append(
            _artifact_object(
                "evidence_detail_source",
                f"{artifact_id}_source",
                "method_knowledge",
                {"source": source},
            )
        )
    method = projection.get("method")
    if method is not None:
        objects.append(
            _artifact_object(
                "evidence_detail_method",
                f"{artifact_id}_method",
                "method_knowledge",
                method,
            )
        )
    extra = {
        "fact_id": projection["fact_id"],
        "detail_kind": projection["detail_kind"],
        "topics": projection["topics"],
        "status": projection["status"],
        "detail": projection,
    }
    return _focused_snapshot_envelope(snapshot, artifact_id, objects, extra)


def _snapshot_evidence_fact(snapshot, fact_id):
    for fact in snapshot.get("evidence") or []:
        if fact.get("fact_id") == fact_id:
            return fact
    return None
