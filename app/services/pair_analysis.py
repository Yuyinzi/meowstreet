from app.services import ticker_industry_context as ticker_context_service
from app.tools import market_data, pair_analysis


MAX_SESSIONS = 260
DEFAULT_SESSIONS = 60


def _normalize_sessions(sessions):
    try:
        value = int(sessions)
    except (TypeError, ValueError):
        raise ValueError(f"sessions {sessions} is not a number") from None
    if value < 2:
        raise ValueError(f"sessions {value} is too small")
    return min(value, MAX_SESSIONS)


def _price_rows(payload):
    prices = payload["prices"]
    return [
        {"date": date_value, "adjusted_close": close}
        for date_value, close in zip(prices["dates"], prices["adjusted_close"])
    ]


def get_pair_analysis(
    long_symbol, short_symbol, sessions=DEFAULT_SESSIONS, db_path=None, http_client=None
):
    window = _normalize_sessions(sessions)
    long_context = ticker_context_service.get_ticker_industry_context(
        long_symbol, db_path=db_path, http_client=http_client
    )
    short_context = ticker_context_service.get_ticker_industry_context(
        short_symbol, db_path=db_path, http_client=http_client
    )
    market_kwargs = {"interval": "1d", "http_client": http_client}
    if db_path is not None:
        market_kwargs["db_path"] = db_path
    long_payload = market_data.fetch_market_data(long_symbol, **market_kwargs)
    short_payload = market_data.fetch_market_data(short_symbol, **market_kwargs)
    aligned = pair_analysis.align_price_series(
        _price_rows(long_payload), _price_rows(short_payload)
    )
    sliced = {
        "dates": aligned["dates"][-window:],
        "long_close": aligned["long_close"][-window:],
        "short_close": aligned["short_close"][-window:],
    }
    ratios = pair_analysis.ratio_series(sliced)
    return {
        "long": long_context,
        "short": short_context,
        "pair": pair_analysis.classify_pair(long_context, short_context),
        "window": {
            "sessions": len(sliced["dates"]),
            "start_date": sliced["dates"][0],
            "end_date": sliced["dates"][-1],
        },
        "outperformance": pair_analysis.window_outperformance(aligned, window),
        "series": {
            "dates": sliced["dates"],
            "ratio": ratios,
            "spread": pair_analysis.spread_series(sliced),
            "cew_index": pair_analysis.cew_index_series(
                sliced["long_close"], sliced["short_close"], ratios[0]
            ),
        },
    }
