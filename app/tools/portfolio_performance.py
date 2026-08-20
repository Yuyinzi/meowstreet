_VALID_SIDES = (1, -1)


def equal_dollar_shares(target_gross, price):
    if target_gross <= 0:
        raise ValueError(f"target gross must be positive, got {target_gross}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    return round(target_gross / price)


def nrb_portfolio_series(positions, dates, prices_by_symbol):
    series = _aligned_series(positions, dates, prices_by_symbol, "prices")
    initial_value = sum(
        abs(position["shares"]) * price_series[0]
        for position, price_series in zip(positions, series)
    )
    pnl = [None]
    value = [initial_value]
    weights = [_gross_weights(positions, series, 0)]
    for index in range(1, len(dates)):
        day_pnl = sum(
            position["shares"] * position["side"] * (price_series[index] - price_series[index - 1])
            for position, price_series in zip(positions, series)
        )
        pnl.append(day_pnl)
        value.append(value[-1] + day_pnl)
        weights.append(_gross_weights(positions, series, index))
    return {"dates": list(dates), "pnl": pnl, "value": value, "weights": weights}


def cw_portfolio_series(positions, dates, returns_by_symbol, start_index=100000):
    if start_index <= 0:
        raise ValueError(f"start index must be positive, got {start_index}")
    series = _aligned_series(positions, dates, returns_by_symbol, "returns")
    portfolio_return = []
    index_values = []
    current_index = start_index
    for index in range(len(dates)):
        day_return = sum(
            position["weight"] * position["side"] * return_series[index]
            for position, return_series in zip(positions, series)
        )
        current_index *= 1 + day_return
        portfolio_return.append(day_return)
        index_values.append(current_index)
    return {"dates": list(dates), "portfolio_return": portfolio_return, "index": index_values}


def outperformance_inference(gross_long, gross_short):
    if gross_long <= 0:
        raise ValueError(f"gross long exposure must be positive, got {gross_long}")
    if gross_short <= 0:
        raise ValueError(f"gross short exposure must be positive, got {gross_short}")
    if gross_long != gross_short:
        return {
            "status": "invalid_unequal_gross_weights",
            "gross_long": gross_long,
            "gross_short": gross_short,
            "conclusion": "portfolio gains do not prove longs beat shorts when gross weights differ",
        }
    return {
        "status": "valid",
        "gross_long": gross_long,
        "gross_short": gross_short,
        "conclusion": "equal gross weights allow comparing long-side and short-side performance",
    }


def _aligned_series(positions, dates, values_by_symbol, label):
    if not positions:
        raise ValueError("positions are required")
    if not dates:
        raise ValueError("dates are required")
    series = []
    for position in positions:
        symbol = position["symbol"]
        if position["side"] not in _VALID_SIDES:
            raise ValueError(f"position {symbol} side must be 1 or -1, got {position['side']}")
        if symbol not in values_by_symbol:
            raise ValueError(f"missing {label} for symbol {symbol}")
        symbol_series = values_by_symbol[symbol]
        if len(symbol_series) != len(dates):
            raise ValueError(
                f"{label} series for {symbol} has length {len(symbol_series)}, expected {len(dates)}"
            )
        series.append(symbol_series)
    return series


def _gross_weights(positions, series, index):
    exposures = [
        abs(position["shares"]) * price_series[index]
        for position, price_series in zip(positions, series)
    ]
    gross = sum(exposures)
    if gross <= 0:
        raise ValueError(f"gross exposure must be positive at index {index}")
    return {
        position["symbol"]: exposure / gross
        for position, exposure in zip(positions, exposures)
    }
