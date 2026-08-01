from app.tools import price_distribution


def test_distribution_from_observations_uses_requested_method_metadata():
    result = price_distribution.build_distribution_from_observations(
        [
            {"date": "2016-01-04", "value": 100.0},
            {"date": "2016-01-05", "value": 101.0},
            {"date": "2016-01-06", "value": 99.0},
        ],
        "daily",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        minimum_samples=2,
    )
    assert result["method_version"] == "non_oil_price_distribution_v1"
    assert result["sample_count"] == 2
    assert result["classification"] == "normal"


def test_distribution_from_observations_excludes_rows_before_start_date():
    result = price_distribution.build_distribution_from_observations(
        [
            {"date": "2015-12-31", "value": 10.0},
            {"date": "2016-01-01", "value": 100.0},
            {"date": "2016-01-04", "value": 110.0},
            {"date": "2016-01-05", "value": 121.0},
        ],
        "daily",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        minimum_samples=2,
    )
    assert result["sample_start_date"] == "2016-01-04"
    assert result["sample_end_date"] == "2016-01-05"
    assert result["sample_count"] == 2


def test_distribution_from_returns_uses_supplied_rows_directly():
    result = price_distribution.build_distribution_from_returns(
        [
            {"date": "2026-01-02", "value": 0.1},
            {"date": "2026-01-05", "value": -0.05},
            {"date": "2026-01-06", "value": 0.03},
        ],
        "daily",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        return_definition="arithmetic_close_to_close",
        minimum_samples=2,
    )
    assert result["sample_count"] == 3
    assert result["current_return"] == 0.03


def test_weekly_distribution_does_not_bridge_across_missing_iso_week():
    result = price_distribution.build_distribution_from_observations(
        [
            {"date": "2025-12-26", "value": 100.0},
            {"date": "2026-01-02", "value": 110.0},
            {"date": "2026-01-09", "value": 121.0},
            {"date": "2026-01-23", "value": 145.2},
        ],
        "weekly",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        minimum_samples=2,
    )
    assert result["sample_count"] == 2
    assert result["current_return"] == 0.1
    assert result["sample_end_date"] == "2026-01-09"


def test_distribution_classifies_zero_standard_deviation():
    result = price_distribution.build_distribution_from_returns(
        [
            {"date": "2026-01-02", "value": 0.02},
            {"date": "2026-01-05", "value": 0.02},
            {"date": "2026-01-06", "value": 0.02},
        ],
        "daily",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        return_definition="arithmetic_close_to_close",
        minimum_samples=2,
    )
    assert result["sample_standard_deviation"] == 0.0
    assert result["classification"] == "normal"


def test_insufficient_samples_returns_exact_reason_string():
    result = price_distribution.build_distribution_from_returns(
        [{"date": "2026-01-02", "value": 0.01}],
        "daily",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        return_definition="arithmetic_close_to_close",
        minimum_samples=252,
    )
    assert result["classification"] == "unavailable"
    assert result["reason"] == "at least 252 daily returns are required"


def test_default_minimum_samples_match_oil_frequency_defaults():
    daily = price_distribution.build_distribution_from_returns(
        [{"date": "2026-01-02", "value": 0.01}],
        "daily",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        return_definition="arithmetic_close_to_close",
    )
    weekly = price_distribution.build_distribution_from_returns(
        [{"date": "2026-01-02", "value": 0.01}],
        "weekly",
        method_version="non_oil_price_distribution_v1",
        distribution_window="2016-01-01_to_latest_available",
        return_definition="arithmetic_close_to_close",
    )
    assert daily["minimum_samples"] == 252
    assert daily["reason"] == "at least 252 daily returns are required"
    assert weekly["minimum_samples"] == 52
    assert weekly["reason"] == "at least 52 weekly returns are required"
