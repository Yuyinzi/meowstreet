from datetime import date

import pytest

from app.tools import inflation_distribution
from app.tools import price_distribution


def _monthly_rows(values, start=date(2016, 1, 1)):
    rows = []
    current = start
    for value in values:
        rows.append({"date": current.isoformat(), "value": value})
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return rows


def _jump_rows(final_value, return_count, start=date(2016, 1, 1)):
    values = [100.0] * return_count + [final_value]
    return _monthly_rows(values, start)


def test_monthly_distribution_uses_2016_window_and_arithmetic_sample_std():
    result = inflation_distribution.build_distribution(
        _monthly_rows([100.0, 101.0, 102.515, 103.74518]), minimum_samples=2
    )

    assert result["method_version"] == "inflation_price_distribution_v1"
    assert result["distribution_window"] == "2016-01-01_to_latest_available"
    assert result["return_definition"] == "arithmetic_month_over_month"
    assert result["standard_deviation"] == "sample"
    assert result["frequency"] == "monthly"
    assert result["week_definition"] is None
    assert result["classification"] == "normal"
    assert result["current_return"] == pytest.approx(0.012)


def test_monthly_distribution_excludes_pre_2016_observations():
    all_rows = _monthly_rows([10.0, 100.0, 110.0, 121.0], start=date(2015, 11, 1))
    result = inflation_distribution.build_distribution(all_rows, minimum_samples=2)
    expected = inflation_distribution.build_distribution(
        all_rows[2:], minimum_samples=2
    )

    assert result["sample_count"] == expected["sample_count"]
    assert result["sample_mean"] == expected["sample_mean"]
    assert result["sample_standard_deviation"] == expected["sample_standard_deviation"]
    assert result["sample_start_date"] == expected["sample_start_date"]
    assert result["sample_end_date"] == expected["sample_end_date"]


def test_monthly_distribution_computes_mom_returns_only_on_adjacent_calendar_months():
    rows = [
        {"date": "2016-01-01", "value": 100.0},
        {"date": "2016-02-01", "value": 105.0},
        {"date": "2016-04-01", "value": 115.5},
        {"date": "2016-05-01", "value": 121.275},
    ]

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["sample_count"] == 2
    assert result["current_return"] == pytest.approx(0.05)
    assert result["sample_start_date"] == "2016-02-01"
    assert result["sample_end_date"] == "2016-05-01"


def test_monthly_distribution_classifies_normal_within_one_sigma():
    rows = _jump_rows(100.0 * (1.0 + 0.707), 2)

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["classification"] == "normal"


def test_monthly_distribution_classifies_abnormal_1sigma():
    rows = _jump_rows(100.0 * 1.155, 3)

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["classification"] == "abnormal_1sigma"


def test_monthly_distribution_classifies_abnormal_2sigma():
    rows = _jump_rows(100.0 * 2.475, 8)

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["classification"] == "abnormal_2sigma"


def test_monthly_distribution_classifies_abnormal_3sigma():
    rows = _jump_rows(100.0 * 3.75, 16)

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["classification"] == "abnormal_3sigma"


def test_monthly_distribution_requires_minimum_history_by_default():
    result = inflation_distribution.build_distribution(_monthly_rows([100.0] * 35))

    assert result["classification"] == "unavailable"
    assert result["minimum_samples"] == 36
    assert result["reason"] == "at least 36 monthly returns are required"


def test_monthly_distribution_returns_unavailable_for_empty_observations():
    result = inflation_distribution.build_distribution([])

    assert result["classification"] == "unavailable"
    assert result["sample_count"] == 0
    assert result["reason"] == "no monthly observations are available"


def test_monthly_distribution_is_unavailable_when_latest_observation_is_invalid():
    rows = _monthly_rows([100.0] * 37 + [None])

    result = inflation_distribution.build_distribution(rows, minimum_samples=36)

    assert result["classification"] == "unavailable"
    assert result["reason"] == "the latest monthly observation has no valid value"


def test_monthly_distribution_is_unavailable_when_latest_month_has_no_prior_month():
    rows = [
        {"date": "2016-01-01", "value": 100.0},
        {"date": "2016-02-01", "value": 101.0},
        {"date": "2016-04-01", "value": 104.0},
    ]

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["classification"] == "unavailable"
    assert result["reason"] == (
        "the latest monthly observation has no adjacent prior month"
    )


def test_monthly_distribution_excludes_observations_after_as_of_date():
    rows = _monthly_rows([100.0] * 39 + [150.0], start=date(2016, 1, 1))
    as_of = date(2016, 3, 1).isoformat()

    result = inflation_distribution.build_distribution(
        rows, as_of_date=as_of, minimum_samples=1
    )

    assert result["sample_end_date"] == "2016-03-01"
    assert result["current_return"] == pytest.approx(0.0)
    assert result["sample_count"] == 2


def test_monthly_distribution_excludes_non_finite_values():
    rows = _monthly_rows([100.0, float("nan")], start=date(2016, 1, 1))

    result = inflation_distribution.build_distribution(
        rows, as_of_date="2016-03-01", minimum_samples=1
    )

    assert result["classification"] == "unavailable"
    assert result["reason"] == "the latest monthly observation has no valid value"


def test_monthly_distribution_dedupes_duplicate_dates_last_wins():
    rows = _monthly_rows([100.0, 105.0, 110.0])
    rows.append({"date": "2016-02-01", "value": 108.0})

    result = inflation_distribution.build_distribution(rows, minimum_samples=1)

    assert result["sample_count"] == 2
    assert result["current_return"] == pytest.approx(110.0 / 108.0 - 1)


def test_monthly_distribution_is_deterministic_for_repeated_inputs():
    rows = _monthly_rows([100.0, 102.0, 101.0, 103.0, 105.0])

    first = inflation_distribution.build_distribution(rows, minimum_samples=2)
    second = inflation_distribution.build_distribution(rows, minimum_samples=2)

    assert first == second


def test_monthly_distribution_calculates_each_series_independently():
    cpi_rows = _monthly_rows([100.0, 101.0, 102.0, 103.0])
    ppi_rows = _monthly_rows([100.0, 110.0, 121.0, 133.1])

    cpi_result = inflation_distribution.build_distribution(
        cpi_rows, minimum_samples=2
    )
    ppi_result = inflation_distribution.build_distribution(
        ppi_rows, minimum_samples=2
    )

    assert cpi_result["sample_mean"] != ppi_result["sample_mean"]
    assert (
        cpi_result["sample_standard_deviation"]
        != (ppi_result["sample_standard_deviation"])
    )


def test_monthly_distribution_rejects_unsupported_frequency_input():
    with pytest.raises(ValueError, match="distribution frequency is invalid"):
        price_distribution.build_distribution_from_returns(
            [{"date": "2016-02-01", "value": 0.1}],
            "quarterly",
            method_version=inflation_distribution.METHOD_VERSION,
            distribution_window=inflation_distribution.DISTRIBUTION_WINDOW,
            return_definition=inflation_distribution.RETURN_DEFINITION,
            minimum_samples=2,
        )


def test_valid_monthly_observations_filters_as_of_and_invalid_values():
    rows = _monthly_rows([100.0, 101.0, float("nan"), 103.0, 104.0])
    rows.append({"date": "2016-06-01", "value": 105.0})

    result = inflation_distribution.valid_monthly_observations(
        rows, as_of_date="2016-04-01"
    )

    assert [row["date"] for row in result] == [
        "2016-01-01",
        "2016-02-01",
        "2016-04-01",
    ]
    assert result[-1]["value"] == 103.0


def test_valid_monthly_observations_dedupes_duplicate_dates_last_wins():
    rows = _monthly_rows([100.0, 101.0, 102.0])
    rows.append({"date": "2016-02-01", "value": 108.0})

    result = inflation_distribution.valid_monthly_observations(rows)

    assert [row["date"] for row in result] == [
        "2016-01-01",
        "2016-02-01",
        "2016-03-01",
    ]
    assert result[1]["value"] == 108.0


def test_monthly_level_context_computes_mom_and_yoy_on_adjacent_calendar_months():
    rows = [
        {"date": "2015-12-01", "value": 90.0},
        {"date": "2016-01-01", "value": 100.0},
        {"date": "2016-02-01", "value": 110.0},
    ]

    context = inflation_distribution.monthly_level_context(rows)

    assert context["latest_date"] == "2016-02-01"
    assert context["latest_value"] == 110.0
    assert context["mom_pct"] == pytest.approx(0.1)
    assert context["yoy_pct"] is None


def test_monthly_level_context_yoy_uses_exactly_twelve_calendar_months_back():
    values = [100.0 + index for index in range(13)]
    rows = _monthly_rows(values)

    context = inflation_distribution.monthly_level_context(rows)

    assert context["latest_date"] == "2017-01-01"
    assert context["yoy_pct"] == pytest.approx(12.0 / 100.0)


def test_monthly_level_context_mom_is_none_across_missing_month_gap():
    rows = [
        {"date": "2016-01-01", "value": 100.0},
        {"date": "2016-02-01", "value": 101.0},
        {"date": "2016-04-01", "value": 110.0},
    ]

    context = inflation_distribution.monthly_level_context(rows)

    assert context["latest_date"] == "2016-04-01"
    assert context["mom_pct"] is None


def test_monthly_level_context_yoy_is_none_across_missing_12_month_observation():
    rows = [
        {"date": "2016-06-01", "value": 100.0},
        {"date": "2017-05-01", "value": 150.0},
    ]

    context = inflation_distribution.monthly_level_context(rows)

    assert context["latest_date"] == "2017-05-01"
    assert context["mom_pct"] is None
    assert context["yoy_pct"] is None


def test_monthly_level_context_respects_as_of_date():
    rows = _monthly_rows([100.0, 101.0, 102.0])
    rows.append({"date": "2016-04-01", "value": 110.0})

    context = inflation_distribution.monthly_level_context(
        rows, as_of_date="2016-03-01"
    )

    assert context["latest_date"] == "2016-03-01"
    assert context["mom_pct"] == pytest.approx(102.0 / 101.0 - 1)


def test_monthly_level_context_returns_none_for_empty_observations():
    assert inflation_distribution.monthly_level_context([]) is None
