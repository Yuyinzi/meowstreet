import pytest

from app.tools import regime_bias


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("rising", "expansion"),
        ("improving", "expansion"),
        ("slowing", "contraction"),
        ("falling", "contraction"),
        ("stable", "neutral"),
        ("mixed", "unknown"),
        (None, "unknown"),
        ("", "unknown"),
        ("rebound_risk", "unknown"),
        ("sideways", "unknown"),
    ],
)
def test_regime_bias_mapping(direction, expected):
    assert regime_bias.regime_bias_from_gdp_direction(direction) == expected


def test_regime_bias_is_deterministic():
    first = regime_bias.regime_bias_from_gdp_direction("slowing")
    second = regime_bias.regime_bias_from_gdp_direction("slowing")

    assert first == second == "contraction"


def test_regime_bias_normalizes_case_and_whitespace():
    assert regime_bias.regime_bias_from_gdp_direction(" Rising ") == "expansion"
