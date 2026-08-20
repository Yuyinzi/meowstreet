import json
import math
from pathlib import Path

import pytest

from app.tools import portfolio_volatility

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "p18_portfolio_volatility.json"


def p18_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def report_fixture_result():
    fixture = p18_fixture()
    positions = [
        {"symbol": position["ticker"], "allocation": position["net_allocation"]}
        for position in fixture["positions"]
    ]
    return fixture, portfolio_volatility.portfolio_volatility_report(
        positions, fixture["returns"]["series"]
    )


def test_simple_returns():
    assert portfolio_volatility.simple_returns([100.0, 110.0, 105.0]) == pytest.approx(
        [0.1, 105.0 / 110.0 - 1]
    )


def test_simple_returns_rejects_short_series():
    with pytest.raises(ValueError, match="at least 2 closes"):
        portfolio_volatility.simple_returns([100.0])


def test_simple_returns_rejects_zero_close():
    with pytest.raises(ValueError, match="close at index 0 is zero"):
        portfolio_volatility.simple_returns([0.0, 100.0])


def test_sample_covariance_matches_known_values():
    assert portfolio_volatility.sample_covariance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert portfolio_volatility.sample_covariance([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(2.0)
    assert portfolio_volatility.sample_covariance([1.0, 2.0, 3.0], [6.0, 4.0, 2.0]) == pytest.approx(-2.0)


def test_sample_covariance_rejects_unequal_lengths():
    with pytest.raises(ValueError, match="series lengths differ"):
        portfolio_volatility.sample_covariance([1.0, 2.0], [1.0])


def test_sample_covariance_rejects_short_series():
    with pytest.raises(ValueError, match="at least 2 observations"):
        portfolio_volatility.sample_covariance([1.0], [2.0])


def test_covariance_matrix_is_symmetric_with_variance_diagonal():
    returns = {"AAA": [0.01, -0.02, 0.03], "BBB": [0.02, -0.01, 0.01]}

    matrix = portfolio_volatility.covariance_matrix(returns, ["AAA", "BBB"])

    assert matrix[0][1] == pytest.approx(matrix[1][0])
    assert matrix[0][0] == pytest.approx(
        portfolio_volatility.sample_covariance(returns["AAA"], returns["AAA"])
    )
    assert matrix[0][1] == pytest.approx(
        portfolio_volatility.sample_covariance(returns["AAA"], returns["BBB"])
    )


def test_covariance_matrix_requires_return_series():
    with pytest.raises(ValueError, match="missing return series for BBB"):
        portfolio_volatility.covariance_matrix({"AAA": [0.01, 0.02]}, ["AAA", "BBB"])


def test_signed_weights_match_workbook():
    fixture = p18_fixture()
    allocations = [position["net_allocation"] for position in fixture["positions"]]

    weights = portfolio_volatility.signed_weights(allocations)

    gross = sum(abs(allocation) for allocation in allocations)
    assert gross == pytest.approx(4 * 12500.0 + 6 * 8333.0)
    assert weights == pytest.approx(
        [position["weight"] for position in fixture["positions"]], abs=1e-9
    )
    assert sum(abs(weight) for weight in weights) == pytest.approx(1.0)


def test_signed_weights_reject_zero_gross():
    with pytest.raises(ValueError, match="gross exposure is zero"):
        portfolio_volatility.signed_weights([0.0, 0.0])


def test_portfolio_variance_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="dimensions do not match weights"):
        portfolio_volatility.portfolio_variance([0.5, 0.5], [[1.0]])


def test_weekly_and_annualized_volatility():
    result = portfolio_volatility.weekly_and_annualized_volatility(0.0004)

    assert result["weekly_stdev"] == pytest.approx(0.02)
    assert result["annualized_stdev"] == pytest.approx(0.02 * math.sqrt(52))


def test_weekly_and_annualized_volatility_rejects_negative_variance():
    with pytest.raises(ValueError, match="negative"):
        portfolio_volatility.weekly_and_annualized_volatility(-0.0001)


def test_average_asset_volatility_uses_mean_variance():
    result = portfolio_volatility.average_asset_volatility([0.0004, 0.0009])

    assert result["weekly_stdev"] == pytest.approx(math.sqrt(0.00065))
    assert result["annualized_stdev"] == pytest.approx(math.sqrt(0.00065) * math.sqrt(52))


def test_average_asset_volatility_requires_variances():
    with pytest.raises(ValueError, match="variances are required"):
        portfolio_volatility.average_asset_volatility([])


def test_portfolio_volatility_report_matches_workbook():
    fixture, report = report_fixture_result()
    expected = fixture["expected"]

    assert report["gross_exposure"] == pytest.approx(4 * 12500.0 + 6 * 8333.0)
    assert [position["signed_weight"] for position in report["positions"]] == pytest.approx(
        [position["weight"] for position in fixture["positions"]], abs=1e-9
    )
    assert report["variance"] == pytest.approx(expected["portfolio_variance"], abs=1e-9)
    assert report["weekly_stdev"] == pytest.approx(expected["portfolio_stdev_weekly"], abs=1e-9)
    assert report["annualized_stdev"] == pytest.approx(expected["portfolio_stdev_annual"], abs=1e-9)
    assert report["average_asset_annualized_stdev"] == pytest.approx(
        expected["avg_asset_stdev_annual"], abs=1e-9
    )
    assert report["average_asset_weekly_stdev"] == pytest.approx(
        expected["avg_asset_stdev_annual"] / math.sqrt(52), abs=1e-9
    )


def test_portfolio_volatility_report_sharpe_scenarios():
    _, report = report_fixture_result()

    assert [scenario["sharpe"] for scenario in report["sharpe_scenarios"]] == [0.5, 1.0, 1.5, 2.0]
    for scenario in report["sharpe_scenarios"]:
        assert scenario["expected_annual_return"] == pytest.approx(
            scenario["sharpe"] * report["annualized_stdev"]
        )


def test_realized_volatility_uses_sample_stdev():
    result = portfolio_volatility.realized_volatility([1.0, 2.0, 3.0], 252)

    assert result["stdev"] == pytest.approx(1.0)
    assert result["annualized"] == pytest.approx(math.sqrt(252))
    assert result["sample_size"] == 3


def test_realized_volatility_rejects_short_series():
    with pytest.raises(ValueError, match="at least 2 returns"):
        portfolio_volatility.realized_volatility([0.01], 252)


def test_realized_volatility_rejects_non_positive_periods():
    with pytest.raises(ValueError, match="must be positive"):
        portfolio_volatility.realized_volatility([0.01, 0.02], 0)


def test_realized_volatility_report_horizons():
    daily_closes = [100.0 * (1.001 ** index) for index in range(101)]
    weekly_closes = [100.0 * (1.002 ** index) for index in range(60)]

    report = portfolio_volatility.realized_volatility_report(daily_closes, weekly_closes)

    assert report["daily"]["sample_size"] == 100
    assert report["weekly"]["sample_size"] == 59
    assert report["monthly_21d"]["sample_size"] == 21
    assert report["quarterly_63d"]["sample_size"] == 63
    assert report["daily"]["annualized"] == pytest.approx(
        report["daily"]["stdev"] * math.sqrt(252)
    )
    assert report["weekly"]["annualized"] == pytest.approx(
        report["weekly"]["stdev"] * math.sqrt(52)
    )
    assert report["monthly_21d"]["annualized"] == pytest.approx(
        report["monthly_21d"]["stdev"] * math.sqrt(252)
    )
    assert report["monthly_21d"]["stdev"] == pytest.approx(
        portfolio_volatility.realized_volatility(
            portfolio_volatility.simple_returns(daily_closes)[-21:], 252
        )["stdev"]
    )


def test_realized_volatility_report_flags_insufficient_horizons():
    daily_closes = [100.0 * (1.001 ** index) for index in range(11)]
    weekly_closes = [100.0 * (1.002 ** index) for index in range(10)]

    report = portfolio_volatility.realized_volatility_report(daily_closes, weekly_closes)

    assert report["monthly_21d"] == {"status": "insufficient_data", "sample_size": 10, "required": 21}
    assert report["quarterly_63d"] == {"status": "insufficient_data", "sample_size": 10, "required": 63}
    assert report["daily"]["sample_size"] == 10
    assert report["weekly"]["sample_size"] == 9


@pytest.mark.parametrize("count,within_range,warning", [
    (7, False, "under_diversified"),
    (8, True, None),
    (10, True, None),
    (12, True, None),
    (13, False, "over_diversified"),
])
def test_position_count_check(count, within_range, warning):
    result = portfolio_volatility.position_count_check(count)

    assert result == {"count": count, "within_range": within_range, "warning": warning}
