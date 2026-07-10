import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


TONE_DIMENSIONS = [
    "policy_decision",
    "rate_guidance",
    "inflation",
    "labor_growth",
    "balance_sheet",
    "voting",
]

TONE_RUBRIC = [
    "-2 = strongly dovish: explicit easing, cuts, QE, or urgent downside-risk support",
    "-1 = dovish: easing bias, weaker labor/growth focus, or lower inflation concern",
    "0 = neutral: balanced, wait-and-see, no clear easing or tightening bias",
    "+1 = hawkish: inflation/restriction emphasis, less easing bias, or tighter guidance",
    "+2 = strongly hawkish: explicit hikes, tightening urgency, or forceful inflation alarm",
]

TONE_EXAMPLES = [
    {
        "case": "hold decision with hawkish language bias",
        "policy_action": "hold",
        "guidance_bias": "neutral",
        "language_tone": "hawkish",
        "overall_bias": "mild_hawkish",
        "statement_tone": "hawkish",
        "tone_score": 1,
        "tone_change": "more_hawkish",
        "confidence": "medium",
        "facts": [
            {
                "dimension": "inflation",
                "claim": "inflation remains elevated and price stability is emphasized",
                "evidence": "Inflation remains elevated... The Committee will deliver price stability.",
            }
        ],
        "comparison": {
            "inflation": {
                "previous": "previous statement used softer inflation language",
                "current": "current statement adds firmer price-stability commitment",
                "change": "more_hawkish",
            }
        },
        "reason": "The decision is a hold and guidance is not explicit, but solid growth and elevated inflation create a mild hawkish policy bias.",
    }
]


Tone = Literal["hawkish", "dovish", "neutral", "mixed", "unknown"]
PolicyAction = Literal["hike", "cut", "hold", "other", "unknown"]
OverallBias = Literal[
    "strong_dovish",
    "dovish",
    "mild_dovish",
    "neutral",
    "mild_hawkish",
    "hawkish",
    "strong_hawkish",
    "mixed",
    "unknown",
]
ToneChange = Literal["more_hawkish", "more_dovish", "unchanged", "mixed", "unknown"]
Confidence = Literal["high", "medium", "low"]
_VALID_TONE_CHANGES = {
    "more_hawkish",
    "more_dovish",
    "unchanged",
    "mixed",
    "unknown",
}


class ExtractorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_action: PolicyAction
    guidance_bias: Tone
    language_tone: Tone
    overall_bias: OverallBias
    statement_tone: Tone | None = None
    tone_score: int = Field(ge=-2, le=2)
    tone_change: ToneChange
    confidence: Confidence
    facts: list[dict[str, Any]]
    comparison: dict[str, Any]
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value):
        if not value.strip():
            raise ValueError("reason is required")
        return value.strip()

    @field_validator("comparison")
    @classmethod
    def _comparison_change_valid(cls, value):
        for dimension, comparison in value.items():
            if not isinstance(comparison, dict):
                raise ValueError(f"comparison {dimension} must be an object")
            change = comparison.get("change")
            if change is not None and change not in _VALID_TONE_CHANGES:
                raise ValueError(f"comparison {dimension} change is invalid")
        return value


class ReviewerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    feedback: list[str]

    @field_validator("feedback", mode="before")
    @classmethod
    def _feedback_list(cls, value):
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("feedback")
    @classmethod
    def _feedback_clean(cls, value):
        return [item.strip() for item in value if item.strip()]


def parse_extractor_response(content):
    try:
        parsed = ExtractorResponse.model_validate_json(content)
    except ValidationError as exc:
        for error in exc.errors():
            if error.get("loc") and error["loc"][0] in {
                "statement_tone",
                "policy_action",
                "guidance_bias",
                "language_tone",
                "overall_bias",
            }:
                raise ValueError("statement tone is invalid") from exc
        raise ValueError(str(exc)) from exc
    statement_tone = parsed.statement_tone or parsed.language_tone
    return {
        "policy_action": parsed.policy_action,
        "guidance_bias": parsed.guidance_bias,
        "language_tone": parsed.language_tone,
        "overall_bias": parsed.overall_bias,
        "statement_tone": statement_tone,
        "minutes_tone": "unknown",
        "marker_tone": "unknown",
        "tone_score": parsed.tone_score,
        "tone_change": parsed.tone_change,
        "confidence": parsed.confidence,
        "facts": parsed.facts,
        "comparison": parsed.comparison,
        "reason": parsed.reason,
    }


def parse_reviewer_response(content):
    try:
        parsed = ReviewerResponse.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return {"approved": parsed.approved, "feedback": parsed.feedback}


def _marker_tone(extraction, extraction_status):
    if extraction_status != "approved":
        return "unknown"
    if extraction["confidence"] == "low":
        return "unknown"
    if extraction.get("overall_bias") in {
        "mild_hawkish",
        "hawkish",
        "strong_hawkish",
    }:
        return "hawkish"
    if extraction.get("overall_bias") in {
        "mild_dovish",
        "dovish",
        "strong_dovish",
    }:
        return "dovish"
    if extraction.get("overall_bias") in {"neutral", "mixed", "unknown"}:
        return extraction["overall_bias"]
    return extraction["statement_tone"]


def tone_extraction_row(
    event_id,
    source_document_type,
    source_hash,
    previous_event_id,
    extraction,
    reviewer_feedback,
    extraction_status,
    review_rounds,
    extractor_model,
    reviewer_model,
    generated_at,
    final_reviewer_feedback=None,
):
    final_feedback = (
        reviewer_feedback if final_reviewer_feedback is None else final_reviewer_feedback
    )
    return {
        "event_id": event_id,
        "source_document_type": source_document_type,
        "source_hash": source_hash,
        "previous_event_id": previous_event_id,
        "policy_action": extraction.get("policy_action", "unknown"),
        "guidance_bias": extraction.get("guidance_bias", "unknown"),
        "language_tone": extraction.get("language_tone", extraction["statement_tone"]),
        "overall_bias": extraction.get("overall_bias", extraction["statement_tone"]),
        "statement_tone": extraction["statement_tone"],
        "minutes_tone": extraction.get("minutes_tone", "unknown"),
        "marker_tone": _marker_tone(extraction, extraction_status),
        "tone_score": int(extraction["tone_score"]),
        "tone_change": extraction["tone_change"],
        "confidence": extraction["confidence"],
        "extraction_status": extraction_status,
        "review_rounds": int(review_rounds),
        "extractor_model": extractor_model,
        "reviewer_model": reviewer_model,
        "facts_json": json.dumps(extraction["facts"], sort_keys=True),
        "comparison_json": json.dumps(extraction["comparison"], sort_keys=True),
        "reviewer_feedback_json": json.dumps(reviewer_feedback, sort_keys=True),
        "final_reviewer_feedback_json": json.dumps(final_feedback, sort_keys=True),
        "reason": extraction["reason"],
        "generated_at": generated_at,
    }


def build_extractor_prompt(
    event, current_document, previous_event, previous_document, feedback=None
):
    feedback_text = (
        "\nReviewer feedback to address:\n" + json.dumps(feedback, ensure_ascii=False)
        if feedback
        else ""
    )
    return "\n".join(
        [
            "Extract FOMC statement policy tone as strict JSON.",
            "Use the current statement as the official market-facing signal.",
            "Separate policy action from policy bias.",
            "policy_action is the mechanical decision: hike, cut, hold, other, or unknown.",
            "guidance_bias is explicit forward guidance about future policy direction.",
            "language_tone is the current statement's hawkish/dovish language bias.",
            "overall_bias combines action, guidance, and language for market expectations.",
            "Hold does not mean neutral tone.",
            "Hold + solid growth + elevated inflation + price-stability commitment should usually be mild_hawkish unless strong dovish offsets exist.",
            "statement_tone is a backward-compatible copy of language_tone.",
            "tone_change measures current statement versus previous statement.",
            "Do not mark language_tone as hawkish only because it is more hawkish than the previous statement.",
            "A neutral language_tone can still have tone_change more_hawkish if it removed dovish language or became less supportive of easing.",
            "Compare only these dimensions:",
            json.dumps(TONE_DIMENSIONS, ensure_ascii=False),
            "Tone score rubric:",
            "\n".join(TONE_RUBRIC),
            "Return keys: policy_action, guidance_bias, language_tone, overall_bias, statement_tone, tone_score, tone_change, confidence, facts, comparison, reason.",
            "Allowed policy_action: hike, cut, hold, other, unknown.",
            "Allowed guidance_bias, language_tone, statement_tone: hawkish, dovish, neutral, mixed, unknown.",
            "Allowed overall_bias: strong_dovish, dovish, mild_dovish, neutral, mild_hawkish, hawkish, strong_hawkish, mixed, unknown.",
            "Allowed tone_change: more_hawkish, more_dovish, unchanged, mixed, unknown.",
            "tone_score must be integer -2, -1, 0, 1, or 2.",
            "facts must be a JSON array of objects, never a string.",
            "Each facts object must use keys dimension, claim, evidence.",
            "comparison must be a JSON object keyed by dimension, never a string.",
            "Each comparison dimension should include previous, current, and change.",
            "Each comparison dimension change must be one of: more_hawkish, more_dovish, unchanged, mixed, unknown.",
            "Do not use less_dovish or less_hawkish; translate them to more_hawkish or more_dovish.",
            "Examples:",
            json.dumps(TONE_EXAMPLES, sort_keys=True, ensure_ascii=False),
            "Use this exact output shape:",
            json.dumps(
                {
                    "policy_action": "hold",
                    "guidance_bias": "neutral",
                    "language_tone": "hawkish",
                    "overall_bias": "mild_hawkish",
                    "statement_tone": "hawkish",
                    "tone_score": 1,
                    "tone_change": "unchanged",
                    "confidence": "medium",
                    "facts": [
                        {
                            "dimension": "inflation",
                            "claim": "inflation language is broadly unchanged",
                            "evidence": "quote or short paraphrase from current statement",
                        }
                    ],
                    "comparison": {
                        "inflation": {
                            "previous": "short previous-language summary",
                            "current": "short current-language summary",
                            "change": "unchanged",
                        }
                    },
                    "reason": "One concise explanation of the tone decision.",
                },
                sort_keys=True,
                ensure_ascii=False,
            ),
            "facts must cite concise evidence from the current statement.",
            "Current event:",
            json.dumps(event, sort_keys=True, ensure_ascii=False),
            "Current statement:",
            current_document["text"],
            "Previous event:",
            json.dumps(previous_event or {}, sort_keys=True, ensure_ascii=False),
            "Previous statement:",
            previous_document["text"] if previous_document else "",
            feedback_text,
        ]
    )


def build_reviewer_prompt(event, current_document, previous_document, extraction):
    return "\n".join(
        [
            "Review this FOMC statement tone extraction.",
            "Approve only if tone, tone_change, facts, comparison, and reason are supported by source text.",
            "Return strict JSON with keys approved and feedback.",
            "feedback must be a JSON array of strings, never a string.",
            "Use this exact shape:",
            json.dumps(
                {
                    "approved": True,
                    "feedback": ["brief reviewer note"],
                },
                sort_keys=True,
                ensure_ascii=False,
            ),
            "Current event:",
            json.dumps(event, sort_keys=True, ensure_ascii=False),
            "Current statement:",
            current_document["text"],
            "Previous statement:",
            previous_document["text"] if previous_document else "",
            "Extraction JSON:",
            json.dumps(extraction, sort_keys=True, ensure_ascii=False),
        ]
    )
