from app.tools import oil_distribution


def test_daily_distribution_uses_arithmetic_adjacent_close_returns_and_sample_std():
    rows = [
        {"date": "2026-01-02", "value": 100.0},
        {"date": "2026-01-05", "value": 110.0},
        {"date": "2026-01-06", "value": 99.0},
    ]

    result = oil_distribution.build_distribution(rows, "daily", minimum_samples=2)

    assert result["return_definition"] == "arithmetic_close_to_close"
    assert result["standard_deviation"] == "sample"
    assert result["sample_count"] == 2
    assert result["current_return"] == -0.1
    assert result["classification"] == "normal"


def test_weekly_distribution_uses_last_available_iso_week_close_and_does_not_bridge_gap():
    rows = [
        {"date": "2025-12-26", "value": 100.0},
        {"date": "2026-01-02", "value": 110.0},
        {"date": "2026-01-16", "value": 121.0},
    ]

    returns = oil_distribution.iso_weekly_returns(rows)

    assert returns == [{"date": "2026-01-02", "value": 0.1}]


def test_distribution_classifies_threshold_boundaries_without_trade_direction():
    result = oil_distribution.classify_return(0.03, 0.0, 0.01)

    assert result == "abnormal_3sigma"


def test_distribution_is_unavailable_below_minimum_sample_count():
    result = oil_distribution.build_distribution(
        [{"date": "2026-01-02", "value": 100.0}], "daily", minimum_samples=252
    )

    assert result["classification"] == "unavailable"
    assert result["reason"] == "at least 252 daily returns are required"
