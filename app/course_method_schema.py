import re


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]*$")
_VALID_SIDES = {"long", "short", "both"}
_VALID_OPERATORS = {
    "exists",
    "truthy",
    "falsy",
    "equals",
    "not_equals",
    "contains",
    "in",
    "any_of",
    "all_of",
    "gt",
    "gte",
    "lt",
    "lte",
}

_VALID_COMPUTE_STATUSES = {
    "computed",
    "manual_input",
    "future_tool_hook",
    "supporting_only",
}

_VALID_GRAPH_REVIEW_ACTIONS = {
    "keep",
    "rename",
    "split",
    "merge",
    "demote_to_sub_method",
    "remove",
}


def _text(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _value(value):
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_value(item) for item in value]
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    return value


def _array(payload, key):
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _required_text(obj, key, label):
    value = _text(obj.get(key))
    if not value:
        raise ValueError(f"{label} {key} is required")
    obj[key] = value
    return value


def _source_refs(source_refs, label):
    if source_refs is None:
        return []
    if not isinstance(source_refs, list):
        raise ValueError(f"{label} source_refs must be a list")
    for index, source_ref in enumerate(source_refs):
        if not isinstance(source_ref, dict):
            raise ValueError(f"{label} source_ref {index} must be an object")
        if "document" in source_ref:
            _required_text(source_ref, "document", f"{label} source_ref {index}")
        _required_text(source_ref, "section", f"{label} source_ref {index}")
    return source_refs


def _normalize_sub_methods(node):
    node_id = node["id"]
    sub_methods = node.get("sub_methods", [])
    if not isinstance(sub_methods, list):
        raise ValueError(f"workflow node {node_id} sub_methods must be a list")
    for index, sub_method in enumerate(sub_methods):
        if not isinstance(sub_method, dict):
            raise ValueError(
                f"workflow node {node_id} sub_method {index} must be an object"
            )
        sub_method_id = _required_text(
            sub_method, "id", f"workflow node {node_id} sub_method"
        )
        _required_text(
            sub_method, "title", f"workflow node {node_id} sub_method {sub_method_id}"
        )
        _required_text(
            sub_method, "summary", f"workflow node {node_id} sub_method {sub_method_id}"
        )
        sub_method["source_refs"] = _source_refs(
            sub_method.get("source_refs", []),
            f"workflow node {node_id} sub_method {sub_method_id}",
        )
    node["sub_methods"] = sub_methods


def _normalize_indicators(node):
    node_id = node["id"]
    indicators = node.get("indicators", [])
    if not isinstance(indicators, list):
        raise ValueError(f"workflow node {node_id} indicators must be a list")
    indicator_ids = set()
    for index, indicator in enumerate(indicators):
        if not isinstance(indicator, dict):
            raise ValueError(
                f"workflow node {node_id} indicator {index} must be an object"
            )
        indicator_id = _required_text(
            indicator, "id", f"workflow node {node_id} indicator"
        )
        if indicator_id in indicator_ids:
            raise ValueError(
                f"workflow node {node_id} indicator {indicator_id} is duplicated"
            )
        _required_text(
            indicator, "title", f"workflow node {node_id} indicator {indicator_id}"
        )
        _required_text(
            indicator,
            "description",
            f"workflow node {node_id} indicator {indicator_id}",
        )
        if "formula" not in indicator:
            indicator["formula"] = ""
        if "required_inputs" not in indicator:
            indicator["required_inputs"] = []
        if not isinstance(indicator["required_inputs"], list):
            raise ValueError(
                f"workflow node {node_id} indicator {indicator_id} required_inputs must be a list"
            )
        compute_status = _text(indicator.get("compute_status")) or "supporting_only"
        if compute_status not in _VALID_COMPUTE_STATUSES:
            raise ValueError(
                f"workflow node {node_id} indicator {indicator_id} compute_status is invalid"
            )
        indicator["compute_status"] = compute_status
        if "future_tool_hooks" not in indicator:
            indicator["future_tool_hooks"] = []
        if not isinstance(indicator["future_tool_hooks"], list):
            raise ValueError(
                f"workflow node {node_id} indicator {indicator_id} future_tool_hooks must be a list"
            )
        indicator["source_refs"] = _source_refs(
            indicator.get("source_refs", []),
            f"workflow node {node_id} indicator {indicator_id}",
        )
        indicator_ids.add(indicator_id)
    node["indicators"] = indicators


def _normalize_cautions_and_examples(node):
    node_id = node["id"]
    for key in ("cautions", "examples"):
        values = node.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"workflow node {node_id} {key} must be a list")
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                raise ValueError(
                    f"workflow node {node_id} {key} {index} must be an object"
                )
            value_id = _required_text(value, "id", f"workflow node {node_id} {key}")
            _required_text(value, "title", f"workflow node {node_id} {key} {value_id}")
            _required_text(
                value, "summary", f"workflow node {node_id} {key} {value_id}"
            )
            value["source_refs"] = _source_refs(
                value.get("source_refs", []),
                f"workflow node {node_id} {key} {value_id}",
            )
        node[key] = values


def _normalize_graph_review(normalized):
    graph_review = normalized.get("graph_review", {})
    if graph_review is None:
        graph_review = {}
    if not isinstance(graph_review, dict):
        raise ValueError("graph_review must be an object")
    previous_nodes = graph_review.get("previous_nodes", [])
    if not isinstance(previous_nodes, list):
        raise ValueError("graph_review previous_nodes must be a list")
    actions = graph_review.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("graph_review actions must be a list")
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"graph_review action {index} must be an object")
        action_name = _required_text(action, "action", f"graph_review action {index}")
        if action_name not in _VALID_GRAPH_REVIEW_ACTIONS:
            raise ValueError(f"graph_review action {index} action is invalid")
        _required_text(action, "rationale", f"graph_review action {index}")
    proposed_node_mappings = graph_review.get("proposed_node_mappings", [])
    if not isinstance(proposed_node_mappings, list):
        raise ValueError("graph_review proposed_node_mappings must be a list")
    fallback_decision_areas = graph_review.get("fallback_decision_areas", [])
    if not isinstance(fallback_decision_areas, list):
        raise ValueError("graph_review fallback_decision_areas must be a list")
    dependency_edge_suggestions = graph_review.get("dependency_edge_suggestions", [])
    if not isinstance(dependency_edge_suggestions, list):
        raise ValueError("graph_review dependency_edge_suggestions must be a list")
    routing_audit_moves = graph_review.get("routing_audit_moves", [])
    if not isinstance(routing_audit_moves, list):
        raise ValueError("graph_review routing_audit_moves must be a list")
    routing_audit_run_id = _text(graph_review.get("routing_audit_run_id"))
    normalized["graph_review"] = {
        "previous_nodes": previous_nodes,
        "actions": actions,
        "proposed_node_mappings": proposed_node_mappings,
        "fallback_decision_areas": fallback_decision_areas,
        "dependency_edge_suggestions": dependency_edge_suggestions,
        "routing_audit_run_id": routing_audit_run_id,
        "routing_audit_moves": routing_audit_moves,
    }


def normalize_method_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("method method payload must be an object")

    normalized = _value(payload)
    version = _text(normalized.get("version"))
    if not version:
        raise ValueError("method method version is required")
    normalized["version"] = version

    workflow_nodes = _array(normalized, "workflow_nodes")
    node_checks = _array(normalized, "node_checks")
    if not workflow_nodes:
        raise ValueError("workflow_nodes must not be empty")
    if not node_checks:
        raise ValueError("node_checks must not be empty")

    node_ids = set()
    for index, node in enumerate(workflow_nodes):
        if not isinstance(node, dict):
            raise ValueError(f"workflow node {index} must be an object")
        node_id = _required_text(node, "id", "workflow node")
        if node_id in node_ids:
            raise ValueError(f"workflow node {node_id} is duplicated")
        _required_text(node, "title", f"workflow node {node_id}")
        _required_text(node, "decision_question", f"workflow node {node_id}")
        _required_text(node, "description", f"workflow node {node_id}")
        for key in (
            "required_inputs",
            "criteria",
            "tool_hooks",
            "incoming_edges",
            "outgoing_edges",
            "source_refs",
        ):
            if key not in node:
                node[key] = []
            if not isinstance(node[key], list):
                raise ValueError(f"workflow node {node_id} {key} must be a list")
        node_ids.add(node_id)
        _normalize_sub_methods(node)
        _normalize_indicators(node)
        _normalize_cautions_and_examples(node)

    for node in workflow_nodes:
        node_id = node["id"]
        for key in ("incoming_edges", "outgoing_edges"):
            for edge_node_id in node[key]:
                edge_node_id = _text(edge_node_id)
                if not edge_node_id:
                    raise ValueError(
                        f"workflow node {node_id} {key} contains invalid node id"
                    )
                if edge_node_id not in node_ids:
                    raise ValueError(
                        f"workflow node {node_id} {key} references unknown node"
                    )

    for index, check in enumerate(node_checks):
        if not isinstance(check, dict):
            raise ValueError(f"node check {index} must be an object")
        check_id = _required_text(check, "id", "node check")
        node_id = _required_text(check, "node_id", f"node check {check_id}")
        if node_id not in node_ids:
            raise ValueError(f"node check {check_id} references unknown node")
        _required_text(check, "title", f"node check {check_id}")
        _required_text(check, "field", f"node check {check_id}")
        operator = _required_text(check, "operator", f"node check {check_id}")
        if operator not in _VALID_OPERATORS:
            raise ValueError(f"node check {check_id} operator is invalid")
        side = _required_text(check, "side", f"node check {check_id}")
        if side not in _VALID_SIDES:
            raise ValueError(f"node check {check_id} side is invalid")
        if "source_refs" not in check:
            check["source_refs"] = []
        if not isinstance(check["source_refs"], list):
            raise ValueError(f"node check {check_id} source_refs must be a list")
        check["required"] = check.get("required") is True

    for key in ("concepts", "decision_rules", "extraction_warnings"):
        if key not in normalized:
            normalized[key] = []
        if not isinstance(normalized[key], list):
            raise ValueError(f"{key} must be a list")
    if "source_documents" in normalized and not isinstance(
        normalized["source_documents"], list
    ):
        raise ValueError("source_documents must be a list")

    _normalize_graph_review(normalized)

    return normalized


def normalize_graph_observation_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("observation payload must be an object")
    normalized = _value(payload)
    symbol = _text(normalized.get("symbol"))
    if not symbol:
        raise ValueError("observation symbol is required")
    symbol = symbol.upper()
    if not _SYMBOL_RE.match(symbol):
        raise ValueError("observation symbol is invalid")
    if "observations" not in normalized or not isinstance(
        normalized.get("observations"), dict
    ):
        raise ValueError("observations must be an object")
    normalized["symbol"] = symbol
    return normalized
