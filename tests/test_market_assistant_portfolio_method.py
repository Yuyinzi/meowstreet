import json

import pytest

from app.tools.market_assistant_portfolio_method import OPERATION_IDS
from app.tools.market_assistant_portfolio_method import load_portfolio_method_knowledge
from app.tools.market_assistant_portfolio_method import validate_operation_params


def valid_knowledge():
    return {
        "version": "portfolio_method_knowledge_v1",
        "record_id": "portfolio_method",
        "operations": [
            {
                "operation": operation,
                "summary": f"{operation} summary",
                "params_contract": f"{operation} contract",
            }
            for operation in OPERATION_IDS
        ],
        "interpretation_guide": "guide",
        "interaction_rules": "rules",
    }


def test_shipped_knowledge_file_loads_and_validates():
    record = load_portfolio_method_knowledge()
    assert record["version"] == "portfolio_method_knowledge_v1"
    assert record["record_id"] == "portfolio_method"
    assert sorted(entry["operation"] for entry in record["operations"]) == sorted(
        OPERATION_IDS
    )
    for entry in record["operations"]:
        assert entry["summary"].strip()
        assert entry["params_contract"].strip()
    assert record["interpretation_guide"].strip()
    assert record["interaction_rules"].strip()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"version": ""}),
        lambda payload: payload.pop("record_id"),
        lambda payload: payload.pop("interpretation_guide"),
        lambda payload: payload.pop("interaction_rules"),
        lambda payload: payload.update({"unknown_field": "x"}),
        lambda payload: payload["operations"].pop(0),
        lambda payload: payload["operations"].append(
            {"operation": "unknown_op", "summary": "s", "params_contract": "c"}
        ),
        lambda payload: payload["operations"][0].update({"summary": ""}),
        lambda payload: payload["operations"][0].update({"extra": "x"}),
    ],
)
def test_knowledge_validation_rejects_bad_payloads(tmp_path, mutate):
    payload = valid_knowledge()
    mutate(payload)
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="portfolio method knowledge is invalid"):
        load_portfolio_method_knowledge(path)


def test_validate_ticker_risk_params():
    assert validate_operation_params("ticker_risk_profile", {"symbol": "NVDA"}) == {
        "symbol": "NVDA"
    }


def test_validate_ticker_context_params():
    assert validate_operation_params(
        "ticker_industry_context", {"symbol": "AAPL"}
    ) == {"symbol": "AAPL"}


def test_validate_ticker_quant_context_params_keeps_optional_peer():
    assert validate_operation_params(
        "ticker_quant_context", {"symbol": "NVDA", "peer": "AMD"}
    ) == {"symbol": "NVDA", "peer": "AMD"}


def test_validate_portfolio_analysis_params_drops_unset_optionals():
    validated = validate_operation_params(
        "portfolio_analysis",
        {
            "positions": [
                {"symbol": "NVDA", "side": "long", "allocation": 100},
                {"symbol": "MSFT", "side": "short", "allocation": 50.5},
            ]
        },
    )
    assert validated == {
        "positions": [
            {"symbol": "NVDA", "side": "long", "allocation": 100.0},
            {"symbol": "MSFT", "side": "short", "allocation": 50.5},
        ]
    }


def test_validate_portfolio_analysis_params_keeps_optionals():
    validated = validate_operation_params(
        "portfolio_analysis",
        {
            "positions": [{"symbol": "NVDA", "side": "long", "allocation": 100}],
            "margin_capital": 100000,
            "declared_bias": "neutral",
            "instrument": "us_stock",
        },
    )
    assert validated["margin_capital"] == 100000.0
    assert validated["declared_bias"] == "neutral"
    assert validated["instrument"] == "us_stock"


@pytest.mark.parametrize(
    ("operation", "params"),
    [
        ("ticker_risk_profile", {}),
        ("ticker_risk_profile", {"symbol": ""}),
        ("ticker_risk_profile", {"symbol": "NVDA", "extra": 1}),
        (
            "portfolio_analysis",
            {"positions": [{"symbol": "NVDA", "side": "hold", "allocation": 100}]},
        ),
        (
            "portfolio_analysis",
            {"positions": [{"symbol": "NVDA", "side": "long", "allocation": -1}]},
        ),
        (
            "portfolio_analysis",
            {"positions": [{"symbol": "NVDA", "side": "long", "allocation": 0}]},
        ),
        ("portfolio_analysis", {"positions": []}),
        (
            "portfolio_analysis",
            {
                "positions": [{"symbol": "NVDA", "side": "long", "allocation": 1}],
                "declared_bias": "mixed",
            },
        ),
        (
            "portfolio_analysis",
            {
                "positions": [{"symbol": "NVDA", "side": "long", "allocation": 1}],
                "instrument": "futures",
            },
        ),
        ("pair_analysis", {"long_symbol": "NVDA"}),
        ("pair_analysis", {"long_symbol": "NVDA", "short_symbol": "AMD", "sessions": 1}),
        (
            "pair_analysis",
            {"long_symbol": "NVDA", "short_symbol": "AMD", "sessions": 261},
        ),
        (
            "pair_analysis",
            {
                "long_symbol": "NVDA",
                "short_symbol": "AMD",
                "sessions": 60,
                "extra": True,
            },
        ),
        ("ticker_industry_context", {"symbol": "NVDA", "industry_override": "x"}),
        ("ticker_quant_context", {"symbol": "NVDA", "unexpected": "x"}),
        ("ticker_quant_context", {"peer": "AMD"}),
    ],
)
def test_validate_operation_params_rejects_bad_contracts(operation, params):
    with pytest.raises(ValueError, match="portfolio query params are invalid"):
        validate_operation_params(operation, params)


def test_validate_pair_params_defaults_and_sessions():
    validated = validate_operation_params(
        "pair_analysis", {"long_symbol": "NVDA", "short_symbol": "AMD"}
    )
    assert validated == {"long_symbol": "NVDA", "short_symbol": "AMD"}
    validated = validate_operation_params(
        "pair_analysis",
        {"long_symbol": "NVDA", "short_symbol": "AMD", "sessions": 120},
    )
    assert validated["sessions"] == 120


def test_validate_operation_params_rejects_unknown_operation():
    with pytest.raises(ValueError, match="unknown portfolio operation"):
        validate_operation_params("unknown_op", {})


def test_validate_operation_params_rejects_non_dict_params():
    with pytest.raises(ValueError, match="portfolio query params must be an object"):
        validate_operation_params("ticker_risk_profile", ["NVDA"])
