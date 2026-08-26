import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import quant_screen as quant_screen_router
from app.services import quant_screen as quant_screen_service

app = FastAPI()
app.include_router(quant_screen_router.router)
client = TestClient(app)


def fake_payload():
    return {
        "disclaimer": "Candidate identification only",
        "row_count": 1,
        "sector": {
            "mean_pe1": 20.0,
            "mean_pe2": 18.0,
            "mean_eg1": 0.1,
            "mean_eg2": 0.12,
            "mean_method": "arithmetic mean of valid values",
            "leave_one_out": [],
        },
        "rows": [
            {
                "symbol": "A",
                "price": 30.0,
                "market_cap": 5e9,
                "market_cap_tier": "mid",
                "eps_fy0": 1.0,
                "eps_fy1": 1.2,
                "eps_fy2": 1.5,
                "eps_fy3": None,
                "eg1": 0.2,
                "eg2": 0.25,
                "eg3": None,
                "pe1": 25.0,
                "pe2": 20.0,
                "pe3": None,
                "peg1": 1.25,
                "peg2": 0.8,
                "peg3": None,
                "flags": [],
                "eg_case": 1,
                "eg_case_reason": None,
                "long_filter": {"steps": [], "first_failed": None, "passes": True},
                "short_filter": {"steps": [], "first_failed": None, "passes": False},
            }
        ],
        "row_errors": [],
    }


def test_evaluate_returns_service_payload(monkeypatch):
    seen = {}

    def fake_run(table_text):
        seen["table_text"] = table_text
        return fake_payload()

    monkeypatch.setattr(quant_screen_service, "run_quant_screen", fake_run)

    response = client.post("/api/quant-screen", json={"table_text": "Ticker\tPrice\nA\t10"})

    assert response.status_code == 200
    assert response.json() == fake_payload()
    assert seen["table_text"] == "Ticker\tPrice\nA\t10"


def test_evaluate_rejects_missing_table_text():
    response = client.post("/api/quant-screen", json={})

    assert response.status_code == 400
    assert "table_text" in response.json()["detail"]


def test_evaluate_rejects_non_string_table_text():
    response = client.post("/api/quant-screen", json={"table_text": 123})

    assert response.status_code == 400
    assert "table_text" in response.json()["detail"]


def test_evaluate_converts_value_error_to_400(monkeypatch):
    def fake_run(table_text):
        raise ValueError("screener table is empty")

    monkeypatch.setattr(quant_screen_service, "run_quant_screen", fake_run)

    response = client.post("/api/quant-screen", json={"table_text": "bad"})

    assert response.status_code == 400
    assert "screener table is empty" in response.json()["detail"]
