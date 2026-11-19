from fastapi.testclient import TestClient

from app.api import app
from app.services import macro_data_freshness as service


def test_api_get_is_read_only_and_disables_caching(monkeypatch, tmp_path):
    get = service.get_overview
    monkeypatch.setattr(service, "get_overview", lambda: get(db_path=tmp_path / "data.sqlite", notification_db_path=tmp_path / "tasks.sqlite"))
    client = TestClient(app)
    response = client.get("/api/macro-data-freshness")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["datasets"]
    assert list(tmp_path.iterdir()) == []
    assert client.post("/api/macro-data-freshness").status_code == 405


def test_catalog_failure_returns_retryable_sanitized_error(monkeypatch):
    def fail():
        raise ValueError("secret malformed configuration")
    monkeypatch.setattr(service, "get_overview", fail)
    response = TestClient(app).get("/api/macro-data-freshness")
    assert response.status_code == 503
    assert "retry" in response.json()["detail"]
    assert "secret" not in response.text
