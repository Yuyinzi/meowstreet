from fastapi.testclient import TestClient

from app.api import app
from app.services import portfolio_analysis as portfolio_analysis_service

client = TestClient(app)


def profile_payload():
    return {
        "symbol": "AAA",
        "benchmark": "^GSPC",
        "beta": {
            "windows": [
                {
                    "window": 105,
                    "label": "2y",
                    "status": "ok",
                    "beta": 2.0,
                    "standard_error": 0.0,
                    "sample_size": 105,
                }
            ],
            "rolling_beta": [{"end_date": "2026-01-05", "beta": 2.0}],
        },
        "realized_volatility": {
            "daily": {"stdev": 0.01, "annualized": 0.158, "sample_size": 69},
            "weekly": {"stdev": 0.02, "annualized": 0.144, "sample_size": 129},
            "monthly_21d": {"stdev": 0.01, "annualized": 0.158, "sample_size": 21},
            "quarterly_63d": {"stdev": 0.01, "annualized": 0.158, "sample_size": 63},
        },
        "data": {
            "weekly_start": "2020-01-06",
            "weekly_end": "2022-06-27",
            "weekly_count": 130,
        },
    }


def analysis_payload():
    return {
        "positions": [{"symbol": "AAA", "side": 1, "allocation": 100.0}],
        "missing_inputs": [],
        "window": {
            "start_date": "2020-01-06",
            "end_date": "2022-06-27",
            "weekly_count": 130,
        },
        "volatility": {"status": "insufficient_data", "reason": "fewer than 2 usable positions"},
        "correlation": {"status": "insufficient_data", "reason": "fewer than 2 usable positions"},
        "beta": {"status": "insufficient_data", "reason": "fewer than 2 usable positions"},
        "gates": {
            "position_count": {"status": "unknown", "reason": "margin_capital not provided"},
            "volatility": {"status": "unknown", "reason": "portfolio volatility unavailable"},
            "correlation": {"status": "unknown", "reason": "portfolio correlation unavailable"},
            "net_beta": {"status": "unknown", "reason": "portfolio beta unavailable"},
        },
        "outperformance_inference": {
            "status": "insufficient_data",
            "reason": "both long and short gross exposure are required",
            "gross_long": 100.0,
            "gross_short": 0,
        },
    }


def test_ticker_risk_route_returns_service_payload(monkeypatch):
    seen = {}

    def fake_profile(symbol, db_path=None, http_client=None):
        seen["symbol"] = symbol
        return profile_payload()

    monkeypatch.setattr(
        portfolio_analysis_service, "get_ticker_risk_profile", fake_profile
    )

    response = client.get("/api/ticker-risk/aaa")

    assert response.status_code == 200
    assert response.json() == profile_payload()
    assert seen["symbol"] == "aaa"


def test_ticker_risk_route_converts_value_error_to_400(monkeypatch):
    def fake_profile(symbol, db_path=None, http_client=None):
        raise ValueError(f"market data is missing for {symbol}")

    monkeypatch.setattr(
        portfolio_analysis_service, "get_ticker_risk_profile", fake_profile
    )

    response = client.get("/api/ticker-risk/UNKNOWN")

    assert response.status_code == 400
    assert "market data is missing for UNKNOWN" in response.json()["detail"]


def test_portfolio_analysis_route_returns_service_payload(monkeypatch):
    seen = {}

    def fake_analysis(payload, db_path=None, http_client=None):
        seen["payload"] = payload
        return analysis_payload()

    monkeypatch.setattr(
        portfolio_analysis_service, "get_portfolio_analysis", fake_analysis
    )

    body = {"positions": [{"symbol": "AAA", "side": "long", "allocation": 100}]}
    response = client.post("/api/portfolio-analysis", json=body)

    assert response.status_code == 200
    assert response.json() == analysis_payload()
    assert seen["payload"] == body


def test_portfolio_analysis_route_converts_value_error_to_400(monkeypatch):
    def fake_analysis(payload, db_path=None, http_client=None):
        raise ValueError("positions must be a non-empty list")

    monkeypatch.setattr(
        portfolio_analysis_service, "get_portfolio_analysis", fake_analysis
    )

    response = client.post("/api/portfolio-analysis", json={})

    assert response.status_code == 400
    assert "positions must be a non-empty list" in response.json()["detail"]


def test_portfolio_analysis_route_validates_payload():
    response = client.post(
        "/api/portfolio-analysis",
        json={"positions": [{"symbol": "AAA", "side": "flat", "allocation": 100}]},
    )

    assert response.status_code == 400
    assert "side must be long or short" in response.json()["detail"]
