import json

import pytest

from app.tools import fomc_minutes_structure


def valid_minutes_payload():
    return {
        "statement_bias": "hawkish",
        "risk_focus": "inflation",
        "risk_bias": "hawkish",
        "divergence_level": "medium",
        "uncertainty_level": "medium",
        "policy_conviction": "moderate",
        "minutes_confirmation": "confirmed_but_divided",
        "confidence": "medium",
        "participant_distribution": [
            {
                "group": "many participants",
                "topic": "inflation",
                "stance": "inflation remained a material risk",
                "evidence": "many participants noted inflation risks",
            }
        ],
        "facts": [
            {
                "dimension": "risk_focus",
                "claim": "inflation risk dominates the minutes",
                "evidence": "participants noted inflation risks",
            }
        ],
        "comparison": {
            "statement_vs_minutes": {
                "statement": "statement was hawkish",
                "minutes": "minutes confirmed inflation concern with division",
                "conclusion": "confirmed_but_divided",
            }
        },
        "reason": "Minutes confirm the statement's hawkish bias but show some internal division.",
    }


def test_parse_minutes_response_returns_structure_fields():
    parsed = fomc_minutes_structure.parse_extractor_response(
        json.dumps(valid_minutes_payload())
    )

    assert parsed["risk_focus"] == "inflation"
    assert parsed["risk_bias"] == "hawkish"
    assert parsed["divergence_level"] == "medium"
    assert parsed["uncertainty_level"] == "medium"
    assert parsed["policy_conviction"] == "moderate"
    assert parsed["minutes_confirmation"] == "confirmed_but_divided"
    assert parsed["minutes_tone"] == "hawkish"
    assert parsed["confidence"] == "medium"


def test_parse_minutes_response_rejects_invalid_confirmation():
    payload = valid_minutes_payload()
    payload["minutes_confirmation"] = "very_confirmed"

    with pytest.raises(ValueError, match="minutes structure is invalid"):
        fomc_minutes_structure.parse_extractor_response(json.dumps(payload))


def test_minutes_extractor_prompt_uses_statement_as_baseline():
    prompt = fomc_minutes_structure.build_extractor_prompt(
        {"event_id": "fomc_2026_06_16"},
        {
            "marker_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "reason": "inflation remains elevated",
        },
        "Minutes text",
    )

    assert "Do not re-score the statement baseline" in prompt
    assert "Statement tells public direction" in prompt
    assert "Minutes tell conviction, divergence, uncertainty, and risk focus" in prompt
    assert "minutes_confirmation" in prompt
    assert "policy_conviction" in prompt
