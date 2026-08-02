from datetime import date, timedelta

import pytest

from app.tools import usd_distribution


def _daily_rows(values, start=date(2016, 1, 4)):
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "value": value}
        for i, value in enumerate(values)
    ]


def test_usd_daily_distribution_uses_2016_window_and_arithmetic_sample_std():
    result = usd_distribution.build_distribution(
        _daily_rows([100.0, 110.0, 99.0]), "daily", minimum_samples=2
    )

    assert result["method_version"] == "usd_price_distribution_v1"
    assert result["distribution_window"] == "2016-01-01_to_latest_available"
    assert result["return_definition"] == "arithmetic_close_to_close"
    assert result["standard_deviation"] == "sample"
    assert result["classification"] == "normal"


def test_usd_distribution_excludes_pre_2016_observations():
    all_rows = _daily_rows([10.0, 100.0, 110.0, 121.0], start=date(2015, 12, 31))
    result = usd_distribution.build_distribution(
        all_rows, "daily", minimum_samples=2
    )
    expected = usd_distribution.build_distribution(
        all_rows[1:], "daily", minimum_samples=2
    )

    assert result["sample_count"] == expected["sample_count"]
    assert result["sample_mean"] == expected["sample_mean"]
    assert result["sample_standard_deviation"] == expected["sample_standard_deviation"]
    assert result["sample_end_date"] == expected["sample_end_date"]


def test_usd_weekly_distribution_uses_iso_calendar_week_last_available_trading_day():
    rows = [
        {"date": "2016-01-08", "value": 100.0},
        {"date": "2016-01-15", "value": 110.0},
        {"date": "2016-01-22", "value": 121.0},
    ]

    result = usd_distribution.build_distribution(rows, "weekly", minimum_samples=2)

    assert result["week_definition"] == "iso_calendar_week_last_available_trading_day"
    assert result["sample_count"] == 2
    assert result["classification"] == "normal"


def test_usd_distribution_returns_generic_short_history_reasons_for_default_minimums():
    daily = usd_distribution.build_distribution([], "daily")
    weekly = usd_distribution.build_distribution([], "weekly")

    assert daily["classification"] == "unavailable"
    assert daily["reason"] == "at least 252 daily returns are required"
    assert weekly["classification"] == "unavailable"
    assert weekly["reason"] == "at least 52 weekly returns are required"


def test_usd_distribution_classifies_large_final_return_abnormal_with_lowered_minimum():
    result = usd_distribution.build_distribution(
        _daily_rows([100.0, 101.0, 102.0, 51.0]), "daily", minimum_samples=2
    )

    assert result["classification"].startswith("abnormal_")
    assert result["current_return"] == pytest.approx(51.0 / 102.0 - 1)
