import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.tools import correlation

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "correlation.json"


def fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def weekly_dates(count, newest=date(2021, 6, 10)):
    return [(newest - timedelta(weeks=offset)).isoformat() for offset in range(count)]


def test_pearson_matches_known_values():
    assert correlation.pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    assert correlation.pearson([1.0, 2.0, 3.0], [6.0, 4.0, 2.0]) == pytest.approx(-1.0)


def test_pearson_rejects_unequal_lengths():
    with pytest.raises(ValueError, match="series lengths differ"):
        correlation.pearson([0.01, 0.02], [0.01])


def test_pearson_rejects_short_series():
    with pytest.raises(ValueError, match="at least 2 observations"):
        correlation.pearson([0.01], [0.02])


def test_pearson_rejects_zero_variance_series():
    with pytest.raises(ValueError, match="zero variance"):
        correlation.pearson([0.01, 0.01, 0.01], [0.02, 0.03, 0.04])


def test_pearson_matches_workbook_overall_wms_ogs():
    fixture_data = fixture()["wms_ogs"]

    result = correlation.pearson(fixture_data["wms_returns"], fixture_data["ogs_returns"])

    assert result == pytest.approx(fixture_data["expected"]["overall_correl"], abs=1e-9)


def test_correlation_windows_match_workbook_wms_ogs():
    fixture_data = fixture()["wms_ogs"]

    result = correlation.correlation_windows(
        fixture_data["dates"], fixture_data["wms_returns"], fixture_data["ogs_returns"]
    )

    assert result["overall"]["status"] == "ok"
    assert result["overall"]["correlation"] == pytest.approx(
        fixture_data["expected"]["overall_correl"], abs=1e-9
    )
    assert result["overall"]["sample_size"] == 308
    assert result["one_year"]["status"] == "ok"
    assert result["one_year"]["correlation"] == pytest.approx(
        fixture_data["expected"]["one_year_correl"], abs=1e-9
    )
    assert result["two_year"]["status"] == "ok"
    assert result["two_year"]["correlation"] == pytest.approx(
        fixture_data["expected"]["two_year_correl"], abs=1e-9
    )


def test_correlation_windows_flag_insufficient_below_one_year():
    returns_a = [0.01 * ((-1) ** index) for index in range(40)]
    returns_b = [0.02 * ((-1) ** index) for index in range(40)]

    result = correlation.correlation_windows(weekly_dates(40), returns_a, returns_b)

    assert result["one_year"]["status"] == "insufficient_data"
    assert result["one_year"]["sample_size"] == 40
    assert result["two_year"]["status"] == "insufficient_data"
    assert result["overall"]["status"] == "ok"
    assert result["overall"]["sample_size"] == 40
    assert result["overall"]["correlation"] == pytest.approx(
        correlation.pearson(returns_a, returns_b)
    )


def test_correlation_windows_flag_insufficient_overall_below_two_returns():
    result = correlation.correlation_windows(weekly_dates(1), [0.01], [0.02])

    assert result["overall"] == {"status": "insufficient_data", "sample_size": 1}
    assert result["one_year"]["status"] == "insufficient_data"
    assert result["two_year"]["status"] == "insufficient_data"


def test_rolling_correlation_drops_incomplete_windows():
    returns_a = [0.01 * ((-1) ** index) for index in range(60)]
    returns_b = [0.02 * ((-1) ** index) for index in range(60)]
    dates = weekly_dates(60)

    result = correlation.rolling_correlation(dates, returns_a, returns_b, 52)

    assert len(result) == 60 - 52 + 1
    assert result[0]["end_date"] == dates[0]
    assert result[0]["correlation"] == pytest.approx(1.0)
    assert correlation.rolling_correlation(dates[:51], returns_a[:51], returns_b[:51], 52) == []


def test_rolling_correlation_rejects_tiny_windows():
    with pytest.raises(ValueError, match="correlation window 1 is too small"):
        correlation.rolling_correlation(["2021-06-10", "2021-06-03"], [0.01, 0.02], [0.01, 0.02], 1)


def test_rolling_correlation_requires_aligned_inputs():
    with pytest.raises(ValueError, match="dates length"):
        correlation.rolling_correlation(["2021-06-10"], [0.01, 0.02], [0.01, 0.02], 2)


def signed_matrix_fixture_result():
    fixture_data = fixture()["portfolio"]
    positions = [
        {"symbol": position["ticker"], "side": position["side"]}
        for position in fixture_data["positions"]
    ]
    return fixture_data, correlation.signed_correlation_matrix(positions, fixture_data["returns"]["series"])


def test_signed_correlation_matrix_matches_workbook():
    fixture, result = signed_matrix_fixture_result()

    assert result["symbols"] == [position["ticker"] for position in fixture["positions"]]
    assert result["sides"] == [position["side"] for position in fixture["positions"]]
    for position, average in zip(fixture["positions"], result["per_position_average"]):
        assert average == pytest.approx(position["avg_correlation_cached"], abs=1e-9)
    assert result["overall_average"] == pytest.approx(
        fixture["expected_portfolio_avg_correlation"], abs=1e-9
    )
    assert result["disclaimer"] == "indicative only, does not account for weightings"


def test_signed_correlation_matrix_diagonal_is_none_and_excluded_from_averages():
    returns = {
        "AAA": [0.01, -0.02, 0.03, 0.005],
        "BBB": [0.02, -0.01, 0.01, 0.004],
        "CCC": [-0.01, 0.02, -0.02, 0.001],
    }
    positions = [
        {"symbol": "AAA", "side": 1},
        {"symbol": "BBB", "side": 1},
        {"symbol": "CCC", "side": 1},
    ]

    result = correlation.signed_correlation_matrix(positions, returns)

    assert all(result["matrix"][index][index] is None for index in range(3))
    off_diagonal = [
        result["matrix"][row][col]
        for row in range(3)
        for col in range(3)
        if row != col
    ]
    assert all(value is not None for value in off_diagonal)
    assert result["per_position_average"][0] == pytest.approx(
        (result["matrix"][0][1] + result["matrix"][0][2]) / 2
    )
    upper_triangle = [result["matrix"][0][1], result["matrix"][0][2], result["matrix"][1][2]]
    assert result["overall_average"] == pytest.approx(sum(upper_triangle) / 3)


def test_signed_correlation_matrix_applies_side_signs():
    series = [0.01, -0.02, 0.03, 0.005]
    returns = {"AAA": series, "BBB": list(series)}
    positions = [{"symbol": "AAA", "side": 1}, {"symbol": "BBB", "side": -1}]

    result = correlation.signed_correlation_matrix(positions, returns)

    assert result["matrix"][0][1] == pytest.approx(-1.0)
    assert result["matrix"][1][0] == pytest.approx(-1.0)
    assert result["overall_average"] == pytest.approx(-1.0)


def test_signed_correlation_matrix_requires_two_positions():
    with pytest.raises(ValueError, match="at least 2 positions"):
        correlation.signed_correlation_matrix(
            [{"symbol": "AAA", "side": 1}], {"AAA": [0.01, 0.02]}
        )


def test_signed_correlation_matrix_rejects_invalid_side():
    with pytest.raises(ValueError, match="side must be 1 or -1"):
        correlation.signed_correlation_matrix(
            [{"symbol": "AAA", "side": 1}, {"symbol": "BBB", "side": 0}],
            {"AAA": [0.01, 0.02], "BBB": [0.01, 0.02]},
        )


def test_signed_correlation_matrix_requires_return_series():
    with pytest.raises(ValueError, match="missing return series for BBB"):
        correlation.signed_correlation_matrix(
            [{"symbol": "AAA", "side": 1}, {"symbol": "BBB", "side": 1}],
            {"AAA": [0.01, 0.02]},
        )


def test_signed_correlation_matrix_requires_equal_length_series():
    with pytest.raises(ValueError, match="equal length"):
        correlation.signed_correlation_matrix(
            [{"symbol": "AAA", "side": 1}, {"symbol": "BBB", "side": 1}],
            {"AAA": [0.01, 0.02], "BBB": [0.01, 0.02, 0.03]},
        )
