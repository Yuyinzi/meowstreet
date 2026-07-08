import json

import pytest

from app.db import us_rates_liquidity
from scripts import generate_m2_ai_interpretation


def test_build_prompt_explains_state_change_shock_and_cat_voice():
    snapshot = {
        "as_of": "2021-01-01",
        "status": "shock",
        "metrics": {
            "state": {
                "yoy_growth": 0.258,
                "yoy_percent_rank": 1.0,
                "level_billions_usd": 19394.6,
            },
            "change": {
                "three_month_change": 0.034,
            },
            "shock": {
                "mom_growth": 0.016,
                "mom_percent_rank": 0.9866,
            },
        },
        "latest_shock_event": {
            "value": 1,
            "signal": "strong_injection",
            "percentile": 98.66,
        },
    }

    prompt = generate_m2_ai_interpretation.build_prompt(snapshot)

    assert "CaiCai" in prompt
    assert "财财" in prompt
    assert "State" in prompt
    assert "Change" in prompt
    assert "Shock" in prompt
    assert "liquidity confirmation" in prompt
    assert "Interpret the metric_context first" in prompt
    assert "Do not merely read the numbers back" in prompt
    assert "Do not name historical causes" in prompt
    assert "unless the snapshot contains a sourced event context" in prompt
    assert "dashboard does not attach a named cause" in prompt
    assert "Do not give buy or sell instructions" in prompt
    assert "Do not mention P06" in prompt
    assert "25.8" in prompt or "0.258" in prompt
    assert "strict JSON" in prompt


def test_parse_response_requires_bilingual_text():
    parsed = generate_m2_ai_interpretation.parse_response(
        json.dumps(
            {
                "text_en": "M2 state is strong, but treat it as confirmation.",
                "text_zh": "M2状态偏强，但应作为确认信号。",
            }
        )
    )

    assert parsed == {
        "text_en": "M2 state is strong, but treat it as confirmation.",
        "text_zh": "M2状态偏强，但应作为确认信号。",
    }


def test_parse_response_raises_on_missing_text_en():
    with pytest.raises(ValueError, match="text_en"):
        generate_m2_ai_interpretation.parse_response('{"text_zh": "仅中文"}')


def test_parse_response_raises_on_missing_text_zh():
    with pytest.raises(ValueError, match="text_zh"):
        generate_m2_ai_interpretation.parse_response('{"text_en": "english only"}')


def test_interpretation_row_uses_m2_scope_and_prompt_version():
    snapshot = {
        "scope": "m2_money_supply",
        "hash": "abc123",
        "prompt_version": "m2-cat-v1",
        "as_of": "2021-01-01",
        "status": "shock",
        "metrics": {},
    }

    row = generate_m2_ai_interpretation.interpretation_row(
        snapshot,
        {"text_en": "english", "text_zh": "中文"},
        "gpt-4.1-mini",
    )

    assert row["scope"] == "m2_money_supply"
    assert row["snapshot_hash"] == "abc123"
    assert row["prompt_version"] == "m2-cat-v1"
    assert row["tone"] == "trader_cat"
    assert row["status"] == "shock"
    assert json.loads(row["metrics_json"])["scope"] == "m2_money_supply"


def test_main_skips_generation_when_snapshot_unchanged(tmp_path, monkeypatch):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    monkeypatch.setattr(
        generate_m2_ai_interpretation.us_rates_liquidity,
        "connect",
        lambda path: con,
    )
    monkeypatch.setattr(
        generate_m2_ai_interpretation,
        "load_current_snapshot",
        lambda con: {
            "scope": "m2_money_supply",
            "hash": "abc123",
            "prompt_version": "m2-cat-v1",
            "as_of": "2021-01-01",
            "status": "shock",
            "metrics": {},
        },
    )
    monkeypatch.setattr(
        generate_m2_ai_interpretation.us_rates_liquidity,
        "load_ai_interpretation",
        lambda con, scope, hash: {"scope": scope, "snapshot_hash": hash},
    )

    exit_code = generate_m2_ai_interpretation.main(
        ["--db-path", str(tmp_path / "db.sqlite")]
    )

    assert exit_code == 0
