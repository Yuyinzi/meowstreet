import json
from pathlib import Path

import pytest

from app.tools import portfolio_performance

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "p17_portfolio_performance.json"


def p17_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def nrb_positions():
    return [
        {"symbol": position["ticker"], "shares": position["shares"], "side": position["sign"]}
        for position in p17_fixture()["nrb"]["positions"]
    ]


def cw_positions():
    return [
        {"symbol": position["ticker"], "weight": position["weight"], "side": position["sign"]}
        for position in p17_fixture()["cw"]["positions"]
    ]


def nrb_series():
    nrb = p17_fixture()["nrb"]
    return portfolio_performance.nrb_portfolio_series(
        nrb_positions(), nrb["grid"]["dates"], nrb["grid"]["prices"]
    )


def test_equal_dollar_shares_matches_workbook_share_counts():
    nrb = p17_fixture()["nrb"]

    for position in nrb["positions"]:
        start_price = nrb["grid"]["prices"][position["ticker"]][0]
        assert portfolio_performance.equal_dollar_shares(10_000, start_price) == position["shares"]


def test_equal_dollar_shares_rejects_non_positive_price():
    with pytest.raises(ValueError, match="price must be positive"):
        portfolio_performance.equal_dollar_shares(10_000, 0)


def test_equal_dollar_shares_rejects_non_positive_target_gross():
    with pytest.raises(ValueError, match="target gross must be positive"):
        portfolio_performance.equal_dollar_shares(0, 100.0)


def test_nrb_portfolio_series_matches_workbook_samples():
    nrb = p17_fixture()["nrb"]

    result = nrb_series()

    assert result["dates"] == nrb["grid"]["dates"]
    assert len(result["pnl"]) == len(nrb["grid"]["dates"])
    assert len(result["value"]) == len(nrb["grid"]["dates"])
    samples = nrb["cached_samples"]["first"] + nrb["cached_samples"]["last"]
    for sample in samples:
        index = nrb["grid"]["dates"].index(sample["date"])
        if sample["pnl"] is None:
            assert result["pnl"][index] is None
        else:
            assert result["pnl"][index] == pytest.approx(sample["pnl"], abs=1e-6)
        assert result["value"][index] == pytest.approx(sample["value"], abs=1e-6)


def test_nrb_initial_value_is_gross_exposure_not_signed():
    nrb = p17_fixture()["nrb"]
    first_prices = nrb["grid"]["prices"]

    result = nrb_series()

    gross = sum(
        abs(position["shares"]) * first_prices[position["ticker"]][0]
        for position in nrb["positions"]
    )
    signed = sum(
        position["sign"] * position["shares"] * first_prices[position["ticker"]][0]
        for position in nrb["positions"]
    )
    assert result["value"][0] == pytest.approx(nrb["initial_value"], abs=1e-6)
    assert result["value"][0] == pytest.approx(gross, abs=1e-9)
    assert result["value"][0] != pytest.approx(signed, abs=1e-6)


def test_nrb_weights_are_gross_weights_summing_to_one():
    nrb = p17_fixture()["nrb"]

    result = nrb_series()

    symbols = [position["symbol"] for position in nrb_positions()]
    assert len(result["weights"]) == len(nrb["grid"]["dates"])
    for weights in (result["weights"][0], result["weights"][50], result["weights"][-1]):
        assert set(weights) == set(symbols)
        assert sum(weights.values()) == pytest.approx(1.0)
        assert all(weight > 0 for weight in weights.values())


def test_nrb_portfolio_series_rejects_missing_symbol():
    nrb = p17_fixture()["nrb"]
    prices = {key: value for key, value in nrb["grid"]["prices"].items() if key != "FRPT"}

    with pytest.raises(ValueError, match="missing prices for symbol FRPT"):
        portfolio_performance.nrb_portfolio_series(nrb_positions(), nrb["grid"]["dates"], prices)


def test_nrb_portfolio_series_rejects_misaligned_series():
    nrb = p17_fixture()["nrb"]
    prices = dict(nrb["grid"]["prices"])
    prices["FRPT"] = prices["FRPT"][:-1]

    with pytest.raises(ValueError, match="prices series for FRPT has length 109"):
        portfolio_performance.nrb_portfolio_series(nrb_positions(), nrb["grid"]["dates"], prices)


def test_nrb_portfolio_series_rejects_empty_positions():
    with pytest.raises(ValueError, match="positions are required"):
        portfolio_performance.nrb_portfolio_series([], ["2024-01-02"], {})


def test_nrb_portfolio_series_rejects_invalid_side():
    positions = [{"symbol": "AAA", "shares": 10, "side": 2}]

    with pytest.raises(ValueError, match="position AAA side must be 1 or -1"):
        portfolio_performance.nrb_portfolio_series(
            positions, ["2024-01-02"], {"AAA": [100.0]}
        )


def test_cw_portfolio_series_matches_workbook_samples():
    cw = p17_fixture()["cw"]

    result = portfolio_performance.cw_portfolio_series(
        cw_positions(), cw["grid"]["dates"], cw["grid"]["returns"]
    )

    assert result["dates"] == cw["grid"]["dates"]
    samples = cw["cached_samples"]["first"] + cw["cached_samples"]["last"]
    for sample in samples:
        index = cw["grid"]["dates"].index(sample["date"])
        assert result["portfolio_return"][index] == pytest.approx(
            sample["portfolio_return"], abs=1e-12
        )
        assert result["index"][index] == pytest.approx(sample["index"], abs=1e-6)


def test_cw_portfolio_series_compounds_from_start_index():
    cw = p17_fixture()["cw"]

    result = portfolio_performance.cw_portfolio_series(
        cw_positions(), cw["grid"]["dates"], cw["grid"]["returns"], start_index=50_000
    )

    first_sample = cw["cached_samples"]["first"][0]
    assert result["index"][0] == pytest.approx(
        50_000 * (1 + first_sample["portfolio_return"]), abs=1e-6
    )


def test_cw_portfolio_series_rejects_non_positive_start_index():
    cw = p17_fixture()["cw"]

    with pytest.raises(ValueError, match="start index must be positive"):
        portfolio_performance.cw_portfolio_series(
            cw_positions(), cw["grid"]["dates"], cw["grid"]["returns"], start_index=0
        )


def test_cw_portfolio_series_rejects_missing_symbol():
    cw = p17_fixture()["cw"]
    returns = {key: value for key, value in cw["grid"]["returns"].items() if key != "EIX"}

    with pytest.raises(ValueError, match="missing returns for symbol EIX"):
        portfolio_performance.cw_portfolio_series(cw_positions(), cw["grid"]["dates"], returns)


def test_outperformance_inference_valid_with_equal_gross_weights():
    result = portfolio_performance.outperformance_inference(100_000, 100_000)

    assert result["status"] == "valid"
    assert result["gross_long"] == 100_000
    assert result["gross_short"] == 100_000


def test_outperformance_inference_invalid_with_unequal_gross_weights():
    result = portfolio_performance.outperformance_inference(120_000, 80_000)

    assert result["status"] == "invalid_unequal_gross_weights"
    assert "do not prove longs beat shorts" in result["conclusion"]


@pytest.mark.parametrize("gross_long,gross_short,match", [
    (0, 100_000, "gross long exposure must be positive"),
    (100_000, -5_000, "gross short exposure must be positive"),
])
def test_outperformance_inference_rejects_non_positive_gross(gross_long, gross_short, match):
    with pytest.raises(ValueError, match=match):
        portfolio_performance.outperformance_inference(gross_long, gross_short)
