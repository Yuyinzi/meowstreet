from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.tools.ism_official_report import METRIC_LABELS


METRIC_LABEL_TO_SERIES_ID = {}
_SEEN_SERIES_IDS = set()
for _label, _series_id in METRIC_LABELS.items():
    if _series_id not in _SEEN_SERIES_IDS:
        _SEEN_SERIES_IDS.add(_series_id)
        METRIC_LABEL_TO_SERIES_ID[_label] = _series_id

REQUIRED_SERIES_IDS = set(METRIC_LABEL_TO_SERIES_ID.values())

SignalType = Literal[
    "overall_growth",
    "overall_contraction",
    "new_orders",
    "production",
    "employment",
    "supplier_deliveries",
    "inventories",
    "customer_inventories",
    "prices",
    "backlog",
    "new_export_orders",
    "imports",
]

Direction = Literal[
    "growth",
    "contraction",
    "higher",
    "lower",
    "increase",
    "decrease",
    "slower",
    "faster",
    "too_low",
    "too_high",
    "no_change",
]


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    report_month: str
    title: str
    source_name: str
    source_url: str


class AtAGlanceRowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_id: str
    label: str
    current_value: float
    previous_value: float
    point_change: float
    direction: str
    rate_of_change: str
    trend_months: int = Field(ge=0)

    @field_validator("series_id")
    @classmethod
    def validate_series_id(cls, value):
        if value not in REQUIRED_SERIES_IDS:
            raise ValueError(f"series id is unknown: {value}")
        return value


class IndustrySignalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: SignalType
    direction: Direction
    industry: str
    rank: int
    evidence_text: str


class RespondentCommentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry: str
    comment_text: str


class CommoditySignalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commodity: str
    signal_type: Literal["up_in_price", "down_in_price", "short_supply"]
    months: int | None = Field(default=None, ge=1)


class NarrativeFactsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturing_gdp_share_contracted_percent: float | None = None
    manufacturing_gdp_share_strong_contraction_percent: float | None = None
    pmi_implied_real_gdp_annualized_percent: float | None = None
    largest_industries_expanded: list[str] = Field(default_factory=list)


class IsmRichExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ReportModel
    at_a_glance_rows: list[AtAGlanceRowModel]
    industry_signals: list[IndustrySignalModel]
    respondent_comments: list[RespondentCommentModel]
    commodities: list[CommoditySignalModel]
    narrative_facts: NarrativeFactsModel

    @model_validator(mode="after")
    def validate_metric_set(self):
        if len(self.at_a_glance_rows) != 11:
            raise ValueError("at_a_glance_rows must contain exactly 11 rows")
        series_ids = {row.series_id for row in self.at_a_glance_rows}
        if series_ids != REQUIRED_SERIES_IDS:
            raise ValueError(
                "at_a_glance_rows series ids do not match required ISM metrics"
            )
        return self


def validate_extraction(payload):
    try:
        return IsmRichExtractionModel.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
