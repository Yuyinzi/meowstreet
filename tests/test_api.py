from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_method_endpoint_returns_graph():
    response = client.get("/api/ticker-workflow/method")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v1"
    assert payload["workflow_nodes"]
    assert payload["node_checks"]


def test_method_endpoint_uses_stable_top_level_graph():
    response = client.get("/api/ticker-workflow/method")

    assert response.status_code == 200
    payload = response.json()
    assert [node["id"] for node in payload["workflow_nodes"]] == [
        "data_readiness",
        "macro_regime",
        "sector_theme_context",
        "fundamental_quantitative_bias",
        "fundamental_qualitative_bias",
        "international_adr_workflow",
        "catalyst_window",
        "technical_timing",
        "portfolio_construction",
        "trade_risk_management",
        "process_discipline",
        "final_synthesis",
    ]


def test_workflow_evaluate_endpoint_accepts_sparse_ticker_payload(monkeypatch):
    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "XYZ"
    assert "nodes" in payload
    assert "final_status" in payload


def test_workflow_evaluate_endpoint_uses_tool_runner(monkeypatch):
    def fake_apply_tools(method, observation_payload):
        assert observation_payload["symbol"] == "AAPL"
        observations = dict(observation_payload.get("observations", {}))
        observations["metrics"] = {
            "price": 123.45,
            "avg_dollar_volume_millions": 10,
        }
        observations["data"] = {
            "price_series_current": True,
            "uses_adjusted_close": True,
            "no_missing_required_fields": True,
        }
        observations["prices"] = {
            "dates": ["2026-06-30"],
            "adjusted_close": [123.45],
        }
        return observations

    from app import api

    monkeypatch.setattr(api.tool_runner, "apply_tools", fake_apply_tools)

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={"symbol": "AAPL", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    readiness_node = next(
        node for node in payload["nodes"] if node["node_id"] == "data_readiness"
    )
    groups = {
        check["check_id"]: check.get("group") for check in readiness_node["checks"]
    }
    assert groups["symbol_present"] == "instrument_identity"
    assert groups["market_price_available"] == "market_data"
    assert groups["price_floor"] == "liquidity_tradability"
