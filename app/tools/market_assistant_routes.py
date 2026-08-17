import re
from typing import Literal
from typing import NoReturn

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError

from app.tools.market_assistant_evidence_detail_registry import DETAIL_TOPICS
from app.tools.market_assistant_evidence_detail_registry import (
    match_evidence_detail_question,
)

ROUTE_IDS = (
    "current_setup_overview",
    "why_macro_regime",
    "why_market_confirmation",
    "why_portfolio_posture",
    "indicator_confirmation",
    "indicator_definition",
    "indicator_method",
    "evidence_detail",
    "react",
)

_REACT_ROUTE_ID = "react"

_INDICATOR_ROUTE_IDS = frozenset(
    {"indicator_confirmation", "indicator_definition", "indicator_method"}
)

_VIEW_TYPE_IDS = (
    "setup_explanation",
    "indicator_explanation",
    "method_explanation",
    "evidence_detail",
    "react_anchor",
)

_OPERATION_IDS = (
    "get_setup_overview",
    "get_macro_regime_explanation",
    "get_confirmation_tests",
    "get_posture_explanation",
    "get_approved_counterfactuals",
    "get_indicator_confirmation",
    "get_indicator_definition",
    "get_indicator_method",
    "get_evidence_detail",
)

_SUPPLEMENTARY_TOOL_IDS = (
    "get_indicator_current",
    "get_indicator_definition",
    "get_indicator_method",
    "query_indicator_history",
)

_STANDARD_BUDGET = {
    "max_rounds": 2,
    "max_parallel_calls": 4,
    "max_tool_calls": 8,
    "max_tool_result_bytes": 32 * 1024,
    "deadline_seconds": 90.0,
}

_DEEP_ANALYSIS_BUDGET = {
    "max_rounds": 4,
    "max_parallel_calls": 4,
    "max_tool_calls": 12,
    "max_tool_result_bytes": 96 * 1024,
    "deadline_seconds": 300.0,
}

_BUDGETS = {False: _STANDARD_BUDGET, True: _DEEP_ANALYSIS_BUDGET}

_ROUTE_OPERATIONS = {
    "current_setup_overview": (
        "get_setup_overview",
        "get_macro_regime_explanation",
        "get_confirmation_tests",
        "get_posture_explanation",
        "get_approved_counterfactuals",
    ),
    "why_macro_regime": ("get_macro_regime_explanation",),
    "why_market_confirmation": ("get_confirmation_tests",),
    "why_portfolio_posture": ("get_posture_explanation",),
    "indicator_confirmation": ("get_indicator_confirmation",),
    "indicator_definition": ("get_indicator_definition",),
    "indicator_method": ("get_indicator_method",),
    "evidence_detail": ("get_evidence_detail",),
    "react": (),
}

_SUPPLEMENTARY_TOOLS = {
    "current_setup_overview": (
        "get_indicator_current",
        "get_indicator_definition",
        "get_indicator_method",
    ),
    "why_macro_regime": ("get_indicator_current", "get_indicator_definition"),
    "why_market_confirmation": ("get_indicator_current", "get_indicator_definition"),
    "why_portfolio_posture": ("get_indicator_current", "get_indicator_definition"),
    "indicator_confirmation": (
        "get_indicator_definition",
        "get_indicator_method",
        "query_indicator_history",
    ),
    "indicator_definition": ("get_indicator_current", "get_indicator_method"),
    "indicator_method": ("get_indicator_current", "get_indicator_definition"),
    "evidence_detail": (),
    "react": (),
}

_VIEW_TYPES = {
    "current_setup_overview": "setup_explanation",
    "why_macro_regime": "setup_explanation",
    "why_market_confirmation": "setup_explanation",
    "why_portfolio_posture": "setup_explanation",
    "indicator_confirmation": "indicator_explanation",
    "indicator_definition": "indicator_explanation",
    "indicator_method": "method_explanation",
    "evidence_detail": "evidence_detail",
    "react": "react_anchor",
}

_INDICATOR_ALIASES = (
    ("ism manufacturing pmi", "ism_manufacturing_pmi"),
    ("ism pmi", "ism_manufacturing_pmi"),
    ("ism", "ism_manufacturing_pmi"),
    ("m2 money stock", "m2_money_stock"),
    ("m2", "m2_money_stock"),
    ("s&p 500", "sp500_close"),
    ("sp 500", "sp500_close"),
    ("vix", "vix"),
    ("credit conditions", "credit_conditions"),
    ("信贷", "credit_conditions"),
    ("信用状况", "credit_conditions"),
)

_EXPLANATION_TOPICS = (
    ("why_macro_regime", ("宏观", "macro regime", "macro environment")),
    ("why_market_confirmation", ("确认", "market confirmation", "confirmation")),
    (
        "why_portfolio_posture",
        (
            "组合",
            "仓位",
            "持仓",
            "偏积极",
            "portfolio posture",
            "posture",
            "risk-on",
            "mild risk on",
        ),
    ),
)

_OVERVIEW_MARKERS = (
    "现在市场怎么样",
    "市场现在怎么样",
    "目前市场怎么样",
    "市场情况怎么样",
    "当前市场情况",
    "市场情况如何",
    "解释当前",
    "解释市场状态",
    "解释市场情况",
    "现在行情怎么样",
    "行情如何",
    "how is the market",
    "how is the current market",
    "what is the current market",
    "current market setup",
    "market setup overview",
    "what is the market doing",
    "how does the market look",
    "explain the current",
    "explain the market setup",
    "explain the current setup",
    "explain the setup",
    "explain the market situation",
    "explain the current market situation",
    "what is the market setup",
)

_CONFIRMATION_MARKERS = (
    "确认",
    "确认信号",
    "confirmation",
    "confirm",
)

_DEFINITION_MARKERS = (
    "是什么",
    "什么是",
    "的定义",
    "定义",
    "what is",
    "what does",
    "define",
    "definition of",
    "meaning of",
)

_METHOD_MARKERS = (
    "怎么计算",
    "如何计算",
    "计算方法",
    "计算公式",
    "calculated",
    "calculation",
    "formula",
    "measured",
    "measurement",
)

_HISTORY_MARKERS = (
    "历史",
    "过去",
    "最近",
    "走势",
    "变化",
    "history",
    "historical",
    "recent",
    "recently",
    "six months",
    "over the last",
    "over the past",
    "changed",
    "changes",
    "trend",
)

_COMPARISON_MARKERS = (
    "比较",
    "对比",
    "compare",
    "comparison",
    "comparing",
    "versus",
    "relationship",
    "关系",
    "相关",
)

_SOURCE_MARKERS = (
    "来源",
    "数据来源",
    "source",
    "comes from",
    "come from",
    "where does",
    "where do",
)


class _Budget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_rounds: int
    max_parallel_calls: int
    max_tool_calls: int
    max_tool_result_bytes: int
    deadline_seconds: float


class _RouteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation_id: Literal[*_OPERATION_IDS]
    indicator_id: str | None = Field(default=None, min_length=1)
    fact_id: str | None = Field(default=None, min_length=1)
    topics: list[Literal[*DETAIL_TOPICS]] | None = Field(default=None, min_length=1)


class _RouteSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    route_id: Literal[*ROUTE_IDS]
    routing_source: Literal["deterministic", "react"]
    initial_operations: list[_RouteOperation]
    supplementary_tools: list[Literal[*_SUPPLEMENTARY_TOOL_IDS]]
    view_type: Literal[*_VIEW_TYPE_IDS]
    budget: _Budget


def budget_for_mode(deep_analysis: bool) -> dict:
    if not isinstance(deep_analysis, bool):
        raise ValueError("deep_analysis must be a boolean")
    return dict(_BUDGETS[deep_analysis])


def route_question(question: str, *, deep_analysis: bool) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    if not isinstance(deep_analysis, bool):
        raise ValueError("deep_analysis must be a boolean")
    normalized = " ".join(question.split())
    route = _route(normalized)
    payload = _build_route_payload(route, deep_analysis)
    return validate_route(payload)


def validate_route(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("route is required")
    try:
        validated = _RouteSchema.model_validate(payload)
    except ValidationError as exc:
        _raise_route_validation_error(exc)
    route = validated.model_dump()
    _validate_route_invariants(route)
    return route


def _route(normalized):
    lowered = normalized.lower()
    compact = re.sub(r"\s+", "", normalized)
    if _is_compound_question(lowered, compact):
        return _route_match(_REACT_ROUTE_ID)
    if _is_overview_question(lowered, compact) and not _has_why_clause(
        lowered, compact
    ):
        return _route_match("current_setup_overview")
    indicator_match = _indicator_route(lowered, compact)
    if indicator_match is not None:
        return indicator_match
    route_id = _explanation_route(lowered, compact)
    if route_id is not None:
        return _route_match(route_id)
    detail_match = match_evidence_detail_question(normalized)
    if detail_match is not None:
        return _route_match(
            "evidence_detail",
            fact_id=detail_match["fact_id"],
            topics=detail_match["default_topics"],
        )
    return _route_match(_REACT_ROUTE_ID)


def _route_match(route_id, indicator_id=None, fact_id=None, topics=None):
    match = {"route_id": route_id}
    if indicator_id is not None:
        match["indicator_id"] = indicator_id
    if fact_id is not None:
        match["fact_id"] = fact_id
        match["topics"] = topics
    return match


def _explanation_route(lowered, compact):
    if "为什么" not in compact and "why" not in lowered:
        return None
    for route_id, topics in _EXPLANATION_TOPICS:
        if _contains_any(compact, lowered, topics):
            return route_id
    return None


def _is_overview_question(lowered, compact):
    return _contains_any(compact, lowered, _OVERVIEW_MARKERS)


def _has_why_clause(lowered, compact):
    return "为什么" in compact or "why" in lowered


def _is_compound_question(lowered, compact):
    if _contains_any(compact, lowered, _HISTORY_MARKERS):
        return True
    if _contains_any(compact, lowered, _COMPARISON_MARKERS):
        return True
    if _contains_any(compact, lowered, _SOURCE_MARKERS):
        return True
    return len(_matched_indicator_ids(lowered, compact)) > 1


def _indicator_route(lowered, compact):
    indicator_ids = _matched_indicator_ids(lowered, compact)
    if len(indicator_ids) != 1:
        return None
    indicator_id = indicator_ids[0]
    if _contains_any(compact, lowered, _CONFIRMATION_MARKERS):
        return _route_match("indicator_confirmation", indicator_id)
    if _contains_any(compact, lowered, _DEFINITION_MARKERS):
        return _route_match("indicator_definition", indicator_id)
    if _contains_any(compact, lowered, _METHOD_MARKERS):
        return _route_match("indicator_method", indicator_id)
    return None


def _contains_any(compact, lowered, markers):
    return any(marker in compact for marker in markers if not marker.isascii()) or any(
        marker in lowered for marker in markers if marker.isascii()
    )


def _matched_indicator_ids(lowered, compact):
    matched = []
    for alias, indicator_id in _INDICATOR_ALIASES:
        if not _alias_present(alias, lowered, compact):
            continue
        if indicator_id not in matched:
            matched.append(indicator_id)
    return matched


def _alias_present(alias, lowered, compact):
    if alias.isascii():
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")
        return pattern.search(lowered) is not None
    return alias in compact


def _build_route_payload(route, deep_analysis):
    route_id = route["route_id"]
    initial_operations = []
    for operation_id in _ROUTE_OPERATIONS[route_id]:
        operation = {"operation_id": operation_id}
        if route.get("indicator_id") is not None:
            operation["indicator_id"] = route["indicator_id"]
        if route.get("fact_id") is not None:
            operation["fact_id"] = route["fact_id"]
            operation["topics"] = route["topics"]
        initial_operations.append(operation)
    return {
        "route_id": route_id,
        "routing_source": _routing_source(route_id),
        "initial_operations": initial_operations,
        "supplementary_tools": list(_SUPPLEMENTARY_TOOLS[route_id]),
        "view_type": _VIEW_TYPES[route_id],
        "budget": budget_for_mode(deep_analysis),
    }


def _routing_source(route_id):
    return "react" if route_id == _REACT_ROUTE_ID else "deterministic"


def _raise_route_validation_error(exc) -> NoReturn:
    errors = exc.errors()
    error_types = {error["type"] for error in errors}
    if "extra_forbidden" in error_types:
        raise ValueError("extra route fields are not permitted")
    for error in errors:
        if error["type"] == "missing":
            raise ValueError(f"route is missing required field: {error['loc'][0]}")
        if "initial_operations" in error["loc"]:
            raise ValueError("route initial operations are invalid")
        if "supplementary_tools" in error["loc"]:
            raise ValueError("route supplementary tools are unknown")
        if "budget" in error["loc"]:
            raise ValueError("route budget is invalid")
        field = error["loc"][0]
        if field == "route_id":
            raise ValueError("route id is unknown")
        if field == "routing_source":
            raise ValueError("routing source is unknown")
        if field == "view_type":
            raise ValueError("route view type is unknown")
    raise ValueError("route is invalid")


def _validate_route_invariants(route):
    if route["route_id"] == _REACT_ROUTE_ID:
        if route["routing_source"] != "react":
            raise ValueError("react route must use react routing source")
        if route["initial_operations"]:
            raise ValueError("react route has no initial operations")
        return
    if route["routing_source"] != "deterministic":
        raise ValueError("fast path route must use deterministic routing source")
    if not route["initial_operations"]:
        raise ValueError("fast path route requires initial operations")
    _validate_operation_detail_fields(route)
    if route["route_id"] == "evidence_detail":
        if len(route["initial_operations"]) != 1:
            raise ValueError(
                "evidence detail route requires exactly one initial operation"
            )
        if route["initial_operations"][0]["operation_id"] != "get_evidence_detail":
            raise ValueError(
                "evidence detail route requires the evidence detail operation"
            )


def _validate_operation_detail_fields(route):
    for operation in route["initial_operations"]:
        if operation["operation_id"] == "get_evidence_detail":
            if route["route_id"] != "evidence_detail":
                raise ValueError(
                    "evidence detail operation requires the evidence detail route"
                )
            if operation.get("fact_id") is None or operation.get("topics") is None:
                raise ValueError(
                    "evidence detail operation requires fact id and topics"
                )
            continue
        if operation.get("fact_id") is not None or operation.get("topics") is not None:
            raise ValueError("detail fields are only valid on the detail operation")
