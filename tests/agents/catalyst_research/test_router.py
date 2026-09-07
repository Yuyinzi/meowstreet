import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.catalyst_research import router as catalyst_router


class FakeConnection:
    def close(self):
        pass


def _latest_result(**overrides):
    result = {
        "schema_version": "catalyst_research_result_v1",
        "research_version": "catalyst_research_v1",
        "job_id": "cr_1",
        "status": "completed",
        "ticker": "NVDA",
        "company_name": "NVIDIA Corporation",
        "cik": 1045810,
        "as_of": "2026-09-04",
        "requested_window": {"start": "2022-09-04", "end": "2026-09-04", "years": 4},
        "sources": [
            {
                "source_id": "irs_1",
                "job_id": "cr_1",
                "ticker": "NVDA",
                "source_type": "press_releases",
                "url": "https://nvidianews.example.test/news",
                "final_url": "https://nvidianews.example.test/news",
                "acceptance_status": "accepted",
                "extraction_status": "complete",
                "active_adapter_id": "ira_1",
                "adapter_version": 2,
                "executor_version": "executor-v1",
                "evidence_result_ids": ["sr_1", "sr_2"],
                "requested_start": "2022-09-04",
                "requested_end": "2026-09-04",
                "coverage_start": "2022-09-04",
                "coverage_end": "2026-09-04",
                "coverage_continuous": True,
                "verification_reason": None,
                "page_count": 3,
                "item_count": 78,
                "content_hash": "abc",
                "snapshot_hash": "def",
                "truncation_reason": None,
                "discovery_provider": None,
                "execution_path": "hot",
                "checked_at": "2026-09-04T01:00:00+00:00",
            }
        ],
        "statistics": {"press_releases": {"total": 78}},
        "warnings": [],
        "next_actions": [],
        "error_summary": None,
        "completed_at": "2026-09-04T01:00:00+00:00",
        "observation_count": 109,
        "execution_paths": {"press_releases": "hot"},
        "call_counts": {"discovery": 0},
        "latest_job_id": "cr_1",
        "latest_job_status": "completed",
        "latest_job_completed_at": "2026-09-04T01:00:00+00:00",
    }
    result.update(overrides)
    return result


def _client(monkeypatch, *, latest=None, events_page=None, adapter_brief=None, recorded=None):
    monkeypatch.setattr(catalyst_router.repository, "connect", lambda *args, **kwargs: FakeConnection())
    monkeypatch.setattr(catalyst_router.repository, "load_latest_result", lambda con, ticker: latest)

    def events(con, ticker, job_id, limit, cursor):
        if recorded is not None:
            recorded.append({"ticker": ticker, "job_id": job_id, "limit": limit, "cursor": cursor})
        if isinstance(events_page, Exception):
            raise events_page
        return events_page

    monkeypatch.setattr(catalyst_router.repository, "load_events_page", events)
    monkeypatch.setattr(catalyst_router.repository, "load_adapter_brief", lambda con, adapter_id: adapter_brief)
    app = FastAPI()
    app.include_router(catalyst_router.router)
    return TestClient(app)


def test_summary_unknown_ticker_returns_not_researched_with_cli_next_action(monkeypatch):
    client = _client(monkeypatch, latest=None)

    response = client.get("/api/ticker-quant/nvda/catalyst-research")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_researched"
    assert payload["ticker"] == "NVDA"
    assert payload["observation_count"] == 0
    assert payload["next_actions"]
    assert "python -m app.agents.catalyst_research NVDA" in payload["next_actions"][0]


def test_summary_completed_exposes_compact_sources_and_hides_internal_evidence(monkeypatch):
    client = _client(
        monkeypatch,
        latest=_latest_result(),
        adapter_brief={"adapter_id": "ira_1", "version": 2, "status": "active", "access_mode": "html"},
    )

    response = client.get("/api/ticker-quant/NVDA/catalyst-research")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["observation_count"] == 109
    source = payload["sources"][0]
    assert source == {
        "source_type": "press_releases",
        "url": "https://nvidianews.example.test/news",
        "acceptance_status": "accepted",
        "extraction_status": "complete",
        "execution_path": "hot",
        "coverage_start": "2022-09-04",
        "coverage_end": "2026-09-04",
        "observation_count": 78,
        "truncation_reason": None,
        "adapter": {"adapter_id": "ira_1", "version": 2, "status": "active", "access_mode": "html"},
    }
    forbidden = ("evidence_result_ids", "adapter_json", "raw_html", "structural_html", "snapshot_hash", "content_hash", "prompt")
    assert all(key not in response.text for key in forbidden)
    assert "cik" not in payload
    assert "call_counts" not in payload
    assert "execution_paths" not in payload
    assert "error_summary" not in payload


def test_summary_partial_identifies_truncated_source(monkeypatch):
    latest = _latest_result(status="completed_partial")
    latest["sources"][0]["extraction_status"] = "partial"
    latest["sources"][0]["truncation_reason"] = "max_pages"
    latest["sources"][0]["active_adapter_id"] = None
    latest["sources"][0]["execution_path"] = "cold"
    latest["sources"][0]["discovery_provider"] = "manual_override"
    client = _client(monkeypatch, latest=latest)

    payload = client.get("/api/ticker-quant/NVDA/catalyst-research").json()

    assert payload["status"] == "completed_partial"
    source = payload["sources"][0]
    assert source["extraction_status"] == "partial"
    assert source["truncation_reason"] == "max_pages"
    assert source["discovery_provider"] == "manual_override"
    assert "adapter" not in source


@pytest.mark.parametrize("latest_status", ["running", "failed"])
def test_summary_returns_older_usable_result_with_newest_job_status(monkeypatch, latest_status):
    latest = _latest_result(latest_job_id="cr_2", latest_job_status=latest_status, latest_job_completed_at=None)
    client = _client(monkeypatch, latest=latest)

    payload = client.get("/api/ticker-quant/NVDA/catalyst-research").json()

    assert payload["status"] == "completed"
    assert payload["job_id"] == "cr_1"
    assert payload["latest_job_status"] == latest_status
    assert payload["completed_at"] == "2026-09-04T01:00:00+00:00"
    assert payload["latest_job_completed_at"] is None


def test_events_default_job_limit_and_field_whitelist(monkeypatch):
    recorded = []
    page = {
        "ticker": "NVDA",
        "job_id": "cr_1",
        "events": [
            {
                "event_id": "ire_1",
                "job_id": "cr_1",
                "source_id": "irs_1",
                "ticker": "NVDA",
                "published_date": "2026-08-27",
                "event_date": None,
                "count_date": "2026-08-27",
                "title": "NVIDIA Announces Financial Results",
                "normalized_title": "nvidia announces financial results",
                "canonical_url": "https://nvidianews.example.test/news/1",
                "source_type": "press_releases",
                "earnings_state": "earnings",
                "classification_method": "rule_v1",
                "adapter_id": "ira_1",
                "adapter_version": 2,
                "executor_version": "executor-v1",
                "first_seen_at": "2026-09-04T01:00:00+00:00",
                "content_hash": "abc",
            }
        ],
        "next_cursor": "cursor-1",
    }
    client = _client(monkeypatch, latest=_latest_result(), events_page=page, recorded=recorded)

    response = client.get("/api/ticker-quant/nvda/catalyst-research/events")

    assert response.status_code == 200
    assert recorded == [{"ticker": "NVDA", "job_id": "cr_1", "limit": 100, "cursor": None}]
    payload = response.json()
    assert payload["job_id"] == "cr_1"
    assert payload["next_cursor"] == "cursor-1"
    assert payload["events"] == [
        {
            "published_date": "2026-08-27",
            "event_date": None,
            "count_date": "2026-08-27",
            "title": "NVIDIA Announces Financial Results",
            "url": "https://nvidianews.example.test/news/1",
            "source_type": "press_releases",
            "earnings_state": "earnings",
            "classification_method": "rule_v1",
            "first_seen_at": "2026-09-04T01:00:00+00:00",
        }
    ]


@pytest.mark.parametrize("limit", [1, 200])
def test_events_accepts_boundary_limits(monkeypatch, limit):
    recorded = []
    page = {"ticker": "NVDA", "job_id": "cr_1", "events": [], "next_cursor": None}
    client = _client(monkeypatch, latest=_latest_result(), events_page=page, recorded=recorded)

    response = client.get(f"/api/ticker-quant/NVDA/catalyst-research/events?limit={limit}")

    assert response.status_code == 200
    assert recorded[0]["limit"] == limit


@pytest.mark.parametrize("limit", [0, 201])
def test_events_rejects_out_of_range_limits(monkeypatch, limit):
    client = _client(monkeypatch, latest=_latest_result(), events_page={})

    response = client.get(f"/api/ticker-quant/NVDA/catalyst-research/events?limit={limit}")

    assert response.status_code == 422


def test_events_passes_explicit_job_and_cursor_through(monkeypatch):
    recorded = []
    page = {"ticker": "NVDA", "job_id": "cr_9", "events": [], "next_cursor": None}
    client = _client(monkeypatch, latest=_latest_result(), events_page=page, recorded=recorded)

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/events?job_id=cr_9&cursor=abc")

    assert response.status_code == 200
    assert recorded == [{"ticker": "NVDA", "job_id": "cr_9", "limit": 100, "cursor": "abc"}]


def test_events_cross_job_or_ticker_cursor_is_rejected(monkeypatch):
    client = _client(monkeypatch, latest=_latest_result(), events_page=ValueError("event cursor does not belong to ticker or job"))

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/events?cursor=abc")

    assert response.status_code == 400
    assert "ticker or job" in response.json()["detail"]


def test_events_unknown_ticker_returns_not_researched(monkeypatch):
    recorded = []
    client = _client(monkeypatch, latest=None, events_page={}, recorded=recorded)

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_researched"
    assert payload["events"] == []
    assert recorded == []
