import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.services import pair_analysis as pair_analysis_service

client = TestClient(app)


def analysis_payload():
    return {
        "long": {"symbol": "NVDA", "status": "resolved", "sector": "Information Technology"},
        "short": {"symbol": "KO", "status": "resolved", "sector": "Consumer Staples"},
        "pair": {
            "pair_type": "cross_sector_constituent",
            "retained_risks": ["sector", "stock"],
            "missing": [],
        },
        "window": {"sessions": 60, "start_date": "2026-05-01", "end_date": "2026-07-31"},
        "outperformance": {
            "sessions": 60,
            "start_date": "2026-05-01",
            "end_date": "2026-07-31",
            "long_return": 0.12,
            "short_return": -0.03,
            "outperformance": 0.15,
        },
        "series": {
            "dates": ["2026-07-31"],
            "ratio": [5.1],
            "spread": [140.0],
            "cew_index": [5.1],
        },
    }


def test_pair_analysis_route_returns_service_payload(monkeypatch):
    seen = {}

    def fake_analysis(long_symbol, short_symbol, sessions=60):
        seen["args"] = (long_symbol, short_symbol, sessions)
        return analysis_payload()

    monkeypatch.setattr(
        pair_analysis_service, "get_pair_analysis", fake_analysis
    )

    response = client.get("/api/pair-analysis/nvda/ko", params={"sessions": 20})

    assert response.status_code == 200
    assert response.json() == analysis_payload()
    assert seen["args"] == ("nvda", "ko", 20)


def test_pair_analysis_route_converts_value_error_to_400(monkeypatch):
    def fake_analysis(long_symbol, short_symbol, sessions=60):
        raise ValueError("fewer than 2 common trading sessions between the pair")

    monkeypatch.setattr(
        pair_analysis_service, "get_pair_analysis", fake_analysis
    )

    response = client.get("/api/pair-analysis/AAA/BBB")

    assert response.status_code == 400
    assert "fewer than 2 common trading sessions" in response.json()["detail"]
