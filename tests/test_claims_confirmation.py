from datetime import date, timedelta

import pytest

from app.tools import claims_confirmation


NOW = "2026-07-29T12:00:00+00:00"
LATEST_WEEK = "2026-07-25"

_CHANGE_FOR_CLASS = {
    "deteriorating": 0.035,
    "improving": -0.035,
    "stable": 0.0,
}

_AGGREGATION_CASES = [
    ("deteriorating", "deteriorating", "deteriorating"),
    ("improving", "improving", "improving"),
    ("stable", "stable", "stable"),
    ("deteriorating", "stable", "partially_deteriorating"),
    ("stable", "deteriorating", "partially_deteriorating"),
    ("improving", "stable", "partially_improving"),
    ("stable", "improving", "partially_improving"),
    ("improving", "deteriorating", "conflicting"),
    ("deteriorating", "improving", "conflicting"),
]

_DECELERATING_MAPPING = [
    ("deteriorating", "deteriorating", "confirming"),
    ("stable", "stable", "not_confirming"),
    ("improving", "improving", "conflicting"),
]

_ACCELERATING_MAPPING = [
    ("improving", "improving", "confirming"),
    ("stable", "stable", "not_confirming"),
    ("deteriorating", "deteriorating", "conflicting"),
]


def _weekly_periods(count, latest=LATEST_WEEK):
    end = date.fromisoformat(latest)
    return [
        (end - timedelta(days=7 * (count - 1 - index))).isoformat()
        for index in range(count)
    ]


def _claim_row(series_id, reference_period, value):
    return {
        "series_id": series_id,
        "reference_period": reference_period,
        "vintage_id": f"{series_id}:{reference_period}",
        "value": value,
        "value_at_release": value,
        "latest_revised_value": None,
        "revision_number": 0,
        "seasonal_adjustment": "seasonally_adjusted",
        "release_date": reference_period,
        "as_of_timestamp": NOW,
        "source_url": "https://oui.doleta.gov/unemploy/pdf/claims.pdf",
        "source_hash": f"hash:{series_id}:{reference_period}",
    }


def _claim_rows(series_id, values, latest=LATEST_WEEK):
    periods = _weekly_periods(len(values), latest)
    return [
        _claim_row(series_id, period, value) for period, value in zip(periods, values)
    ]


def _trend_rows(series_id, change_pct, comparison_level=100.0, latest=LATEST_WEEK):
    latest_level = comparison_level * (1 + change_pct)
    values = [comparison_level] * 13 + [latest_level] * 4
    return _claim_rows(series_id, values, latest)


def initial_deteriorating():
    return _trend_rows("initial_claims_sa", 0.035)


def initial_stable():
    return _trend_rows("initial_claims_sa", 0.0)


def initial_improving():
    return _trend_rows("initial_claims_sa", -0.035)


def continuing_deteriorating():
    return _trend_rows("continuing_claims_sa", 0.035)


def continuing_stable():
    return _trend_rows("continuing_claims_sa", 0.0)


def continuing_improving():
    return _trend_rows("continuing_claims_sa", -0.035)


def test_deteriorating_and_stable_claims_are_partial_for_decelerating_growth():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "growth_decelerating", NOW
    )
    assert result["claims_direction"] == "partially_deteriorating"
    assert result["confirmation_status"] == "partial"


@pytest.mark.parametrize("initial_class,continuing_class,expected", _AGGREGATION_CASES)
def test_claims_direction_aggregation_table(initial_class, continuing_class, expected):
    result = claims_confirmation.build_claims_confirmation(
        _trend_rows("initial_claims_sa", _CHANGE_FOR_CLASS[initial_class]),
        _trend_rows("continuing_claims_sa", _CHANGE_FOR_CLASS[continuing_class]),
        "growth_decelerating",
        NOW,
    )
    assert result["initial_claims"]["classification"] == initial_class
    assert result["continuing_claims"]["classification"] == continuing_class
    assert result["claims_direction"] == expected


def test_exactly_negative_three_percent_change_is_improving_not_stable():
    result = claims_confirmation.build_claims_confirmation(
        _trend_rows("initial_claims_sa", -0.03),
        continuing_stable(),
        "growth_decelerating",
        NOW,
    )
    assert result["initial_claims"]["change_pct"] == pytest.approx(-0.03)
    assert result["initial_claims"]["classification"] == "improving"


def test_exactly_positive_three_percent_change_is_deteriorating_not_stable():
    result = claims_confirmation.build_claims_confirmation(
        _trend_rows("initial_claims_sa", 0.03),
        continuing_stable(),
        "growth_decelerating",
        NOW,
    )
    assert result["initial_claims"]["change_pct"] == pytest.approx(0.03)
    assert result["initial_claims"]["classification"] == "deteriorating"


def test_change_just_inside_stable_band_is_stable():
    for change_pct in (-0.0299, 0.0299):
        result = claims_confirmation.build_claims_confirmation(
            _trend_rows("initial_claims_sa", change_pct),
            continuing_stable(),
            "growth_decelerating",
            NOW,
        )
        assert result["initial_claims"]["classification"] == "stable"


def test_missing_claims_data_returns_data_missing():
    result = claims_confirmation.build_claims_confirmation(
        [], [], "growth_decelerating", NOW
    )
    assert result["claims_direction"] == "unavailable"
    assert result["confirmation_status"] == "unavailable"
    assert result["unavailable_reason"] == "data_missing"
    assert result["initial_claims"]["unavailable_reason"] == "data_missing"
    assert result["continuing_claims"]["unavailable_reason"] == "data_missing"


def test_fewer_than_seventeen_observations_returns_insufficient_history():
    rows = _claim_rows("initial_claims_sa", [100.0] * 10)
    result = claims_confirmation.build_claims_confirmation(
        rows, continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["classification"] == "unavailable"
    assert result["initial_claims"]["unavailable_reason"] == "insufficient_history"
    assert result["claims_direction"] == "unavailable"
    assert result["unavailable_reason"] == "insufficient_history"


def test_latest_reference_period_past_freshness_ceiling_returns_stale_data():
    stale_rows = _trend_rows("initial_claims_sa", 0.035, latest="2026-05-30")
    result = claims_confirmation.build_claims_confirmation(
        stale_rows, continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["unavailable_reason"] == "stale_data"
    assert result["claims_direction"] == "unavailable"
    assert result["unavailable_reason"] == "stale_data"


def test_future_reference_period_returns_release_not_yet_available():
    future_rows = _trend_rows("initial_claims_sa", 0.035, latest="2026-08-01")
    result = claims_confirmation.build_claims_confirmation(
        future_rows, continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["unavailable_reason"] == "release_not_yet_available"
    assert result["claims_direction"] == "unavailable"
    assert result["unavailable_reason"] == "release_not_yet_available"


def test_malformed_observation_returns_calculation_error():
    rows = _trend_rows("initial_claims_sa", 0.035)
    rows[3]["value"] = "not-a-number"
    result = claims_confirmation.build_claims_confirmation(
        rows, continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["classification"] == "unavailable"
    assert result["initial_claims"]["unavailable_reason"] == "calculation_error"
    assert result["unavailable_reason"] == "calculation_error"


def test_non_seasonally_adjusted_rows_do_not_count_toward_minimum():
    rows = _claim_rows("initial_claims_sa", [100.0] * 17)
    rows[0]["seasonal_adjustment"] = "not_seasonally_adjusted"
    result = claims_confirmation.build_claims_confirmation(
        rows, continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["classification"] == "unavailable"
    assert result["initial_claims"]["unavailable_reason"] == "insufficient_history"


def test_unknown_thesis_returns_calculation_error():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "growth_sideways", NOW
    )
    assert result["confirmation_status"] == "unavailable"
    assert result["unavailable_reason"] == "calculation_error"
    assert result["macro_growth_regime"] == "growth_sideways"


def test_missing_thesis_returns_calculation_error():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), None, NOW
    )
    assert result["confirmation_status"] == "unavailable"
    assert result["unavailable_reason"] == "calculation_error"


def test_mixed_regime_returns_macro_growth_thesis_not_directional():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "mixed", NOW
    )
    assert result["confirmation_status"] == "unavailable"
    assert result["unavailable_reason"] == "macro_growth_thesis_not_directional"
    assert result["macro_growth_regime"] == "mixed"


@pytest.mark.parametrize(
    "initial_class,continuing_class,expected_status", _DECELERATING_MAPPING
)
def test_growth_decelerating_thesis_mapping(
    initial_class, continuing_class, expected_status
):
    result = claims_confirmation.build_claims_confirmation(
        _trend_rows("initial_claims_sa", _CHANGE_FOR_CLASS[initial_class]),
        _trend_rows("continuing_claims_sa", _CHANGE_FOR_CLASS[continuing_class]),
        "growth_decelerating",
        NOW,
    )
    assert result["confirmation_status"] == expected_status


@pytest.mark.parametrize(
    "initial_class,continuing_class,expected_status", _ACCELERATING_MAPPING
)
def test_growth_accelerating_thesis_mapping(
    initial_class, continuing_class, expected_status
):
    result = claims_confirmation.build_claims_confirmation(
        _trend_rows("initial_claims_sa", _CHANGE_FOR_CLASS[initial_class]),
        _trend_rows("continuing_claims_sa", _CHANGE_FOR_CLASS[continuing_class]),
        "growth_accelerating",
        NOW,
    )
    assert result["confirmation_status"] == expected_status


def test_partial_deteriorating_maps_to_partial_for_decelerating():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "growth_decelerating", NOW
    )
    assert result["confirmation_status"] == "partial"


def test_partial_improving_maps_to_partial_for_accelerating():
    result = claims_confirmation.build_claims_confirmation(
        initial_improving(), continuing_stable(), "growth_accelerating", NOW
    )
    assert result["confirmation_status"] == "partial"


def test_confirming_support_reasoning():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_deteriorating(), "growth_decelerating", NOW
    )
    assert result["confirmation_status"] == "confirming"
    assert result["supports"] == (
        "Claims are deteriorating, supporting the decelerating growth thesis"
    )
    assert result["conflicts"] is None


def test_conflicting_reasoning():
    result = claims_confirmation.build_claims_confirmation(
        initial_improving(), continuing_improving(), "growth_decelerating", NOW
    )
    assert result["confirmation_status"] == "conflicting"
    assert result["conflicts"] == (
        "Claims are improving, conflicting with the decelerating growth thesis"
    )
    assert result["supports"] is None


def test_partial_support_reasoning():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "growth_decelerating", NOW
    )
    assert result["supports"] == (
        "Claims are partially deteriorating, partly supporting the decelerating growth thesis"
    )


def test_neutral_reasoning_when_stable():
    result = claims_confirmation.build_claims_confirmation(
        initial_stable(), continuing_stable(), "growth_decelerating", NOW
    )
    assert result["confirmation_status"] == "not_confirming"
    assert result["supports"] is None
    assert result["conflicts"] is None
    assert result["explanation"] == (
        "Claims are stable, neither supporting nor conflicting with the decelerating growth thesis"
    )


def test_method_coverage_and_version():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "growth_decelerating", NOW
    )
    assert result["method_version"] == "claims_confirmation_v1.0"
    assert result["method_coverage"]["initial_claims"] == "included"
    assert result["method_coverage"]["continuing_claims"] == "included"
    assert result["method_coverage"]["payrolls"] == "context_only"
    assert result["method_coverage"]["unemployment_rate"] == "context_only"
    assert result["method_coverage"]["average_weekly_hours"] == "context_only"
    assert result["method_coverage"]["average_hourly_earnings"] == "context_only"
    assert result["method_coverage"]["payroll_revisions"] == "context_only"


def test_trend_records_carry_metric_contract_fields():
    result = claims_confirmation.build_claims_confirmation(
        initial_deteriorating(), continuing_stable(), "growth_decelerating", NOW
    )
    initial = result["initial_claims"]
    assert initial["metric_id"] == "initial_claims_trend"
    assert initial["source"] == "DOL"
    assert initial["seasonal_adjustment"] == "seasonally_adjusted"
    assert initial["raw_frequency"] == "weekly"
    assert initial["aggregation"] == "four_week_moving_average"
    assert initial["comparison"] == {
        "method": "percent_change",
        "baseline": "thirteen_weeks_ago",
    }
    assert initial["classification"] == "deteriorating"
    assert initial["method_version"] == "claims_trend_v1"
    assert initial["change_pct"] == pytest.approx(0.035)
    assert initial["latest_4w_mean"] == pytest.approx(103.5)
    assert initial["comparison_4w_mean"] == pytest.approx(100.0)
    assert len(initial["vintages"]) == 17
    assert set(initial["vintages"][0]) == {
        "reference_period",
        "value",
        "vintage_id",
        "source_url",
    }
    continuing = result["continuing_claims"]
    assert continuing["metric_id"] == "continuing_claims_trend"
    assert continuing["method_version"] == "claims_trend_v1"


def test_vintages_are_deduplicated():
    initial = initial_deteriorating()
    duplicated = initial + [dict(initial[0])]
    result = claims_confirmation.build_claims_confirmation(
        duplicated, [], "growth_decelerating", NOW
    )
    assert len(result["vintages"]) == len(initial)


def test_input_rows_are_sorted_by_reference_period_internally():
    rows = _trend_rows("initial_claims_sa", 0.035)
    result = claims_confirmation.build_claims_confirmation(
        list(reversed(rows)), continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["classification"] == "deteriorating"
    assert result["claims_direction"] == "partially_deteriorating"


def test_claims_trend_uses_effective_value_from_latest_revision():
    rows = _trend_rows("initial_claims_sa", 0.0)
    rows[-1]["value"] = 110.0
    rows[-1]["value_at_release"] = 100.0
    rows[-1]["latest_revised_value"] = 110.0
    result = claims_confirmation.build_claims_confirmation(
        rows, continuing_stable(), "growth_decelerating", NOW
    )
    assert result["initial_claims"]["latest_4w_mean"] == pytest.approx(
        (100.0 + 100.0 + 100.0 + 110.0) / 4
    )
