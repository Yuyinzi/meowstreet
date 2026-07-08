import json

from scripts import generate_credit_ai_interpretation


class FakeConnection:
    def close(self):
        pass


def test_build_prompt_includes_metrics_gap_and_cat_voice():
    snapshot = {
        "as_of": "2026-07-06",
        "status": "risk_rising",
        "metrics": {
            "bbb_credit_spread": {"value": 0.98, "zone": "very_low"},
            "ccc_credit_spread": {"value": 9.42, "zone": "serious_deterioration"},
            "ccc_bbb_quality_spread": {"value": 8.44, "zone": "serious_deterioration"},
        },
        "coverage": {
            "has_gap": True,
            "gap_start": "2021-01-08",
            "gap_end": "2023-07-09",
        },
    }

    prompt = generate_credit_ai_interpretation.build_prompt(snapshot)

    assert "risk_rising" in prompt
    assert "0.98" in prompt
    assert "8.44" in prompt
    assert "2021-01-08" in prompt
    assert "disciplined trader cat" in prompt
    assert "Do not change the regime" in prompt


def test_parse_response_requires_bilingual_text():
    parsed = generate_credit_ai_interpretation.parse_response(
        json.dumps(
            {
                "text_en": "Credit risk is rising.",
                "text_zh": "信用风险正在上升。",
            }
        )
    )

    assert parsed == {
        "text_en": "Credit risk is rising.",
        "text_zh": "信用风险正在上升。",
    }
