from copy import deepcopy
from datetime import datetime

import pytest

from app.services.macro_data_freshness_catalog import load_catalog
from app.tools.macro_data_freshness import build_overview, evaluate_dataset


def dataset(id="macro:m2_money_stock"):
    return next(row for row in load_catalog()["datasets"] if row["id"] == id)


def evaluate(observation, at="2026-11-13T12:00:00+08:00", row=None, schedule=None):
    row = row or dataset()
    schedule = schedule or load_catalog()["schedules"][row["schedule_id"]]
    return evaluate_dataset(row, observation, schedule, datetime.fromisoformat(at))


def available(period, **kwargs):
    return {"availability": "available", "current_period": period, **kwargs}


@pytest.mark.parametrize("at, period, status, expected", [
    ("2026-11-24T17:59:59+00:00", "2026-09-01", "current", "2026-09-01"),
    ("2026-11-24T18:00:00+00:00", "2026-09-01", "due", "2026-10-01"),
    ("2026-11-24T18:00:00+00:00", "2026-10-01", "current", "2026-10-01"),
    ("2027-01-01T12:00:00+00:00", "2026-11-01", "unknown", None),
    ("2026-09-01T12:00:00+00:00", "2026-07-01", "unknown", None),
])
def test_monthly_publication_boundary_and_calendar_horizon(at, period, status, expected):
    result = evaluate(available(period), at)
    assert result["status"] == status
    assert (result.get("expected_release") or {}).get("period") == expected


@pytest.mark.parametrize("obs,status", [
    ({"availability": "missing"}, "missing"),
    ({"availability": "unavailable"}, "unknown"),
    ({"availability": "invalid", "current_period": "bad"}, "unknown"),
    (available("2028-01-01"), "unknown"),
    (available("not-a-date"), "unknown"),
    (available("2026-09-01", retrieved_at="2027-01-01T00:00:00Z"), "unknown"),
])
def test_missing_invalid_and_future_evidence_are_explicit(obs, status):
    assert evaluate(obs)["status"] == status


@pytest.mark.parametrize("id,period,status", [
    ("economic:nonfarm_payrolls_change", "2026-10", "current"),
    ("economic:unemployment_rate", "2026-09", "due"),
    ("economic:capacity_utilization", "2026-09", "current"),
    ("economic:capacity_utilization", "2026-10", "unknown"),
    ("economic:capacity_utilization", "2027-01", "unknown"),
    ("economic:capacity_utilization", "2026-13", "unknown"),
])
def test_real_monthly_economic_period_format(id, period, status):
    result = evaluate(available(period), row=dataset(id))
    assert result["status"] == status


def test_timezone_dst_and_manufacturing_services_have_independent_release_days():
    observation = available("2026-09-01", source_hash="hash", source=available("2026-09-01", source_hash="hash"))
    row = dataset("macro:ism_manufacturing_pmi")
    result = evaluate(observation, "2026-11-02T14:59:59Z", row)
    assert result["status"] == "current"
    assert evaluate(observation, "2026-11-02T15:00:00Z", row)["status"] == "due"
    row = dataset("macro:ism_services_pmi")
    assert evaluate(observation, "2026-11-02T15:00:00Z", row)["status"] == "current"


def test_resampled_cpi_is_not_compared_to_a_monthly_source_label():
    result = evaluate(available("2026-11-08"), row=dataset("macro:cpi_yoy"))
    assert result["status"] == "unknown"
    assert "resampl" in result["reason"].lower()
    assert result["next_release"]["period"] == "2026-11-01"


@pytest.mark.parametrize("source,status", [("2026-10-01", "current"), ("2026-09-01", "due")])
def test_cpi_yoy_uses_verified_source_month_instead_of_weekly_label(source, status):
    obs = available("2026-11-08", source_observation_date=source, lineage_basis="captured_at_import")
    result = evaluate(obs, row=dataset("macro:cpi_yoy"))
    assert result["status"] == status
    assert result["current_period"] == source
    assert result["stored_period"] == "2026-11-08"


def test_source_month_does_not_hide_a_future_stored_weekly_label():
    obs = available("2026-11-22", source_observation_date="2026-10-01", lineage_basis="captured_at_import")
    assert evaluate(obs, row=dataset("macro:cpi_yoy"))["status"] == "unknown"


def test_market_calendar_uncertainty_never_assumes_weekdays_are_sessions():
    result = evaluate(available("2026-11-12"), row=dataset("benchmark:us_sp500"))
    assert result["status"] == "unknown"


def test_fomc_document_and_extraction_hash_are_checked_separately():
    row = dataset("fomc:policy_tone")
    source = {"availability": "available", "current_period": "2026-10-27", "source_hash": "new"}
    obs = available("2026-10-27", source_hash="old", source=source)
    assert evaluate(obs, row=row)["status"] == "processing"
    obs["source_hash"] = "new"
    assert evaluate(obs, row=row)["status"] == "current"
    obs["current_period"] = "2026-09-15"
    obs["source"]["current_period"] = "2026-09-15"
    assert evaluate(obs, row=row)["status"] == "due"
    source["current_period"] = "2026-10-27"
    obs = {"availability": "missing", "source": source}
    assert evaluate(obs, row=row)["status"] == "processing"


def test_existing_processed_output_without_source_version_is_unknown():
    row = dataset("ism:services:industry_rankings")
    obs = available("2026-10-01", source={"availability": "available", "current_period": "2026-10-01", "source_hash": "hash"})
    assert evaluate(obs, row=row)["status"] == "unknown"


def test_date_only_and_approximate_windows_do_not_invent_a_release_time():
    schedule = {"timezone": "America/New_York", "coverage_start": "2026-11-01", "coverage_end": "2026-11-30", "note": "Verified window", "releases": [
        {"at": "2026-11-02", "period": "2026-09-01", "precision": "date"},
        {"at": "2026-11-10", "window_end": "2026-11-12", "period": "2026-10-01", "precision": "window"},
    ]}
    assert evaluate(available("2026-09-01"), "2026-11-11T17:00:00Z", schedule=schedule)["status"] == "unknown"
    assert evaluate(available("2026-09-01"), "2026-11-13T12:00:00Z", schedule=schedule)["status"] == "due"
    result = evaluate(available("2026-10-01"), "2026-11-13T12:00:00Z", schedule=schedule)
    assert result["expected_release"]["at"] == "2026-11-10"
    assert result["expected_release"]["precision"] == "window"


def test_revision_same_period_requires_version_or_post_release_evidence():
    schedule = {"timezone": "America/New_York", "coverage_start": "2026-11-01", "coverage_end": "2026-11-30", "note": "Final release", "releases": [
        {"at": "2026-11-06T10:00:00", "period": "2026-11-01", "precision": "exact", "version": "preliminary"},
        {"at": "2026-11-20T10:00:00", "period": "2026-11-01", "precision": "exact", "version": "final"},
    ]}
    obs = available("2026-11-01", version="preliminary")
    assert evaluate(obs, "2026-11-20T16:00:00Z", schedule=schedule)["status"] == "due"
    obs["version"] = "final"
    assert evaluate(obs, "2026-11-20T16:00:00Z", schedule=schedule)["status"] == "current"
    obs.pop("version")
    assert evaluate(obs, "2026-11-20T16:00:00Z", schedule=schedule)["status"] == "unknown"


def test_pce_previous_release_and_michigan_next_final_date_are_verified():
    assert evaluate(available("2026-09-01"), row=dataset("macro:core_pce_price_index"))["status"] == "current"
    result = evaluate(available("2026-11-01"), row=dataset("macro:umcsi_aggregate"))
    assert result["next_release"]["at"] == "2026-11-20"
    assert result["next_release"]["version"] == "final"
    assert result["status"] == "unknown"


def test_actual_cot_holiday_and_eia_exception_are_respected():
    row = next(x for x in load_catalog()["datasets"] if x["id"].startswith("cot:copper:"))
    assert evaluate(available("2026-11-03"), "2026-11-13T21:00:00Z", row)["status"] == "current"
    assert evaluate(available("2026-11-03"), "2026-11-16T20:30:00Z", row)["status"] == "due"
    row = dataset("macro:oil_crude_production")
    assert evaluate(available("2026-10-30"), "2026-11-12T16:59:59Z", row)["status"] == "current"
    assert evaluate(available("2026-10-30"), "2026-11-12T17:00:00Z", row)["status"] == "due"


def test_overview_is_deterministic_and_task_success_does_not_change_freshness():
    catalog = load_catalog()
    catalog["datasets"] = [dataset()]
    obs = {"macro:m2_money_stock": available("2026-08-01")}
    at = datetime.fromisoformat("2026-11-13T12:00:00+08:00")
    tasks = {"macro:m2_money_stock": {"availability": "available", "last_attempt": {"status": "ok"}}}
    before = deepcopy(obs)
    first = build_overview(catalog, obs, tasks, at)
    assert first == build_overview(catalog, obs, tasks, at)
    assert first["datasets"][0]["status"] == "due"
    assert first["counts"]["due"] == 1
    assert obs == before


def test_naive_evaluation_time_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        evaluate_dataset(dataset(), available("2026-09-01"), {}, datetime(2026, 11, 13))
