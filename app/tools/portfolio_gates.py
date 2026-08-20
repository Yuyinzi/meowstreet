_SOURCE = "P21"

VOL_TARGET_MIN = 0.15
VOL_TARGET_MAX = 0.30
VOL_REALISTIC_MAX = 0.225
CORRELATION_LIMIT = 0.3
NET_BETA_LIMIT = 0.30

_POSITION_COUNT_TIERS = (
    {"min_capital": 25_000, "max_capital": 100_000, "min_positions": 8, "max_positions": 12},
    {"min_capital": 250_000, "max_capital": 1_000_000, "min_positions": 10, "max_positions": 14},
    {"min_capital": 2_000_000, "max_capital": 5_000_000, "min_positions": 12, "max_positions": 16},
)

_MIN_SHARPE_BY_INSTRUMENT = {"options": 3.3, "cfd": 1.5, "us_stock": 2.0}

_DECLARED_BIASES = {"long", "short", "neutral"}


def position_count_tier(margin_capital, position_count):
    tier = next(
        (
            tier
            for tier in _POSITION_COUNT_TIERS
            if tier["min_capital"] <= margin_capital <= tier["max_capital"]
        ),
        None,
    )
    if tier is None:
        return {
            "status": "unknown",
            "margin_capital": margin_capital,
            "position_count": position_count,
            "tier": None,
            "source": _SOURCE,
        }
    if position_count < tier["min_positions"]:
        status = "below"
    elif position_count > tier["max_positions"]:
        status = "above"
    else:
        status = "within"
    return {
        "status": status,
        "margin_capital": margin_capital,
        "position_count": position_count,
        "tier": tier,
        "source": _SOURCE,
    }


def volatility_gate(annual_vol):
    if annual_vol < VOL_TARGET_MIN:
        status = "below"
    elif annual_vol > VOL_TARGET_MAX:
        status = "above"
    else:
        status = "within"
    return {
        "status": status,
        "annual_vol": annual_vol,
        "target_band": {"min": VOL_TARGET_MIN, "max": VOL_TARGET_MAX},
        "realistic_band": VOL_TARGET_MIN <= annual_vol <= VOL_REALISTIC_MAX,
        "source": _SOURCE,
    }


def correlation_gate(avg_correlation):
    return {
        "status": "within" if abs(avg_correlation) <= CORRELATION_LIMIT else "outside",
        "avg_correlation": avg_correlation,
        "limit": CORRELATION_LIMIT,
        "source": _SOURCE,
    }


def net_beta_gate(portfolio_beta):
    return {
        "status": "within" if abs(portfolio_beta) <= NET_BETA_LIMIT else "outside",
        "portfolio_beta": portfolio_beta,
        "limit": NET_BETA_LIMIT,
        "source": _SOURCE,
    }


def return_targets(instrument, annual_vol):
    if instrument not in _MIN_SHARPE_BY_INSTRUMENT:
        raise ValueError(f"unknown instrument {instrument}")
    min_sharpe = _MIN_SHARPE_BY_INSTRUMENT[instrument]
    return {
        "instrument": instrument,
        "annual_vol": annual_vol,
        "min_sharpe": min_sharpe,
        "expected_return": min_sharpe * annual_vol,
        "source": _SOURCE,
    }


def beta_macro_alignment(portfolio_beta, declared_bias):
    if declared_bias is None:
        return {
            "status": "unknown",
            "portfolio_beta": portfolio_beta,
            "declared_bias": None,
            "source": _SOURCE,
        }
    if declared_bias not in _DECLARED_BIASES:
        raise ValueError(f"unknown declared bias {declared_bias}")
    if declared_bias == "neutral":
        aligned = abs(portfolio_beta) <= NET_BETA_LIMIT
    elif declared_bias == "long":
        aligned = portfolio_beta > 0
    else:
        aligned = portfolio_beta < 0
    return {
        "status": "aligned" if aligned else "conflicting",
        "portfolio_beta": portfolio_beta,
        "declared_bias": declared_bias,
        "source": _SOURCE,
    }
