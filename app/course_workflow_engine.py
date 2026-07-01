from numbers import Real

from app.method_indicators import apply_computed_indicators
from app.method_schema import (
    normalize_method_payload,
    normalize_graph_observation_payload,
)


_FAIL_PRIORITY = {
    "pass": 0,
    "fail": 1,
    "missing": 2,
    "reject": 3,
}


def _is_missing(value):
    return value is None or value == "" or value == [] or value == {}


def _get_path(payload, path):
    current = payload
    for part in str(path or "").split("."):
        if not part:
            return None
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_numeric(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def _compare(actual, operator, expected):
    if operator == "exists":
        return not _is_missing(actual)
    if operator == "truthy":
        return bool(actual)
    if operator == "falsy":
        return not bool(actual)
    if _is_missing(actual):
        return False
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return False
    if operator == "in":
        return actual in (expected or [])
    if operator == "any_of":
        if isinstance(actual, (list, tuple, set)):
            return any(item in actual for item in (expected or []))
        return actual in (expected or [])
    if operator == "all_of":
        if not isinstance(actual, (list, tuple, set)):
            return False
        return all(item in actual for item in (expected or []))
    if operator == "gt":
        return _is_numeric(actual) and _is_numeric(expected) and actual > expected
    if operator == "gte":
        return _is_numeric(actual) and _is_numeric(expected) and actual >= expected
    if operator == "lt":
        return _is_numeric(actual) and _is_numeric(expected) and actual < expected
    if operator == "lte":
        return _is_numeric(actual) and _is_numeric(expected) and actual <= expected
    raise ValueError(f"unsupported operator: {operator}")


def _evaluate_check(check, observation):
    actual = _get_path(observation, check["field"])
    if _is_missing(actual):
        status = "missing"
    elif _compare(actual, check["operator"], check.get("value")):
        status = "pass"
    else:
        status = "fail"
    return {
        "check_id": check["id"],
        "node_id": check["node_id"],
        "title": check["title"],
        "field": check["field"],
        "operator": check["operator"],
        "expected": check.get("value"),
        "actual": actual,
        "side": check["side"],
        "required": check.get("required") is True,
        "fail_effect": check.get("fail_effect"),
        "source_refs": check.get("source_refs", []),
        "status": status,
        "message": check.get("missing_message") if status == "missing" else None,
    }


def _summarize_side(checks):
    if not checks:
        return {"status": "pass", "method_basis": []}
    if any(
        check["status"] == "fail" and check["fail_effect"] == "reject"
        for check in checks
    ):
        status = "reject"
    elif any(check["status"] == "missing" and check["required"] for check in checks):
        status = "missing"
    elif any(check["status"] == "fail" and check["required"] for check in checks):
        status = "fail"
    elif any(check["status"] == "missing" for check in checks):
        status = "missing"
    elif any(check["status"] == "fail" for check in checks):
        status = "fail"
    else:
        status = "pass"
    return {
        "status": status,
        "method_basis": [
            {
                "check_id": check["check_id"],
                "title": check["title"],
                "status": check["status"],
                "fail_effect": check["fail_effect"],
            }
            for check in checks
        ],
    }


def _node_status(long_status, short_status):
    if long_status == short_status:
        return long_status
    return "mixed"


def _build_node_result(node, checks):
    long_checks = [check for check in checks if check["side"] in {"both", "long"}]
    short_checks = [check for check in checks if check["side"] in {"both", "short"}]
    long_result = _summarize_side(long_checks)
    short_result = _summarize_side(short_checks)
    return {
        "node_id": node["id"],
        "title": node["title"],
        "decision_question": node["decision_question"],
        "description": node["description"],
        "required_inputs": node["required_inputs"],
        "criteria": node["criteria"],
        "tool_hooks": node["tool_hooks"],
        "incoming_edges": node["incoming_edges"],
        "outgoing_edges": node["outgoing_edges"],
        "indicators": node.get("indicators", []),
        "checks": checks,
        "method_basis": {
            "long": long_result["method_basis"],
            "short": short_result["method_basis"],
        },
        "long": long_result,
        "short": short_result,
        "status": _node_status(long_result["status"], short_result["status"]),
    }


def _missing_information(node_results):
    missing = []
    for node in node_results:
        for check in node["checks"]:
            if check["status"] != "missing":
                continue
            missing.append(
                {
                    "node_id": node["node_id"],
                    "check_id": check["check_id"],
                    "title": check["title"],
                    "field": check["field"],
                    "side": check["side"],
                }
            )
    return missing


def _next_actions(node_results):
    actions = []
    for node in node_results:
        for check in node["checks"]:
            effect = check.get("fail_effect")
            if (
                effect
                and check["status"] in {"fail", "missing"}
                and effect not in actions
            ):
                actions.append(effect)
    return actions


def _flatten_checks(node_results):
    return [check for node in node_results for check in node["checks"]]


def _edges(method):
    edges = []
    for node in method["workflow_nodes"]:
        for target in node["outgoing_edges"]:
            edges.append({"from": node["id"], "to": target})
    return edges


def _side_support(node_results, side):
    support = 0
    for node in node_results:
        side_checks = [
            check
            for check in node["checks"]
            if check["side"] == side and check["status"] == "pass"
        ]
        support += len(side_checks)
        if node[side]["status"] == "pass" and side_checks:
            support += 1
    return support


def _supports_wait_for_timing(check):
    return (
        check["status"] in {"fail", "missing"}
        and not check["required"]
        and check.get("fail_effect") == "wait_for_timing"
    )


def _final_status(node_results):
    all_checks = _flatten_checks(node_results)
    if any(
        check["status"] == "fail" and check["fail_effect"] == "reject"
        for check in all_checks
    ):
        return "reject"
    if any(check["required"] and check["status"] == "missing" for check in all_checks):
        return "insufficient_data"
    for check in all_checks:
        if check["required"] and check["status"] == "fail":
            effect = check.get("fail_effect")
            if effect in {"wait_for_timing", "wait_for_research"}:
                return effect
            return "reject"

    long_support = _side_support(node_results, "long")
    short_support = _side_support(node_results, "short")

    if (
        any(_supports_wait_for_timing(check) for check in all_checks)
        and long_support == short_support == 0
    ):
        return "wait_for_timing"

    if long_support and short_support and abs(long_support - short_support) <= 1:
        return "conflicting_evidence"

    if long_support > short_support:
        return "long_watchlist"
    if short_support > long_support:
        return "short_watchlist"
    return "insufficient_data"


def evaluate_workflow_method(method_payload, observation_payload, tool_runner=None):
    method = normalize_method_payload(method_payload)
    observation = normalize_graph_observation_payload(observation_payload)
    observations = observation["observations"]
    if tool_runner:
        observations = tool_runner(method, observation)
    graph_observation = apply_computed_indicators(dict(observations))
    graph_observation["symbol"] = observation["symbol"]

    checks_by_node = {}
    for check in method["node_checks"]:
        checks_by_node.setdefault(check["node_id"], []).append(
            _evaluate_check(check, graph_observation)
        )

    node_results = [
        _build_node_result(node, checks_by_node.get(node["id"], []))
        for node in method["workflow_nodes"]
    ]

    return {
        "symbol": observation["symbol"],
        "method_version": method["version"],
        "nodes": node_results,
        "edges": _edges(method),
        "missing_information": _missing_information(node_results),
        "next_actions": _next_actions(node_results),
        "final_status": _final_status(node_results),
    }
