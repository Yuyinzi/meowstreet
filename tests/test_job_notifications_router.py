from fastapi.testclient import TestClient
import pytest

from app.api import app
from app.db import job_notifications as db
from app.services import job_notifications as service


client = TestClient(app)


def test_empty_then_complete_run_is_delivered_in_order():
    assert client.get("/api/notifications").json()["events"] == []
    handle = service.start_run("macro_refresh")
    handle.finish(0)
    payload = client.get("/api/notifications/events?after=0").json()
    assert [e["status"] for e in payload["events"]] == ["running", "succeeded"]
    assert payload["unread_count"] == 2
    history = client.get("/api/notifications/runs").json()
    assert history["runs"][0]["run_id"] == handle.run_id
    detail = client.get(f"/api/notifications/runs/{handle.run_id}").json()
    assert detail["status"] == "succeeded"
    result = client.post("/api/notifications/read", json={"event_ids": history["displayed_event_ids"]})
    assert result.json()["unread_count"] == 0
    assert client.get("/api/notifications/runs/unknown").status_code == 404


@pytest.mark.parametrize("path", ["/events?after=-1", "/events?limit=101", "/runs?limit=0", "/runs?status=bogus", "/runs?job_id=bogus", "/runs?before=0"])
def test_invalid_queries_are_rejected(path):
    assert client.get("/api/notifications" + path).status_code in {400, 422}


@pytest.mark.parametrize("body", [{"event_ids": [-1]}, {"event_ids": [True]}, {"event_ids": ["1"]}, {"event_ids": list(range(1, 202))}, {"event_ids": [], "extra": True}])
def test_invalid_read_body_is_rejected(body):
    assert client.post("/api/notifications/read", json=body).status_code in {400, 422}


def test_unavailable_database_is_not_empty_success(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("private path secret")

    monkeypatch.setattr(db, "connect", unavailable)
    response = client.get("/api/notifications")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_read_all_and_clear_keep_history_and_new_results():
    handle = service.start_run("macro_refresh")
    cursor = client.get("/api/notifications").json()["next_cursor"]
    handle.finish(0)
    assert client.post("/api/notifications/read-all", json={"through": cursor}).json()["unread_count"] == 1
    assert client.post("/api/notifications/clear", json={"through": cursor}).status_code == 200
    snapshot = client.get("/api/notifications").json()
    assert [event["status"] for event in snapshot["events"]] == ["succeeded"]
    assert len(client.get("/api/notifications/runs").json()["runs"]) == 1


@pytest.mark.parametrize("body", [{"through": -1}, {"through": True}, {"through": "1"}, {}, {"through": 0, "extra": True}])
def test_bulk_action_requires_an_explicit_valid_cursor(body):
    for endpoint in ("read-all", "clear"):
        assert client.post(f"/api/notifications/{endpoint}", json=body).status_code == 422
