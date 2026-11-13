from fastapi.testclient import TestClient
import pytest

from app.api import app
from app.db import job_notifications as db
from app.services import manual_refresh_notifications as manual
from app.services import ticker_quant_context
from app.tools import benchmark_market_data


client = TestClient(app)


def test_manual_benchmark_return_is_preserved_and_recorded(monkeypatch):
    monkeypatch.setattr(benchmark_market_data, "refresh_benchmarks", lambda ids: [{"benchmark_id": ids[0], "rows": 3}])
    response = client.post("/api/macro-dashboard/market-phase/us_sp500/refresh")
    assert response.json() == {"benchmark_id": "us_sp500", "rows": 3}
    con = db.connect()
    run = db.list_runs(con)["runs"][0]
    assert run["status"] == "succeeded"
    assert run["target"] == "us_sp500"
    assert run["origin"] == "manual"
    con.close()


def test_manual_ticker_refresh_records_only_explicit_operation(monkeypatch):
    monkeypatch.setattr(ticker_quant_context, "get_ticker_quant_context", lambda symbol, **kwargs: {"symbol": symbol, "cache": "refreshed" if kwargs["force_refresh"] else "hit"})
    assert client.get("/api/ticker-quant/AAPL").status_code == 200
    assert client.get("/api/notifications/runs").json()["runs"] == []
    response = client.get("/api/ticker-quant/aapl?refresh=true")
    assert response.json()["symbol"] == "AAPL"
    run = client.get("/api/notifications/runs").json()["runs"][0]
    assert run["job_id"] == "ticker_refresh"
    assert run["target"] == "AAPL"


def test_manual_failure_keeps_original_error_but_sanitizes_notification(monkeypatch):
    def fail(ids):
        raise ValueError("private provider failure")

    monkeypatch.setattr(benchmark_market_data, "refresh_benchmarks", fail)
    response = client.post("/api/macro-dashboard/market-phase/us_sp500/refresh")
    assert response.status_code == 400
    assert response.json()["detail"] == "private provider failure"
    history = client.get("/api/notifications/runs").json()
    assert history["runs"][0]["status"] == "failed"
    assert "private provider failure" not in str(history)


def test_invalid_benchmark_does_not_create_notification():
    with pytest.raises(ValueError, match="benchmark"):
        manual.refresh_benchmark("not-real")
    assert client.get("/api/notifications/runs").json()["runs"] == []
