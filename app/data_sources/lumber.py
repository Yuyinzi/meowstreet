from datetime import UTC, datetime

from app.tools import market_data

_LUMBER_SERIES_ID = "lumber_cme_lbr_yahoo_v1"
_LUMBER_SYMBOL = "LBR=F"
_LUMBER_START_DATE = "2022-08-08"
YAHOO_CHART_SOURCE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/LBR%3DF"

_LUMBER_SOURCE_CONTRACT = {
    "instrument": "CME Lumber Futures",
    "product_code": "LBR",
    "symbol": "LBR=F",
    "source_publisher": "Yahoo Finance",
    "access_adapter": "app.tools.market_data",
    "series_type": "vendor_continuous_or_front_contract",
    "roll_rule": "undocumented",
    "price_field": "close",
    "price_adjustment": "none",
    "official_settlement": False,
    "distribution_window_start": "2022-08-08",
}

_LUMBER_SERIES = {
    "series_id": _LUMBER_SERIES_ID,
    "title": "Lumber (CME LBR)",
    "units": "USD/1,000 board feet",
    "source": "yahoo_finance",
    "source_class": "vendor_free_market_data",
    "source_url": YAHOO_CHART_SOURCE_URL,
    "source_identifier": _LUMBER_SYMBOL,
    "source_contract": _LUMBER_SOURCE_CONTRACT,
}


def _chart_result(payload, symbol):
    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError(f"chart result is missing for {symbol}")
    return results[0]


def _quote_closes(result, symbol):
    indicators = result.get("indicators") if isinstance(result, dict) else None
    quote_blocks = indicators.get("quote") if isinstance(indicators, dict) else None
    if not isinstance(quote_blocks, list) or not quote_blocks:
        raise ValueError(f"close data is missing for {symbol}")
    return quote_blocks[0].get("close")


def _utc_date(timestamp):
    return datetime.fromtimestamp(timestamp, UTC).date().isoformat()


def normalize_lumber_chart(payload, retrieved_at):
    result = _chart_result(payload, _LUMBER_SYMBOL)
    timestamps = result.get("timestamp") or []
    closes = _quote_closes(result, _LUMBER_SYMBOL) or []
    if len(timestamps) != len(closes):
        raise ValueError(
            f"price dates and close lengths differ for {_LUMBER_SYMBOL}"
        )
    observations = []
    for timestamp, close in zip(timestamps, closes):
        day = _utc_date(timestamp)
        if day < _LUMBER_START_DATE:
            raise ValueError(
                f"lumber chart row for {day} is before {_LUMBER_START_DATE} for {_LUMBER_SYMBOL}"
            )
        if close is None:
            continue
        observations.append(
            {
                "date": day,
                "value": float(close),
                "source": "yahoo_finance",
                "source_url": YAHOO_CHART_SOURCE_URL,
                "source_identifier": _LUMBER_SYMBOL,
                "source_class": "vendor_free_market_data",
                "retrieved_at": retrieved_at,
            }
        )
    if not observations:
        raise ValueError(f"close data is missing for {_LUMBER_SYMBOL}")
    return observations


def _default_lumber_chart_fetcher(symbol, start_date, end_date, interval, http_client):
    encoded_symbol = symbol.replace("=", "%3D")
    return market_data.fetch_yahoo_chart_json_for_dates(
        encoded_symbol,
        start_date,
        end_date,
        interval,
        http_client=http_client,
    )


def fetch_lumber_series(start_date, end_date, http_client=None, fetch_chart=None):
    chart_fetcher = fetch_chart or _default_lumber_chart_fetcher
    payload = chart_fetcher(_LUMBER_SYMBOL, start_date, end_date, "1d", http_client)
    retrieved_at = datetime.now(UTC).isoformat()
    return {
        "series": _LUMBER_SERIES,
        "observations": normalize_lumber_chart(payload, retrieved_at),
    }
