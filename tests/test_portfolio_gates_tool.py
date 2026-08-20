import pytest

from app.tools import portfolio_gates


@pytest.mark.parametrize("margin_capital,position_count,status,min_positions,max_positions", [
    (25_000, 8, "within", 8, 12),
    (25_000, 7, "below", 8, 12),
    (100_000, 12, "within", 8, 12),
    (100_000, 13, "above", 8, 12),
    (250_000, 10, "within", 10, 14),
    (1_000_000, 14, "within", 10, 14),
    (2_000_000, 12, "within", 12, 16),
    (5_000_000, 16, "within", 12, 16),
    (5_000_000, 11, "below", 12, 16),
])
def test_position_count_tier_boundaries(
    margin_capital, position_count, status, min_positions, max_positions
):
    result = portfolio_gates.position_count_tier(margin_capital, position_count)

    assert result["status"] == status
    assert result["tier"]["min_positions"] == min_positions
    assert result["tier"]["max_positions"] == max_positions
    assert result["source"] == "P21"


@pytest.mark.parametrize("margin_capital", [24_999, 100_001, 249_999, 1_000_001, 5_000_001])
def test_position_count_tier_unknown_outside_all_tiers(margin_capital):
    result = portfolio_gates.position_count_tier(margin_capital, 10)

    assert result["status"] == "unknown"
    assert result["tier"] is None


@pytest.mark.parametrize("annual_vol,status,realistic", [
    (0.0, "below", False),
    (0.149, "below", False),
    (0.15, "within", True),
    (0.225, "within", True),
    (0.226, "within", False),
    (0.30, "within", False),
    (0.31, "above", False),
])
def test_volatility_gate_boundaries(annual_vol, status, realistic):
    result = portfolio_gates.volatility_gate(annual_vol)

    assert result["status"] == status
    assert result["realistic_band"] is realistic
    assert result["target_band"] == {"min": 0.15, "max": 0.30}
    assert result["source"] == "P21"


@pytest.mark.parametrize("avg_correlation,status", [
    (0.3, "within"),
    (-0.3, "within"),
    (0.0, "within"),
    (0.31, "outside"),
    (-0.31, "outside"),
])
def test_correlation_gate_boundaries(avg_correlation, status):
    result = portfolio_gates.correlation_gate(avg_correlation)

    assert result["status"] == status
    assert result["source"] == "P21"


@pytest.mark.parametrize("portfolio_beta,status", [
    (0.30, "within"),
    (-0.30, "within"),
    (0.0, "within"),
    (0.31, "outside"),
    (-0.31, "outside"),
])
def test_net_beta_gate_boundaries(portfolio_beta, status):
    result = portfolio_gates.net_beta_gate(portfolio_beta)

    assert result["status"] == status
    assert result["source"] == "P21"


@pytest.mark.parametrize("instrument,min_sharpe", [
    ("options", 3.3),
    ("cfd", 1.5),
    ("us_stock", 2.0),
])
def test_return_targets_scale_with_vol(instrument, min_sharpe):
    result = portfolio_gates.return_targets(instrument, 0.2)

    assert result["min_sharpe"] == min_sharpe
    assert result["expected_return"] == pytest.approx(min_sharpe * 0.2)
    assert result["source"] == "P21"


def test_return_targets_reject_unknown_instrument():
    with pytest.raises(ValueError, match="unknown instrument futures"):
        portfolio_gates.return_targets("futures", 0.2)


@pytest.mark.parametrize("portfolio_beta,declared_bias,status", [
    (0.25, "long", "aligned"),
    (-0.25, "long", "conflicting"),
    (-0.25, "short", "aligned"),
    (0.25, "short", "conflicting"),
    (0.30, "neutral", "aligned"),
    (-0.30, "neutral", "aligned"),
    (0.31, "neutral", "conflicting"),
])
def test_beta_macro_alignment(portfolio_beta, declared_bias, status):
    result = portfolio_gates.beta_macro_alignment(portfolio_beta, declared_bias)

    assert result["status"] == status
    assert result["declared_bias"] == declared_bias
    assert result["source"] == "P21"


def test_beta_macro_alignment_unknown_without_declared_bias():
    result = portfolio_gates.beta_macro_alignment(0.5, None)

    assert result["status"] == "unknown"
    assert result["declared_bias"] is None


def test_beta_macro_alignment_rejects_unknown_bias():
    with pytest.raises(ValueError, match="unknown declared bias sideways"):
        portfolio_gates.beta_macro_alignment(0.1, "sideways")
