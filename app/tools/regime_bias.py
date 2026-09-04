REGIME_BIAS_VERSION = "regime_bias_v1"

_DIRECTION_TO_REGIME = {
    "rising": "expansion",
    "improving": "expansion",
    "slowing": "contraction",
    "falling": "contraction",
    "stable": "neutral",
}


def regime_bias_from_gdp_direction(expected_gdp_direction):
    value = str(expected_gdp_direction or "").strip().lower()
    return _DIRECTION_TO_REGIME.get(value, "unknown")
