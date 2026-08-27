_ROLLING_BETA_POINTS = 26
_PAIR_SERIES_POINTS = 60

_BETA_WINDOW_KEYS = ("label", "status", "beta", "standard_error", "sample_size")

_CONTEXT_KEYS = (
    "symbol",
    "company_name",
    "status",
    "sector",
    "industry_group",
    "industry",
    "cycle_tag",
    "regime_bias",
    "side_support",
    "regime_note",
)


def compact_portfolio_result(operation, payload):
    if operation == "ticker_risk_profile":
        return compact_ticker_risk(payload)
    if operation == "portfolio_analysis":
        return compact_portfolio_analysis(payload)
    if operation == "pair_analysis":
        return compact_pair_analysis(payload)
    if operation == "ticker_industry_context":
        return compact_ticker_context(payload)
    if operation == "ticker_quant_context":
        return compact_ticker_quant(payload)
    raise ValueError(f"unknown portfolio operation: {operation}")


def compact_ticker_risk(payload):
    beta = payload["beta"]
    return {
        "symbol": payload["symbol"],
        "benchmark": payload["benchmark"],
        "beta": {
            "windows": [
                {key: entry.get(key) for key in _BETA_WINDOW_KEYS}
                for entry in beta["windows"]
            ],
            "rolling_beta": beta["rolling_beta"][-_ROLLING_BETA_POINTS:],
        },
        "realized_volatility": {
            horizon: _volatility_entry(entry)
            for horizon, entry in payload["realized_volatility"].items()
        },
        "data": payload["data"],
    }


def _volatility_entry(entry):
    compacted = {
        "annualized": entry.get("annualized"),
        "sample_size": entry.get("sample_size"),
    }
    if entry.get("status") is not None:
        compacted["status"] = entry["status"]
    if entry.get("required") is not None:
        compacted["required"] = entry["required"]
    return compacted


def compact_portfolio_analysis(payload):
    return {
        "positions": payload["positions"],
        "missing_inputs": payload["missing_inputs"],
        "window": payload["window"],
        "volatility": _volatility_section(payload["volatility"]),
        "correlation": _correlation_section(payload["correlation"]),
        "beta": _beta_section(payload["beta"]),
        "gates": payload["gates"],
        "outperformance_inference": payload["outperformance_inference"],
    }


def _volatility_section(section):
    if section.get("status") != "ok":
        return {"status": section["status"], "reason": section.get("reason")}
    return {
        "status": "ok",
        "gross_exposure": section["gross_exposure"],
        "weekly_stdev": section["weekly_stdev"],
        "annualized_stdev": section["annualized_stdev"],
        "average_asset_weekly_stdev": section["average_asset_weekly_stdev"],
        "average_asset_annualized_stdev": section["average_asset_annualized_stdev"],
        "sharpe_scenarios": section["sharpe_scenarios"],
        "position_count_check": section["position_count_check"],
    }


def _correlation_section(section):
    if section.get("status") != "ok":
        return {"status": section["status"], "reason": section.get("reason")}
    return {
        "status": "ok",
        "overall_average": section["overall_average"],
        "per_position_average": [
            {"symbol": symbol, "average_correlation": average}
            for symbol, average in zip(
                section["symbols"], section["per_position_average"]
            )
        ],
        "disclaimer": section["disclaimer"],
    }


def _beta_section(section):
    compacted = {"status": section["status"]}
    if section.get("reason") is not None:
        compacted["reason"] = section["reason"]
    if "window" in section:
        compacted["window"] = section["window"]
    if "per_position" in section:
        compacted["per_position"] = section["per_position"]
    if "excluded_from_portfolio" in section:
        compacted["excluded_from_portfolio"] = section["excluded_from_portfolio"]
    portfolio = section.get("portfolio")
    if portfolio:
        compacted["portfolio"] = {
            "portfolio_beta": portfolio["portfolio_beta"],
            "net_weight": portfolio["net_weight"],
            "gross_exposure": portfolio["gross_exposure"],
        }
    sizing = section.get("sizing")
    if sizing:
        compacted["sizing"] = _sizing_scenarios(sizing)
    return compacted


def _sizing_scenarios(sizing):
    if "status" in sizing:
        return sizing
    return {
        name: {
            "positions": [
                {"symbol": position["symbol"], "weight": position["weight"]}
                for position in scenario["positions"]
            ],
            "note": scenario["note"],
        }
        for name, scenario in sizing.items()
    }


def compact_pair_analysis(payload):
    series = payload["series"]
    return {
        "long": compact_ticker_context(payload["long"]),
        "short": compact_ticker_context(payload["short"]),
        "pair": payload["pair"],
        "window": payload["window"],
        "outperformance": payload["outperformance"],
        "series": {
            "dates": series["dates"][-_PAIR_SERIES_POINTS:],
            "ratio": series["ratio"][-_PAIR_SERIES_POINTS:],
            "spread": _series_summary(series["spread"]),
            "cew_index": _series_summary(series["cew_index"]),
        },
    }


def _series_summary(values):
    return {
        "first": values[0],
        "last": values[-1],
        "min": min(values),
        "max": max(values),
    }


def compact_ticker_context(payload):
    return {key: payload.get(key) for key in _CONTEXT_KEYS}


def compact_ticker_quant(payload):
    return {
        "symbol": payload["symbol"],
        "fetched_at": payload.get("fetched_at"),
        "cache": payload.get("cache"),
        "provider": payload.get("provider"),
        "valuation": payload.get("valuation", {}),
        "peer": payload.get("peer"),
        "short_checks": payload.get("short_checks", {}),
        "backward_ratios": payload.get("backward_ratios", {}),
    }
