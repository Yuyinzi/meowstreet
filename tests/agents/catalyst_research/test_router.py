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


def _v1_1_result(**overrides):
    result = _latest_result(
        schema_version="catalyst_research_result_v1_1",
        research_version="catalyst_research_v1_1",
        mode="research",
        statistics={
            "press_releases": {
                "coverage_status": "observed_partial",
                "discovery_methods": ["rss", "search"],
                "observed_start": "2025-09-10",
                "observed_end": "2026-09-08",
                "observed_total": 84,
                "observed_earnings": 4,
                "observed_non_earnings": 80,
                "observed_non_earnings_per_month": 6.67,
                "observed_non_earnings_per_quarter": 20.0,
                "observed_non_earnings_per_year": 80.0,
                "median_days_between_observed_non_earnings": 4.0,
                "coverage_warning": "search and feed history may omit official records",
            },
            "events_presentations": {
                "coverage_status": "missing",
                "discovery_methods": [],
                "observed_start": None,
                "observed_end": None,
                "observed_total": 0,
                "observed_earnings": 0,
                "observed_non_earnings": 0,
                "coverage_warning": "search and feed history may omit official records",
            },
        },
    )
    result["sources"] = [
        {
            "source_id": "irs_9",
            "job_id": "cr_1",
            "ticker": "NVDA",
            "source_type": "press_releases",
            "url": "https://nvidianews.example.test/rss.xml",
            "final_url": "https://nvidianews.example.test/rss.xml",
            "acceptance_status": "accepted",
            "extraction_status": "complete",
            "endpoint_id": "cse_1",
            "item_count": 84,
            "execution_path": "v1_1",
            "coverage_start": None,
            "coverage_end": None,
            "truncation_reason": None,
            "discovery_provider": None,
            "active_adapter_id": None,
        }
    ]
    result.update(overrides)
    return result


def _client(monkeypatch, *, latest=None, events_page=None, activity_page=None, adapter_brief=None, registry=None, endpoints=None, job_schema_version="catalyst_research_result_v1", recorded=None, activity_recorded=None, accumulated=None):
    monkeypatch.setattr(catalyst_router.repository, "connect", lambda *args, **kwargs: FakeConnection())
    monkeypatch.setattr(catalyst_router.repository, "load_latest_result", lambda con, ticker: latest)
    monkeypatch.setattr(catalyst_router.repository, "load_company_registry", lambda con, ticker: registry)
    monkeypatch.setattr(catalyst_router.repository, "load_source_endpoints", lambda con, ticker: endpoints or [])
    monkeypatch.setattr(catalyst_router.repository, "load_accumulated_channel_events", lambda con, ticker, start, end: accumulated or [])
    monkeypatch.setattr(catalyst_router.repository, "load_job_result_schema_version", lambda con, job_id: job_schema_version)

    def events(con, ticker, job_id, limit, cursor):
        if recorded is not None:
            recorded.append({"ticker": ticker, "job_id": job_id, "limit": limit, "cursor": cursor})
        if isinstance(events_page, Exception):
            raise events_page
        return events_page

    def activity(con, ticker, limit, cursor):
        if activity_recorded is not None:
            activity_recorded.append({"ticker": ticker, "limit": limit, "cursor": cursor})
        if isinstance(activity_page, Exception):
            raise activity_page
        return activity_page

    monkeypatch.setattr(catalyst_router.repository, "load_events_page", events)
    monkeypatch.setattr(catalyst_router.repository, "load_ticker_activity_page", activity)
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
    assert payload["schema_version"] == "catalyst_research_result_v1_1"
    assert payload["next_actions"]
    assert "python -m app.agents.catalyst_research NVDA" in payload["next_actions"][0]
    assert "--mode research" in payload["next_actions"][0]


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


def test_activity_default_limit_and_field_projection(monkeypatch):
    activity_recorded = []
    page = {
        "ticker": "NVDA",
        "events": [
            {
                "count_date": "2026-08-27",
                "title": "NVIDIA Announces Financial Results",
                "source_type": "press_releases",
                "earnings_state": "earnings",
                "canonical_url": "https://nvidianews.example.test/news/1",
                "extraction_provider": "firecrawl",
                "content_hash": "abc",
                "normalized_title": "nvidia announces financial results",
            },
            {
                "count_date": "2026-08-20",
                "title": "NVIDIA Announces New Platform",
                "source_type": "events_presentations",
                "earnings_state": "ambiguous",
                "canonical_url": "https://nvidianews.example.test/news/2",
                "extraction_provider": "feed_metadata",
                "content_hash": None,
                "normalized_title": "nvidia announces new platform",
            },
        ],
        "next_cursor": "cursor-1",
    }
    client = _client(monkeypatch, latest=_latest_result(), activity_page=page, activity_recorded=activity_recorded)

    response = client.get("/api/ticker-quant/nvda/catalyst-research/activity")

    assert response.status_code == 200
    assert activity_recorded == [{"ticker": "NVDA", "limit": 200, "cursor": None}]
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["next_cursor"] == "cursor-1"
    assert payload["events"] == [
        {
            "count_date": "2026-08-27",
            "title": "NVIDIA Announces Financial Results",
            "source_type": "press_releases",
            "earnings_state": "earnings",
            "url": "https://nvidianews.example.test/news/1",
            "extraction_provider": "firecrawl",
            "has_content": True,
        },
        {
            "count_date": "2026-08-20",
            "title": "NVIDIA Announces New Platform",
            "source_type": "events_presentations",
            "earnings_state": "ambiguous",
            "url": "https://nvidianews.example.test/news/2",
            "extraction_provider": "feed_metadata",
            "has_content": False,
        },
    ]
    assert "normalized_title" not in response.text
    assert "content_hash" not in response.text


def test_activity_passes_cursor_through(monkeypatch):
    activity_recorded = []
    page = {"ticker": "NVDA", "events": [], "next_cursor": None}
    client = _client(monkeypatch, latest=_latest_result(), activity_page=page, activity_recorded=activity_recorded)

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/activity?limit=50&cursor=abc")

    assert response.status_code == 200
    assert activity_recorded == [{"ticker": "NVDA", "limit": 50, "cursor": "abc"}]


@pytest.mark.parametrize("limit", [0, 201])
def test_activity_rejects_out_of_range_limits(monkeypatch, limit):
    client = _client(monkeypatch, latest=_latest_result(), activity_page={})

    response = client.get(f"/api/ticker-quant/NVDA/catalyst-research/activity?limit={limit}")

    assert response.status_code == 422


def test_activity_invalid_cursor_returns_400(monkeypatch):
    client = _client(monkeypatch, latest=_latest_result(), activity_page=ValueError("activity cursor does not belong to ticker"))

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/activity?cursor=abc")

    assert response.status_code == 400
    assert "activity cursor" in response.json()["detail"]


def test_activity_unknown_ticker_returns_not_researched(monkeypatch):
    activity_recorded = []
    client = _client(monkeypatch, latest=None, activity_page={}, activity_recorded=activity_recorded)

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/activity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_researched"
    assert payload["events"] == []
    assert payload["next_cursor"] is None
    assert activity_recorded == []


def test_events_unknown_ticker_returns_not_researched(monkeypatch):
    recorded = []
    client = _client(monkeypatch, latest=None, events_page={}, recorded=recorded)

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_researched"
    assert payload["events"] == []
    assert recorded == []


_REGISTRY_ROW = {
    "ticker": "NVDA",
    "company_name": "NVIDIA Corporation",
    "official_domains": ["nvidia.com"],
    "source_confidence": "high",
    "registry_version": 1,
    "discovered_at": "2026-09-01T00:00:00+00:00",
    "last_validated_at": "2026-09-08T00:00:00+00:00",
    "updated_at": "2026-09-08T00:00:00+00:00",
}

_ENDPOINT_ROWS = [
    {
        "endpoint_id": "cse_1",
        "ticker": "NVDA",
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.example.test/rss.xml",
        "domain": "nvidianews.example.test",
        "status": "active",
        "confidence": "high",
        "discovered_at": "2026-09-01T00:00:00+00:00",
        "last_checked_at": "2026-09-08T00:00:00+00:00",
    }
]


def test_summary_returns_v1_1_registry_and_observed_channels(monkeypatch):
    client = _client(monkeypatch, latest=_v1_1_result(), registry=dict(_REGISTRY_ROW), endpoints=[dict(_ENDPOINT_ROWS[0])])

    response = client.get("/api/ticker-quant/NVDA/catalyst-research")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "catalyst_research_result_v1_1"
    assert payload["mode"] == "research"
    assert payload["registry"] == {
        "version": 1,
        "source_confidence": "high",
        "last_validated_at": "2026-09-08T00:00:00+00:00",
    }
    channel = payload["channels"]["press_releases"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["observed_total"] == 84
    assert channel["observed_earnings"] == 4
    assert channel["observed_non_earnings"] == 80
    assert channel["observed_start"] == "2025-09-10"
    assert channel["observed_end"] == "2026-09-08"
    assert channel["coverage_warning"] == "search and feed history may omit official records"
    assert payload["channels"]["events_presentations"]["coverage_status"] == "missing"
    assert payload["endpoints"] == [
        {
            "endpoint_id": "cse_1",
            "channel": "press_releases",
            "endpoint_type": "rss",
            "url": "https://nvidianews.example.test/rss.xml",
            "domain": "nvidianews.example.test",
            "status": "active",
            "confidence": "high",
        }
    ]
    source = payload["sources"][0]
    assert source["endpoint_id"] == "cse_1"
    assert source["execution_path"] == "v1_1"


def _accumulated_event(source_type, count_date, title, earnings_state, url=None, discovery_method=None):
    return {
        "source_type": source_type,
        "count_date": count_date,
        "title": title,
        "normalized_title": title.casefold(),
        "canonical_url": url,
        "earnings_state": earnings_state,
        "discovery_method": discovery_method,
    }


def test_summary_channels_accumulate_events_across_jobs(monkeypatch):
    accumulated = [
        _accumulated_event("events_presentations", "2026-03-03", "NVIDIA at GTC 2026", "non_earnings", discovery_method="search"),
        _accumulated_event("events_presentations", "2026-05-21", "Upcoming events for financial community", "non_earnings", discovery_method="search"),
        _accumulated_event("events_presentations", "2026-08-26", "NVIDIA 2nd quarter FY27 financial results", "earnings", discovery_method=None),
        _accumulated_event("press_releases", "2026-08-31", "NVIDIA announces partnership", "non_earnings", url="https://nvidianews.example.test/news/1", discovery_method="rss"),
    ]
    client = _client(monkeypatch, latest=_v1_1_result(), accumulated=accumulated)

    payload = client.get("/api/ticker-quant/NVDA/catalyst-research").json()

    channel = payload["channels"]["events_presentations"]
    assert channel["coverage_status"] == "observed_partial"
    assert channel["observed_total"] == 3
    assert channel["observed_earnings"] == 1
    assert channel["observed_non_earnings"] == 2
    assert channel["observed_start"] == "2026-03-03"
    assert channel["observed_end"] == "2026-08-26"
    assert channel["discovery_methods"] == ["search"]
    assert channel["median_days_between_observed_non_earnings"] == 79.0
    assert channel["coverage_warning"] == "search and feed history may omit official records"
    press = payload["channels"]["press_releases"]
    assert press["observed_total"] == 1
    assert press["discovery_methods"] == ["rss", "search"]


def test_summary_channels_keep_stored_statistics_without_accumulated_events(monkeypatch):
    client = _client(monkeypatch, latest=_v1_1_result(), accumulated=[])

    payload = client.get("/api/ticker-quant/NVDA/catalyst-research").json()

    assert payload["channels"]["press_releases"]["observed_total"] == 84
    assert payload["channels"]["events_presentations"]["coverage_status"] == "missing"


def test_summary_v1_1_without_registry_row_exposes_null_registry(monkeypatch):
    client = _client(monkeypatch, latest=_v1_1_result(), registry=None, endpoints=[])

    payload = client.get("/api/ticker-quant/NVDA/catalyst-research").json()

    assert payload["schema_version"] == "catalyst_research_result_v1_1"
    assert payload["registry"] is None
    assert payload["endpoints"] == []


def test_summary_v1_keeps_legacy_fields_without_v1_1_projection(monkeypatch):
    client = _client(monkeypatch, latest=_latest_result(), registry=dict(_REGISTRY_ROW), endpoints=[dict(_ENDPOINT_ROWS[0])])

    payload = client.get("/api/ticker-quant/NVDA/catalyst-research").json()

    assert payload["schema_version"] == "catalyst_research_result_v1"
    for key in ("mode", "registry", "channels", "endpoints"):
        assert key not in payload
    assert payload["statistics"] == {"press_releases": {"total": 78}}
    assert "endpoint_id" not in payload["sources"][0]


def test_events_v1_1_rows_expose_nullable_provenance(monkeypatch):
    page = {
        "ticker": "NVDA",
        "job_id": "cr_1",
        "events": [
            {
                "event_id": "ire_9",
                "job_id": "cr_1",
                "ticker": "NVDA",
                "published_date": "2026-08-27",
                "event_date": None,
                "count_date": "2026-08-27",
                "title": "NVIDIA Announces New Platform",
                "canonical_url": "https://nvidianews.example.test/news/9",
                "source_type": "press_releases",
                "earnings_state": "non_earnings",
                "classification_method": "rule_v1",
                "first_seen_at": "2026-09-04T01:00:00+00:00",
                "endpoint_id": "cse_1",
                "external_guid": "guid-9",
                "discovery_method": "rss",
                "extraction_provider": "direct_http",
            },
            {
                "event_id": "ire_10",
                "job_id": "cr_1",
                "ticker": "NVDA",
                "published_date": "2026-08-20",
                "event_date": None,
                "count_date": "2026-08-20",
                "title": "NVIDIA Announces Results",
                "canonical_url": "https://nvidianews.example.test/news/10",
                "source_type": "press_releases",
                "earnings_state": "earnings",
                "classification_method": "llm_v1",
                "first_seen_at": "2026-09-04T01:00:00+00:00",
                "endpoint_id": None,
                "external_guid": None,
                "discovery_method": "search",
                "extraction_provider": None,
            },
        ],
        "next_cursor": None,
    }
    client = _client(monkeypatch, latest=_v1_1_result(), events_page=page, job_schema_version="catalyst_research_result_v1_1")

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/events?job_id=cr_1")

    assert response.status_code == 200
    first, second = response.json()["events"]
    assert first["endpoint_id"] == "cse_1"
    assert first["external_guid"] == "guid-9"
    assert first["discovery_method"] == "rss"
    assert first["extraction_provider"] == "direct_http"
    assert second["endpoint_id"] is None
    assert second["external_guid"] is None
    assert second["discovery_method"] == "search"
    assert second["extraction_provider"] is None


def test_events_v1_rows_keep_legacy_fields_without_provenance(monkeypatch):
    page = {
        "ticker": "NVDA",
        "job_id": "cr_1",
        "events": [
            {
                "event_id": "ire_1",
                "job_id": "cr_1",
                "ticker": "NVDA",
                "published_date": "2026-08-27",
                "event_date": None,
                "count_date": "2026-08-27",
                "title": "NVIDIA Announces Financial Results",
                "canonical_url": "https://nvidianews.example.test/news/1",
                "source_type": "press_releases",
                "earnings_state": "earnings",
                "classification_method": "rule_v1",
                "first_seen_at": "2026-09-04T01:00:00+00:00",
                "endpoint_id": "cse_1",
                "discovery_method": "rss",
            }
        ],
        "next_cursor": None,
    }
    client = _client(monkeypatch, latest=_latest_result(), events_page=page)

    response = client.get("/api/ticker-quant/NVDA/catalyst-research/events?job_id=cr_1")

    assert response.status_code == 200
    event = response.json()["events"][0]
    for key in ("endpoint_id", "external_guid", "discovery_method", "extraction_provider"):
        assert key not in event


def test_api_calls_never_trigger_network_or_model_work(monkeypatch):
    from app.agents.catalyst_research import workflow as catalyst_workflow

    calls = []
    monkeypatch.setattr(catalyst_workflow, "run_research", lambda *args, **kwargs: calls.append("run_research"))
    monkeypatch.setattr(catalyst_router.config, "load_collection_config", lambda *args, **kwargs: calls.append("collection_config"))
    page = {"ticker": "NVDA", "job_id": "cr_1", "events": [], "next_cursor": None}
    activity_page = {"ticker": "NVDA", "events": [], "next_cursor": None}
    client = _client(monkeypatch, latest=_v1_1_result(), registry=dict(_REGISTRY_ROW), endpoints=[], events_page=page, activity_page=activity_page)

    summary = client.get("/api/ticker-quant/NVDA/catalyst-research")
    events = client.get("/api/ticker-quant/NVDA/catalyst-research/events")
    activity = client.get("/api/ticker-quant/NVDA/catalyst-research/activity")

    assert summary.status_code == 200
    assert events.status_code == 200
    assert activity.status_code == 200
    assert calls == []
