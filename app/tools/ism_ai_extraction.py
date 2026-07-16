import asyncio
import json
import re
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
SUMMARY_COMMENT_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "also",
    "being",
    "below",
    "could",
    "every",
    "from",
    "have",
    "into",
    "other",
    "their",
    "there",
    "these",
    "those",
    "through",
    "which",
    "while",
    "with",
    "would",
}

_INDUSTRY_COUNT_BY_WORD = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
}
_INDUSTRY_COUNT_PATTERN = r"(?:\d+|" + "|".join(_INDUSTRY_COUNT_BY_WORD) + r")"
_OVERALL_GROWTH_COUNT_RE = re.compile(
    rf"\b(?:the|of the)\s+(?P<count>{_INDUSTRY_COUNT_PATTERN})\s+"
    r"manufacturing industries\s+(?:that\s+)?(?:reported|reporting)\s+growth\b"
    r"(?!\s+in\s+(?:new orders|production|employment|new export orders|imports))",
    re.IGNORECASE,
)
_OVERALL_CONTRACTION_COUNT_RE = re.compile(
    rf"\b(?:the|of the)\s+(?P<count>{_INDUSTRY_COUNT_PATTERN})\s+"
    r"(?:manufacturing\s+)?industries\s+(?:in|reporting|that reported)\s+"
    r"(?:a\s+)?(?:decline|contraction)\b"
    r"(?!\s+in\s+(?:new orders|production|employment|new export orders|imports))",
    re.IGNORECASE,
)
_DECLARED_INDUSTRY_COUNT_RES = [
    re.compile(
        rf"\bof(?: the)?\s+{_INDUSTRY_COUNT_PATTERN}\s+manufacturing industries"
        rf"\s*,\s*(?:the\s+)?(?P<count>{_INDUSTRY_COUNT_PATTERN})\s+"
        r"(?:industries\s+)?(?:reported|reporting|that reported)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:the|of the|only)\s+(?P<count>{_INDUSTRY_COUNT_PATTERN})\s+"
        r"(?:manufacturing\s+)?industr(?:y|ies)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bthe\s+(?P<count>{_INDUSTRY_COUNT_PATTERN})\s+that\s+reported\b",
        re.IGNORECASE,
    ),
]


def _previous_report_month(report_month):
    year, month, _day = report_month.split("-")
    year = int(year)
    month = int(month)
    if month == 1:
        return f"{year - 1}-12-01"
    return f"{year}-{month - 1:02d}-01"


def _normalized_text(value):
    return " ".join(
        value.replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
        .split()
    )


def _validate_respondent_comments_are_from_source(payload, report_text):
    source_text = _normalized_text(report_text)
    for comment in payload.get("respondent_comments", []):
        comment_text = _normalized_text(comment["comment_text"])
        if comment_text not in source_text:
            raise ValueError(
                "respondent comment text is not present in source: "
                f"{comment['comment_text']}"
            )


def _industry_count(value):
    normalized = value.lower()
    if normalized.isdigit():
        return int(normalized)
    return _INDUSTRY_COUNT_BY_WORD[normalized]


def _declared_industry_count(evidence_text):
    for pattern in _DECLARED_INDUSTRY_COUNT_RES:
        match = pattern.search(evidence_text)
        if match:
            return _industry_count(match.group("count"))
    return None


def _validate_industry_signals_are_from_source(payload, report_text):
    source_text = _normalized_text(report_text)
    if not re.search(r"\bindustr(?:y|ies)\b", source_text, re.IGNORECASE):
        return
    groups = {}
    for signal in payload.get("industry_signals", []):
        evidence_text = _normalized_text(signal["evidence_text"])
        if evidence_text not in source_text:
            raise ValueError(
                "industry signal evidence is not present in source: "
                f"{signal['industry']}"
            )
        key = (signal["signal_type"], signal["direction"])
        groups.setdefault(key, []).append(signal)
    for key, signals in groups.items():
        ranks = sorted(signal["rank"] for signal in signals)
        expected_ranks = list(range(1, len(signals) + 1))
        if ranks != expected_ranks:
            raise ValueError(
                f"industry signal ranks are incomplete for {key[0]} {key[1]}"
            )
        industries = [signal["industry"] for signal in signals]
        if len(industries) != len(set(industries)):
            raise ValueError(
                f"industry signals are duplicated for {key[0]} {key[1]}"
            )
        declared_counts = {
            count
            for signal in signals
            if (count := _declared_industry_count(signal["evidence_text"]))
            is not None
        }
        if len(declared_counts) == 1:
            expected_count = declared_counts.pop()
            if len(signals) != expected_count:
                raise ValueError(
                    f"{key[0]} {key[1]} must contain {expected_count} industries "
                    f"from its source list, got {len(signals)}"
                )


def _validate_overall_industry_lists_are_complete(payload, report_text):
    expected_groups = [
        ("overall_growth", "growth", _OVERALL_GROWTH_COUNT_RE),
        ("overall_contraction", "contraction", _OVERALL_CONTRACTION_COUNT_RE),
    ]
    for signal_type, direction, pattern in expected_groups:
        match = pattern.search(report_text)
        if not match:
            continue
        expected_count = _industry_count(match.group("count"))
        signals = [
            signal
            for signal in payload.get("industry_signals", [])
            if signal["signal_type"] == signal_type
            and signal["direction"] == direction
        ]
        if len(signals) != expected_count:
            raise ValueError(
                f"{signal_type} must contain {expected_count} industries from the "
                f"comprehensive source list, got {len(signals)}"
            )


def _validate_industry_signals_against_source(payload, report_text):
    _validate_industry_signals_are_from_source(payload, report_text)
    _validate_overall_industry_lists_are_complete(payload, report_text)


def _comment_keywords(comments):
    keywords = set()
    for comment in comments:
        for token in re.findall(r"[a-z][a-z-]+", comment["comment_text"].lower()):
            if len(token) >= 5 and token not in SUMMARY_COMMENT_STOPWORDS:
                keywords.add(token)
    return keywords


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

_GROUPED_DIRECTIONS_BY_SIGNAL_TYPE = {
    "overall_growth": {"growth"},
    "overall_contraction": {"contraction"},
    "new_orders": {"growth", "decrease"},
    "production": {"growth", "decrease"},
    "employment": {"growth", "decrease"},
    "supplier_deliveries": {"slower", "faster"},
    "inventories": {"higher", "lower"},
    "customer_inventories": {"too_high", "too_low"},
    "prices": {"increase", "decrease"},
    "backlog": {"higher", "lower"},
    "new_export_orders": {"growth", "decrease"},
    "imports": {"higher", "lower"},
}


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
    rank: int = Field(ge=1)
    evidence_text: str


class IndustrySignalListModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: SignalType
    direction: Direction
    industries: list[str] = Field(min_length=1)
    evidence_text: str

    @model_validator(mode="after")
    def validate_signal_list(self):
        allowed_directions = _GROUPED_DIRECTIONS_BY_SIGNAL_TYPE[self.signal_type]
        if self.direction not in allowed_directions:
            raise ValueError(
                f"direction {self.direction} is invalid for {self.signal_type}"
            )
        if len(self.industries) != len(set(self.industries)):
            raise ValueError(
                f"industries are duplicated for {self.signal_type} {self.direction}"
            )
        return self


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


class HeadlineChangeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    series_id: str
    point_change: float

    @field_validator("series_id")
    @classmethod
    def validate_series_id(cls, value):
        if value not in REQUIRED_SERIES_IDS:
            raise ValueError(f"series id is unknown: {value}")
        return value


class AiSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compared_to_report_month: str | None = None
    headline_changes: list[HeadlineChangeModel] = Field(default_factory=list)
    major_changes: list[str] = Field(default_factory=list)
    major_changes_zh: list[str] = Field(default_factory=list)
    summary_text: str
    summary_text_zh: str = ""
    cat_takeaway_en: str = ""
    cat_takeaway_zh: str = ""


class IsmRichExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ReportModel
    at_a_glance_rows: list[AtAGlanceRowModel]
    industry_signals: list[IndustrySignalModel]
    respondent_comments: list[RespondentCommentModel]
    commodities: list[CommoditySignalModel]
    narrative_facts: NarrativeFactsModel
    ai_summary: AiSummaryModel

    @model_validator(mode="after")
    def validate_metric_set(self):
        if len(self.at_a_glance_rows) != 11:
            raise ValueError("at_a_glance_rows must contain exactly 11 rows")
        series_ids = {row.series_id for row in self.at_a_glance_rows}
        if series_ids != REQUIRED_SERIES_IDS:
            raise ValueError(
                "at_a_glance_rows series ids do not match required ISM metrics"
            )
        self.ai_summary.compared_to_report_month = _previous_report_month(
            self.report.report_month
        )
        return self


class ReportSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ReportModel


class AtAGlanceSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_a_glance_rows: list[AtAGlanceRowModel]

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


class IndustrySignalsSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry_signal_lists: list[IndustrySignalListModel] | None = None
    industry_signals: list[IndustrySignalModel] | None = None

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
        return self


class CommentsCommoditiesSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    respondent_comments: list[RespondentCommentModel]
    commodities: list[CommoditySignalModel]


class NarrativeFactsSectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative_facts: NarrativeFactsModel


class IsmFactualExtractionModel(BaseModel):
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


def validate_factual_extraction(payload):
    try:
        return IsmFactualExtractionModel.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


FACTUAL_SECTION_NAMES = [
    "report",
    "at_a_glance_rows",
    "industry_signals",
    "comments_commodities",
    "narrative_facts",
]


def assemble_factual_payload_from_sections(section_rows):
    by_name = {row["section_name"]: row["payload_json"] for row in section_rows}
    missing = [name for name in FACTUAL_SECTION_NAMES if name not in by_name]
    if missing:
        raise ValueError(f"missing factual sections: {', '.join(missing)}")
    payload = {}
    for section_name in FACTUAL_SECTION_NAMES:
        payload.update(by_name[section_name])
    return validate_factual_extraction(payload)


def facts_hash(factual_payload):
    import hashlib

    raw = json.dumps(factual_payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_model(model, payload):
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def validate_summary_against_facts(summary_payload, factual_payload):
    summary = _validate_model(AiSummaryModel, summary_payload)
    if not summary["summary_text_zh"]:
        raise ValueError("summary_text_zh is required")
    if not summary["cat_takeaway_en"]:
        raise ValueError("cat_takeaway_en is required")
    if not summary["cat_takeaway_zh"]:
        raise ValueError("cat_takeaway_zh is required")
    rows_by_series = {
        row["series_id"]: row for row in factual_payload["at_a_glance_rows"]
    }
    for change in summary["headline_changes"]:
        row = rows_by_series.get(change["series_id"])
        if not row:
            raise ValueError(
                f"summary headline change references unknown series: {change['series_id']}"
            )
        if change["point_change"] != row["point_change"]:
            raise ValueError(
                "summary headline change does not match extracted facts: "
                f"{change['series_id']}"
            )
    known_entities = set()
    for signal in factual_payload["industry_signals"]:
        known_entities.add(signal["industry"].lower())
    for commodity in factual_payload["commodities"]:
        known_entities.add(commodity["commodity"].lower())
    for row in factual_payload["at_a_glance_rows"]:
        known_entities.add(row["label"].lower())
        known_entities.add(row["label"].replace("\u00ae", "").strip().lower())
    narrative_fact_entities = {
        "largest manufacturing industries",
        "six largest manufacturing industries",
        "manufacturing gdp share",
        "pmi implied real gdp",
        "real gdp",
    }
    known_entities.update(narrative_fact_entities)
    known_entities.update(_comment_keywords(factual_payload["respondent_comments"]))
    known_entities.discard("")
    for change in summary["major_changes"]:
        text_lower = change.lower()
        if not any(entity in text_lower for entity in known_entities):
            raise ValueError(
                f"summary major_change is not grounded in extracted facts: {change}"
            )
    summary_text_lower = summary["summary_text"].lower()
    for change in summary["headline_changes"]:
        row = rows_by_series[change["series_id"]]
        headline_aliases = {
            change["label"].lower(),
            row["label"].lower(),
            row["label"].replace("\u00ae", "").strip().lower(),
        }
        headline_aliases.discard("")
        if not any(alias in summary_text_lower for alias in headline_aliases):
            raise ValueError(
                f"summary text does not mention headline change: {change['label']}"
            )
    summary["compared_to_report_month"] = _previous_report_month(
        factual_payload["report"]["report_month"]
    )
    return summary


PROMPT_VERSION = "ism-rich-v1"


def _find_marker(text, marker):
    index = text.lower().find(marker.lower())
    return index if index >= 0 else None


def _slice_between(text, start_marker=None, end_markers=None):
    start = 0
    if start_marker:
        start_index = _find_marker(text, start_marker)
        if start_index is None:
            return text
        start = start_index
    end = len(text)
    for marker in end_markers or []:
        marker_index = _find_marker(text[start:], marker)
        if marker_index is not None:
            end = min(end, start + marker_index)
    return text[start:end].strip()


def _industry_list_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z“])", text)
    relevant = [
        sentence.strip()
        for sentence in sentences
        if re.search(r"\bindustr(?:y|ies)\b", sentence, re.IGNORECASE)
        and not re.search(
            r"\b(?:largest|big) manufacturing industries\b",
            sentence,
            re.IGNORECASE,
        )
    ]
    return "\n".join(relevant)


def report_section_texts(report_text):
    intro = _slice_between(
        report_text,
        end_markers=["WHAT RESPONDENTS ARE SAYING", "MANUFACTURING AT A GLANCE"],
    )
    at_a_glance = _slice_between(
        report_text,
        "MANUFACTURING AT A GLANCE",
        ["COMMODITIES REPORTED", "MANUFACTURING INDEX SUMMARIES"],
    )
    comments = _slice_between(
        report_text,
        "WHAT RESPONDENTS ARE SAYING",
        ["MANUFACTURING AT A GLANCE"],
    )
    commodities = _slice_between(
        report_text,
        "COMMODITIES REPORTED",
        ["MANUFACTURING INDEX SUMMARIES"],
    )
    index_summaries = _slice_between(
        report_text,
        "MANUFACTURING INDEX SUMMARIES",
        ["Buying Policy", "About This Report"],
    )
    overall_industry_lists = intro
    overall_marker = re.search(
        r"\b(?:the|of the)\s+"
        + _INDUSTRY_COUNT_PATTERN
        + r"\s+manufacturing industries\s+(?:that\s+)?"
        r"(?:reported|reporting)\s+growth\b",
        intro,
        re.IGNORECASE,
    )
    if overall_marker:
        overall_industry_lists = intro[overall_marker.start() :]
    compact_index_industry_lists = _industry_list_sentences(index_summaries)
    return {
        "report": intro or report_text[:4000],
        "at_a_glance_rows": at_a_glance or report_text,
        "industry_signals": "\n\n".join(
            section
            for section in [overall_industry_lists, compact_index_industry_lists]
            if section
        )
        or report_text,
        "comments_commodities": "\n\n".join(
            section for section in [comments, commodities] if section
        )
        or report_text,
        "narrative_facts": "\n\n".join(
            section
            for section in [intro, at_a_glance, index_summaries[:5000]]
            if section
        )
        or report_text,
    }


def schema_instructions():
    return (
        """
Required JSON shape:
{
  "report": {
    "report_id": "ism_manufacturing_YYYY_MM",
    "report_month": "YYYY-MM-01",
    "title": "...",
    "source_name": "prnewswire or ismworld",
    "source_url": "..."
  },
  "at_a_glance_rows": [
    {
      "series_id": "one of the allowed series ids",
      "label": "official metric label",
      "current_value": 52.6,
      "previous_value": 47.9,
      "point_change": 4.7,
      "direction": "Growing",
      "rate_of_change": "Faster",
      "trend_months": 1
    }
  ],
  "industry_signals": [
    {
      "signal_type": "overall_growth",
      "direction": "growth",
      "industry": "Machinery",
      "rank": 1,
      "evidence_text": "source sentence"
    }
  ],
  "respondent_comments": [
    {"industry": "Machinery", "comment_text": "quoted comment"}
  ],
  "commodities": [
    {"commodity": "Steel", "signal_type": "up_in_price", "months": 2}
  ],
  "narrative_facts": {
    "manufacturing_gdp_share_contracted_percent": 0.0,
    "manufacturing_gdp_share_strong_contraction_percent": 0.0,
    "pmi_implied_real_gdp_annualized_percent": 0.0,
    "largest_industries_expanded": []
  },
  "ai_summary": {
    "compared_to_report_month": "YYYY-MM-01",
    "headline_changes": [
      {
        "label": "Headline PMI",
        "series_id": "ism_manufacturing_pmi",
        "point_change": 1.3
      }
    ],
    "major_changes": ["..."],
    "summary_text": "..."
  }
}

Allowed at_a_glance_rows series_id values:
""".strip()
        + "\n"
        + "\n".join(f"- {series_id}" for series_id in sorted(REQUIRED_SERIES_IDS))
    )


def build_prompt(report_text):
    return f"""
Extract the ISM Manufacturing report into strict JSON.

Return only valid JSON with these keys:
- report
- at_a_glance_rows
- industry_signals
- respondent_comments
- commodities
- narrative_facts
- ai_summary

For ai_summary, generate a concise month-over-month summary using only facts in
the report. The summary should point out the major changes, for example:
"Compared with May

Headline PMI
+1.3

New Orders
+2.4

Production
+1.8

Prices
-0.6

major_changes
• Transportation Equipment moved into expansion.
• Steel was added to commodities up in price.
• Supplier delivery delays increased."

Use the report's previous-month values and point changes. Do not invent changes,
industries, commodities, or causal explanations that are not in the source text.

For industry_signals, extract all available industry lists for:
overall_growth, overall_contraction, new_orders, production, employment,
supplier_deliveries, inventories, customer_inventories, prices, backlog,
new_export_orders, imports.

Preserve industry order as rank starting at 1. Include evidence_text copied
from the source paragraph for each signal. Do not invent industries or values.

{schema_instructions()}

Report text:
{report_text}
""".strip()


def build_report_prompt(report_text):
    return f"""
Extract only report metadata from the ISM Manufacturing report.
Return only valid JSON with this shape:
{{
  "report": {{
    "report_id": "ism_manufacturing_YYYY_MM",
    "report_month": "YYYY-MM-01",
    "title": "...",
    "source_name": "prnewswire or ismworld",
    "source_url": "..."
  }}
}}

Report text:
{report_text}
""".strip()


def build_at_a_glance_prompt(report_text):
    return f"""
Extract only MANUFACTURING AT A GLANCE from the ISM Manufacturing report.
Return only valid JSON with this shape:
{{
  "at_a_glance_rows": [
    {{
      "series_id": "one of the allowed series ids",
      "label": "official metric label",
      "current_value": 52.6,
      "previous_value": 47.9,
      "point_change": 4.7,
      "direction": "Growing",
      "rate_of_change": "Faster",
      "trend_months": 1
    }}
  ]
}}

Return exactly 11 at_a_glance_rows. Use these series_id values exactly:
{chr(10).join(f"- {series_id}" for series_id in sorted(REQUIRED_SERIES_IDS))}

Report text:
{report_text}
""".strip()


def build_industry_signals_prompt(report_text):
    return f"""
Extract only industry signal lists from the ISM Manufacturing report.
Return only valid JSON with this shape:
{{
  "industry_signal_lists": [
    {{
      "signal_type": "overall_growth",
      "direction": "growth",
      "industries": ["Machinery", "Chemical Products"],
      "evidence_text": "source sentence"
    }}
  ]
}}

Return one object per source industry list. Preserve industry order in the
industries array. Include the source evidence sentence once per list. Do not
return one object per industry and do not add rank fields.

Extract all available lists for overall_growth,
overall_contraction, new_orders, production, employment, supplier_deliveries,
inventories, customer_inventories, prices, backlog, new_export_orders, imports.
For overall_growth and overall_contraction, use the comprehensive industry lists.
Do not substitute commentary about only the largest industries for a comprehensive
list. The number of rows must match each count stated in the source.

Use these direction values:
- overall_growth: growth
- overall_contraction: contraction
- new_orders, production, employment: growth or decrease
- supplier_deliveries: slower or faster
- inventories, backlog, imports: higher or lower
- customer_inventories: too_high or too_low
- prices: increase or decrease
- new_export_orders: growth or decrease

Report text:
{report_text}
""".strip()


def build_comments_commodities_prompt(report_text):
    return f"""
Extract only respondent comments and commodities from the ISM Manufacturing report.
Return only valid JSON with this shape:
{{
  "respondent_comments": [
    {{"industry": "Machinery", "comment_text": "quoted comment"}}
  ],
  "commodities": [
    {{"commodity": "Steel", "signal_type": "up_in_price", "months": 2}}
  ]
}}

For respondent_comments, extract only exact quoted respondent comment text that
appears in the source. Preserve the quoted wording exactly, excluding only the
surrounding quote marks. Do not summarize, paraphrase, combine, infer, or create
comments. If no quoted respondent comments are present, return an empty list.

Commodities signal_type must be one of: up_in_price, down_in_price, short_supply.

Report text:
{report_text}
""".strip()


def build_narrative_facts_prompt(report_text):
    return f"""
Extract only narrative facts from the ISM Manufacturing report.
Return only valid JSON with this shape:
{{
  "narrative_facts": {{
    "manufacturing_gdp_share_contracted_percent": 0.0,
    "manufacturing_gdp_share_strong_contraction_percent": 0.0,
    "pmi_implied_real_gdp_annualized_percent": 0.0,
    "largest_industries_expanded": []
  }}
}}

Use only explicit facts from the report text. Do not summarize the report and do
not include ai_summary.

Report text:
{report_text}
""".strip()


def build_validated_summary_prompt(factual_payload, guidance=""):
    return f"""
Summarize only the validated ISM Manufacturing facts below.
Return only valid JSON with this shape:
{{
  "summary_text": "English concise macro summary...",
  "summary_text_zh": "中文宏观摘要...",
  "headline_changes": [
    {{
      "label": "Headline PMI",
      "series_id": "ism_manufacturing_pmi",
      "point_change": 1.3
    }}
  ],
  "major_changes": ["English grounded change..."],
  "major_changes_zh": ["中文对应变化..."],
  "cat_takeaway_en": "A vivid Caicai trader-cat takeaway in English...",
  "cat_takeaway_zh": "中文财财交易猫总结..."
}}

Rules:
- Do not use facts outside this JSON.
- Do not include compared_to_report_month; it is computed by code.
- headline_changes must use series_id values from at_a_glance_rows.
- headline_changes point_change must exactly match the selected at_a_glance_rows row.
- major_changes must be grounded in at_a_glance_rows, industry_signals, commodities, narrative_facts, or respondent_comments.
- Write summary_text in English and summary_text_zh in Chinese.
- Write cat_takeaway_en and cat_takeaway_zh in Caicai（财财） trader-cat voice.
- Caicai（财财） is the Meowstreet trader. Use the name Caicai in English and 财财 in Chinese.
- Caicai can use vivid examples such as buying fish, stocking a pantry, building a house, or checking a market stall.
- Analogies must explain validated facts only; do not invent new data.
- Keep Caicai's tone useful for traders, not cute for its own sake.
- Do not use unsupported jokes or unrelated story details.

Reviewer guidance:
{guidance or "No additional reviewer guidance."}

Validated facts:
{json.dumps(factual_payload, ensure_ascii=False, sort_keys=True)}
""".strip()


def build_repair_prompt(report_text, previous_payload, validation_error):
    return f"""
Your previous JSON failed schema validation. Return a corrected JSON object only.
Do not explain the correction. Do not wrap the JSON in markdown.

Important fixes:
- report must be an object with report_id, report_month, title, source_name, and source_url.
- at_a_glance_rows must contain exactly 11 rows.
- at_a_glance_rows rows must use series_id, label, current_value, previous_value, point_change, direction, rate_of_change, trend_months.
- industry_signals must be a flat list, not a nested object.
- respondent_comments must use comment_text, not comment.
- commodities must be a flat list.
- narrative_facts must be an object.
- ai_summary must be an object with compared_to_report_month, headline_changes, major_changes, and summary_text.

Validation errors:
{validation_error}

Previous invalid JSON:
{previous_payload}

{schema_instructions()}

Report text:
{report_text}
""".strip()


def build_section_repair_prompt(
    report_text, section_name, previous_payload, validation_error, original_prompt
):
    return f"""
Your previous JSON failed schema validation for section: {section_name}.
Return a corrected JSON object only. Do not explain the correction. Do not wrap
the JSON in markdown.

Validation errors:
{validation_error}

Previous invalid JSON:
{previous_payload}

Original extraction instructions:
{original_prompt}

Report text:
{report_text}
""".strip()


SECTION_KEYS = {
    "report": ["report"],
    "at_a_glance_rows": ["at_a_glance_rows"],
    "industry_signals": ["industry_signal_lists", "industry_signals"],
    "comments_commodities": ["respondent_comments", "commodities"],
    "narrative_facts": ["narrative_facts"],
}


def _section_payload(section_name, payload):
    keys = SECTION_KEYS[section_name]
    if not isinstance(payload, dict):
        return payload
    return {key: payload[key] for key in keys if key in payload}


def _normalize_section_payload(section_name, payload):
    if section_name != "industry_signals":
        return payload
    signal_lists = payload.get("industry_signal_lists")
    if signal_lists is None:
        return {"industry_signals": payload["industry_signals"]}
    industry_signals = [
        {
            "signal_type": signal_list["signal_type"],
            "direction": signal_list["direction"],
            "industry": industry,
            "rank": rank,
            "evidence_text": signal_list["evidence_text"],
        }
        for signal_list in signal_lists
        for rank, industry in enumerate(signal_list["industries"], start=1)
    ]
    return {"industry_signals": industry_signals}


async def _complete_json_async(client, prompt):
    if hasattr(client, "complete_json_async"):
        return await client.complete_json_async(prompt)
    return await asyncio.to_thread(client.complete_json, prompt)


async def _extract_section_async(
    section_text,
    client,
    section_name,
    prompt,
    model,
    max_attempts,
):
    payload = None
    validation_error = None
    for attempt in range(max_attempts):
        if attempt == 0:
            current_prompt = prompt
        else:
            current_prompt = build_section_repair_prompt(
                section_text,
                section_name,
                payload,
                validation_error,
                prompt,
            )
        payload = await _complete_json_async(client, current_prompt)
        try:
            section_payload = _validate_model(
                model,
                _section_payload(section_name, payload),
            )
            section_payload = _normalize_section_payload(
                section_name,
                section_payload,
            )
            if section_name == "comments_commodities":
                _validate_respondent_comments_are_from_source(
                    section_payload,
                    section_text,
                )
            if section_name == "industry_signals":
                _validate_industry_signals_against_source(
                    section_payload,
                    section_text,
                )
            return section_payload
        except ValueError as exc:
            validation_error = str(exc)
    raise ValueError(validation_error)


def _extract_section(report_text, client, section_name, prompt, model, max_attempts):
    payload = None
    validation_error = None
    for attempt in range(max_attempts):
        if attempt == 0:
            current_prompt = prompt
        else:
            current_prompt = build_section_repair_prompt(
                report_text,
                section_name,
                payload,
                validation_error,
                prompt,
            )
        payload = client.complete_json(current_prompt)
        try:
            section_payload = _validate_model(
                model,
                _section_payload(section_name, payload),
            )
            section_payload = _normalize_section_payload(
                section_name,
                section_payload,
            )
            if section_name == "comments_commodities":
                _validate_respondent_comments_are_from_source(
                    section_payload,
                    report_text,
                )
            if section_name == "industry_signals":
                _validate_industry_signals_against_source(
                    section_payload,
                    report_text,
                )
            return section_payload
        except ValueError as exc:
            validation_error = str(exc)
    raise ValueError(validation_error)


def _factual_section_definitions(section_texts):
    return [
        (
            "report",
            section_texts["report"],
            build_report_prompt(section_texts["report"]),
            ReportSectionModel,
        ),
        (
            "at_a_glance_rows",
            section_texts["at_a_glance_rows"],
            build_at_a_glance_prompt(section_texts["at_a_glance_rows"]),
            AtAGlanceSectionModel,
        ),
        (
            "industry_signals",
            section_texts["industry_signals"],
            build_industry_signals_prompt(section_texts["industry_signals"]),
            IndustrySignalsSectionModel,
        ),
        (
            "comments_commodities",
            section_texts["comments_commodities"],
            build_comments_commodities_prompt(section_texts["comments_commodities"]),
            CommentsCommoditiesSectionModel,
        ),
        (
            "narrative_facts",
            section_texts["narrative_facts"],
            build_narrative_facts_prompt(section_texts["narrative_facts"]),
            NarrativeFactsSectionModel,
        ),
    ]


async def extract_factual_with_client_async(
    report_text,
    client,
    max_attempts=2,
    max_concurrency=3,
):
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1")
    section_texts = report_section_texts(report_text)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_section(section_name, section_text, prompt, model):
        async with semaphore:
            return await _extract_section_async(
                section_text,
                client,
                section_name,
                prompt,
                model,
                max_attempts,
            )

    section_payloads = await asyncio.gather(
        *[
            run_section(section_name, section_text, prompt, model)
            for section_name, section_text, prompt, model in _factual_section_definitions(
                section_texts
            )
        ]
    )
    payload = {}
    for section_payload in section_payloads:
        payload.update(section_payload)
    return validate_factual_extraction(payload)


def extract_factual_with_client(report_text, client, max_attempts=2):
    section_texts = report_section_texts(report_text)
    payload = {}
    for section_name, section_text, prompt, model in _factual_section_definitions(
        section_texts
    ):
        payload.update(
            _extract_section(
                section_text,
                client,
                section_name,
                prompt,
                model,
                max_attempts,
            )
        )
    return validate_factual_extraction(payload)


def extract_single_payload_with_client(report_text, client, max_attempts=3):
    payload = None
    validation_error = None
    for attempt in range(max_attempts):
        if attempt == 0:
            prompt = build_prompt(report_text)
        else:
            prompt = build_repair_prompt(report_text, payload, validation_error)
        payload = client.complete_json(prompt)
        try:
            return validate_extraction(payload)
        except ValueError as exc:
            validation_error = str(exc)
    raise ValueError(validation_error)


async def generate_summary_from_facts_async(
    factual_payload, client, max_attempts=2, guidance=""
):
    payload = None
    validation_error = None
    prompt = build_validated_summary_prompt(factual_payload, guidance=guidance)
    for attempt in range(max_attempts):
        if attempt == 0:
            current_prompt = prompt
        else:
            current_prompt = f"""
Your previous JSON failed validation. Return a corrected JSON object only.

Validation errors:
{validation_error}

Previous invalid JSON:
{payload}

Original instructions:
{prompt}
""".strip()
        payload = await _complete_json_async(client, current_prompt)
        if "summary_text" in payload:
            summary_payload = payload
        elif "ai_summary" in payload:
            summary_payload = payload["ai_summary"]
        else:
            summary_payload = payload
        try:
            return validate_summary_against_facts(summary_payload, factual_payload)
        except ValueError as exc:
            validation_error = str(exc)
    raise ValueError(validation_error)


def generate_summary_from_facts(factual_payload, client, max_attempts=2, guidance=""):
    return asyncio.run(
        generate_summary_from_facts_async(
            factual_payload,
            client,
            max_attempts=max_attempts,
            guidance=guidance,
        )
    )


def factual_section_definition(section_name, report_text):
    section_texts = report_section_texts(report_text)
    for definition in _factual_section_definitions(section_texts):
        if definition[0] == section_name:
            return definition
    raise ValueError(f"unknown ism factual section: {section_name}")


def extract_section_with_client(
    section_text, client, section_name, prompt, model, max_attempts=2
):
    return _extract_section(
        section_text, client, section_name, prompt, model, max_attempts
    )


async def extract_with_client_async(
    report_text,
    client,
    max_attempts=2,
    max_concurrency=3,
):
    factual_payload = await extract_factual_with_client_async(
        report_text,
        client,
        max_attempts=max_attempts,
        max_concurrency=max_concurrency,
    )
    summary = await generate_summary_from_facts_async(
        factual_payload,
        client,
        max_attempts=max_attempts,
    )
    return validate_extraction({**factual_payload, "ai_summary": summary})


def extract_with_client(report_text, client, max_attempts=2):
    factual_payload = extract_factual_with_client(
        report_text,
        client,
        max_attempts=max_attempts,
    )
    summary = generate_summary_from_facts(
        factual_payload,
        client,
        max_attempts=max_attempts,
    )
    return validate_extraction({**factual_payload, "ai_summary": summary})
