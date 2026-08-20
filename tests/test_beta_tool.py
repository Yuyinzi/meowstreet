import json
from pathlib import Path

import pytest

from app.tools import beta

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "p20_beta.json"


def p20_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def workbook_positions():
    return [
        {
            "symbol": position["ticker"],
            "side": 1 if position["side"] == "long" else -1,
            "beta": position["beta"],
            "price": position["price"],
            "shares": position["shares"],
        }
        for position in p20_fixture()["portfolio_beta"]["positions"]
    ]


def sizing_positions():
    return [
        {"symbol": "AAA", "side": 1, "beta": 1.0, "price": 100.0, "shares": 10},
        {"symbol": "BBB", "side": 1, "beta": 2.0, "price": 50.0, "shares": 20},
        {"symbol": "CCC", "side": -1, "beta": 0.5, "price": 25.0, "shares": 40},
        {"symbol": "DDD", "side": -1, "beta": 4.0, "price": 200.0, "shares": 5},
    ]


@pytest.mark.parametrize("series_key,window,expected_key", [
    ("safm_returns", 105, "beta_2yr"),
    ("safm_returns", 157, "beta_3yr"),
    ("safm_returns", 261, "beta_5yr"),
    ("flr_returns", 105, "beta_2yr"),
    ("flr_returns", 157, "beta_3yr"),
    ("flr_returns", 261, "beta_5yr"),
])
def test_slope_matches_workbook_beta(series_key, window, expected_key):
    equity = p20_fixture()["equity_beta"]
    label = "safm" if series_key.startswith("safm") else "flr"

    result = beta.slope(equity[series_key][:window], equity["sp500_returns"][:window])

    assert result == pytest.approx(equity["expected"][label][expected_key], abs=1e-9)


@pytest.mark.parametrize("series_key,label", [
    ("safm_returns", "safm"),
    ("flr_returns", "flr"),
])
def test_beta_standard_error_matches_workbook(series_key, label):
    equity = p20_fixture()["equity_beta"]

    result = beta.beta_standard_error(equity[series_key][:105], equity["sp500_returns"][:105])

    assert result == pytest.approx(equity["expected"][label]["beta_2yr_se"], abs=1e-9)


def test_slope_rejects_unequal_length():
    with pytest.raises(ValueError, match="series length mismatch 3 != 2"):
        beta.slope([0.1, 0.2, 0.3], [0.1, 0.2])


def test_slope_rejects_short_series():
    with pytest.raises(ValueError, match="at least 2 returns are required"):
        beta.slope([0.1], [0.2])


def test_slope_rejects_zero_market_variance():
    with pytest.raises(ValueError, match="market returns have zero variance"):
        beta.slope([0.1, 0.2, 0.3], [0.5, 0.5, 0.5])


def test_beta_standard_error_rejects_short_series():
    with pytest.raises(ValueError, match="at least 3 returns are required"):
        beta.beta_standard_error([0.1, 0.2], [0.1, 0.2])


def test_beta_windows_match_workbook_with_labels():
    equity = p20_fixture()["equity_beta"]

    result = beta.beta_windows(equity["safm_returns"], equity["sp500_returns"])

    assert [window["label"] for window in result["windows"]] == ["2y", "3y", "5y"]
    for window, expected_key in zip(result["windows"], ("beta_2yr", "beta_3yr", "beta_5yr")):
        assert window["status"] == "ok"
        assert window["beta"] == pytest.approx(equity["expected"]["safm"][expected_key], abs=1e-9)
        assert window["sample_size"] == window["window"]


def test_beta_windows_flag_insufficient_data_per_window():
    equity = p20_fixture()["equity_beta"]
    stock = equity["safm_returns"][:160]
    market = equity["sp500_returns"][:160]

    result = beta.beta_windows(stock, market)

    statuses = {window["window"]: window["status"] for window in result["windows"]}
    assert statuses == {105: "ok", 157: "ok", 261: "insufficient_data"}
    insufficient = result["windows"][2]
    assert insufficient["beta"] is None
    assert insufficient["standard_error"] is None
    assert insufficient["sample_size"] == 160


def test_beta_windows_all_insufficient_when_series_short():
    result = beta.beta_windows([0.01] * 50, [0.02] * 50)

    assert all(window["status"] == "insufficient_data" for window in result["windows"])


def test_rolling_beta_uses_full_windows_only():
    equity = p20_fixture()["equity_beta"]

    result = beta.rolling_beta(
        equity["dates"], equity["safm_returns"], equity["sp500_returns"], window=105
    )

    assert len(result) == len(equity["dates"]) - 105 + 1
    assert result[0]["end_date"] == equity["dates"][104]
    assert result[0]["beta"] == pytest.approx(
        equity["expected"]["safm"]["beta_2yr"], abs=1e-9
    )


def test_rolling_beta_empty_when_series_shorter_than_window():
    result = beta.rolling_beta(
        ["2024-01-05", "2024-01-12"], [0.01, 0.02], [0.01, 0.02], window=105
    )

    assert result == []


def test_rolling_beta_rejects_misaligned_dates():
    with pytest.raises(ValueError, match="dates length 2 does not match stock returns length 3"):
        beta.rolling_beta(["a", "b"], [0.1, 0.2, 0.3], [0.1, 0.2, 0.3], window=2)


def test_rolling_beta_rejects_tiny_window():
    with pytest.raises(ValueError, match="window 1 is too small"):
        beta.rolling_beta(["a", "b"], [0.1, 0.2], [0.1, 0.2], window=1)


def test_portfolio_beta_matches_workbook():
    fixture = p20_fixture()["portfolio_beta"]

    result = beta.portfolio_beta(workbook_positions())

    expected = fixture["expected"]
    assert result["portfolio_beta"] == pytest.approx(expected["portfolio_beta"], abs=1e-9)
    assert result["gross_exposure"] == pytest.approx(expected["gross_exposure"], abs=1e-9)
    assert result["net_exposure"] == pytest.approx(expected["net_exposure"], abs=1e-9)
    assert result["net_weight"] == pytest.approx(expected["net_weight"], abs=1e-9)
    for detail, cached in zip(result["positions"], fixture["positions"]):
        assert detail["symbol"] == cached["ticker"]
        assert detail["net_exposure"] == pytest.approx(cached["net_exposure"], abs=1e-9)
        assert detail["gross_exposure"] == pytest.approx(cached["gross_exposure"], abs=1e-9)
        assert detail["net_weight"] == pytest.approx(cached["net_weight"], abs=1e-9)
        assert detail["net_weighted_beta"] == pytest.approx(cached["net_weighted_beta"], abs=1e-9)


def test_portfolio_beta_rejects_empty_positions():
    with pytest.raises(ValueError, match="positions are required"):
        beta.portfolio_beta([])


def test_portfolio_beta_rejects_zero_gross():
    positions = [{"symbol": "AAA", "side": 1, "beta": 1.0, "price": 100.0, "shares": 0}]

    with pytest.raises(ValueError, match="gross exposure must be positive"):
        beta.portfolio_beta(positions)


def test_portfolio_beta_rejects_invalid_side():
    positions = [{"symbol": "AAA", "side": 0, "beta": 1.0, "price": 100.0, "shares": 10}]

    with pytest.raises(ValueError, match="position AAA side must be 1 or -1"):
        beta.portfolio_beta(positions)


def test_sizing_scenarios_equal_weight_splits_gross_evenly():
    result = beta.sizing_scenarios(sizing_positions(), 100_000)

    equal_weight = result["equal_weight"]["positions"]
    assert [position["weight"] for position in equal_weight] == [0.25, 0.25, 0.25, 0.25]
    assert [position["shares"] for position in equal_weight] == [250, 500, 1000, 125]
    assert result["equal_weight"]["note"] == beta.SIZING_NOTE


def test_sizing_scenarios_risk_parity_weights_sum_to_one():
    result = beta.sizing_scenarios(sizing_positions(), 100_000)

    risk_parity = result["risk_parity"]["positions"]
    assert sum(position["weight"] for position in risk_parity) == pytest.approx(1.0)
    weights = {position["symbol"]: position["weight"] for position in risk_parity}
    assert weights["AAA"] == pytest.approx(1 / 3.75)
    assert weights["CCC"] == pytest.approx(2 / 3.75)
    shares = {position["symbol"]: position["shares"] for position in risk_parity}
    assert shares["AAA"] == round((1 / 3.75) * 100_000 / 100.0)
    assert result["risk_parity"]["note"] == beta.SIZING_NOTE


def test_sizing_scenarios_beta_parity_sides_each_get_half_gross():
    result = beta.sizing_scenarios(sizing_positions(), 100_000)

    beta_parity = result["beta_parity"]["positions"]
    long_weight = sum(
        position["weight"] for position in beta_parity if position["symbol"] in ("AAA", "BBB")
    )
    short_weight = sum(
        position["weight"] for position in beta_parity if position["symbol"] in ("CCC", "DDD")
    )
    assert long_weight == pytest.approx(0.5)
    assert short_weight == pytest.approx(0.5)
    weights = {position["symbol"]: position["weight"] for position in beta_parity}
    assert weights["AAA"] == pytest.approx((1 / 1.5) * 0.5)
    assert weights["DDD"] == pytest.approx((0.25 / 2.25) * 0.5)
    shares = {position["symbol"]: position["shares"] for position in beta_parity}
    assert shares["AAA"] == round((1 / 1.5) * 0.5 * 100_000 / 100.0)
    assert result["beta_parity"]["note"] == beta.SIZING_NOTE


def test_sizing_scenarios_reject_non_positive_beta():
    positions = sizing_positions()
    positions[0]["beta"] = 0
    positions[3]["beta"] = -1.5

    with pytest.raises(ValueError, match="positions with non-positive beta: AAA, DDD"):
        beta.sizing_scenarios(positions, 100_000)


def test_sizing_scenarios_reject_non_positive_target_gross():
    with pytest.raises(ValueError, match="target gross must be positive"):
        beta.sizing_scenarios(sizing_positions(), 0)


def test_sizing_scenarios_reject_non_positive_price():
    positions = sizing_positions()
    positions[1]["price"] = 0

    with pytest.raises(ValueError, match="position BBB price must be positive"):
        beta.sizing_scenarios(positions, 100_000)
