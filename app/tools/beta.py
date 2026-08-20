import math

DEFAULT_WINDOWS = (105, 157, 261)

SIZING_NOTE = "baseline head check only, not a recommendation"

_WINDOW_LABELS = {105: "2y", 157: "3y", 261: "5y"}
_VALID_SIDES = (1, -1)


def slope(y, x):
    _guard_aligned(y, x)
    x_mean = sum(x) / len(x)
    x_variance = sum((value - x_mean) ** 2 for value in x)
    if x_variance == 0:
        raise ValueError("market returns have zero variance")
    y_mean = sum(y) / len(y)
    covariance = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    return covariance / x_variance


def beta_standard_error(y, x):
    _guard_aligned(y, x)
    if len(y) < 3:
        raise ValueError(f"at least 3 returns are required, got {len(y)}")
    x_mean = sum(x) / len(x)
    x_variance = sum((value - x_mean) ** 2 for value in x)
    if x_variance == 0:
        raise ValueError("market returns have zero variance")
    beta_value = slope(y, x)
    y_mean = sum(y) / len(y)
    intercept = y_mean - beta_value * x_mean
    sse = sum((yi - intercept - beta_value * xi) ** 2 for xi, yi in zip(x, y))
    return math.sqrt(sse / (len(y) - 2) / x_variance)


def beta_windows(stock_returns, market_returns, windows=DEFAULT_WINDOWS):
    _guard_aligned(stock_returns, market_returns)
    return {
        "windows": [
            _window_result(stock_returns, market_returns, window) for window in windows
        ]
    }


def rolling_beta(dates, stock_returns, market_returns, window=105):
    if len(dates) != len(stock_returns):
        raise ValueError(f"dates length {len(dates)} does not match stock returns length {len(stock_returns)}")
    _guard_aligned(stock_returns, market_returns)
    if window < 2:
        raise ValueError(f"window {window} is too small")
    return [
        {
            "end_date": dates[index + window - 1],
            "beta": slope(
                stock_returns[index : index + window],
                market_returns[index : index + window],
            ),
        }
        for index in range(0, len(dates) - window + 1)
    ]


def portfolio_beta(positions):
    if not positions:
        raise ValueError("positions are required")
    details = [_position_detail(position) for position in positions]
    gross_exposure = sum(detail["gross_exposure"] for detail in details)
    if gross_exposure <= 0:
        raise ValueError("gross exposure must be positive")
    for detail in details:
        detail["net_weight"] = detail["net_exposure"] / gross_exposure
        detail["net_weighted_beta"] = detail["net_weight"] * detail["beta"]
    net_exposure = sum(detail["net_exposure"] for detail in details)
    return {
        "positions": details,
        "net_exposure": net_exposure,
        "gross_exposure": gross_exposure,
        "net_weight": net_exposure / gross_exposure,
        "portfolio_beta": sum(detail["net_weighted_beta"] for detail in details),
    }


def sizing_scenarios(positions, target_gross):
    if not positions:
        raise ValueError("positions are required")
    if target_gross <= 0:
        raise ValueError(f"target gross must be positive, got {target_gross}")
    for position in positions:
        if position["price"] <= 0:
            raise ValueError(f"position {position['symbol']} price must be positive, got {position['price']}")
    non_positive_beta = [position["symbol"] for position in positions if position["beta"] <= 0]
    if non_positive_beta:
        raise ValueError(f"positions with non-positive beta: {', '.join(non_positive_beta)}")
    return {
        "equal_weight": _equal_weight_scenario(positions, target_gross),
        "risk_parity": _risk_parity_scenario(positions, target_gross),
        "beta_parity": _beta_parity_scenario(positions, target_gross),
    }


def _guard_aligned(y, x):
    if len(y) != len(x):
        raise ValueError(f"series length mismatch {len(y)} != {len(x)}")
    if len(y) < 2:
        raise ValueError(f"at least 2 returns are required, got {len(y)}")


def _window_label(window):
    return _WINDOW_LABELS.get(window, f"{window}w")


def _window_result(stock_returns, market_returns, window):
    if len(stock_returns) < window:
        return {
            "window": window,
            "label": _window_label(window),
            "status": "insufficient_data",
            "beta": None,
            "standard_error": None,
            "sample_size": len(stock_returns),
        }
    y = stock_returns[:window]
    x = market_returns[:window]
    return {
        "window": window,
        "label": _window_label(window),
        "status": "ok",
        "beta": slope(y, x),
        "standard_error": beta_standard_error(y, x),
        "sample_size": window,
    }


def _position_detail(position):
    side = position["side"]
    if side not in _VALID_SIDES:
        raise ValueError(f"position {position['symbol']} side must be 1 or -1, got {side}")
    net_exposure = side * position["shares"] * position["price"]
    return {
        "symbol": position["symbol"],
        "side": side,
        "beta": position["beta"],
        "price": position["price"],
        "shares": position["shares"],
        "net_exposure": net_exposure,
        "gross_exposure": abs(net_exposure),
    }


def _sized_position(position, weight, target_gross):
    return {
        "symbol": position["symbol"],
        "weight": weight,
        "shares": round(weight * target_gross / position["price"]),
    }


def _equal_weight_scenario(positions, target_gross):
    weight = 1 / len(positions)
    return {
        "positions": [_sized_position(position, weight, target_gross) for position in positions],
        "note": SIZING_NOTE,
    }


def _risk_parity_scenario(positions, target_gross):
    inverse_beta_total = sum(1 / position["beta"] for position in positions)
    return {
        "positions": [
            _sized_position(position, (1 / position["beta"]) / inverse_beta_total, target_gross)
            for position in positions
        ],
        "note": SIZING_NOTE,
    }


def _beta_parity_scenario(positions, target_gross):
    side_inverse_totals = {}
    for position in positions:
        side_inverse_totals[position["side"]] = side_inverse_totals.get(position["side"], 0) + 1 / position["beta"]
    return {
        "positions": [
            _sized_position(
                position,
                (1 / position["beta"]) / side_inverse_totals[position["side"]] * 0.5,
                target_gross,
            )
            for position in positions
        ],
        "note": SIZING_NOTE,
    }
