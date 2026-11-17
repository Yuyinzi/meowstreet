from datetime import datetime

import pytest

from app.tools.macro_data_freshness_daily import evaluate_daily_policy
from app.tools.macro_data_freshness import evaluate_dataset
from app.services.macro_data_freshness_catalog import load_catalog


def calendar():
    return {"us": {"timezone": "America/New_York", "coverage_start": "2026-01-01", "coverage_end": "2026-12-31", "holidays": ["2026-11-26", "2026-12-25"], "source_url": "https://www.nyse.com/markets/hours-calendars"}}


def session_row():
    return {"storage": {"kind": "benchmark"}, "freshness_policy": {"kind": "session", "calendar_id": "us", "timezone": "America/New_York"}}


def observation(period, **extra):
    return {"availability": "available", "current_period": period, **extra}


@pytest.mark.parametrize("at,period,status,expected", [
    ("2026-11-17T12:59:59Z", "2026-11-13", "current", "2026-11-13"),
    ("2026-11-17T13:00:00Z", "2026-11-13", "due", "2026-11-16"),
    ("2026-11-17T13:00:00Z", "2026-11-16", "current", "2026-11-16"),
    ("2026-11-22T13:00:00Z", "2026-11-20", "current", "2026-11-20"),
    ("2026-11-27T13:00:00Z", "2026-11-25", "current", "2026-11-25"),
    ("2026-03-10T12:00:00Z", "2026-03-09", "current", "2026-03-09"),
    ("2027-01-02T13:00:00Z", "2026-12-31", "unknown", None),
])
def test_session_deadline_weekend_holiday_dst_and_horizon(at, period, status, expected):
    result = evaluate_daily_policy(session_row(), observation(period), datetime.fromisoformat(at), calendar())
    assert result["status"] == status
    assert result.get("expected_period") == expected


def test_intraday_row_is_not_treated_as_a_completed_close():
    obs = observation("2026-11-17", recent_observations=[{"current_period": "2026-11-17"}, {"current_period": "2026-11-16"}])
    result = evaluate_daily_policy(session_row(), obs, datetime.fromisoformat("2026-11-17T15:00:00Z"), calendar())
    assert result["status"] == "current"
    assert result["current_period"] == "2026-11-16"
    assert evaluate_daily_policy(session_row(), observation("2026-11-17"), datetime.fromisoformat("2026-11-17T15:00:00Z"), calendar())["status"] == "unknown"


def test_asx_calendar_is_identical_for_equivalent_instants_across_midnight():
    from zoneinfo import ZoneInfo
    catalog = load_catalog()
    row = next(r for r in catalog["datasets"] if r["id"] == "benchmark:australia_asx_200")
    obs = observation("2026-11-17", recent_observations=[observation("2026-11-16")])
    at = datetime.fromisoformat("2026-11-16T23:30:00Z")
    result = evaluate_dataset(row, obs, catalog["schedules"][row["schedule_id"]], at, catalog["market_calendars"])
    other = evaluate_dataset(row, obs, catalog["schedules"][row["schedule_id"]], at.astimezone(ZoneInfo("Australia/Sydney")), catalog["market_calendars"])
    assert result == other
    assert result["status"] == "current"
    assert result["current_period"] == "2026-11-16"


@pytest.mark.parametrize("period,status", [("2026-11-12", "current"), ("2026-11-11", "due"), ("2026-11-18", "unknown"), ("bad", "unknown")])
def test_source_local_window_boundary(period, status):
    row = {"storage": {"kind": "macro"}, "freshness_policy": {"kind": "max_age", "max_age_days": 5, "timezone": "America/New_York"}}
    result = evaluate_daily_policy(row, observation(period), datetime.fromisoformat("2026-11-18T02:00:00Z"), {})
    assert result["status"] == status
    assert "window" in result["comparison_basis"].lower()
