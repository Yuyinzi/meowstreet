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


def test_workflow_evaluate_endpoint_accepts_sparse_ticker_payload():
    response = client.post(
        "/api/method-system/workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "XYZ"
    assert "nodes" in payload
    assert "final_status" in payload
