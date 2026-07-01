from copy import deepcopy

from app.tools.macro_dashboard import fetch_macro_dashboard
from app.tools.market_data import fetch_market_data


def _node_tool_hooks(method):
    return {
        hook
        for node in method.get("workflow_nodes", [])
        for hook in node.get("tool_hooks", [])
    }


def _deep_merge_missing(base, incoming):
    merged = deepcopy(base)
    for key, value in incoming.items():
        if key == "symbol":
            continue
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge_missing(merged[key], value)
        elif key not in merged:
            merged[key] = deepcopy(value)
    return merged


def apply_tools(
    method, observation_payload, market_data_fetcher=fetch_market_data,
    macro_dashboard_fetcher=fetch_macro_dashboard,
):
    observations = deepcopy(observation_payload.get("observations", {}))
    hooks = _node_tool_hooks(method)
    if "market_data" in hooks:
        market_payload = market_data_fetcher(observation_payload.get("symbol"))
        observations = _deep_merge_missing(observations, market_payload)
    if "macro_dashboard" in hooks:
        macro_payload = macro_dashboard_fetcher()
        if macro_payload:
            observations = _deep_merge_missing(observations, macro_payload)
    return observations
