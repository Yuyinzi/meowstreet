from datetime import UTC, datetime

import pytest

from app.agents.catalyst_research.registry import (
    approved_domains,
    feed_due,
    registry_ready,
    transition_endpoint,
)


def endpoint_payload(ticker="NVDA", **overrides):
    payload = {
        "ticker": ticker,
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/rss",
        "domain": "nvidianews.nvidia.com",
        "status": "unverified",
        "confidence": "high",
        "discovered_at": "2026-09-01T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def check_payload(outcome="success_new", **overrides):
    payload = {
        "endpoint_id": "cse_feed",
        "checked_at": "2026-09-08T00:00:00+00:00",
        "outcome": outcome,
        "item_count": 3,
        "new_item_count": 1,
        "newest_item_at": "2026-09-07T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("status", "outcome", "failures", "gap_found", "expected"),
    [
        ("unverified", "success_new", 0, False, "active"),
        ("active", "success_empty", 0, False, "quiet"),
        ("quiet", "success_new", 0, False, "active"),
        ("active", "request_failed", 2, False, "failing"),
        ("quiet", "success_empty", 0, True, "stale"),
        ("failing", "success_new", 3, False, "active"),
    ],
)
def test_transition_endpoint(status, outcome, failures, gap_found, expected):
    endpoint = {**endpoint_payload(), "status": status, "consecutive_failures": failures}
    result = transition_endpoint(endpoint, check_payload(outcome), gap_found=gap_found)
    assert result["status"] == expected


def test_months_without_new_items_stay_quiet_and_preserve_last_item_at():
    endpoint = endpoint_payload(status="active", last_item_at="2026-03-01T00:00:00+00:00")
    result = transition_endpoint(
        endpoint,
        check_payload("success_empty", new_item_count=0, newest_item_at=None),
    )
    assert result["status"] == "quiet"
    assert result["last_item_at"] == "2026-03-01T00:00:00+00:00"


@pytest.mark.parametrize("failures", [0, 1])
def test_one_or_two_failures_do_not_become_failing(failures):
    endpoint = endpoint_payload(status="active", consecutive_failures=failures)
    result = transition_endpoint(endpoint, check_payload("request_failed", error_code="http_error"))
    assert result["status"] == "active"
    assert result["consecutive_failures"] == failures + 1


def test_parse_failures_count_toward_failing():
    endpoint = endpoint_payload(status="quiet", consecutive_failures=2)
    result = transition_endpoint(endpoint, check_payload("parse_failed", error_code="parse_failed"))
    assert result["consecutive_failures"] == 3
    assert result["status"] == "failing"


def test_success_recovers_stale_and_failing_and_resets_failures():
    for status in ("stale", "failing"):
        endpoint = endpoint_payload(status=status, consecutive_failures=3, last_error_code="timeout")
        result = transition_endpoint(endpoint, check_payload("success_new"))
        assert result["status"] == "active"
        assert result["consecutive_failures"] == 0
        assert result["last_error_code"] is None
        assert result["last_success_at"] == "2026-09-08T00:00:00+00:00"
        assert result["last_item_at"] == "2026-09-07T12:00:00+00:00"


def test_retired_requires_replacement_validated():
    endpoint = endpoint_payload(status="active")
    result = transition_endpoint(endpoint, check_payload("success_new"))
    assert result["status"] == "active"
    retired = transition_endpoint(endpoint, check_payload("success_new"), replacement_validated=True)
    assert retired["status"] == "retired"


def test_retired_stays_retired_without_replacement():
    endpoint = endpoint_payload(status="retired")
    result = transition_endpoint(endpoint, check_payload("success_new"))
    assert result["status"] == "retired"


def test_unknown_error_code_is_not_persisted():
    endpoint = endpoint_payload(status="active")
    result = transition_endpoint(endpoint, check_payload("request_failed", error_code="boom <!doctype html>"))
    assert result["consecutive_failures"] == 1
    assert result["last_error_code"] is None
    allowed = transition_endpoint(endpoint, check_payload("request_failed", error_code="timeout"))
    assert allowed["last_error_code"] == "timeout"


def test_transition_does_not_mutate_caller_endpoint():
    endpoint = endpoint_payload(status="active", consecutive_failures=2)
    snapshot = dict(endpoint)
    transition_endpoint(endpoint, check_payload("request_failed", error_code="timeout"))
    assert endpoint == snapshot


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("checked_at", "not-a-time"),
        ("newest_item_at", "2026-13-40"),
    ],
)
def test_malformed_timestamps_raise_lowercase_value_error(field, value):
    endpoint = endpoint_payload(status="active")
    with pytest.raises(ValueError, match="malformed"):
        transition_endpoint(endpoint, check_payload("success_new", **{field: value}))


def test_unknown_outcome_and_status_raise_lowercase_value_error():
    with pytest.raises(ValueError, match="outcome"):
        transition_endpoint(endpoint_payload(), check_payload("bogus"))
    with pytest.raises(ValueError, match="status"):
        transition_endpoint(endpoint_payload(status="bogus"), check_payload())


def test_approved_domains_normalizes_to_frozenset():
    registry = {"official_domains": ["NVIDIA.com", " nvidianews.nvidia.com "]}
    assert approved_domains(registry) == frozenset({"nvidia.com", "nvidianews.nvidia.com"})


def test_approved_domains_rejects_malformed_registry():
    with pytest.raises(ValueError, match="official domains"):
        approved_domains({"ticker": "NVDA"})
    with pytest.raises(ValueError, match="non-empty strings"):
        approved_domains({"official_domains": ["nvidia.com", "  "]})


def test_registry_ready_requires_dict_with_domains():
    assert registry_ready(None, []) is False
    assert registry_ready({"ticker": "NVDA"}, []) is False
    assert registry_ready({"official_domains": []}, []) is False


def test_registry_ready_requires_approved_domain_and_usable_event_channel():
    registry = {"ticker": "NVDA", "official_domains": ["nvidia.com"]}
    endpoints = [
        {"channel": "press_releases", "endpoint_type": "rss", "status": "active", "domain": "nvidia.com"}
    ]
    assert registry_ready(registry, endpoints) is True


def test_registry_ready_rejects_unapproved_or_unusable_endpoints():
    registry = {"official_domains": ["nvidia.com"]}
    unapproved = [
        {"channel": "press_releases", "endpoint_type": "rss", "status": "active", "domain": "evil.com"}
    ]
    failing = [
        {"channel": "press_releases", "endpoint_type": "rss", "status": "failing", "domain": "nvidia.com"}
    ]
    search_only = [
        {
            "channel": "press_releases",
            "endpoint_type": "search_domain",
            "status": "active",
            "domain": "nvidia.com",
        }
    ]
    assert registry_ready(registry, unapproved) is False
    assert registry_ready(registry, failing) is False
    assert registry_ready(registry, search_only) is False


def test_feed_due_once_per_calendar_day():
    endpoint = {**endpoint_payload(), "last_checked_at": "2026-09-08T00:01:00+00:00"}
    assert feed_due(endpoint, datetime(2026, 9, 8, 23, tzinfo=UTC)) is False
    assert feed_due(endpoint, datetime(2026, 9, 9, 0, tzinfo=UTC)) is True


def test_feed_due_normalizes_timezones_to_utc_days():
    endpoint = {**endpoint_payload(), "last_checked_at": "2026-09-08T23:30:00-07:00"}
    assert feed_due(endpoint, datetime(2026, 9, 9, 0, tzinfo=UTC)) is False
    assert feed_due(endpoint, datetime(2026, 9, 10, 0, tzinfo=UTC)) is True


def test_feed_due_without_prior_check_is_due():
    assert feed_due(endpoint_payload(), datetime(2026, 9, 8, tzinfo=UTC)) is True


def test_feed_due_ignores_non_feed_endpoints():
    endpoint = endpoint_payload(
        endpoint_type="search_domain",
        last_checked_at="2026-09-01T00:00:00+00:00",
    )
    assert feed_due(endpoint, datetime(2026, 9, 9, tzinfo=UTC)) is False


def test_feed_due_rejects_malformed_last_checked_at():
    endpoint = endpoint_payload(last_checked_at="not-a-time")
    with pytest.raises(ValueError, match="malformed"):
        feed_due(endpoint, datetime(2026, 9, 9, tzinfo=UTC))
