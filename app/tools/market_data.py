import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta

from app.db import market_data as market_data_db
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


def _today_iso():
    return datetime.now(UTC).date().isoformat()


def _tomorrow_iso(today_date):
    return (date.fromisoformat(today_date) + timedelta(days=1)).isoformat()


def _payload_from_cached_rows(symbol, rows):
    adjusted_close = [row["adjusted_close"] for row in rows]
    dates = [row["date"] for row in rows]
    price = adjusted_close[-1] if adjusted_close else None
    return {
        "symbol": symbol,
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


def fetch_market_data(
    symbol,
    period="max",
    interval="1d",
    fetch_json=None,
    db_path=market_data_db.DEFAULT_DB_PATH,
    today_date=None,
    refresh_days=1,
    overlap_days=5,
):
    normalized_symbol = _normalize_symbol(symbol)
    effective_today = today_date or _today_iso()
    con = market_data_db.connect(db_path)
    try:
        latest_date = market_data_db.latest_price_date(con, normalized_symbol, interval)
        if market_data_db.should_refresh_prices(
            latest_date,
            effective_today,
            refresh_days=refresh_days,
        ):
            if fetch_json:
                try:
                    payload = fetch_json(normalized_symbol, period, interval)
                except HTTPError as exc:
                    raise ValueError(
                        f"market data fetch failed for {normalized_symbol}: HTTP {exc.code} {exc.reason}"
                    ) from exc
                except URLError as exc:
                    raise ValueError(
                        f"market data fetch failed for {normalized_symbol}: {exc.reason}"
                    ) from exc
            else:
                start_date = market_data_db.fetch_start_date(
                    latest_date,
                    effective_today,
                    overlap_days=overlap_days,
                )
                payload = fetch_yahoo_chart_json_for_dates(
                    normalized_symbol,
                    start_date=start_date,
                    end_date=_tomorrow_iso(effective_today),
                    interval=interval,
                )
            rows = chart_payload_to_price_rows(payload, normalized_symbol)
            market_data_db.save_price_rows(con, normalized_symbol, interval, rows)
        rows = market_data_db.load_price_rows(con, normalized_symbol, interval)
    finally:
        con.close()
    if not rows:
        raise ValueError(f"market data is missing for {normalized_symbol}")
    return _payload_from_cached_rows(normalized_symbol, rows)


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


def _date_to_timestamp(date_value):
    parsed = date.fromisoformat(date_value)
    return int(datetime.combine(parsed, time.min, tzinfo=UTC).timestamp())


def fetch_yahoo_chart_json_for_dates(symbol, start_date, end_date, interval):
    normalized_symbol = _normalize_symbol(symbol)
    query = urlencode(
        {
            "period1": _date_to_timestamp(start_date),
            "period2": _date_to_timestamp(end_date),
            "interval": interval,
            "events": "history",
        }
    )
    url = f"{_YAHOO_CHART_URL.format(symbol=normalized_symbol)}?{query}"
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
            f"market data fetch failed for {normalized_symbol}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except URLError as exc:
        raise ValueError(
            f"market data fetch failed for {normalized_symbol}: {exc.reason}"
        ) from exc


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
