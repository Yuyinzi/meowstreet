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

SERVICES_SIGNAL_TYPES = frozenset(
    {
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
    }
)

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


class ServicesIndustrySignalListModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: ServicesSignalType
    direction: ServicesDirection
    declared_count: int | None = Field(default=None, ge=0)
    industries: list[str]
    evidence_text: str

    @model_validator(mode="after")
    def validate_signal_list(self):
        allowed = _SERVICES_GROUPED_DIRECTIONS_BY_SIGNAL_TYPE.get(self.signal_type)
        if allowed and self.direction not in allowed:
            raise ValueError(
                f"direction {self.direction} is invalid for {self.signal_type}"
            )
        if len(self.industries) != len(set(self.industries)):
            raise ValueError(
                f"industries are duplicated for {self.signal_type} {self.direction}"
            )
        if self.declared_count is not None and self.declared_count != len(
            self.industries
        ):
            raise ValueError(
                f"declared_count {self.declared_count} does not match "
                f"{len(self.industries)} industries for "
                f"{self.signal_type} {self.direction}"
            )
        if not self.industries and self.declared_count != 0:
            raise ValueError(
                f"empty industries require declared_count 0 for "
                f"{self.signal_type} {self.direction}"
            )
        return self


class ServicesIndustrySignalCoverageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: ServicesSignalType
    direction: ServicesDirection | Literal["unknown"]
    list_present: bool
    declared_count: int | None = Field(default=None, ge=0)
    extracted_count: int = Field(ge=0)
    validation_status: Literal["complete", "partial", "absent"]
    evidence_text: str


def _absent_signal_coverage(represented_signal_types):
    return [
        {
            "signal_type": signal_type,
            "direction": "unknown",
            "list_present": False,
            "declared_count": None,
            "extracted_count": 0,
            "validation_status": "absent",
            "evidence_text": "",
        }
        for signal_type in sorted(SERVICES_SIGNAL_TYPES - represented_signal_types)
    ]


def _normalize_grouped_industry_signals(signal_lists):
    validated_lists = [
        ServicesIndustrySignalListModel.model_validate(signal_list).model_dump()
        for signal_list in signal_lists
    ]
    keys = [
        (signal_list["signal_type"], signal_list["direction"])
        for signal_list in validated_lists
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("industry signal type and direction lists are duplicated")
    industry_signals = [
        {
            "signal_type": signal_list["signal_type"],
            "direction": signal_list["direction"],
            "industry": industry,
            "rank": rank,
            "source_excerpt": signal_list["evidence_text"],
        }
        for signal_list in validated_lists
        for rank, industry in enumerate(signal_list["industries"], start=1)
    ]
    coverage = [
        {
            "signal_type": signal_list["signal_type"],
            "direction": signal_list["direction"],
            "list_present": True,
            "declared_count": signal_list["declared_count"],
            "extracted_count": len(signal_list["industries"]),
            "validation_status": (
                "complete"
                if signal_list["declared_count"] is not None
                else "partial"
            ),
            "evidence_text": signal_list["evidence_text"],
        }
        for signal_list in validated_lists
    ]
    represented = {row["signal_type"] for row in validated_lists}
    coverage.extend(_absent_signal_coverage(represented))
    return industry_signals, coverage


def _normalize_legacy_industry_signals(industry_signals):
    groups = {}
    for signal in industry_signals:
        key = (signal["signal_type"], signal["direction"])
        groups.setdefault(key, []).append(signal)
    coverage = [
        {
            "signal_type": signal_type,
            "direction": direction,
            "list_present": True,
            "declared_count": None,
            "extracted_count": len(signals),
            "validation_status": "partial",
            "evidence_text": signals[0].get("source_excerpt", ""),
        }
        for (signal_type, direction), signals in groups.items()
    ]
    represented = {signal_type for signal_type, _direction in groups}
    coverage.extend(_absent_signal_coverage(represented))
    return industry_signals, coverage


def _normalize_industry_payload(payload):
    if payload.get("industry_signal_lists") is not None:
        return _normalize_grouped_industry_signals(payload["industry_signal_lists"])
    return _normalize_legacy_industry_signals(payload.get("industry_signals", []))


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
    industry_signal_coverage: list[ServicesIndustrySignalCoverageModel]
    respondent_comments: list[ServicesRespondentCommentModel]
    commodities: list[ServicesCommoditySignalModel]
    narrative_facts: ServicesNarrativeFactsModel

    @model_validator(mode="before")
    @classmethod
    def normalize_industry_payload(cls, value):
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("industry_signal_lists") is not None:
            industry_signals, coverage = _normalize_industry_payload(payload)
            payload.pop("industry_signal_lists")
            payload["industry_signals"] = industry_signals
            payload["industry_signal_coverage"] = coverage
        else:
            payload.pop("industry_signal_lists", None)
        if "industry_signal_coverage" not in payload:
            industry_signals, coverage = _normalize_industry_payload(payload)
            payload["industry_signals"] = industry_signals
            payload["industry_signal_coverage"] = coverage
        return payload

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

    industry_signal_lists: list[ServicesIndustrySignalListModel] | None = None
    industry_signals: list[ServicesIndustrySignalModel] | None = None

    @model_validator(mode="after")
    def validate_payload_format(self):
        formats = [
            self.industry_signal_lists is not None,
            self.industry_signals is not None,
        ]
        if sum(formats) != 1:
            raise ValueError(
                "exactly one of industry_signal_lists or industry_signals is required"
            )
        if self.industry_signal_lists is not None:
            keys = [
                (signal_list.signal_type, signal_list.direction)
                for signal_list in self.industry_signal_lists
            ]
            if len(keys) != len(set(keys)):
                raise ValueError(
                    "industry signal type and direction lists are duplicated"
                )
        return self


class ServicesCommentsCommoditiesSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    respondent_comments: list[ServicesRespondentCommentModel]
    commodities: list[ServicesCommoditySignalModel]


class ServicesNarrativeFactsSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative_facts: ServicesNarrativeFactsModel


SECTION_PROMPT_VERSIONS = {
    "report": "ism-services-report-v3",
    "at_a_glance_rows": "ism-services-glance-v2",
    "industry_signals": "ism-services-industries-v5",
    "comments_commodities": "ism-services-comments-v2",
    "narrative_facts": "ism-services-narrative-v3",
}

SECTION_RESPONSE_MODELS = {
    "report": ServicesReportSectionModel,
    "at_a_glance_rows": ServicesAtAGlanceSectionModel,
    "industry_signals": ServicesIndustrySignalsSectionModel,
    "comments_commodities": ServicesCommentsCommoditiesSectionModel,
    "narrative_facts": ServicesNarrativeFactsSectionModel,
}

FACTUAL_SECTION_NAMES = list(SECTION_PROMPT_VERSIONS.keys())


def _normalized_in_source(text, normalized_source):
    return bool(text) and re.sub(r"\s+", " ", text).lower() in normalized_source


def _ground_report(payload, normalized_source):
    report = payload.get("report", {})
    title = report.get("title", "")
    lower_title = title.lower()
    if "ism" in lower_title and "services" in lower_title and "pmi" in lower_title:
        if not re.search(r"ism\s*(?:®\s*)?services", normalized_source):
            raise ValueError(
                "report title not grounded: ISM Services not found in source"
            )


def _ground_at_a_glance(payload, normalized_source):
    for row in payload.get("at_a_glance_rows", []):
        value_str = f"{row['current_value']:.1f}"
        if value_str not in normalized_source:
            raise ValueError(
                f"at-a-glance value {value_str} for {row.get('series_id', 'unknown')} "
                f"not found in source text"
            )


def _ground_industry_signals(payload, normalized_source):
    signal_rows = payload.get("industry_signal_lists")
    if signal_rows is None:
        signal_rows = payload.get("industry_signals", [])
    for signal in signal_rows:
        excerpt = signal.get("evidence_text", signal.get("source_excerpt", ""))
        if not _normalized_in_source(excerpt, normalized_source):
            raise ValueError(
                f"source excerpt for {signal.get('signal_type', 'unknown')} "
                f"signal not found in source text"
            )


def _ground_comments_commodities(payload, normalized_source):
    for comment in payload.get("respondent_comments", []):
        text = comment.get("comment_text", "")
        if not _normalized_in_source(text, normalized_source):
            raise ValueError(
                f"respondent comment not found in source text: {text[:60]}"
            )
        industry = comment.get("industry", "")
        if industry and not _normalized_in_source(industry, normalized_source):
            raise ValueError(f"comment industry {industry} not found in source text")
    for commodity in payload.get("commodities", []):
        name = commodity.get("commodity", "")
        if not _normalized_in_source(name, normalized_source):
            raise ValueError(f"commodity name not found in source text: {name}")


def _ground_narrative_facts(payload, normalized_source):
    facts = payload.get("narrative_facts", {})
    if facts.get("broad_based_expansion_mentioned"):
        phrases = ["broad based expansion", "broad-based expansion", "broad"]
        if not any(p in normalized_source for p in phrases):
            raise ValueError(
                "broad_based_expansion_mentioned grounded but phrase not in source"
            )
    if facts.get("inflationary_pressure_mentioned"):
        if "inflationary pressure" not in normalized_source:
            raise ValueError(
                "inflationary_pressure_mentioned grounded but phrase not in source"
            )
    if facts.get("consecutive_expansion_months") is not None:
        num = str(facts["consecutive_expansion_months"])
        expansion_phrases = [f"{num} consecutive month", f"{num} month", f"{num}th"]
        if not any(p in normalized_source for p in expansion_phrases):
            if num not in normalized_source:
                raise ValueError(
                    f"consecutive_expansion_months={num} value not found in source"
                )
    if facts.get("services_economy_gdp_share_percent") is not None:
        pct = str(facts["services_economy_gdp_share_percent"])
        phrases = [f"{pct} percent", f"{pct}%", "gdp"]
        if not any(p in normalized_source for p in phrases):
            raise ValueError(
                f"services_economy_gdp_share_percent={pct} value not found in source"
            )


_SECTION_GROUNDERS = {
    "report": _ground_report,
    "at_a_glance_rows": _ground_at_a_glance,
    "industry_signals": _ground_industry_signals,
    "comments_commodities": _ground_comments_commodities,
    "narrative_facts": _ground_narrative_facts,
}


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
    grounder = _SECTION_GROUNDERS.get(section_name)
    if grounder:
        grounder(dumped, normalized_source)
    return dumped


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
        f"Return only valid JSON.\n"
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
        + "Directions by signal_type:\n"
        + "overall_growth: growth; overall_contraction: contraction;\n"
        + "business_activity, new_orders, employment: growth or decrease;\n"
        + "supplier_deliveries: slower or faster;\n"
        + "inventories, backlog, imports: higher or lower;\n"
        + "inventory_sentiment: too_high or too_low; prices: increase or decrease;\n"
        + "new_export_orders: growth or decrease.\n"
        + "Return one grouped object per source list. Preserve industry order.\n"
        + "Set declared_count to the explicit source count, or null when unstated.\n"
        + "Include explicit zero-industry lists with declared_count 0 and industries [].\n"
        + "Omit no-change statements. Do not add rank fields.\n"
        + 'Include exact source text as "evidence_text" for each list.\n'
        + '\n{"industry_signal_lists": [{"signal_type": "...", "direction": "growth|contraction|higher|lower|increase|decrease|slower|faster|too_low|too_high", "declared_count": 2, "industries": ["Construction", "Retail Trade"], "evidence_text": "..."}]}'
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
        + 'Set inflationary_pressure_mentioned true only when the exact phrase "inflationary pressure" appears.\n'
        + '{"narrative_facts": {"consecutive_expansion_months": null, "services_economy_gdp_share_percent": null, "broad_based_expansion_mentioned": false, "inflationary_pressure_mentioned": false}}'
    )


BUILD_PROMPT_FOR_SECTION = {
    "report": build_report_prompt,
    "at_a_glance_rows": build_at_a_glance_prompt,
    "industry_signals": build_industry_signals_prompt,
    "comments_commodities": build_comments_commodities_prompt,
    "narrative_facts": build_narrative_facts_prompt,
}
