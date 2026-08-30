from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ticker_quant as ticker_quant_router
from app.services import ticker_quant_context as ticker_quant_context_service


_test_app = FastAPI()
_test_app.include_router(ticker_quant_router.router)
client = TestClient(_test_app)


def resolved_payload():
    return {
        "symbol": "NVDA",
        "fetched_at": "2026-08-26T07:00:00+00:00",
        "cache": "refreshed",
        "provider": "yahoo",
        "valuation": {
            "forward_pe": 16.34,
            "forward_eps": 13.041,
            "trailing_eps": 6.67,
            "market_cap": 5.16e12,
        },
        "peer": None,
        "short_checks": {
            "short_percent_of_float": 0.0126,
            "days_to_cover": {"value": 15.0, "status": "within", "sample_days": 30},
            "dividend": {
                "yield": 0.0048,
                "review_questions": ["Is the company paying a dividend?"],
            },
        },
        "backward_ratios": {"ratios": [], "missing_inputs": []},
        "estimate_consensus": {"status": "insufficient_data"},
        "estimate_revision_trend": {"status": "accumulating", "sample_snapshots": 0},
    }


def test_lookup_returns_service_payload(monkeypatch):
    seen = {}

    def fake_context(symbol, peer=None, db_path=None, http_client=None):
        seen["symbol"] = symbol
        seen["peer"] = peer
        return resolved_payload()

    monkeypatch.setattr(
        ticker_quant_context_service, "get_ticker_quant_context", fake_context
    )

    response = client.get("/api/ticker-quant/nvda")

    assert response.status_code == 200
    assert response.json() == resolved_payload()
    assert seen == {"symbol": "nvda", "peer": None}


def test_lookup_passes_peer_override(monkeypatch):
    seen = {}

    def fake_context(symbol, peer=None, db_path=None, http_client=None):
        seen["peer"] = peer
        return resolved_payload()

    monkeypatch.setattr(
        ticker_quant_context_service, "get_ticker_quant_context", fake_context
    )

    response = client.get("/api/ticker-quant/NVDA", params={"peer": "AMD"})

    assert response.status_code == 200
    assert seen["peer"] == "AMD"


def test_lookup_converts_value_error_to_400(monkeypatch):
    def fake_context(symbol, peer=None, db_path=None, http_client=None):
        raise ValueError("symbol is required")

    monkeypatch.setattr(
        ticker_quant_context_service, "get_ticker_quant_context", fake_context
    )

    response = client.get("/api/ticker-quant/%20%20")

    assert response.status_code == 400
    assert "symbol is required" in response.json()["detail"]
