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

    for node in workflow_nodes:
        node_id = node["id"]
        for key in ("incoming_edges", "outgoing_edges"):
            for edge_node_id in node[key]:
                edge_node_id = _text(edge_node_id)
                if not edge_node_id:
                    raise ValueError(f"workflow node {node_id} {key} contains invalid node id")
                if edge_node_id not in node_ids:
                    raise ValueError(f"workflow node {node_id} {key} references unknown node")

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

    for key in ("source_documents", "concepts", "decision_rules", "extraction_warnings"):
        if key not in normalized:
            normalized[key] = []
        if not isinstance(normalized[key], list):
            raise ValueError(f"{key} must be a list")

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
    if "observations" not in normalized or not isinstance(normalized.get("observations"), dict):
        raise ValueError("observations must be an object")
    normalized["symbol"] = symbol
    return normalized
