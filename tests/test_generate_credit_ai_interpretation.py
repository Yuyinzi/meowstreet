import json

import pytest

from app.db import us_rates_liquidity
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
    assert "CaiCai" in prompt
    assert "财财" in prompt
    assert "ginger cat" in prompt
    assert "fish" in prompt
    assert "easy for a non-specialist" in prompt
    assert "Do not call the narrator credit cat" in prompt
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


def test_parse_response_raises_on_missing_text_en():
    with pytest.raises(ValueError, match="text_en"):
        generate_credit_ai_interpretation.parse_response('{"text_zh": "仅中文"}')


def test_parse_response_raises_on_missing_text_zh():
    with pytest.raises(ValueError, match="text_zh"):
        generate_credit_ai_interpretation.parse_response('{"text_en": "english only"}')


def test_parse_response_raises_on_invalid_json():
    with pytest.raises(ValueError):
        generate_credit_ai_interpretation.parse_response("not json")


def test_main_skips_generation_when_snapshot_unchanged(tmp_path, monkeypatch):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    monkeypatch.setattr(
        generate_credit_ai_interpretation.us_rates_liquidity,
        "connect",
        lambda path: con,
    )
    monkeypatch.setattr(
        generate_credit_ai_interpretation,
        "load_current_snapshot",
        lambda con: {
            "scope": "us_credit_conditions",
            "hash": "abc123",
            "prompt_version": "credit-cat-v1",
            "as_of": "2026-07-06",
            "status": "risk_rising",
            "metrics": {},
            "coverage": {},
        },
    )
    monkeypatch.setattr(
        generate_credit_ai_interpretation.us_rates_liquidity,
        "load_ai_interpretation",
        lambda con, scope, hash: {"scope": scope, "snapshot_hash": hash},
    )

    exit_code = generate_credit_ai_interpretation.main(
        ["--db-path", str(tmp_path / "db.sqlite")]
    )

    assert exit_code == 0
