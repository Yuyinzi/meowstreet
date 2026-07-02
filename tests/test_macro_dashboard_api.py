from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_macro_dashboard_page_routes_are_served():
    response = client.get("/macro-dashboard.html")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_market_phase_api_returns_markets(monkeypatch):
    from app import api

    def fake_connect():
        return object()

    def fake_load_price_rows(con, benchmark_id):
        assert con is not None
        if benchmark_id != "us_sp500":
            return []
        return [
            {"date": "2020-01-01", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
            {"date": "2020-01-02", "open": 79.0, "high": 79.0, "low": 79.0, "close": 79.0},
        ]

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(api.benchmark_market_data, "load_price_rows", fake_load_price_rows)

    response = client.get("/api/macro-dashboard/market-phase")

    assert response.status_code == 200
    payload = response.json()
    assert payload["markets"][0]["benchmark_id"] == "us_sp500"
    assert payload["markets"][0]["latest"]["market_phase_status"] == "bear_market"
