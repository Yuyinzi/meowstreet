import inspect
from datetime import date
from datetime import timedelta

import pytest

from app.db import economic_confirmation as economic_confirmation_db
from app.services import economic_confirmation

NOW = "2026-07-29T12:00:00+00:00"
LATEST_WEEK = "2026-07-25"


def _weekly_periods(count, latest=LATEST_WEEK):
    end = date.fromisoformat(latest)
    return [
        (end - timedelta(days=7 * (count - 1 - index))).isoformat()
        for index in range(count)
    ]


def _vintage_observation(series_id, reference_period, value, as_of=NOW):
    return {
        "series_id": series_id,
        "reference_period": reference_period,
        "vintage_id": f"{series_id}:{reference_period}:v1",
        "release_date": reference_period,
        "as_of_timestamp": as_of,
        "value_at_release": value,
        "latest_revised_value": None,
        "revision_number": 0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://oui.doleta.gov/unemploy/pdf/claims.pdf",
        "source_hash": f"hash:{series_id}:{reference_period}",
    }


def _claims_trend_observations(
    series_id, change_pct, comparison_level=100.0, latest=LATEST_WEEK, as_of=NOW
):
    latest_level = comparison_level * (1 + change_pct)
    values = [comparison_level] * 13 + [latest_level] * 4
    periods = _weekly_periods(len(values), latest)
    return [
        _vintage_observation(series_id, period, value, as_of=as_of)
        for period, value in zip(periods, values)
    ]


def _esr_observations():
    specs = {
        "nonfarm_payrolls_change": 57.0,
        "payrolls_3m_average_change": 111.0,
        "unemployment_rate": 4.0,
        "average_weekly_hours": 34.4,
        "average_hourly_earnings": 36.7,
    }
    rows = []
    for series_id, value in specs.items():
        for reference_period in ("2026-05", "2026-06"):
            rows.append(_vintage_observation(series_id, reference_period, value))
    return rows


def _g17_observations():
    rows = []
    for series_id in (
        "manufacturing_production",
        "total_industrial_production",
        "capacity_utilization",
    ):
        for reference_period in ("2026-05", "2026-06"):
            rows.append(_vintage_observation(series_id, reference_period, 100.0))
    return rows


def _vintage_snapshot(series_id):
    return {
        "series_id": series_id,
        "reference_period": "2026-06",
        "value": 100.0,
        "value_at_release": 100.0,
        "latest_revised_value": None,
        "revision_number": 0,
        "release_date": "2026-06",
        "source_url": "https://oui.doleta.gov/unemploy/pdf/claims.pdf",
    }


def _scheduled_events():
    return [
        {
            "event_id": "bls_employment_situation",
            "scheduled_at": "2026-08-07T08:30:00",
            "status": "upcoming",
            "timezone": "ET",
            "source_url": "https://www.bls.gov/news.release/pdf/empsit.pdf",
        }
    ]


def _claims_observations():
    return _claims_trend_observations(
        "initial_claims_sa", 0.035
    ) + _claims_trend_observations("continuing_claims_sa", 0.0)


def seeded_con(tmp_path):
    con = economic_confirmation_db.connect(tmp_path / "market.sqlite")
    economic_confirmation_db.record_vintage_batch(con, _claims_observations())
    economic_confirmation_db.record_vintage_batch(con, _esr_observations())
    economic_confirmation_db.record_vintage_batch(con, _g17_observations())
    economic_confirmation_db.record_scheduled_events(con, _scheduled_events())
    return con


def test_context_cannot_change_claims_status_or_posture(tmp_path):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["economic_confirmation"]["status"] == "limited_coverage"
    assert payload["real_activity"]["confirmation_status"] == "unavailable"


def test_service_composes_claims_confirmation_with_direction_and_status(tmp_path):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    claims = payload["claims_confirmation"]
    assert claims["method_version"] == "claims_confirmation_v1.0"
    assert claims["claims_direction"] == "partially_deteriorating"
    assert claims["confirmation_status"] == "partial"


def test_national_claims_history_rows_classify_both_series(tmp_path):
    initial = _claims_trend_observations("initial_claims_sa", 0.035)
    continuing = _claims_trend_observations("continuing_claims_sa", 0.0)
    assert len(initial) == 17
    assert len(continuing) == 17
    con = economic_confirmation_db.connect(tmp_path / "market.sqlite")
    economic_confirmation_db.record_vintage_batch(con, initial + continuing)

    payload = economic_confirmation.load_overview(
        con, {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    claims = payload["claims_confirmation"]
    assert claims["initial_claims"]["classification"] != "unavailable"
    assert claims["continuing_claims"]["classification"] != "unavailable"


def test_labor_context_is_context_only_and_cannot_change_claims_status(tmp_path):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    labor = payload["labor_context"]
    assert labor["role"] == "context_only"
    assert labor["data_status"] == "available"
    assert "nonfarm_payrolls_change" in labor["metrics"]
    assert "average_hourly_earnings" in labor["metrics"]

    claims_only_con = economic_confirmation_db.connect(tmp_path / "claims_only.sqlite")
    economic_confirmation_db.record_vintage_batch(
        claims_only_con, _claims_observations()
    )
    sparse = economic_confirmation.load_overview(
        claims_only_con, {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert sparse["labor_context"]["data_status"] == "missing"
    assert sparse["claims_confirmation"]["confirmation_status"] == "partial"


def _html_esr_observations():
    specs = {
        "nonfarm_payrolls_change": 57.0,
        "payrolls_3m_average_change": 111.0,
        "unemployment_rate": 4.2,
        "average_weekly_hours": 34.3,
        "average_hourly_earnings": 37.64,
    }
    return [
        _vintage_observation(series_id, "2026-06", value)
        for series_id, value in specs.items()
    ]


def test_labor_context_available_from_html_imported_observations(tmp_path):
    con = economic_confirmation_db.connect(tmp_path / "market.sqlite")
    economic_confirmation_db.record_vintage_batch(con, _claims_observations())
    economic_confirmation_db.record_vintage_batch(con, _html_esr_observations())
    economic_confirmation_db.record_vintage_batch(con, _g17_observations())
    economic_confirmation_db.record_scheduled_events(con, _scheduled_events())

    payload = economic_confirmation.load_overview(
        con, {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["labor_context"]["data_status"] == "available"
    assert payload["labor_context"]["method_status"] == "pending_approval"
    assert payload["labor_context"]["confirmation_status"] == "unavailable"
    assert payload["real_activity"]["confirmation_status"] == "unavailable"
    assert payload["economic_confirmation"]["coverage"] == "claims_only"


def test_later_bls_vintages_keep_point_in_time_snapshots(tmp_path):
    con = economic_confirmation_db.connect(tmp_path / "market.sqlite")
    economic_confirmation_db.record_vintage_batch(con, _claims_observations())
    initial = _vintage_observation(
        "nonfarm_payrolls_change",
        "2026-06",
        57.0,
        as_of="2026-07-02T08:30:00+00:00",
    )
    revised = dict(initial)
    revised["vintage_id"] = "nonfarm_payrolls_change:2026-06:2026-07-02:rev"
    revised["as_of_timestamp"] = "2026-07-30T08:30:00+00:00"
    revised["value_at_release"] = 58.0
    revised["latest_revised_value"] = 58.0
    revised["revision_number"] = 1
    revised["source_hash"] = "hash:bls-revision"
    economic_confirmation_db.record_vintage_batch(con, [initial, revised])

    detail = economic_confirmation.load_detail(
        con,
        {"expected_gdp_direction": "growth_decelerating"},
        "2026-07-02T12:00:00+00:00",
    )
    overview = economic_confirmation.load_overview(
        con,
        {"expected_gdp_direction": "growth_decelerating"},
        "2026-07-29T12:00:00+00:00",
    )
    assert (
        detail["labor_context"]["metrics"]["nonfarm_payrolls_change"][
            "value_at_release"
        ]
        == 57.0
    )
    assert (
        overview["labor_context"]["metrics"]["nonfarm_payrolls_change"]["value"] == 58.0
    )


def test_real_activity_block_is_exact(tmp_path):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["real_activity"] == {
        "data_status": "available",
        "method_status": "pending_approval",
        "confirmation_status": "unavailable",
        "unavailable_reason": "method_not_approved",
        "metrics": {
            "manufacturing_production": _vintage_snapshot("manufacturing_production"),
            "total_industrial_production": _vintage_snapshot(
                "total_industrial_production"
            ),
            "capacity_utilization": _vintage_snapshot("capacity_utilization"),
        },
    }


def test_real_activity_is_missing_when_no_g17_series_stored(tmp_path):
    con = economic_confirmation_db.connect(tmp_path / "market.sqlite")
    economic_confirmation_db.record_vintage_batch(con, _claims_observations())
    economic_confirmation_db.record_vintage_batch(con, _esr_observations())
    payload = economic_confirmation.load_overview(
        con, {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["real_activity"]["data_status"] == "missing"
    assert payload["real_activity"]["method_status"] == "pending_approval"
    assert payload["real_activity"]["confirmation_status"] == "unavailable"
    assert payload["real_activity"]["unavailable_reason"] == "method_not_approved"
    assert payload["real_activity"]["metrics"] == {}


def test_event_risk_direction_is_unknown_and_independent(tmp_path):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["event_risk"]["direction"] == "unknown"
    assert payload["event_risk"]["next_event"]["event_id"] == "bls_employment_situation"
    assert payload["event_risk"]["next_event"]["status"] == "upcoming"
    assert payload["event_risk"]["data_status"] == "available"
    assert payload["economic_confirmation"]["status"] == "limited_coverage"


def test_overall_economic_confirmation_block_is_exact(tmp_path):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["economic_confirmation"] == {
        "status": "limited_coverage",
        "based_on": ["claims_confirmation_v1.0"],
        "excluded_modules": [
            {"module": "esr_labor_context", "reason": "method_not_approved"},
            {"module": "real_activity", "reason": "method_not_approved"},
        ],
        "coverage": "claims_only",
        "approved_directional_modules": 1,
        "context_only_modules": 2,
    }


def test_later_vintages_do_not_affect_point_in_time_reads(tmp_path):
    con = economic_confirmation_db.connect(tmp_path / "market.sqlite")
    initial = _claims_trend_observations(
        "initial_claims_sa", 0.0, as_of="2026-07-29T08:00:00+00:00"
    )
    continuing = _claims_trend_observations(
        "continuing_claims_sa", 0.0, as_of="2026-07-29T08:00:00+00:00"
    )
    economic_confirmation_db.record_vintage_batch(con, initial + continuing)
    revision = dict(initial[-1])
    revision["vintage_id"] = f"initial_claims_sa:{revision['reference_period']}:rev"
    revision["as_of_timestamp"] = "2026-07-30T08:00:00+00:00"
    revision["latest_revised_value"] = 999.0
    revision["revision_number"] = 1
    revision["source_hash"] = "hash:revision"
    economic_confirmation_db.record_vintage_batch(con, [revision])

    detail = economic_confirmation.load_detail(
        con,
        {"expected_gdp_direction": "growth_decelerating"},
        "2026-07-29T12:00:00+00:00",
    )
    overview = economic_confirmation.load_overview(
        con,
        {"expected_gdp_direction": "growth_decelerating"},
        "2026-07-29T12:00:00+00:00",
    )
    assert detail["vintage_policy"] == "point_in_time"
    assert detail["claims_confirmation"]["initial_claims"]["latest_4w_mean"] == 100.0
    assert overview["claims_confirmation"]["initial_claims"]["latest_4w_mean"] == 324.75


def test_load_detail_returns_full_structure(tmp_path):
    payload = economic_confirmation.load_detail(
        seeded_con(tmp_path), {"expected_gdp_direction": "growth_decelerating"}, NOW
    )
    assert payload["claims_confirmation"]["confirmation_status"] == "partial"
    assert payload["economic_confirmation"]["status"] == "limited_coverage"
    assert payload["real_activity"]["confirmation_status"] == "unavailable"


def test_service_never_performs_network_requests():
    source = inspect.getsource(economic_confirmation)
    assert "HttpClient" not in source
    assert "httpx" not in source
    assert "urllib" not in source


@pytest.mark.parametrize(
    ("direction", "expected_status", "expected_reason"),
    [
        ("growth_decelerating", "partial", None),
        ("growth_accelerating", "conflicting", None),
        ("mixed", "unavailable", "macro_growth_thesis_not_directional"),
        (None, "unavailable", "macro_growth_thesis_not_directional"),
    ],
)
def test_varying_macro_growth_context_changes_confirmation_status(
    tmp_path, direction, expected_status, expected_reason
):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": direction}, NOW
    )
    assert payload["claims_confirmation"]["confirmation_status"] == expected_status
    assert payload["claims_confirmation"]["unavailable_reason"] == expected_reason


@pytest.mark.parametrize(
    ("upstream_direction", "expected_status", "expected_reason"),
    [
        ("slowing", "partial", None),
        ("falling", "partial", None),
        ("rising", "conflicting", None),
        ("improving", "conflicting", None),
        ("stable", "unavailable", "macro_growth_thesis_not_directional"),
        ("mixed", "unavailable", "macro_growth_thesis_not_directional"),
        ("growth_decelerating", "partial", None),
        ("growth_accelerating", "conflicting", None),
        ("growth_sideways", "unavailable", "calculation_error"),
    ],
)
def test_translation_mapping_from_upstream_direction(
    tmp_path, upstream_direction, expected_status, expected_reason
):
    payload = economic_confirmation.load_overview(
        seeded_con(tmp_path), {"expected_gdp_direction": upstream_direction}, NOW
    )
    assert payload["claims_confirmation"]["confirmation_status"] == expected_status
    assert payload["claims_confirmation"]["unavailable_reason"] == expected_reason
