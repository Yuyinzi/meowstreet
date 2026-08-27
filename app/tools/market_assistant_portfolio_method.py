import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError
from pydantic import model_validator

from app.resources import resource_path

KNOWLEDGE_PATH = resource_path("portfolio_method")

OPERATION_IDS = (
    "ticker_risk_profile",
    "portfolio_analysis",
    "pair_analysis",
    "ticker_industry_context",
    "ticker_quant_context",
)


class _OperationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal[*OPERATION_IDS]
    summary: str = Field(min_length=1)
    params_contract: str = Field(min_length=1)


class _PortfolioMethodKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    operations: list[_OperationContract] = Field(min_length=len(OPERATION_IDS))
    interpretation_guide: str = Field(min_length=1)
    interaction_rules: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_operation_coverage(self):
        covered = sorted(entry.operation for entry in self.operations)
        if covered != sorted(OPERATION_IDS):
            raise ValueError(
                "operations must cover each portfolio operation exactly once"
            )
        return self


def load_portfolio_method_knowledge(path=KNOWLEDGE_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        validated = _PortfolioMethodKnowledge.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("portfolio method knowledge is invalid") from exc
    return validated.model_dump()


class _TickerRiskParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    symbol: str = Field(min_length=1)


class _PositionParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    symbol: str = Field(min_length=1)
    side: Literal["long", "short"]
    allocation: float = Field(gt=0)


class _PortfolioAnalysisParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    positions: list[_PositionParams] = Field(min_length=1)
    margin_capital: float | None = Field(default=None, gt=0)
    declared_bias: Literal["long", "short", "neutral"] | None = None
    instrument: Literal["options", "cfd", "us_stock"] | None = None


class _PairAnalysisParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    long_symbol: str = Field(min_length=1)
    short_symbol: str = Field(min_length=1)
    sessions: int | None = Field(default=None, ge=2, le=260)


class _TickerContextParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    symbol: str = Field(min_length=1)


class _TickerQuantContextParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    symbol: str = Field(min_length=1)
    peer: str | None = Field(default=None, min_length=1)


_OPERATION_PARAM_MODELS = {
    "ticker_risk_profile": _TickerRiskParams,
    "portfolio_analysis": _PortfolioAnalysisParams,
    "pair_analysis": _PairAnalysisParams,
    "ticker_industry_context": _TickerContextParams,
    "ticker_quant_context": _TickerQuantContextParams,
}


def validate_operation_params(operation, params):
    model = _OPERATION_PARAM_MODELS.get(operation)
    if model is None:
        raise ValueError(f"unknown portfolio operation: {operation}")
    if not isinstance(params, dict):
        raise ValueError("portfolio query params must be an object")
    try:
        validated = model.model_validate(params)
    except ValidationError as exc:
        raise ValueError(
            f"portfolio query params are invalid: {_concise_errors(exc)}"
        ) from exc
    return validated.model_dump(exclude_none=True)


def _concise_errors(exc):
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error["loc"]) or "params"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)
