import re
from datetime import date
from typing import Annotated
from typing import Literal
from typing import NoReturn
from typing import Union

from pydantic import AfterValidator
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import TypeAdapter
from pydantic import ValidationError
from pydantic import field_validator

from app.tools.market_assistant_exploration import STATISTIC_IDS

_OPERATIONS = {
    "resolve_current_explanation",
    "get_historical_snapshot",
    "get_snapshot_object",
    "get_counterfactuals",
    "compare_snapshots",
    "get_indicator_definition",
    "get_indicator_method",
    "get_indicator_source",
    "get_indicator_current",
    "query_indicator_history",
    "compare_indicator_periods",
    "query_release_history",
    "research_focused",
    "research_standard",
    "research_deep",
    "get_setup_overview",
    "get_macro_regime_explanation",
    "get_confirmation_test",
    "get_confirmation_tests",
    "get_posture_explanation",
    "get_approved_counterfactuals",
    "get_indicator_knowledge",
}

_INTENTS = (
    "decision_explanation",
    "current_evidence",
    "definition",
    "method",
    "source",
    "governance",
    "counterfactual",
    "local_current",
    "local_history",
    "local_comparison",
    "release_history",
    "historical_snapshot",
    "snapshot_comparison",
    "illustration",
    "external_research",
)

_HISTORICAL_INTENTS = frozenset({"historical_snapshot", "snapshot_comparison"})

_RESEARCH_OPERATION_TIERS = {
    "research_focused": "focused",
    "research_standard": "standard",
    "research_deep": "deep",
}

_ALLOWED_INDICATOR_IDS = (
    "vix",
    "ism_manufacturing_pmi",
    "sp500_close",
    "m2_money_stock",
    "credit_conditions",
    "initial_claims_sa",
    "continuing_claims_sa",
)

_TEST_IDS = ("equity", "credit", "vix")

_KNOWLEDGE_TOPICS = ("definition", "method", "source")

_HISTORY_WINDOWS = ("1m", "3m", "6m", "1y")

_QUERY_FORBIDDEN_RE = re.compile(
    r"https?://|api_key|password|token|secret|;|\$\(|`|&&|\|\||[|><\n]",
    re.IGNORECASE,
)

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_INDICATOR_ALIASES = (
    ("ism manufacturing pmi", "ism_manufacturing_pmi"),
    ("continuing claims", "continuing_claims_sa"),
    ("initial claims", "initial_claims_sa"),
    ("jobless claims", "initial_claims_sa"),
    ("m2 money stock", "m2_money_stock"),
    ("ism pmi", "ism_manufacturing_pmi"),
    ("s&p 500", "sp500_close"),
    ("sp 500", "sp500_close"),
    ("m2", "m2_money_stock"),
    ("credit conditions", "credit_conditions"),
    ("信贷条件", "credit_conditions"),
    ("信贷", "credit_conditions"),
    ("信用状况", "credit_conditions"),
    ("vix", "vix"),
    ("ism", "ism_manufacturing_pmi"),
)

_SEARCH_MARKERS = (
    "search",
    "verify",
    "find the latest",
    "check the latest",
    "look up the latest",
    "what is the latest",
    "what does the latest",
    "latest report",
)

_HISTORY_MARKERS = (
    "history",
    "trend",
    "past ",
    "between",
    "since",
    "历史",
    "走势",
    "变化",
    "之间",
    "以来",
)

_SOURCE_MARKERS = ("source of", "where does", "come from", "origin of")

_METHOD_MARKERS = ("formula", "calculated", "method", "how does", "how is", "measured")

_DECISION_QUESTION_PREFIXES = (
    "why is the current setup",
    "why is the current market setup",
    "why this setup",
    "explain the market setup",
    "explain the current market setup",
)


def _valid_iso_date(value):
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be an iso calendar date") from exc
    return value


_ISO_DATE = Annotated[str, AfterValidator(_valid_iso_date)]


class _OperationParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _EmptyParams(_OperationParams):
    pass


class _ContextIdParams(_OperationParams):
    context_id: str = Field(min_length=1)


class _SnapshotObjectParams(_OperationParams):
    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)


class _CompareSnapshotsParams(_OperationParams):
    context_a_id: str = Field(min_length=1)
    context_b_id: str = Field(min_length=1)


class _IndicatorIdParams(_OperationParams):
    indicator_id: str = Field(min_length=1)


class _IndicatorCurrentParams(_IndicatorIdParams):
    statistics: list[Literal[*STATISTIC_IDS]] = Field(default_factory=list)


class _IndicatorWindowParams(_IndicatorIdParams):
    start: _ISO_DATE
    end: _ISO_DATE
    statistics: list[Literal[*STATISTIC_IDS]] = Field(default_factory=list)


class _DateWindow(_OperationParams):
    start: _ISO_DATE
    end: _ISO_DATE


class _IndicatorComparisonParams(_IndicatorIdParams):
    period_a: _DateWindow
    period_b: _DateWindow
    statistics: list[Literal[*STATISTIC_IDS]] = Field(default_factory=list)


class _ResearchParams(_OperationParams):
    purpose: Literal[
        "external_context",
        "current_events",
        "historical_context",
        "source_verification",
        "document_summary",
    ]
    queries: list[str] = Field(min_length=1)
    expected_source_class: Literal[
        "official_publication",
        "news",
        "market_data",
        "financial_media",
        "academic",
    ]
    approved_domains: list[str] | None = None
    time_window: _DateWindow | None = None

    @field_validator("queries")
    @classmethod
    def _validate_queries(cls, queries):
        for query in queries:
            if not query.strip():
                raise ValueError("research query is empty")
            if _QUERY_FORBIDDEN_RE.search(query):
                raise ValueError("research query contains forbidden content")
        return queries


class _ConfirmationTestParams(_OperationParams):
    test_id: Literal[*_TEST_IDS]


class _ConfirmationTestsParams(_OperationParams):
    test_ids: list[Literal[*_TEST_IDS]] = Field(min_length=1)


class _IndicatorKnowledgeParams(_OperationParams):
    indicator_id: Literal[*_ALLOWED_INDICATOR_IDS]
    topic: Literal[*_KNOWLEDGE_TOPICS]


class _OperationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _ResolveCurrentExplanationOperation(_OperationRecord):
    operation_id: Literal["resolve_current_explanation"]
    parameters: _EmptyParams


class _GetHistoricalSnapshotOperation(_OperationRecord):
    operation_id: Literal["get_historical_snapshot"]
    parameters: _ContextIdParams


class _GetSnapshotObjectOperation(_OperationRecord):
    operation_id: Literal["get_snapshot_object"]
    parameters: _SnapshotObjectParams


class _GetCounterfactualsOperation(_OperationRecord):
    operation_id: Literal["get_counterfactuals"]
    parameters: _ContextIdParams


class _CompareSnapshotsOperation(_OperationRecord):
    operation_id: Literal["compare_snapshots"]
    parameters: _CompareSnapshotsParams


class _GetIndicatorDefinitionOperation(_OperationRecord):
    operation_id: Literal["get_indicator_definition"]
    parameters: _IndicatorIdParams


class _GetIndicatorMethodOperation(_OperationRecord):
    operation_id: Literal["get_indicator_method"]
    parameters: _IndicatorIdParams


class _GetIndicatorSourceOperation(_OperationRecord):
    operation_id: Literal["get_indicator_source"]
    parameters: _IndicatorIdParams


class _GetIndicatorCurrentOperation(_OperationRecord):
    operation_id: Literal["get_indicator_current"]
    parameters: _IndicatorCurrentParams


class _QueryIndicatorHistoryOperation(_OperationRecord):
    operation_id: Literal["query_indicator_history"]
    parameters: _IndicatorWindowParams


class _CompareIndicatorPeriodsOperation(_OperationRecord):
    operation_id: Literal["compare_indicator_periods"]
    parameters: _IndicatorComparisonParams


class _QueryReleaseHistoryOperation(_OperationRecord):
    operation_id: Literal["query_release_history"]
    parameters: _IndicatorWindowParams


class _ResearchFocusedOperation(_OperationRecord):
    operation_id: Literal["research_focused"]
    parameters: _ResearchParams


class _ResearchStandardOperation(_OperationRecord):
    operation_id: Literal["research_standard"]
    parameters: _ResearchParams


class _ResearchDeepOperation(_OperationRecord):
    operation_id: Literal["research_deep"]
    parameters: _ResearchParams


class _GetSetupOverviewOperation(_OperationRecord):
    operation_id: Literal["get_setup_overview"]
    parameters: _EmptyParams


class _GetMacroRegimeExplanationOperation(_OperationRecord):
    operation_id: Literal["get_macro_regime_explanation"]
    parameters: _EmptyParams


class _GetConfirmationTestOperation(_OperationRecord):
    operation_id: Literal["get_confirmation_test"]
    parameters: _ConfirmationTestParams


class _GetConfirmationTestsOperation(_OperationRecord):
    operation_id: Literal["get_confirmation_tests"]
    parameters: _ConfirmationTestsParams


class _GetPostureExplanationOperation(_OperationRecord):
    operation_id: Literal["get_posture_explanation"]
    parameters: _EmptyParams


class _GetApprovedCounterfactualsOperation(_OperationRecord):
    operation_id: Literal["get_approved_counterfactuals"]
    parameters: _EmptyParams


class _GetIndicatorKnowledgeOperation(_OperationRecord):
    operation_id: Literal["get_indicator_knowledge"]
    parameters: _IndicatorKnowledgeParams


_OperationRecord = Annotated[
    Union[
        _ResolveCurrentExplanationOperation,
        _GetHistoricalSnapshotOperation,
        _GetSnapshotObjectOperation,
        _GetCounterfactualsOperation,
        _CompareSnapshotsOperation,
        _GetIndicatorDefinitionOperation,
        _GetIndicatorMethodOperation,
        _GetIndicatorSourceOperation,
        _GetIndicatorCurrentOperation,
        _QueryIndicatorHistoryOperation,
        _CompareIndicatorPeriodsOperation,
        _QueryReleaseHistoryOperation,
        _ResearchFocusedOperation,
        _ResearchStandardOperation,
        _ResearchDeepOperation,
        _GetSetupOverviewOperation,
        _GetMacroRegimeExplanationOperation,
        _GetConfirmationTestOperation,
        _GetConfirmationTestsOperation,
        _GetPostureExplanationOperation,
        _GetApprovedCounterfactualsOperation,
        _GetIndicatorKnowledgeOperation,
    ],
    Field(discriminator="operation_id"),
]

_OPERATION_ADAPTER = TypeAdapter(_OperationRecord)


class TaskPlanSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    intent: Literal[*_INTENTS]
    context_mode: Literal["current", "historical"]
    operations: list[_OperationRecord] = Field(min_length=1)
    answer_depth: Literal["concise", "standard", "detailed"]
    research_tier: Literal["focused", "standard", "deep"] | None = None


def registered_operation_ids():
    return set(_OPERATIONS)


def validate_operation(operation_id, parameters):
    payload = {"operation_id": operation_id, "parameters": parameters}
    try:
        return _OPERATION_ADAPTER.validate_python(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise ValueError("operation is invalid") from exc


def validate_task_plan(payload):
    if not isinstance(payload, dict):
        raise ValueError("task plan is required")
    try:
        validated = TaskPlanSchema.model_validate(payload)
    except ValidationError as exc:
        _raise_plan_validation_error(exc)
    plan = validated.model_dump()
    _validate_cross_contract(plan)
    return plan


def _raise_plan_validation_error(exc) -> NoReturn:
    errors = exc.errors()
    error_types = {error["type"] for error in errors}
    if "extra_forbidden" in error_types:
        raise ValueError("extra inputs are not permitted")
    if "union_tag_invalid" in error_types:
        raise ValueError("task plan is invalid")
    for error in errors:
        if error["type"] == "missing":
            if "parameters" in error["loc"]:
                raise ValueError("task plan operation parameters are invalid")
            raise ValueError(f"task plan is missing required field: {error['loc'][0]}")
        if error["type"] == "too_short" and error["loc"] == ("operations",):
            raise ValueError("task plan operations are required")
        if "parameters" in error["loc"]:
            raise ValueError("task plan operation parameters are invalid")
        field = error["loc"][0]
        if field == "intent":
            raise ValueError("task plan intent is unknown")
        if field == "context_mode":
            raise ValueError("task plan context mode is unknown")
        if field == "answer_depth":
            raise ValueError("task plan answer depth is unknown")
        if field == "research_tier":
            raise ValueError("task plan research tier is unknown")
    raise ValueError("task plan is invalid")


def _validate_cross_contract(plan):
    if (
        plan["context_mode"] == "historical"
        and plan["intent"] not in _HISTORICAL_INTENTS
    ):
        raise ValueError("historical context requires historical intent")
    if plan["intent"] in _HISTORICAL_INTENTS and plan["context_mode"] != "historical":
        raise ValueError("historical intent requires historical context")
    research_tiers = [
        _RESEARCH_OPERATION_TIERS[operation["operation_id"]]
        for operation in plan["operations"]
        if operation["operation_id"] in _RESEARCH_OPERATION_TIERS
    ]
    if research_tiers:
        if plan["research_tier"] is None:
            raise ValueError("research operation requires research tier")
        if any(tier != plan["research_tier"] for tier in research_tiers):
            raise ValueError("research tier does not match research operation")


def deterministic_plan(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    lowered = question.strip().lower()
    plan = _route_question(lowered)
    if plan["intent"] == "unsupported":
        return plan
    return validate_task_plan(plan)


def _route_question(lowered):
    research_plan = _research_plan(lowered)
    if research_plan is not None:
        return research_plan
    if _is_decision_question(lowered):
        return _plan("decision_explanation", [("resolve_current_explanation", {})])
    indicator_id = _match_indicator(lowered)
    knowledge_plan = _knowledge_plan(lowered, indicator_id)
    if knowledge_plan is not None:
        return knowledge_plan
    history_plan = _history_plan(lowered, indicator_id)
    if history_plan is not None:
        return history_plan
    return _unsupported_plan()


def _research_plan(lowered):
    if "deep research" in lowered:
        return _plan_with_tier(
            "external_research",
            [("research_deep", _research_parameters(lowered))],
            "deep",
        )
    if any(marker in lowered for marker in _SEARCH_MARKERS):
        return _plan_with_tier(
            "external_research",
            [("research_focused", _research_parameters(lowered))],
            "focused",
        )
    return None


def _research_parameters(lowered):
    return {
        "purpose": "current_events",
        "queries": [lowered],
        "expected_source_class": "official_publication",
    }


def _is_decision_question(lowered):
    return lowered.startswith(_DECISION_QUESTION_PREFIXES) or lowered.startswith(
        "why is the current"
    )


def _knowledge_plan(lowered, indicator_id):
    if indicator_id is None:
        return None
    if any(marker in lowered for marker in _SOURCE_MARKERS):
        return _plan(
            "source", [("get_indicator_source", {"indicator_id": indicator_id})]
        )
    if any(marker in lowered for marker in _METHOD_MARKERS):
        return _plan(
            "method", [("get_indicator_method", {"indicator_id": indicator_id})]
        )
    if _is_definition_question(lowered):
        return _plan(
            "definition",
            [("get_indicator_definition", {"indicator_id": indicator_id})],
        )
    return None


def _is_definition_question(lowered):
    return (
        lowered.startswith("what is ")
        or lowered.startswith("what does ")
        or lowered.startswith("define ")
        or "definition of" in lowered
        or "meaning of" in lowered
    )


def _history_plan(lowered, indicator_id):
    if indicator_id is None or not any(
        marker in lowered for marker in _HISTORY_MARKERS
    ):
        return None
    window = _parse_date_window(lowered)
    if window is None:
        return None
    return _plan(
        "local_history",
        [
            (
                "query_indicator_history",
                {
                    "indicator_id": indicator_id,
                    "start": window[0],
                    "end": window[1],
                },
            )
        ],
    )


def _parse_date_window(text):
    matches = _ISO_DATE_RE.findall(text)
    if len(matches) < 2:
        return None
    start, end = matches[0], matches[1]
    try:
        if date.fromisoformat(start) <= date.fromisoformat(end):
            return (start, end)
    except ValueError:
        return None
    return None


def _match_indicator(lowered):
    for alias, indicator_id in _INDICATOR_ALIASES:
        if alias.isascii():
            matched = re.search(rf"\b{re.escape(alias)}\b", lowered)
        else:
            matched = alias in lowered
        if matched:
            return indicator_id
    return None


def _plan(intent, operations):
    return {
        "intent": intent,
        "context_mode": "current",
        "operations": [
            {"operation_id": operation_id, "parameters": parameters}
            for operation_id, parameters in operations
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }


def _plan_with_tier(intent, operations, tier):
    plan = _plan(intent, operations)
    plan["research_tier"] = tier
    return plan


def _unsupported_plan():
    return {
        "intent": "unsupported",
        "context_mode": "current",
        "operations": [],
        "answer_depth": "standard",
        "reason_code": "unsupported_request",
    }
