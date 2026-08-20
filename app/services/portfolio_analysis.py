from app.tools import beta as beta_tool
from app.tools import correlation as correlation_tool
from app.tools import market_data
from app.tools import pair_analysis as pair_analysis_tool
from app.tools import portfolio_gates as gates_tool
from app.tools import portfolio_performance as performance_tool
from app.tools import portfolio_volatility as volatility_tool

BENCHMARK_SYMBOL = "^GSPC"
BETA_WINDOW = 105

_VALID_SIDES = ("long", "short")
_VALID_INSTRUMENTS = ("options", "cfd", "us_stock")
_VALID_BIASES = ("long", "short", "neutral")


def get_ticker_risk_profile(symbol, db_path=None, http_client=None):
    normalized = _normalize_symbol(symbol)
    stock_weekly = _fetch_market_payload(normalized, "1wk", db_path, http_client)
    benchmark_weekly = _fetch_market_payload(BENCHMARK_SYMBOL, "1wk", db_path, http_client)
    stock_daily = _fetch_market_payload(normalized, "1d", db_path, http_client)
    aligned = pair_analysis_tool.align_price_series(
        _price_rows(stock_weekly), _price_rows(benchmark_weekly)
    )
    stock_returns = volatility_tool.simple_returns(aligned["long_close"])
    market_returns = volatility_tool.simple_returns(aligned["short_close"])
    beta = beta_tool.beta_windows(
        list(reversed(stock_returns)), list(reversed(market_returns))
    )
    beta["rolling_beta"] = beta_tool.rolling_beta(
        aligned["dates"][1:], stock_returns, market_returns, window=BETA_WINDOW
    )
    return {
        "symbol": stock_weekly["symbol"],
        "benchmark": BENCHMARK_SYMBOL,
        "beta": beta,
        "realized_volatility": volatility_tool.realized_volatility_report(
            stock_daily["prices"]["adjusted_close"], aligned["long_close"]
        ),
        "data": {
            "weekly_start": aligned["dates"][0],
            "weekly_end": aligned["dates"][-1],
            "weekly_count": len(aligned["dates"]),
        },
    }


def get_portfolio_analysis(payload, db_path=None, http_client=None):
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    positions = _validate_positions(payload.get("positions"))
    _validate_optionals(payload)
    closes_by_symbol, missing_inputs = _fetch_closes(positions, db_path, http_client)
    usable, common_dates = _align_series(positions, closes_by_symbol, missing_inputs)
    returns_by_symbol = _returns_by_symbol(usable, closes_by_symbol, common_dates)
    window = None
    if common_dates:
        window = {
            "start_date": common_dates[0],
            "end_date": common_dates[-1],
            "weekly_count": len(common_dates),
        }
    volatility = _volatility_section(usable, returns_by_symbol)
    correlation = _correlation_section(usable, returns_by_symbol)
    beta = _beta_section(usable, closes_by_symbol)
    return {
        "positions": positions,
        "missing_inputs": missing_inputs,
        "window": window,
        "volatility": volatility,
        "correlation": correlation,
        "beta": beta,
        "gates": _gates_section(payload, positions, volatility, correlation, beta),
        "outperformance_inference": _outperformance_section(positions),
    }


def _fetch_market_payload(symbol, interval, db_path, http_client):
    kwargs = {"interval": interval, "http_client": http_client}
    if db_path is not None:
        kwargs["db_path"] = db_path
    return market_data.fetch_market_data(symbol, **kwargs)


def _normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def _price_rows(payload):
    prices = payload["prices"]
    return [
        {"date": date_value, "adjusted_close": close}
        for date_value, close in zip(prices["dates"], prices["adjusted_close"])
    ]


def _close_by_date(payload):
    return {
        row["date"]: row["adjusted_close"] for row in _price_rows(payload)
    }


def _validate_positions(positions):
    if not isinstance(positions, list) or not positions:
        raise ValueError("positions must be a non-empty list")
    validated = []
    seen = set()
    for position in positions:
        if not isinstance(position, dict):
            raise ValueError("each position must be a dict")
        symbol = str(position.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("position symbol is required")
        if symbol in seen:
            raise ValueError(f"position symbol {symbol} is duplicated")
        seen.add(symbol)
        side = position.get("side")
        if side not in _VALID_SIDES:
            raise ValueError(f"position {symbol} side must be long or short, got {side}")
        allocation = position.get("allocation")
        if (
            not isinstance(allocation, (int, float))
            or isinstance(allocation, bool)
            or allocation <= 0
        ):
            raise ValueError(
                f"position {symbol} allocation must be positive, got {allocation}"
            )
        validated.append(
            {
                "symbol": symbol,
                "side": 1 if side == "long" else -1,
                "allocation": float(allocation),
            }
        )
    return validated


def _validate_optionals(payload):
    margin_capital = payload.get("margin_capital")
    if margin_capital is not None and (
        not isinstance(margin_capital, (int, float))
        or isinstance(margin_capital, bool)
        or margin_capital <= 0
    ):
        raise ValueError(f"margin_capital must be positive, got {margin_capital}")
    declared_bias = payload.get("declared_bias")
    if declared_bias is not None and declared_bias not in _VALID_BIASES:
        raise ValueError(f"unknown declared bias {declared_bias}")
    instrument = payload.get("instrument")
    if instrument is not None and instrument not in _VALID_INSTRUMENTS:
        raise ValueError(f"unknown instrument {instrument}")


def _fetch_closes(positions, db_path, http_client):
    closes_by_symbol = {}
    missing = []
    for position in positions:
        symbol = position["symbol"]
        try:
            payload = _fetch_market_payload(symbol, "1wk", db_path, http_client)
        except ValueError as exc:
            missing.append({"symbol": symbol, "reason": str(exc)})
            continue
        closes_by_symbol[symbol] = _close_by_date(payload)
    benchmark_payload = _fetch_market_payload(BENCHMARK_SYMBOL, "1wk", db_path, http_client)
    closes_by_symbol[BENCHMARK_SYMBOL] = _close_by_date(benchmark_payload)
    return closes_by_symbol, missing


def _align_series(positions, closes_by_symbol, missing):
    common = set(closes_by_symbol[BENCHMARK_SYMBOL])
    usable = []
    for position in positions:
        symbol = position["symbol"]
        if symbol not in closes_by_symbol:
            continue
        candidate = common & set(closes_by_symbol[symbol])
        if len(candidate) < 2:
            missing.append(
                {"symbol": symbol, "reason": "fewer than 2 common weekly sessions"}
            )
            continue
        common = candidate
        usable.append(position)
    if not usable:
        return usable, []
    return usable, sorted(common)


def _returns_by_symbol(usable, closes_by_symbol, common_dates):
    if len(common_dates) < 3:
        return {}
    symbols = [position["symbol"] for position in usable] + [BENCHMARK_SYMBOL]
    return {
        symbol: volatility_tool.simple_returns(
            [closes_by_symbol[symbol][date_value] for date_value in common_dates]
        )
        for symbol in symbols
    }


def _section_unavailable_reason(usable, returns_by_symbol):
    if len(usable) < 2:
        return "fewer than 2 usable positions"
    if not returns_by_symbol:
        return "fewer than 2 weekly returns in the common window"
    return None


def _volatility_section(usable, returns_by_symbol):
    reason = _section_unavailable_reason(usable, returns_by_symbol)
    if reason:
        return {"status": "insufficient_data", "reason": reason}
    signed = [
        {
            "symbol": position["symbol"],
            "side": position["side"],
            "allocation": position["side"] * position["allocation"],
        }
        for position in usable
    ]
    report = volatility_tool.portfolio_volatility_report(signed, returns_by_symbol)
    report["position_count_check"] = volatility_tool.position_count_check(len(usable))
    return {"status": "ok", **report}


def _correlation_section(usable, returns_by_symbol):
    reason = _section_unavailable_reason(usable, returns_by_symbol)
    if reason:
        return {"status": "insufficient_data", "reason": reason}
    report = correlation_tool.signed_correlation_matrix(usable, returns_by_symbol)
    return {"status": "ok", **report}


def _beta_positions(positions):
    return [
        {
            "symbol": position["symbol"],
            "side": position["side"],
            "beta": position["beta"],
            "price": position["allocation"],
            "shares": 1,
        }
        for position in positions
    ]


def _position_beta_entry(position, closes_by_symbol):
    symbol = position["symbol"]
    stock_closes = closes_by_symbol[symbol]
    benchmark_closes = closes_by_symbol[BENCHMARK_SYMBOL]
    dates = sorted(set(stock_closes) & set(benchmark_closes))
    if len(dates) < 3:
        return {
            "window": BETA_WINDOW,
            "label": "2y",
            "status": "insufficient_data",
            "beta": None,
            "standard_error": None,
            "sample_size": max(len(dates) - 1, 0),
        }
    stock_returns = volatility_tool.simple_returns([stock_closes[d] for d in dates])
    market_returns = volatility_tool.simple_returns([benchmark_closes[d] for d in dates])
    windows = beta_tool.beta_windows(
        list(reversed(stock_returns)), list(reversed(market_returns))
    )["windows"]
    return next(item for item in windows if item["window"] == BETA_WINDOW)


def _beta_section(usable, closes_by_symbol):
    if len(usable) < 2:
        return {"status": "insufficient_data", "reason": "fewer than 2 usable positions"}
    per_position = []
    beta_ready = []
    for position in usable:
        entry = _position_beta_entry(position, closes_by_symbol)
        per_position.append(
            {"symbol": position["symbol"], "side": position["side"], **entry}
        )
        if entry["status"] == "ok":
            beta_ready.append({**position, "beta": entry["beta"]})
    section = {
        "status": "ok",
        "window": BETA_WINDOW,
        "per_position": per_position,
        "excluded_from_portfolio": [
            item["symbol"] for item in per_position if item["status"] != "ok"
        ],
    }
    if not beta_ready:
        section["status"] = "insufficient_data"
        section["reason"] = "no position has a computable 2y beta"
        section["portfolio"] = None
        section["sizing"] = None
        return section
    portfolio = beta_tool.portfolio_beta(_beta_positions(beta_ready))
    section["portfolio"] = portfolio
    if any(position["beta"] <= 0 for position in beta_ready):
        section["sizing"] = {
            "status": "skipped",
            "reason": "sizing scenarios require positive betas",
        }
    else:
        section["sizing"] = beta_tool.sizing_scenarios(
            _beta_positions(beta_ready), portfolio["gross_exposure"]
        )
    return section


def _gates_section(payload, positions, volatility, correlation, beta):
    gates = {}
    margin_capital = payload.get("margin_capital")
    if margin_capital is None:
        gates["position_count"] = {
            "status": "unknown",
            "reason": "margin_capital not provided",
        }
    else:
        gates["position_count"] = gates_tool.position_count_tier(
            margin_capital, len(positions)
        )
    if volatility.get("status") == "ok":
        gates["volatility"] = gates_tool.volatility_gate(volatility["annualized_stdev"])
    else:
        gates["volatility"] = {
            "status": "unknown",
            "reason": "portfolio volatility unavailable",
        }
    if correlation.get("status") == "ok":
        gates["correlation"] = gates_tool.correlation_gate(correlation["overall_average"])
    else:
        gates["correlation"] = {
            "status": "unknown",
            "reason": "portfolio correlation unavailable",
        }
    portfolio_beta = beta.get("portfolio")
    if portfolio_beta:
        gates["net_beta"] = gates_tool.net_beta_gate(portfolio_beta["portfolio_beta"])
    else:
        gates["net_beta"] = {"status": "unknown", "reason": "portfolio beta unavailable"}
    instrument = payload.get("instrument")
    if instrument is not None:
        if volatility.get("status") == "ok":
            gates["return_targets"] = gates_tool.return_targets(
                instrument, volatility["annualized_stdev"]
            )
        else:
            gates["return_targets"] = {
                "status": "unknown",
                "reason": "portfolio volatility unavailable",
            }
    declared_bias = payload.get("declared_bias")
    if declared_bias is not None:
        if portfolio_beta:
            gates["beta_macro_alignment"] = gates_tool.beta_macro_alignment(
                portfolio_beta["portfolio_beta"], declared_bias
            )
        else:
            gates["beta_macro_alignment"] = {
                "status": "unknown",
                "reason": "portfolio beta unavailable",
            }
    return gates


def _outperformance_section(positions):
    gross_long = sum(
        position["allocation"] for position in positions if position["side"] == 1
    )
    gross_short = sum(
        position["allocation"] for position in positions if position["side"] == -1
    )
    if gross_long <= 0 or gross_short <= 0:
        return {
            "status": "insufficient_data",
            "reason": "both long and short gross exposure are required",
            "gross_long": gross_long,
            "gross_short": gross_short,
        }
    return performance_tool.outperformance_inference(gross_long, gross_short)
