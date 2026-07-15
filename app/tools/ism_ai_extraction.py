import asyncio
import json
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
    summary_text: str


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

    industry_signals: list[IndustrySignalModel]


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


def _validate_model(model, payload):
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def validate_summary_against_facts(summary_payload, factual_payload):
    summary = _validate_model(AiSummaryModel, summary_payload)
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
    return {
        "report": intro or report_text[:4000],
        "at_a_glance_rows": at_a_glance or report_text,
        "industry_signals": index_summaries or report_text,
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
  "industry_signals": [
    {{
      "signal_type": "overall_growth",
      "direction": "growth",
      "industry": "Machinery",
      "rank": 1,
      "evidence_text": "source sentence"
    }}
  ]
}}

Use a flat list. Extract all available lists for overall_growth,
overall_contraction, new_orders, production, employment, supplier_deliveries,
inventories, customer_inventories, prices, backlog, new_export_orders, imports.
Do not return nested objects.

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


def build_validated_summary_prompt(factual_payload):
    return f"""
Summarize only the validated ISM Manufacturing facts below.
Return only valid JSON with this shape:
{{
  "summary_text": "...",
  "headline_changes": [
    {{
      "label": "Headline PMI",
      "series_id": "ism_manufacturing_pmi",
      "point_change": 1.3
    }}
  ],
  "major_changes": ["..."]
}}

Rules:
- Do not use facts outside this JSON.
- Do not include compared_to_report_month; it is computed by code.
- headline_changes must use series_id values from at_a_glance_rows.
- headline_changes point_change must exactly match the selected at_a_glance_rows row.
- major_changes must be grounded in at_a_glance_rows, industry_signals, commodities, narrative_facts, or respondent_comments.

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
    "industry_signals": ["industry_signals"],
    "comments_commodities": ["respondent_comments", "commodities"],
    "narrative_facts": ["narrative_facts"],
}


def _section_payload(section_name, payload):
    keys = SECTION_KEYS[section_name]
    if not isinstance(payload, dict):
        return payload
    return {key: payload[key] for key in keys if key in payload}


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
            if section_name == "comments_commodities":
                _validate_respondent_comments_are_from_source(
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
            if section_name == "comments_commodities":
                _validate_respondent_comments_are_from_source(
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


def extract_split_with_client(report_text, client, max_attempts=2):
    section_texts = report_section_texts(report_text)
    sections = [
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
    payload = {}
    for section_name, section_text, prompt, model in sections:
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


async def generate_summary_from_facts_async(factual_payload, client, max_attempts=2):
    payload = None
    validation_error = None
    prompt = build_validated_summary_prompt(factual_payload)
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
        try:
            return validate_summary_against_facts(payload, factual_payload)
        except ValueError as exc:
            validation_error = str(exc)
    raise ValueError(validation_error)


def generate_summary_from_facts(factual_payload, client, max_attempts=2):
    return asyncio.run(
        generate_summary_from_facts_async(
            factual_payload,
            client,
            max_attempts=max_attempts,
        )
    )


def extract_with_client(report_text, client, max_attempts=2):
    return extract_split_with_client(report_text, client, max_attempts=max_attempts)
