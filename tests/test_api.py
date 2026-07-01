from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_method_endpoint_returns_graph():
    response = client.get("/api/method-system/method")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v1"
    assert payload["workflow_nodes"]
    assert payload["node_checks"]


def test_workflow_evaluate_endpoint_accepts_sparse_ticker_payload(monkeypatch):
    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/method-system/workflow/evaluate",
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
        observations["metrics"] = {"price": 123.45}
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
        "/api/method-system/workflow/evaluate",
        json={"symbol": "AAPL", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    readiness_node = next(
        node for node in payload["nodes"] if node["node_id"] == "data_readiness"
    )
    assert readiness_node["checks"]
