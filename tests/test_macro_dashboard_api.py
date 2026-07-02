from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_macro_dashboard_page_routes_are_served():
    response = client.get("/macro-dashboard.html")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_market_phase_api_returns_lightweight_market_overview(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection:
            def close(self):
                pass

        return FakeConnection()

    def fake_load_price_rows(con, benchmark_id):
        assert con is not None
        if benchmark_id != "us_sp500":
            return []
        return [
            {
                "date": "2020-01-01",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            },
            {
                "date": "2020-01-02",
                "open": 79.0,
                "high": 79.0,
                "low": 79.0,
                "close": 79.0,
            },
        ]

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", fake_load_price_rows
    )

    response = client.get("/api/macro-dashboard/market-phase")

    assert response.status_code == 200
    payload = response.json()
    assert payload["markets"][0]["benchmark_id"] == "us_sp500"
    assert payload["markets"][0]["latest"]["market_phase_status"] == "bear_market"
    assert "series" not in payload["markets"][0]


def test_market_phase_detail_api_returns_one_chart_series(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection:
            def close(self):
                pass

        return FakeConnection()

    def fake_load_price_rows(con, benchmark_id):
        assert con is not None
        assert benchmark_id == "us_sp500"
        return [
            {
                "date": "2020-01-01",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            },
            {
                "date": "2020-01-02",
                "open": 79.0,
                "high": 79.0,
                "low": 79.0,
                "close": 79.0,
            },
        ]

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", fake_load_price_rows
    )

    response = client.get("/api/macro-dashboard/market-phase/us_sp500")

    assert response.status_code == 200
    payload = response.json()
    assert payload["benchmark_id"] == "us_sp500"
    assert payload["latest"]["market_phase_status"] == "bear_market"
    assert len(payload["series"]) == 2


def test_market_phase_detail_api_returns_400_for_unknown_benchmark(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection:
            def close(self):
                pass

        return FakeConnection()

    def fake_load_price_rows(con, benchmark_id):
        return []

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", fake_load_price_rows
    )

    response = client.get("/api/macro-dashboard/market-phase/unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "benchmark is unknown: unknown"


def test_market_phase_refresh_api_refreshes_one_benchmark(monkeypatch):
    from app import api

    calls = []

    def fake_refresh_benchmarks(benchmark_ids):
        calls.append(benchmark_ids)
        return [
            {
                "benchmark_id": "us_sp500",
                "symbol": "^GSPC",
                "rows_upserted": 2,
                "latest_date": "2026-07-01",
                "source": "yahoo_finance:^GSPC",
            }
        ]

    monkeypatch.setattr(
        api.benchmark_market_data_tool, "refresh_benchmarks", fake_refresh_benchmarks
    )

    response = client.post("/api/macro-dashboard/market-phase/us_sp500/refresh")

    assert response.status_code == 200
    assert response.json() == {
        "benchmark_id": "us_sp500",
        "symbol": "^GSPC",
        "rows_upserted": 2,
        "latest_date": "2026-07-01",
        "source": "yahoo_finance:^GSPC",
    }
    assert calls == [["us_sp500"]]


def test_market_phase_refresh_api_returns_400_for_refresh_errors(monkeypatch):
    from app import api

    def fake_refresh_benchmarks(benchmark_ids):
        raise ValueError("benchmark refresh is unknown: unknown")

    monkeypatch.setattr(
        api.benchmark_market_data_tool, "refresh_benchmarks", fake_refresh_benchmarks
    )

    response = client.post("/api/macro-dashboard/market-phase/unknown/refresh")

    assert response.status_code == 400
    assert response.json() == {"detail": "benchmark refresh is unknown: unknown"}
