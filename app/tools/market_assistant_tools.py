import json
from typing import Annotated
from typing import Literal
from typing import Union

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import TypeAdapter
from pydantic import ValidationError
from pydantic import field_validator
from pydantic import model_validator

from app.tools.market_assistant_evidence_detail_registry import DETAIL_TOPICS
from app.tools.market_assistant_evidence_detail_registry import EVIDENCE_DETAIL_FACT_IDS
from app.tools.market_assistant_evidence_detail_registry import (
    evidence_detail_tool_catalog,
)
from app.tools.market_assistant_exploration import STATISTIC_IDS
from app.tools.market_assistant_plans import _ALLOWED_INDICATOR_IDS
from app.tools.market_assistant_plans import _CompareSnapshotsParams
from app.tools.market_assistant_plans import _ConfirmationTestParams
from app.tools.market_assistant_plans import _ConfirmationTestsParams
from app.tools.market_assistant_plans import _EmptyParams
from app.tools.market_assistant_plans import _HISTORY_WINDOWS
from app.tools.market_assistant_plans import _IndicatorKnowledgeParams
from app.tools.market_assistant_plans import _ISO_DATE
from app.tools.market_assistant_plans import _ResearchParams

TOOL_IDS = (
    "get_setup_overview",
    "get_macro_regime_explanation",
    "get_confirmation_test",
    "get_confirmation_tests",
    "get_posture_explanation",
    "get_approved_counterfactuals",
    "get_indicator_knowledge",
    "query_indicator_history",
    "compare_snapshots",
    "get_indicator_current",
    "get_indicator_definition",
    "get_indicator_method",
    "get_evidence_detail",
    "research_focused",
    "research_standard",
    "research_deep",
    "get_portfolio_method",
    "portfolio_query",
)

_EVIDENCE_DETAIL_CATALOG_CACHE = None


def _evidence_detail_catalog():
    global _EVIDENCE_DETAIL_CATALOG_CACHE
    if _EVIDENCE_DETAIL_CATALOG_CACHE is None:
        _EVIDENCE_DETAIL_CATALOG_CACHE = evidence_detail_tool_catalog()
    return _EVIDENCE_DETAIL_CATALOG_CACHE


class _ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _IndicatorIdArguments(_ToolArguments):
    indicator_id: Literal[*_ALLOWED_INDICATOR_IDS]


class _HistoryArguments(_ToolArguments):
    indicator_id: Literal[*_ALLOWED_INDICATOR_IDS]
    window: Literal[*_HISTORY_WINDOWS] | None = None
    start: _ISO_DATE | None = None
    end: _ISO_DATE | None = None
    statistics: list[Literal[*STATISTIC_IDS]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_history_arguments(self):
        has_window = self.window is not None
        has_start = self.start is not None
        has_end = self.end is not None
        if has_window and (has_start or has_end):
            raise ValueError("history window and dates are mutually exclusive")
        if not has_window and not (has_start and has_end):
            raise ValueError("history window or dates are required")
        return self


class _EvidenceDetailArguments(_ToolArguments):
    fact_id: Literal[*EVIDENCE_DETAIL_FACT_IDS]
    topics: list[Literal[*DETAIL_TOPICS]] = Field(min_length=1, max_length=4)

    @field_validator("topics")
    @classmethod
    def _validate_unique_topics(cls, topics):
        if len(topics) != len(set(topics)):
            raise ValueError("evidence detail topics are duplicated")
        return topics


class _ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    call_id: str = Field(min_length=1)

    @field_validator("call_id")
    @classmethod
    def _validate_call_id(cls, call_id):
        if not call_id.strip():
            raise ValueError("call id is empty")
        return call_id


class _GetSetupOverviewCall(_ToolCallRecord):
    tool_name: Literal["get_setup_overview"]
    arguments: _EmptyParams


class _GetMacroRegimeExplanationCall(_ToolCallRecord):
    tool_name: Literal["get_macro_regime_explanation"]
    arguments: _EmptyParams


class _GetConfirmationTestCall(_ToolCallRecord):
    tool_name: Literal["get_confirmation_test"]
    arguments: _ConfirmationTestParams


class _GetConfirmationTestsCall(_ToolCallRecord):
    tool_name: Literal["get_confirmation_tests"]
    arguments: _ConfirmationTestsParams


class _GetPostureExplanationCall(_ToolCallRecord):
    tool_name: Literal["get_posture_explanation"]
    arguments: _EmptyParams


class _GetApprovedCounterfactualsCall(_ToolCallRecord):
    tool_name: Literal["get_approved_counterfactuals"]
    arguments: _EmptyParams


class _GetIndicatorKnowledgeCall(_ToolCallRecord):
    tool_name: Literal["get_indicator_knowledge"]
    arguments: _IndicatorKnowledgeParams


class _QueryIndicatorHistoryCall(_ToolCallRecord):
    tool_name: Literal["query_indicator_history"]
    arguments: _HistoryArguments


class _CompareSnapshotsCall(_ToolCallRecord):
    tool_name: Literal["compare_snapshots"]
    arguments: _CompareSnapshotsParams


class _GetIndicatorCurrentCall(_ToolCallRecord):
    tool_name: Literal["get_indicator_current"]
    arguments: _IndicatorIdArguments


class _GetIndicatorDefinitionCall(_ToolCallRecord):
    tool_name: Literal["get_indicator_definition"]
    arguments: _IndicatorIdArguments


class _GetIndicatorMethodCall(_ToolCallRecord):
    tool_name: Literal["get_indicator_method"]
    arguments: _IndicatorIdArguments


class _GetEvidenceDetailCall(_ToolCallRecord):
    tool_name: Literal["get_evidence_detail"]
    arguments: _EvidenceDetailArguments


class _ResearchFocusedCall(_ToolCallRecord):
    tool_name: Literal["research_focused"]
    arguments: _ResearchParams


class _ResearchStandardCall(_ToolCallRecord):
    tool_name: Literal["research_standard"]
    arguments: _ResearchParams


class _ResearchDeepCall(_ToolCallRecord):
    tool_name: Literal["research_deep"]
    arguments: _ResearchParams


class _GetPortfolioMethodCall(_ToolCallRecord):
    tool_name: Literal["get_portfolio_method"]
    arguments: _EmptyParams


class _PortfolioQueryArguments(_ToolArguments):
    operation: Literal[
        "ticker_risk_profile",
        "portfolio_analysis",
        "pair_analysis",
        "ticker_industry_context",
        "ticker_quant_context",
    ]
    params: dict = Field(default_factory=dict)


class _PortfolioQueryCall(_ToolCallRecord):
    tool_name: Literal["portfolio_query"]
    arguments: _PortfolioQueryArguments


_ToolCallRecord = Annotated[
    Union[
        _GetSetupOverviewCall,
        _GetMacroRegimeExplanationCall,
        _GetConfirmationTestCall,
        _GetConfirmationTestsCall,
        _GetPostureExplanationCall,
        _GetApprovedCounterfactualsCall,
        _GetIndicatorKnowledgeCall,
        _QueryIndicatorHistoryCall,
        _CompareSnapshotsCall,
        _GetIndicatorCurrentCall,
        _GetIndicatorDefinitionCall,
        _GetIndicatorMethodCall,
        _GetEvidenceDetailCall,
        _ResearchFocusedCall,
        _ResearchStandardCall,
        _ResearchDeepCall,
        _GetPortfolioMethodCall,
        _PortfolioQueryCall,
    ],
    Field(discriminator="tool_name"),
]

_TOOL_CALL_ADAPTER = TypeAdapter(_ToolCallRecord)

_TOOL_ARGUMENT_MODELS = {
    "get_setup_overview": _EmptyParams,
    "get_macro_regime_explanation": _EmptyParams,
    "get_confirmation_test": _ConfirmationTestParams,
    "get_confirmation_tests": _ConfirmationTestsParams,
    "get_posture_explanation": _EmptyParams,
    "get_approved_counterfactuals": _EmptyParams,
    "get_indicator_knowledge": _IndicatorKnowledgeParams,
    "query_indicator_history": _HistoryArguments,
    "compare_snapshots": _CompareSnapshotsParams,
    "get_indicator_current": _IndicatorIdArguments,
    "get_indicator_definition": _IndicatorIdArguments,
    "get_indicator_method": _IndicatorIdArguments,
    "get_evidence_detail": _EvidenceDetailArguments,
    "research_focused": _ResearchParams,
    "research_standard": _ResearchParams,
    "research_deep": _ResearchParams,
    "get_portfolio_method": _EmptyParams,
    "portfolio_query": _PortfolioQueryArguments,
}

ALL_TOOL_IDS = tuple(_TOOL_ARGUMENT_MODELS)

_TOOL_DESCRIPTIONS = {
    "get_setup_overview": "read the current market setup overview. Start here for any market-environment question: the snapshot anchor already contains the current conclusions, and this returns the compact overview. Prefer it over drilling into individual evidence facts",
    "get_macro_regime_explanation": "read the current macro regime explanation. Use only when the overview does not give enough macro regime detail",
    "get_confirmation_test": "read one market confirmation test result (equity, credit, or vix). Prefer get_confirmation_tests when you need more than one test",
    "get_confirmation_tests": "read several market confirmation test results in one call. Prefer this over repeated get_confirmation_test calls",
    "get_posture_explanation": "read the current portfolio posture explanation. Use only when the overview does not give enough posture detail",
    "get_approved_counterfactuals": "read approved counterfactuals for the current setup, e.g. what would change if a confirmation test flipped",
    "get_indicator_knowledge": "read approved definition, method, or source knowledge for an indicator. Documentation only; it does not return current values",
    "query_indicator_history": "query local accepted history for one indicator over a window or date range. Not for the current setup state",
    "compare_snapshots": "compare two market setup snapshots to explain what changed between them",
    "get_indicator_current": "read the current registered value of one indicator",
    "get_indicator_definition": "read the approved definition of a registered indicator",
    "get_indicator_method": "read the approved calculation method of a registered indicator",
    "get_evidence_detail": "drill into ONE specific market setup fact by fact_id. Use only to inspect a particular fact in depth; never for a broad overview, and never call the same fact_id again with a different topic combination",
    "research_focused": "run a focused external web research search. External results are background only and never override the local snapshot; requires the user to enable external search",
    "research_standard": "run a standard external web research search. External results are background only and never override the local snapshot; requires the user to enable external search",
    "research_deep": "run a deep external web research search. External results are background only and never override the local snapshot; requires the user to enable external search and deep research",
    "get_portfolio_method": "read the portfolio methodology knowledge and the portfolio_query operation contracts. MUST be called before the first portfolio_query",
    "portfolio_query": "run one deterministic ticker or portfolio operation: ticker_risk_profile, portfolio_analysis, pair_analysis, ticker_industry_context, or ticker_quant_context. Read get_portfolio_method first for the params contracts. Never repeat an identical call; if a symbol comes back unavailable, retry once with the single most likely corrected symbol",
}


def validate_tool_call(payload):
    if not isinstance(payload, dict):
        raise ValueError("tool call is invalid")
    try:
        validated = _TOOL_CALL_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise ValueError("tool call is invalid") from exc
    return validated.model_dump()


def tool_definitions(tool_ids):
    if not isinstance(tool_ids, list):
        raise ValueError("tool ids are required")
    catalog = _evidence_detail_catalog()
    definitions = []
    for tool_id in tool_ids:
        parameter_model = _TOOL_ARGUMENT_MODELS.get(tool_id)
        if parameter_model is None:
            raise ValueError(f"tool is not registered: {tool_id}")
        parameters = parameter_model.model_json_schema()
        description = _TOOL_DESCRIPTIONS[tool_id]
        if tool_id == "get_evidence_detail":
            description = f"{description}\n\n{catalog}"
        definitions.append(
            {
                "type": "function",
                "name": tool_id,
                "description": description,
                "parameters": parameters,
            }
        )
    return definitions


def normalized_tool_call_key(call):
    if not isinstance(call, dict):
        raise ValueError("tool call is invalid")
    tool_name = call.get("tool_name")
    arguments = call.get("arguments")
    if not isinstance(tool_name, str) or not isinstance(arguments, dict):
        raise ValueError("tool call is invalid")
    return json.dumps(
        {"tool_name": tool_name, "arguments": _sorted_arguments(arguments)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sorted_arguments(value):
    if isinstance(value, dict):
        return {key: _sorted_arguments(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_sorted_arguments(item) for item in value]
    return value
