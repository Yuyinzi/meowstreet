import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


StatementBias = Literal["hawkish", "dovish", "neutral", "mixed", "unknown"]
RiskFocus = Literal[
    "inflation",
    "growth_labor",
    "financial_stability",
    "balanced",
    "unknown",
]
RiskBias = Literal["hawkish", "dovish", "neutral", "mixed", "unknown"]
DivergenceLevel = Literal["low", "medium", "high", "unknown"]
UncertaintyLevel = Literal["low", "medium", "high", "unknown"]
PolicyConviction = Literal["high", "moderate", "low", "divided", "unknown"]
MinutesConfirmation = Literal[
    "confirmed",
    "confirmed_but_divided",
    "weakened",
    "stronger_underneath",
    "contradicted",
    "mixed",
    "pending",
    "unknown",
]
Confidence = Literal["high", "medium", "low"]


class MinutesExtractorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_bias: StatementBias
    risk_focus: RiskFocus
    risk_bias: RiskBias
    divergence_level: DivergenceLevel
    uncertainty_level: UncertaintyLevel
    policy_conviction: PolicyConviction
    minutes_confirmation: MinutesConfirmation
    confidence: Confidence
    participant_distribution: list[dict[str, Any]]
    facts: list[dict[str, Any]]
    comparison: dict[str, Any]
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value):
        if not value.strip():
            raise ValueError("reason is required")
        return value.strip()


class MinutesReviewerResponse(BaseModel):
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
        parsed = MinutesExtractorResponse.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError("minutes structure is invalid") from exc
    return {
        "statement_bias": parsed.statement_bias,
        "risk_focus": parsed.risk_focus,
        "risk_bias": parsed.risk_bias,
        "divergence_level": parsed.divergence_level,
        "uncertainty_level": parsed.uncertainty_level,
        "policy_conviction": parsed.policy_conviction,
        "minutes_confirmation": parsed.minutes_confirmation,
        "minutes_tone": parsed.risk_bias,
        "confidence": parsed.confidence,
        "participant_distribution": parsed.participant_distribution,
        "facts": parsed.facts,
        "comparison": parsed.comparison,
        "reason": parsed.reason,
    }


def parse_reviewer_response(content):
    try:
        parsed = MinutesReviewerResponse.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return {"approved": parsed.approved, "feedback": parsed.feedback}


def build_extractor_prompt(event, statement_tone, minutes_text, feedback=None):
    feedback_text = (
        "\nReviewer feedback to address:\n" + json.dumps(feedback, ensure_ascii=False)
        if feedback
        else ""
    )
    return "\n".join(
        [
            "Extract FOMC minutes structure as strict JSON.",
            "Do not re-score the statement baseline.",
            "Statement tells public direction.",
            "Minutes tell conviction, divergence, uncertainty, and risk focus.",
            "Use the provided statement tone only as baseline context.",
            "Do not output a simple minutes headline tone as the main conclusion.",
            "risk_focus is the main risk emphasized by the discussion.",
            "risk_bias maps risk focus into hawkish/dovish/neutral/mixed.",
            "divergence_level measures internal disagreement among participants.",
            "uncertainty_level measures data-dependence and unclear policy path language.",
            "policy_conviction combines divergence and uncertainty into high, moderate, low, divided, or unknown.",
            "minutes_confirmation compares minutes structure against the statement baseline.",
            "Allowed minutes_confirmation: confirmed, confirmed_but_divided, weakened, stronger_underneath, contradicted, mixed, pending, unknown.",
            "Return keys: statement_bias, risk_focus, risk_bias, divergence_level, uncertainty_level, policy_conviction, minutes_confirmation, confidence, participant_distribution, facts, comparison, reason.",
            "Use evidence from the minutes for every important claim.",
            "Event:",
            json.dumps(event, ensure_ascii=False, sort_keys=True),
            "Statement baseline:",
            json.dumps(statement_tone, ensure_ascii=False, sort_keys=True),
            "Minutes text:",
            minutes_text,
            feedback_text,
        ]
    )


def build_reviewer_prompt(event, statement_tone, minutes_text, extraction):
    return "\n".join(
        [
            "Review this FOMC minutes structure extraction.",
            "Approve only if it keeps statement baseline separate from minutes structure.",
            "Approve only if minutes_confirmation follows from risk focus, divergence, uncertainty, and the statement baseline.",
            "Approve only if facts contain evidence from the minutes text.",
            "Return strict JSON with keys: approved, feedback.",
            "Event:",
            json.dumps(event, ensure_ascii=False, sort_keys=True),
            "Statement baseline:",
            json.dumps(statement_tone, ensure_ascii=False, sort_keys=True),
            "Minutes text:",
            minutes_text,
            "Extraction:",
            json.dumps(extraction, ensure_ascii=False, sort_keys=True),
        ]
    )


def tone_extraction_row(
    event_id,
    source_hash,
    statement_tone,
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
        reviewer_feedback
        if final_reviewer_feedback is None
        else final_reviewer_feedback
    )
    return {
        "event_id": event_id,
        "source_document_type": "minutes",
        "source_hash": source_hash,
        "previous_event_id": statement_tone.get("previous_event_id"),
        "policy_action": statement_tone.get("policy_action", "unknown"),
        "guidance_bias": statement_tone.get("guidance_bias", "unknown"),
        "language_tone": statement_tone.get("language_tone", "unknown"),
        "overall_bias": statement_tone.get("overall_bias", "unknown"),
        "statement_tone": statement_tone.get("statement_tone", "unknown"),
        "minutes_tone": extraction["minutes_tone"],
        "marker_tone": statement_tone.get("marker_tone", "unknown"),
        "tone_score": int(statement_tone.get("tone_score", 0)),
        "tone_change": statement_tone.get("tone_change", "unknown"),
        "confidence": extraction["confidence"],
        "extraction_status": extraction_status,
        "review_rounds": int(review_rounds),
        "extractor_model": extractor_model,
        "reviewer_model": reviewer_model,
        "facts_json": json.dumps(
            {
                "risk_focus": extraction["risk_focus"],
                "risk_bias": extraction["risk_bias"],
                "divergence_level": extraction["divergence_level"],
                "uncertainty_level": extraction["uncertainty_level"],
                "policy_conviction": extraction["policy_conviction"],
                "minutes_confirmation": extraction["minutes_confirmation"],
                "participant_distribution": extraction["participant_distribution"],
                "facts": extraction["facts"],
            },
            sort_keys=True,
        ),
        "comparison_json": json.dumps(extraction["comparison"], sort_keys=True),
        "reviewer_feedback_json": json.dumps(reviewer_feedback, sort_keys=True),
        "final_reviewer_feedback_json": json.dumps(final_feedback, sort_keys=True),
        "reason": extraction["reason"],
        "generated_at": generated_at,
    }
