import json

import pytest

from app.tools.market_assistant_portfolio_views import compact_pair_analysis
from app.tools.market_assistant_portfolio_views import compact_portfolio_analysis
from app.tools.market_assistant_portfolio_views import compact_portfolio_result
from app.tools.market_assistant_portfolio_views import compact_ticker_context
from app.tools.market_assistant_portfolio_views import compact_ticker_risk


def ticker_risk_payload(rolling_points=60):
    return {
        "symbol": "NVDA",
        "benchmark": "^GSPC",
        "beta": {
            "windows": [
                {
                    "window": 105,
                    "label": "2y",
                    "status": "ok",
                    "beta": 1.4,
                    "standard_error": 0.21,
                    "sample_size": 105,
                },
                {
                    "window": 261,
                    "label": "5y",
                    "status": "insufficient_data",
                    "beta": None,
                    "standard_error": None,
                    "sample_size": 105,
                },
            ],
            "rolling_beta": [
                {"end_date": f"2026-02-{(index % 28) + 1:02d}", "beta": 1.0 + index}
                for index in range(rolling_points)
            ],
        },
        "realized_volatility": {
            "daily": {"stdev": 0.02, "annualized": 0.32, "sample_size": 250},
            "weekly": {"stdev": 0.045, "annualized": 0.33, "sample_size": 105},
            "monthly_21d": {
                "status": "insufficient_data",
                "sample_size": 10,
                "required": 21,
            },
            "quarterly_63d": {"stdev": 0.05, "annualized": 0.31, "sample_size": 63},
        },
        "data": {
            "weekly_start": "2024-01-01",
            "weekly_end": "2026-01-01",
            "weekly_count": 105,
        },
    }


def context_payload(symbol):
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Inc",
        "status": "resolved",
        "resolution": "provider",
        "sector": "Information Technology",
        "industry_group": "Semiconductors",
        "industry": "Semiconductors",
        "official_industry": "Semiconductors",
        "cycle_tag": "cyclical",
        "provider": "yahoo",
        "provider_sector": "Technology",
        "provider_industry": "Semiconductors",
        "regime_bias": "unknown",
        "side_support": "unknown",
        "regime_note": "Side support cannot be determined.",
        "tag_provenance": {"tag_source": "manual", "source_vintage": "2026"},
    }


def portfolio_analysis_payload():
    return {
        "positions": [
            {"symbol": "NVDA", "side": 1, "allocation": 100.0},
            {"symbol": "MSFT", "side": -1, "allocation": 100.0},
        ],
        "missing_inputs": [],
        "window": {
            "start_date": "2024-01-01",
            "end_date": "2026-01-01",
            "weekly_count": 105,
        },
        "volatility": {
            "status": "ok",
            "gross_exposure": 200.0,
            "positions": [
                {"symbol": "NVDA", "allocation": 100.0, "signed_weight": 0.5},
                {"symbol": "MSFT", "allocation": -100.0, "signed_weight": -0.5},
            ],
            "variance": 0.002,
            "weekly_stdev": 0.045,
            "annualized_stdev": 0.32,
            "average_asset_weekly_stdev": 0.05,
            "average_asset_annualized_stdev": 0.36,
            "sharpe_scenarios": [
                {"sharpe": 0.5, "expected_annual_return": 0.16},
                {"sharpe": 1.0, "expected_annual_return": 0.32},
            ],
            "position_count_check": {
                "count": 2,
                "within_range": False,
                "warning": "under_diversified",
            },
        },
        "correlation": {
            "status": "ok",
            "symbols": ["NVDA", "MSFT"],
            "sides": [1, -1],
            "matrix": [[None, -0.2], [-0.2, None]],
            "per_position_average": [-0.2, -0.2],
            "overall_average": -0.2,
            "disclaimer": "indicative only, does not account for weightings",
        },
        "beta": {
            "status": "ok",
            "window": 105,
            "per_position": [
                {
                    "symbol": "NVDA",
                    "side": 1,
                    "window": 105,
                    "label": "2y",
                    "status": "ok",
                    "beta": 1.4,
                    "standard_error": 0.21,
                    "sample_size": 105,
                }
            ],
            "excluded_from_portfolio": ["MSFT"],
            "portfolio": {
                "positions": [{"symbol": "NVDA", "shares": 1, "price": 100.0}],
                "net_exposure": 100.0,
                "gross_exposure": 100.0,
                "net_weight": 1.0,
                "portfolio_beta": 1.4,
            },
            "sizing": {
                "equal_weight": {
                    "positions": [{"symbol": "NVDA", "weight": 1.0, "shares": 1}],
                    "note": "baseline head check only, not a recommendation",
                },
                "risk_parity": {
                    "positions": [{"symbol": "NVDA", "weight": 1.0, "shares": 1}],
                    "note": "baseline head check only, not a recommendation",
                },
                "beta_parity": {
                    "positions": [{"symbol": "NVDA", "weight": 0.5, "shares": 1}],
                    "note": "baseline head check only, not a recommendation",
                },
            },
        },
        "gates": {
            "position_count": {"status": "unknown", "reason": "margin_capital not provided"},
            "volatility": {"status": "above", "annual_vol": 0.32},
        },
        "outperformance_inference": {
            "status": "valid",
            "gross_long": 100.0,
            "gross_short": 100.0,
            "conclusion": "equal gross weights allow comparing",
        },
    }


def pair_analysis_payload(sessions=120):
    return {
        "long": context_payload("NVDA"),
        "short": context_payload("AMD"),
        "pair": {
            "pair_type": "intra_sector_constituent",
            "retained_risks": ["stock"],
            "missing": [],
        },
        "window": {
            "sessions": sessions,
            "start_date": "2025-01-01",
            "end_date": "2026-01-01",
        },
        "outperformance": {
            "sessions": sessions,
            "start_date": "2025-01-01",
            "end_date": "2026-01-01",
            "long_return": 0.4,
            "short_return": 0.1,
            "outperformance": 0.3,
        },
        "series": {
            "dates": [f"2025-{(index % 12) + 1:02d}-15" for index in range(sessions)],
            "ratio": [1.0 + index * 0.01 for index in range(sessions)],
            "spread": [10.0 + index for index in range(sessions)],
            "cew_index": [100.0 + index * 0.5 for index in range(sessions)],
        },
    }


def test_compact_ticker_risk_keeps_windows_and_trims_rolling_beta():
    compacted = compact_ticker_risk(ticker_risk_payload())
    assert compacted["symbol"] == "NVDA"
    assert compacted["benchmark"] == "^GSPC"
    assert compacted["beta"]["windows"][0] == {
        "label": "2y",
        "status": "ok",
        "beta": 1.4,
        "standard_error": 0.21,
        "sample_size": 105,
    }
    assert compacted["beta"]["windows"][1]["status"] == "insufficient_data"
    rolling = compacted["beta"]["rolling_beta"]
    assert len(rolling) == 26
    assert rolling == ticker_risk_payload()["beta"]["rolling_beta"][-26:]
    assert compacted["realized_volatility"]["daily"] == {
        "annualized": 0.32,
        "sample_size": 250,
    }
    assert compacted["realized_volatility"]["monthly_21d"] == {
        "annualized": None,
        "sample_size": 10,
        "status": "insufficient_data",
        "required": 21,
    }
    assert compacted["data"]["weekly_count"] == 105


def test_compact_ticker_risk_short_rolling_beta_is_untouched():
    payload = ticker_risk_payload(rolling_points=10)
    compacted = compact_ticker_risk(payload)
    assert compacted["beta"]["rolling_beta"] == payload["beta"]["rolling_beta"]


def test_compact_portfolio_analysis_drops_matrix_and_sizing_shares():
    payload = portfolio_analysis_payload()
    compacted = compact_portfolio_analysis(payload)
    correlation = compacted["correlation"]
    assert "matrix" not in correlation
    assert "sides" not in correlation
    assert correlation["overall_average"] == -0.2
    assert correlation["per_position_average"] == [
        {"symbol": "NVDA", "average_correlation": -0.2},
        {"symbol": "MSFT", "average_correlation": -0.2},
    ]
    assert correlation["disclaimer"].startswith("indicative only")
    volatility = compacted["volatility"]
    assert "positions" not in volatility
    assert "variance" not in volatility
    assert volatility["annualized_stdev"] == 0.32
    assert volatility["position_count_check"]["warning"] == "under_diversified"
    beta = compacted["beta"]
    assert beta["portfolio"] == {
        "portfolio_beta": 1.4,
        "net_weight": 1.0,
        "gross_exposure": 100.0,
    }
    assert beta["excluded_from_portfolio"] == ["MSFT"]
    for scenario in beta["sizing"].values():
        assert "shares" not in scenario["positions"][0]
        assert set(scenario["positions"][0]) == {"symbol", "weight"}
        assert scenario["note"].startswith("baseline head check")
    assert compacted["gates"] == payload["gates"]
    assert compacted["outperformance_inference"]["status"] == "valid"
    assert compacted["window"]["weekly_count"] == 105
    assert len(json.dumps(compacted)) < len(json.dumps(payload))


def test_compact_portfolio_analysis_preserves_insufficient_sections():
    payload = portfolio_analysis_payload()
    payload["volatility"] = {
        "status": "insufficient_data",
        "reason": "fewer than 2 usable positions",
    }
    payload["correlation"] = {
        "status": "insufficient_data",
        "reason": "fewer than 2 usable positions",
    }
    payload["beta"] = {
        "status": "insufficient_data",
        "reason": "fewer than 2 usable positions",
    }
    compacted = compact_portfolio_analysis(payload)
    assert compacted["volatility"]["status"] == "insufficient_data"
    assert compacted["correlation"]["status"] == "insufficient_data"
    assert compacted["beta"]["status"] == "insufficient_data"


def test_compact_pair_analysis_trims_ratio_and_summarizes_series():
    payload = pair_analysis_payload()
    compacted = compact_pair_analysis(payload)
    assert compacted["pair"]["pair_type"] == "intra_sector_constituent"
    assert compacted["window"]["sessions"] == 120
    assert compacted["outperformance"]["outperformance"] == 0.3
    assert len(compacted["series"]["ratio"]) == 60
    assert compacted["series"]["ratio"] == payload["series"]["ratio"][-60:]
    assert compacted["series"]["dates"] == payload["series"]["dates"][-60:]
    assert compacted["series"]["spread"] == {
        "first": 10.0,
        "last": 129.0,
        "min": 10.0,
        "max": 129.0,
    }
    assert compacted["series"]["cew_index"] == {
        "first": 100.0,
        "last": 159.5,
        "min": 100.0,
        "max": 159.5,
    }
    assert compacted["long"]["symbol"] == "NVDA"
    assert compacted["short"]["cycle_tag"] == "cyclical"


def test_compact_ticker_context_keeps_essentials():
    compacted = compact_ticker_context(context_payload("NVDA"))
    assert compacted == {
        "symbol": "NVDA",
        "company_name": "NVDA Inc",
        "status": "resolved",
        "sector": "Information Technology",
        "industry_group": "Semiconductors",
        "industry": "Semiconductors",
        "cycle_tag": "cyclical",
        "regime_bias": "unknown",
        "side_support": "unknown",
        "regime_note": "Side support cannot be determined.",
    }


def test_compact_portfolio_result_dispatches_per_operation():
    assert compact_portfolio_result("ticker_risk_profile", ticker_risk_payload())[
        "symbol"
    ] == "NVDA"
    assert compact_portfolio_result(
        "ticker_industry_context", context_payload("AMD")
    )["symbol"] == "AMD"
    with pytest.raises(ValueError, match="unknown portfolio operation"):
        compact_portfolio_result("unknown_op", {})
