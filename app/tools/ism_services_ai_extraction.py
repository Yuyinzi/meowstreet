import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


SERVICES_SERIES_IDS = frozenset(
    {
        "ism_services_pmi",
        "ism_services_business_activity",
        "ism_services_new_orders",
        "ism_services_employment",
        "ism_services_supplier_deliveries",
        "ism_services_inventories",
        "ism_services_inventory_sentiment",
        "ism_services_prices",
        "ism_services_order_backlog",
        "ism_services_new_export_orders",
        "ism_services_imports",
    }
)

ServicesSignalType = Literal[
    "overall_growth",
    "overall_contraction",
    "business_activity",
    "new_orders",
    "employment",
    "supplier_deliveries",
    "inventories",
    "inventory_sentiment",
    "prices",
    "backlog",
    "new_export_orders",
    "imports",
]

ServicesDirection = Literal[
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

ServicesCommodityDirection = Literal[
    "up_in_price",
    "down_in_price",
    "short_supply",
]


class ServicesReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    report_month: str
    title: str
    source_name: str
    source_url: str


class ServicesAtAGlanceRowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_id: str
    label: str
    current_value: float
    previous_value: float
    point_change: float
    direction: str
    rate_of_change: str
    trend_months: int = Field(ge=0)


_SERVICES_GROUPED_DIRECTIONS_BY_SIGNAL_TYPE = {
    "overall_growth": {"growth"},
    "overall_contraction": {"contraction"},
    "business_activity": {"growth", "decrease"},
    "new_orders": {"growth", "decrease"},
    "employment": {"growth", "decrease"},
    "supplier_deliveries": {"slower", "faster"},
    "inventories": {"higher", "lower"},
    "inventory_sentiment": {"too_high", "too_low"},
    "prices": {"increase", "decrease"},
    "backlog": {"higher", "lower"},
    "new_export_orders": {"growth", "decrease"},
    "imports": {"higher", "lower"},
}


class ServicesIndustrySignalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: ServicesSignalType
    direction: ServicesDirection
    industry: str
    rank: int = Field(ge=1)
    source_excerpt: str

    @model_validator(mode="after")
    def validate_direction(self):
        allowed = _SERVICES_GROUPED_DIRECTIONS_BY_SIGNAL_TYPE.get(self.signal_type)
        if allowed and self.direction not in allowed:
            raise ValueError(
                f"direction {self.direction} is invalid for {self.signal_type}"
            )
        return self


class ServicesRespondentCommentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry: str
    comment_text: str


class ServicesCommoditySignalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commodity: str
    signal_type: ServicesCommodityDirection
    months: int | None = Field(default=None, ge=1)


class ServicesNarrativeFactsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consecutive_expansion_months: int | None = None
    services_economy_gdp_share_percent: float | None = None
    broad_based_expansion_mentioned: bool = False
    inflationary_pressure_mentioned: bool = False


class ServicesFactualExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ServicesReportModel
    at_a_glance_rows: list[ServicesAtAGlanceRowModel]
    industry_signals: list[ServicesIndustrySignalModel]
    respondent_comments: list[ServicesRespondentCommentModel]
    commodities: list[ServicesCommoditySignalModel]
    narrative_facts: ServicesNarrativeFactsModel

    @model_validator(mode="after")
    def validate_component_coverage(self):
        if len(self.at_a_glance_rows) != 11:
            raise ValueError("at_a_glance_rows must contain exactly 11 rows")
        series_ids = {row.series_id for row in self.at_a_glance_rows}
        if series_ids != SERVICES_SERIES_IDS:
            raise ValueError(
                "at_a_glance_rows series ids do not match required services ISM metrics"
            )
        if not self.report.report_id.startswith("ism_services_"):
            raise ValueError(
                f"report_id must start with ism_services_, got {self.report.report_id}"
            )
        return self


class ServicesReportSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ServicesReportModel


class ServicesAtAGlanceSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_a_glance_rows: list[ServicesAtAGlanceRowModel]

    @model_validator(mode="after")
    def validate_component_coverage(self):
        if len(self.at_a_glance_rows) != 11:
            raise ValueError("at_a_glance_rows must contain exactly 11 rows")
        series_ids = {row.series_id for row in self.at_a_glance_rows}
        if series_ids != SERVICES_SERIES_IDS:
            raise ValueError(
                "at_a_glance_rows series ids do not match required services ISM metrics"
            )
        return self


class ServicesIndustrySignalsSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry_signals: list[ServicesIndustrySignalModel]


class ServicesCommentsCommoditiesSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    respondent_comments: list[ServicesRespondentCommentModel]
    commodities: list[ServicesCommoditySignalModel]


class ServicesNarrativeFactsSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative_facts: ServicesNarrativeFactsModel


SECTION_PROMPT_VERSIONS = {
    "report": "ism-services-report-v1",
    "at_a_glance_rows": "ism-services-glance-v1",
    "industry_signals": "ism-services-industries-v1",
    "comments_commodities": "ism-services-comments-v1",
    "narrative_facts": "ism-services-narrative-v1",
}

SECTION_RESPONSE_MODELS = {
    "report": ServicesReportSectionModel,
    "at_a_glance_rows": ServicesAtAGlanceSectionModel,
    "industry_signals": ServicesIndustrySignalsSectionModel,
    "comments_commodities": ServicesCommentsCommoditiesSectionModel,
    "narrative_facts": ServicesNarrativeFactsSectionModel,
}

FACTUAL_SECTION_NAMES = list(SECTION_PROMPT_VERSIONS.keys())


def validate_section_payload(section_name, payload, source_text):
    model_cls = SECTION_RESPONSE_MODELS.get(section_name)
    if model_cls is None:
        raise ValueError(f"unknown section: {section_name}")
    try:
        validated = model_cls.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    dumped = validated.model_dump()
    normalized_source = re.sub(r"\s+", " ", source_text).lower()
    for value in _collect_excerpts(dumped):
        if value and re.sub(r"\s+", " ", value).lower() not in normalized_source:
            raise ValueError(
                f"source excerpt for {section_name} not found in source text"
            )
    return dumped


def _collect_excerpts(payload):
    excerpts = []
    if isinstance(payload, dict):
        for v in payload.values():
            excerpts.extend(_collect_excerpts(v))
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "source_excerpt" in item:
                excerpts.append(item["source_excerpt"])
            excerpts.extend(_collect_excerpts(item))
    return excerpts


def assemble_factual_extraction(section_payloads):
    by_name = {sp["section_name"]: sp["payload"] for sp in section_payloads}
    missing = [name for name in FACTUAL_SECTION_NAMES if name not in by_name]
    if missing:
        raise ValueError(f"missing factual sections: {', '.join(missing)}")
    payload = {}
    for section_name in FACTUAL_SECTION_NAMES:
        payload.update(by_name[section_name])
    report_ids = {
        sp["payload"].get("report", {}).get("report_id")
        for sp in section_payloads
        if "report" in sp.get("payload", {})
    }
    if len(report_ids) > 1:
        raise ValueError(f"inconsistent report_id across sections: {report_ids}")
    try:
        validated = ServicesFactualExtractionModel.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return validated.model_dump()


def _build_prompt_intro(section_name, excerpt):
    return (
        f"You are extracting structured data from an ISM Services PMI report section.\n"
        f"Extract only explicit facts found in the excerpt below.\n"
        f"Do not infer classifications or add information not present.\n"
        f"Return empty lists or null for absent facts.\n"
        f"Section: {section_name}\n\n"
        f"Excerpt:\n{excerpt}\n"
    )


def build_report_prompt(excerpt):
    return (
        _build_prompt_intro("report", excerpt)
        + "\nExtract the report identity:\n"
        + '{"report": {"report_id": "ism_services_YYYY_MM", "report_month": "YYYY-MM-01", "title": "...", "source_name": "ismworld or prnewswire", "source_url": "..."}}'
    )


def build_at_a_glance_prompt(excerpt):
    return (
        _build_prompt_intro("at_a_glance_rows", excerpt)
        + "\nExtract all 11 at-a-glance rows. Allowed series_ids:\n"
        + ", ".join(sorted(SERVICES_SERIES_IDS))
        + '\n\n{"at_a_glance_rows": [{"series_id": "...", "label": "...", "current_value": 0.0, "previous_value": 0.0, "point_change": 0.0, "direction": "...", "rate_of_change": "...", "trend_months": 0}]}'
    )


def build_industry_signals_prompt(excerpt):
    return (
        _build_prompt_intro("industry_signals", excerpt)
        + "\nExtract industry signals. Allowed signal_types:\n"
        + "overall_growth, overall_contraction, business_activity, new_orders, employment, supplier_deliveries, inventories, inventory_sentiment, prices, backlog, new_export_orders, imports\n"
        + 'Include a "source_excerpt" for each signal with the exact sentence it came from.\n'
        + '\n{"industry_signals": [{"signal_type": "...", "direction": "growth|contraction|higher|lower|increase|decrease|slower|faster|too_low|too_high|no_change", "industry": "...", "rank": 1, "source_excerpt": "..."}]}'
    )


def build_comments_commodities_prompt(excerpt):
    return (
        _build_prompt_intro("comments_commodities", excerpt)
        + "\nExtract respondent comments and commodity signals:\n"
        + '{"respondent_comments": [{"industry": "...", "comment_text": "..."}], "commodities": [{"commodity": "...", "signal_type": "up_in_price|down_in_price|short_supply", "months": null}]}'
    )


def build_narrative_facts_prompt(excerpt):
    return (
        _build_prompt_intro("narrative_facts", excerpt)
        + "\nExtract narrative facts about the services economy:\n"
        + '{"narrative_facts": {"consecutive_expansion_months": null, "services_economy_gdp_share_percent": null, "broad_based_expansion_mentioned": false, "inflationary_pressure_mentioned": false}}'
    )


BUILD_PROMPT_FOR_SECTION = {
    "report": build_report_prompt,
    "at_a_glance_rows": build_at_a_glance_prompt,
    "industry_signals": build_industry_signals_prompt,
    "comments_commodities": build_comments_commodities_prompt,
    "narrative_facts": build_narrative_facts_prompt,
}
