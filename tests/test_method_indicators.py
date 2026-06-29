from app import method_indicators


def test_apply_computed_indicators_adds_estimate_midpoint_and_skew():
    observations = {
        "estimates": {
            "next_year_eps_low": 1.0,
            "next_year_eps_high": 2.0,
            "next_year_eps_mean": 1.75,
        }
    }

    result = method_indicators.apply_computed_indicators(observations)

    assert result["estimates"]["next_year_eps_midpoint"] == 1.5
    assert result["estimates"]["next_year_eps_skew"] == 0.25


def test_apply_computed_indicators_adds_pe_differential():
    observations = {
        "valuation": {
            "forward_pe": 30,
            "peer_forward_pe": 20,
        }
    }

    result = method_indicators.apply_computed_indicators(observations)

    assert result["valuation"]["pe_differential"] == 1.5


def test_apply_computed_indicators_adds_abnormal_volume_ratio():
    observations = {
        "volume": {
            "current": 300,
            "average": 100,
        }
    }

    result = method_indicators.apply_computed_indicators(observations)

    assert result["volume"]["abnormal_volume_ratio"] == 3


def test_apply_computed_indicators_skips_missing_or_zero_inputs():
    observations = {
        "valuation": {
            "forward_pe": 30,
            "peer_forward_pe": 0,
        }
    }

    result = method_indicators.apply_computed_indicators(observations)

    assert "pe_differential" not in result["valuation"]
