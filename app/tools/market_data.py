import argparse
import json
import sys
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def _fetch_yahoo_chart_json(symbol, period, interval):
    query = urlencode({"range": period, "interval": interval})
    url = f"{_YAHOO_CHART_URL.format(symbol=symbol)}?{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValueError(
            f"market data fetch failed for {symbol}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except URLError as exc:
        raise ValueError(f"market data fetch failed for {symbol}: {exc.reason}") from exc


def _chart_result(payload, symbol):
    chart = payload.get("chart") if isinstance(payload, dict) else None
    error = chart.get("error") if isinstance(chart, dict) else None
    if error:
        description = error.get("description") or error.get("code") or "unknown error"
        raise ValueError(f"market data fetch failed for {symbol}: {description}")
    results = chart.get("result") if isinstance(chart, dict) else None
    if not results:
        raise ValueError(f"market data is missing for {symbol}")
    return results[0]


def _dates_from_timestamps(timestamps):
    return [
        datetime.fromtimestamp(timestamp, UTC).date().isoformat()
        for timestamp in timestamps
    ]


def _adjusted_close_values(result, symbol):
    indicators = result.get("indicators") if isinstance(result, dict) else None
    adjusted_close_blocks = (
        indicators.get("adjclose") if isinstance(indicators, dict) else None
    )
    if not adjusted_close_blocks:
        raise ValueError(f"adjusted close data is missing for {symbol}")
    values = adjusted_close_blocks[0].get("adjclose")
    if not values:
        raise ValueError(f"adjusted close data is missing for {symbol}")
    return values


def _has_required_market_data(price, dates, adjusted_close):
    return price is not None and bool(dates) and bool(adjusted_close)


def fetch_market_data(symbol, period="1y", interval="1d", fetch_json=None):
    normalized_symbol = _normalize_symbol(symbol)
    fetcher = fetch_json or _fetch_yahoo_chart_json
    try:
        payload = fetcher(normalized_symbol, period, interval)
    except HTTPError as exc:
        raise ValueError(
            f"market data fetch failed for {normalized_symbol}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except URLError as exc:
        raise ValueError(
            f"market data fetch failed for {normalized_symbol}: {exc.reason}"
        ) from exc
    result = _chart_result(payload, normalized_symbol)
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    timestamps = result.get("timestamp") or []
    adjusted_close = _adjusted_close_values(result, normalized_symbol)
    dates = _dates_from_timestamps(timestamps)
    if len(dates) != len(adjusted_close):
        raise ValueError(f"price dates and adjusted close lengths differ for {normalized_symbol}")
    return {
        "symbol": normalized_symbol,
        "metrics": {
            "price": price,
        },
        "prices": {
            "dates": dates,
            "adjusted_close": adjusted_close,
        },
        "data": {
            "price_series_current": bool(dates),
            "uses_adjusted_close": True,
            "no_missing_required_fields": _has_required_market_data(
                price,
                dates,
                adjusted_close,
            ),
        },
    }


def _quote_values(result, key):
    indicators = result.get("indicators") if isinstance(result, dict) else None
    quote_blocks = indicators.get("quote") if isinstance(indicators, dict) else None
    if not quote_blocks:
        return []
    values = quote_blocks[0].get(key)
    return values or []


def _value_at(values, index):
    return values[index] if index < len(values) else None


def chart_payload_to_price_rows(payload, symbol):
    normalized_symbol = _normalize_symbol(symbol)
    result = _chart_result(payload, normalized_symbol)
    timestamps = result.get("timestamp") or []
    dates = _dates_from_timestamps(timestamps)
    adjusted_close = _adjusted_close_values(result, normalized_symbol)
    if len(dates) != len(adjusted_close):
        raise ValueError(f"price dates and adjusted close lengths differ for {normalized_symbol}")
    opens = _quote_values(result, "open")
    highs = _quote_values(result, "high")
    lows = _quote_values(result, "low")
    closes = _quote_values(result, "close")
    volumes = _quote_values(result, "volume")
    return [
        {
            "date": date_value,
            "open": _value_at(opens, index),
            "high": _value_at(highs, index),
            "low": _value_at(lows, index),
            "close": _value_at(closes, index),
            "adjusted_close": adjusted_close[index],
            "volume": _value_at(volumes, index),
        }
        for index, date_value in enumerate(dates)
        if adjusted_close[index] is not None
    ]


def main(argv=None, fetch_json=None):
    parser = argparse.ArgumentParser(description="Fetch market data for a ticker")
    parser.add_argument("symbol")
    parser.add_argument("--period", default="1y")
    parser.add_argument("--interval", default="1d")
    args = parser.parse_args(argv)
    try:
        payload = fetch_market_data(
            args.symbol,
            period=args.period,
            interval=args.interval,
            fetch_json=fetch_json,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
