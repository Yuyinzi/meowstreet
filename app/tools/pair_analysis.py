_VALID_PAIR_TYPES = {
    "intra_sector_constituent",
    "cross_sector_constituent",
    "unclassifiable",
}

_RETAINED_RISKS = {
    "intra_sector_constituent": ["stock"],
    "cross_sector_constituent": ["sector", "stock"],
}


def align_price_series(long_rows, short_rows):
    short_by_date = {row["date"]: row["adjusted_close"] for row in short_rows}
    dates, long_close, short_close = [], [], []
    for row in long_rows:
        date_value = row["date"]
        short_value = short_by_date.get(date_value)
        if short_value is None:
            continue
        dates.append(date_value)
        long_close.append(row["adjusted_close"])
        short_close.append(short_value)
    if len(dates) < 2:
        raise ValueError("fewer than 2 common trading sessions between the pair")
    return {"dates": dates, "long_close": long_close, "short_close": short_close}


def ratio_series(aligned):
    return [
        long_value / short_value
        for long_value, short_value in zip(aligned["long_close"], aligned["short_close"])
    ]


def spread_series(aligned):
    return [
        long_value - short_value
        for long_value, short_value in zip(aligned["long_close"], aligned["short_close"])
    ]


def _returns(closes):
    return [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]


def cew_index_series(long_closes, short_closes, start):
    long_returns = _returns(long_closes)
    short_returns = _returns(short_closes)
    index_values = [start]
    for long_return, short_return in zip(long_returns, short_returns):
        index_values.append(
            index_values[-1] * (1 + (long_return - short_return) / 2)
        )
    return index_values


def window_outperformance(aligned, sessions):
    if sessions < 2:
        raise ValueError(f"sessions window {sessions} is too small")
    dates = aligned["dates"][-sessions:]
    long_close = aligned["long_close"][-sessions:]
    short_close = aligned["short_close"][-sessions:]
    if len(dates) < 2:
        raise ValueError("fewer than 2 common trading sessions in the window")
    long_return = long_close[-1] / long_close[0] - 1
    short_return = short_close[-1] / short_close[0] - 1
    return {
        "sessions": len(dates),
        "start_date": dates[0],
        "end_date": dates[-1],
        "long_return": long_return,
        "short_return": short_return,
        "outperformance": long_return - short_return,
    }


def classify_pair(long_context, short_context):
    missing = [
        context["symbol"]
        for context in (long_context, short_context)
        if context.get("status") != "resolved"
    ]
    if missing:
        return {
            "pair_type": "unclassifiable",
            "retained_risks": [],
            "missing": missing,
        }
    if long_context["sector"] == short_context["sector"]:
        pair_type = "intra_sector_constituent"
    else:
        pair_type = "cross_sector_constituent"
    return {
        "pair_type": pair_type,
        "retained_risks": _RETAINED_RISKS[pair_type],
        "missing": [],
    }
