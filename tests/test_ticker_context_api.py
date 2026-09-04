import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.services import ticker_industry_context as ticker_context_service

client = TestClient(app)


def resolved_payload():
    return {
        "symbol": "NVDA",
        "company_name": "NVIDIA Corporation",
        "status": "resolved",
        "resolution": "provider",
        "sector": "Information Technology",
        "industry_group": "Semiconductors & Semi Conductor Equipment",
        "industry": "Semiconductors & Semi Conductor Equipment",
        "official_industry": "Semiconductors & Semiconductor Equipment",
        "cycle_tag": "cyclical",
        "provider": "yahoo",
        "provider_sector": "Technology",
        "provider_industry": "Semiconductors",
        "regime_bias": "unknown",
        "regime_source": None,
        "side_support": "unknown",
        "regime_note": "Side support is unavailable: the survey-based GDP growth direction is mixed, missing, or stale.",
        "tag_provenance": {
            "tag_source": "method_workbook",
            "source_vintage": "2021-gics",
        },
    }


def test_lookup_returns_service_payload(monkeypatch):
    seen = {}

    def fake_context(symbol, industry_override=None):
        seen["symbol"] = symbol
        seen["industry_override"] = industry_override
        return resolved_payload()

    monkeypatch.setattr(
        ticker_context_service, "get_ticker_industry_context", fake_context
    )

    response = client.get("/api/ticker-context/nvda")

    assert response.status_code == 200
    assert response.json() == resolved_payload()
    assert seen == {"symbol": "nvda", "industry_override": None}


def test_lookup_passes_industry_override(monkeypatch):
    seen = {}

    def fake_context(symbol, industry_override=None):
        seen["industry_override"] = industry_override
        return resolved_payload()

    monkeypatch.setattr(
        ticker_context_service, "get_ticker_industry_context", fake_context
    )

    response = client.get(
        "/api/ticker-context/NVDA",
        params={"industry": "Semiconductors & Semi Conductor Equipment"},
    )

    assert response.status_code == 200
    assert seen["industry_override"] == "Semiconductors & Semi Conductor Equipment"


def test_lookup_converts_value_error_to_400(monkeypatch):
    def fake_context(symbol, industry_override=None):
        raise ValueError("asset profile fetch failed for NOPE: HTTP 404 Not Found")

    monkeypatch.setattr(
        ticker_context_service, "get_ticker_industry_context", fake_context
    )

    response = client.get("/api/ticker-context/NOPE")

    assert response.status_code == 400
    assert "asset profile fetch failed for NOPE" in response.json()["detail"]


def test_industries_returns_tag_rows(monkeypatch):
    monkeypatch.setattr(
        ticker_context_service,
        "list_gics_industries",
        lambda: [{"industry": "Banks", "cycle_tag": "cyclical"}],
    )

    response = client.get("/api/ticker-context/industries")

    assert response.status_code == 200
    assert response.json() == {
        "industries": [{"industry": "Banks", "cycle_tag": "cyclical"}]
    }
