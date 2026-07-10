import json

import pytest

from app.tools import fomc_policy_tone


def test_parse_extractor_response_requires_statement_tone_fields():
    parsed = fomc_policy_tone.parse_extractor_response(
        json.dumps(
            {
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "medium",
                "facts": [
                    {"dimension": "inflation", "claim": "inflation remains elevated"}
                ],
                "comparison": {"inflation": {"change": "more_hawkish"}},
                "reason": "Inflation language became firmer.",
            }
        )
    )

    assert parsed["policy_action"] == "hold"
    assert parsed["guidance_bias"] == "neutral"
    assert parsed["language_tone"] == "hawkish"
    assert parsed["overall_bias"] == "mild_hawkish"
    assert parsed["statement_tone"] == "hawkish"
    assert parsed["minutes_tone"] == "unknown"
    assert parsed["marker_tone"] == "unknown"


def test_parse_extractor_response_rejects_invalid_tone():
    with pytest.raises(ValueError, match="statement tone is invalid"):
        fomc_policy_tone.parse_extractor_response(
            json.dumps(
                {
                    "policy_action": "hold",
                    "guidance_bias": "neutral",
                    "language_tone": "hawkish",
                    "overall_bias": "mild_hawkish",
                    "statement_tone": "bullish",
                    "tone_score": 1,
                    "tone_change": "more_hawkish",
                    "confidence": "medium",
                    "facts": [],
                    "comparison": {},
                    "reason": "bad tone",
                }
            )
        )


def test_parse_extractor_response_rejects_invalid_comparison_change():
    with pytest.raises(ValueError, match="comparison.*change"):
        fomc_policy_tone.parse_extractor_response(
            json.dumps(
                {
                    "policy_action": "hold",
                    "guidance_bias": "neutral",
                    "language_tone": "neutral",
                    "overall_bias": "neutral",
                    "statement_tone": "neutral",
                    "tone_score": 0,
                    "tone_change": "more_hawkish",
                    "confidence": "medium",
                    "facts": [],
                    "comparison": {
                        "labor_growth": {
                            "previous": "weaker labor language",
                            "current": "stronger labor language",
                            "change": "less_dovish",
                        }
                    },
                    "reason": "bad nested comparison change",
                }
            )
        )


def test_parse_extractor_response_rejects_invalid_overall_bias():
    with pytest.raises(ValueError, match="statement tone is invalid"):
        fomc_policy_tone.parse_extractor_response(
            json.dumps(
                {
                    "policy_action": "hold",
                    "guidance_bias": "neutral",
                    "language_tone": "hawkish",
                    "overall_bias": "slightly_hawkish",
                    "statement_tone": "hawkish",
                    "tone_score": 1,
                    "tone_change": "more_hawkish",
                    "confidence": "medium",
                    "facts": [],
                    "comparison": {},
                    "reason": "bad bias",
                }
            )
        )


def test_parse_reviewer_response_returns_feedback():
    parsed = fomc_policy_tone.parse_reviewer_response(
        json.dumps(
            {
                "approved": False,
                "feedback": [
                    "Tone change should be unchanged because guidance language did not change."
                ],
            }
        )
    )

    assert parsed == {
        "approved": False,
        "feedback": [
            "Tone change should be unchanged because guidance language did not change."
        ],
    }


def test_parse_reviewer_response_accepts_single_feedback_string():
    parsed = fomc_policy_tone.parse_reviewer_response(
        json.dumps(
            {
                "approved": True,
                "feedback": "The extraction is supported by the source text.",
            }
        )
    )

    assert parsed == {
        "approved": True,
        "feedback": ["The extraction is supported by the source text."],
    }


def test_final_row_uses_statement_tone_only_after_approval():
    extraction = {
        "policy_action": "hold",
        "guidance_bias": "neutral",
        "language_tone": "hawkish",
        "overall_bias": "mild_hawkish",
        "statement_tone": "hawkish",
        "minutes_tone": "unknown",
        "tone_score": 1,
        "tone_change": "more_hawkish",
        "confidence": "medium",
        "facts": [{"dimension": "inflation"}],
        "comparison": {"inflation": {"change": "more_hawkish"}},
        "reason": "Inflation language became firmer.",
    }

    row = fomc_policy_tone.tone_extraction_row(
        event_id="fomc_2026_07_28",
        source_document_type="statement",
        source_hash="abc123",
        previous_event_id="fomc_2026_06_16",
        extraction=extraction,
        reviewer_feedback=[],
        extraction_status="approved",
        review_rounds=1,
        extractor_model="gpt-4.1-mini",
        reviewer_model="gpt-4.1",
        final_reviewer_feedback=["Final approval."],
        generated_at="2026-07-30T00:00:00Z",
    )

    assert row["policy_action"] == "hold"
    assert row["guidance_bias"] == "neutral"
    assert row["language_tone"] == "hawkish"
    assert row["overall_bias"] == "mild_hawkish"
    assert row["marker_tone"] == "hawkish"
    assert row["facts_json"] == '[{"dimension": "inflation"}]'
    assert row["reviewer_feedback_json"] == "[]"
    assert row["final_reviewer_feedback_json"] == '["Final approval."]'


def test_final_row_uses_unknown_tone_when_not_approved():
    extraction = {
        "policy_action": "hold",
        "guidance_bias": "neutral",
        "language_tone": "hawkish",
        "overall_bias": "mild_hawkish",
        "statement_tone": "hawkish",
        "minutes_tone": "unknown",
        "tone_score": 1,
        "tone_change": "more_hawkish",
        "confidence": "medium",
        "facts": [],
        "comparison": {},
        "reason": "test",
    }

    row = fomc_policy_tone.tone_extraction_row(
        event_id="fomc_2026_07_28",
        source_document_type="statement",
        source_hash="abc123",
        previous_event_id=None,
        extraction=extraction,
        reviewer_feedback=[],
        extraction_status="max_rounds_reached",
        review_rounds=3,
        extractor_model="gpt-4.1-mini",
        reviewer_model="gpt-4.1",
        generated_at="2026-07-30T00:00:00Z",
    )

    assert row["marker_tone"] == "unknown"


def test_final_row_uses_unknown_tone_when_confidence_is_low():
    extraction = {
        "policy_action": "hold",
        "guidance_bias": "neutral",
        "language_tone": "hawkish",
        "overall_bias": "mild_hawkish",
        "statement_tone": "hawkish",
        "minutes_tone": "unknown",
        "tone_score": 1,
        "tone_change": "more_hawkish",
        "confidence": "low",
        "facts": [],
        "comparison": {},
        "reason": "test",
    }

    row = fomc_policy_tone.tone_extraction_row(
        event_id="fomc_2026_07_28",
        source_document_type="statement",
        source_hash="abc123",
        previous_event_id=None,
        extraction=extraction,
        reviewer_feedback=[],
        extraction_status="approved",
        review_rounds=1,
        extractor_model="gpt-4.1-mini",
        reviewer_model="gpt-4.1",
        generated_at="2026-07-30T00:00:00Z",
    )

    assert row["marker_tone"] == "unknown"


def test_extractor_prompt_defines_absolute_tone_and_relative_change():
    prompt = fomc_policy_tone.build_extractor_prompt(
        {"event_id": "fomc_2026_06_16"},
        {"text": "current statement"},
        {"event_id": "fomc_2026_04_28"},
        {"text": "previous statement"},
    )

    assert "policy_action is the mechanical decision" in prompt
    assert "guidance_bias is explicit forward guidance" in prompt
    assert "language_tone is the current statement's hawkish/dovish" in prompt
    assert "overall_bias combines action, guidance, and language" in prompt
    assert "Hold does not mean neutral tone" in prompt
    assert "tone_change measures current statement versus previous statement" in prompt
    assert (
        "Do not mark language_tone as hawkish only because it is more hawkish"
        in prompt
    )
    assert "A neutral language_tone can still have tone_change more_hawkish" in prompt


def test_extractor_prompt_contains_rubric_dimensions_and_example():
    prompt = fomc_policy_tone.build_extractor_prompt(
        {"event_id": "fomc_2026_06_16"},
        {"text": "current statement"},
        {"event_id": "fomc_2026_04_28"},
        {"text": "previous statement"},
    )

    for dimension in [
        "policy_decision",
        "rate_guidance",
        "inflation",
        "labor_growth",
        "balance_sheet",
        "voting",
    ]:
        assert dimension in prompt
    assert "-2 = strongly dovish" in prompt
    assert "+2 = strongly hawkish" in prompt
    assert '"policy_action": "hold"' in prompt
    assert '"guidance_bias": "neutral"' in prompt
    assert '"language_tone": "hawkish"' in prompt
    assert '"overall_bias": "mild_hawkish"' in prompt
    assert '"statement_tone": "hawkish"' in prompt
    assert '"tone_change": "more_hawkish"' in prompt


def test_pydantic_model_reports_missing_required_fields():
    with pytest.raises(ValueError, match="facts"):
        fomc_policy_tone.parse_extractor_response(
            json.dumps(
                {
                    "policy_action": "hold",
                    "guidance_bias": "neutral",
                    "language_tone": "hawkish",
                    "overall_bias": "mild_hawkish",
                    "statement_tone": "hawkish",
                    "tone_score": 1,
                    "tone_change": "more_hawkish",
                    "confidence": "medium",
                    "comparison": {},
                    "reason": "missing facts",
                }
            )
        )
