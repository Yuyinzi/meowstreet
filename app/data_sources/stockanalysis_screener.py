from datetime import UTC, datetime
import json
import re

import httpx

from app.http_client import HttpClient


_UNIVERSE_URL = "https://stockanalysis.com/stocks/screener/__data.json"
_FORECAST_URL = "https://stockanalysis.com/stocks/{symbol}/forecast/"
_FORECAST_DATA_URL = "https://stockanalysis.com/stocks/{symbol}/forecast/__data.json"
_FETCH_ATTEMPTS = 3
_FETCH_TIMEOUT_SECONDS = 45

_REQUIRED_UNIVERSE_KEYS = {"s", "n", "marketCap", "price", "industry"}
_FORECAST_DATA_ROOT_KEYS = {"estimates", "estimatesCharts", "estimatesSource"}

_EPS_CARD_RE = re.compile(
    r">EPS\s+(?P<card>This Year|Next Year)</div>"
    r".*?class=\"[^\"]*text-2xl\s+font-semibold[^\"]*\"[^>]*>"
    r"(?P<value>[-\d.,]+)"
    r"(?:.*?from\s+(?P<from_value>[-\d.,]+))?"
    , re.DOTALL
)


def _normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def _client(http_client):
    return http_client or HttpClient(max_attempts=_FETCH_ATTEMPTS)


def parse_universe_data(json_text):
    data = json.loads(json_text)
    nodes = data.get("nodes", [])
    array = None
    for node in nodes:
        if node.get("type") == "data" and isinstance(node.get("data"), list):
            candidate = node["data"]
            if any(
                isinstance(item, dict) and _REQUIRED_UNIVERSE_KEYS.issubset(item.keys())
                for item in candidate
            ):
                array = candidate
                break
    if array is None:
        raise ValueError("universe data node not found")
    rows = []
    for index, item in enumerate(array):
        if not isinstance(item, dict):
            continue
        if not _REQUIRED_UNIVERSE_KEYS.issubset(item.keys()):
            continue
        try:
            symbol = array[item["s"]]
            name = array[item["n"]]
            market_cap = array[item["marketCap"]]
            price = array[item["price"]]
            industry = array[item["industry"]]
        except (IndexError, TypeError) as exc:
            raise ValueError(f"universe row at index {index} is malformed") from exc
        if market_cap is None or price is None:
            continue
        try:
            market_cap_float = float(market_cap)
            price_float = float(price)
        except (ValueError, TypeError):
            continue
        rows.append({
            "symbol": str(symbol).strip().upper(),
            "name": str(name).strip(),
            "market_cap": market_cap_float,
            "price": price_float,
            "industry": str(industry).strip(),
        })
    return rows


def fetch_universe(http_client=None):
    client = _client(http_client)
    try:
        response = client.request(
            "GET",
            _UNIVERSE_URL,
            headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
            timeout=_FETCH_TIMEOUT_SECONDS,
            browser=True,
        )
        return parse_universe_data(response.content.decode("utf-8"))
    except httpx.HTTPStatusError as exc:
        if exc.response is not None:
            raise ValueError(
                f"universe fetch failed: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
            ) from exc
        raise ValueError(f"universe fetch failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"universe fetch failed: {exc}") from exc


def _resolve_devalue_value(value, flat_array):
    if isinstance(value, dict):
        return {key: _resolve_devalue_value(item, flat_array) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_devalue_value(item, flat_array) for item in value]
    if not isinstance(value, int):
        return value
    if value < 0 or value >= len(flat_array):
        return None
    resolved = flat_array[value]
    if isinstance(resolved, (dict, list)):
        return _resolve_devalue_value(resolved, flat_array)
    return resolved


def _find_forecast_data_array(nodes):
    for node in nodes:
        if node.get("type") != "data":
            continue
        data = node.get("data")
        if not isinstance(data, list) or len(data) < 2:
            continue
        root = data[0]
        if isinstance(root, dict) and _FORECAST_DATA_ROOT_KEYS.issubset(root.keys()):
            return data
    return None


def parse_forecast_data(json_text, symbol, today=None):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    nodes = data.get("nodes", [])
    flat_array = _find_forecast_data_array(nodes)
    if flat_array is None:
        raise ValueError(f"estimate consensus unavailable for {normalized}")

    root = flat_array[0]
    estimates_charts = _resolve_devalue_value(root.get("estimatesCharts"), flat_array)
    if not isinstance(estimates_charts, dict):
        raise ValueError(f"estimate consensus unavailable for {normalized}")
    eps_charts = estimates_charts.get("eps")
    if not isinstance(eps_charts, dict):
        raise ValueError(f"estimate consensus unavailable for {normalized}")

    if today is None:
        reference = datetime.now(UTC).date()
    elif isinstance(today, str):
        reference = datetime.fromisoformat(today).date()
    elif isinstance(today, datetime):
        reference = today.date()
    else:
        reference = today
    usable = []
    for date_str, value in eps_charts.items():
        if value == "[PRO]":
            continue
        if not isinstance(value, dict):
            continue
        try:
            date = datetime.fromisoformat(date_str).date()
        except (ValueError, TypeError):
            continue
        if date <= reference:
            continue
        usable.append((date, date_str, value))
    if not usable:
        raise ValueError(f"estimate consensus unavailable for {normalized}")

    _, nearest_date_str, nearest = min(usable, key=lambda entry: entry[0])
    no_value = nearest.get("no")
    avg_value = nearest.get("avg")
    low_value = nearest.get("low")
    high_value = nearest.get("high")
    if no_value is None or avg_value is None or low_value is None or high_value is None:
        raise ValueError(f"estimate consensus unavailable for {normalized}")
    return {
        "fiscal_year_end": nearest_date_str,
        "analyst_count": int(no_value),
        "avg": float(avg_value),
        "low": float(low_value),
        "high": float(high_value),
    }


def fetch_forecast_document(symbol, http_client=None):
    normalized = _normalize_symbol(symbol)
    client = _client(http_client)
    url = _FORECAST_DATA_URL.format(symbol=normalized.lower())
    try:
        response = client.request(
            "GET",
            url,
            headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
            timeout=_FETCH_TIMEOUT_SECONDS,
            browser=True,
        )
        return response.content.decode("utf-8")
    except httpx.HTTPStatusError as exc:
        if exc.response is not None:
            raise ValueError(
                f"forecast data fetch failed for {normalized}: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
            ) from exc
        raise ValueError(f"forecast data fetch failed for {normalized}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"forecast data fetch failed for {normalized}: {exc}") from exc


def fetch_estimate_consensus(symbol, http_client=None):
    normalized = _normalize_symbol(symbol)
    return parse_forecast_data(fetch_forecast_document(normalized, http_client=http_client), normalized)


_RATING_COUNT_KEYS = ("strongBuy", "buy", "hold", "sell", "strongSell")


def _parse_price_target(targets):
    if not isinstance(targets, dict):
        return None
    avg = targets.get("avg")
    count = targets.get("numPriceTargets")
    if avg is None or count is None:
        return None
    return {
        "avg": float(avg),
        "median": float(targets["median"]) if targets.get("median") is not None else None,
        "low": float(targets["low"]) if targets.get("low") is not None else None,
        "high": float(targets["high"]) if targets.get("high") is not None else None,
        "count": int(count),
    }


def _parse_monthly_history(recommendations):
    if not isinstance(recommendations, list):
        return []
    entries = []
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        date = item.get("date")
        if date is None:
            continue
        if any(not isinstance(item.get(key), (int, float)) for key in _RATING_COUNT_KEYS):
            continue
        entries.append({
            "date": str(date),
            "strong_buy": int(item["strongBuy"]),
            "buy": int(item["buy"]),
            "hold": int(item["hold"]),
            "sell": int(item["sell"]),
            "strong_sell": int(item["strongSell"]),
            "total": int(item["total"]) if isinstance(item.get("total"), (int, float)) else None,
            "consensus": str(item["consensus"]) if item.get("consensus") else None,
        })
    return entries


def parse_analyst_ratings(json_text, symbol):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    flat_array = _find_forecast_data_array(data.get("nodes", []))
    if flat_array is None:
        raise ValueError(f"analyst ratings unavailable for {normalized}")
    root = flat_array[0]
    ratings = _resolve_devalue_value(root.get("currentRatings"), flat_array)
    if not isinstance(ratings, dict):
        raise ValueError(f"analyst ratings unavailable for {normalized}")
    counts = {key: ratings.get(key) for key in _RATING_COUNT_KEYS}
    analyst_count = ratings.get("count")
    if analyst_count is None or any(not isinstance(value, (int, float)) for value in counts.values()):
        raise ValueError(f"analyst ratings unavailable for {normalized}")
    return {
        "symbol": normalized,
        "consensus": str(ratings["consensus"]) if ratings.get("consensus") else None,
        "score": float(ratings["score"]) if isinstance(ratings.get("score"), (int, float)) else None,
        "analyst_count": int(analyst_count),
        "strong_buy": int(counts["strongBuy"]),
        "buy": int(counts["buy"]),
        "hold": int(counts["hold"]),
        "sell": int(counts["sell"]),
        "strong_sell": int(counts["strongSell"]),
        "price_target": _parse_price_target(_resolve_devalue_value(root.get("priceTargets"), flat_array)),
        "monthly_history": _parse_monthly_history(_resolve_devalue_value(root.get("recommendations"), flat_array)),
        "provider": "stockanalysis",
    }


def fetch_analyst_ratings(symbol, http_client=None):
    normalized = _normalize_symbol(symbol)
    return parse_analyst_ratings(fetch_forecast_document(normalized, http_client=http_client), normalized)


def parse_forecast_html(html, symbol):
    cards = {}
    for match in _EPS_CARD_RE.finditer(html):
        card = match.group("card")
        value = _parse_forecast_number(match.group("value"))
        from_value = _parse_forecast_number(match.group("from_value"))
        cards[card] = {"value": value, "from_value": from_value}
    if not cards:
        raise ValueError(f"forecast estimates unavailable for {symbol}")
    this_year = cards.get("This Year", {})
    next_year = cards.get("Next Year", {})
    return {
        "symbol": symbol,
        "eps_fy0": this_year.get("from_value"),
        "eps_fy1": this_year.get("value"),
        "eps_fy2": next_year.get("value"),
        "provider": "stockanalysis",
    }


def _parse_forecast_number(value):
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_forecast_eps(symbol, http_client=None):
    normalized = _normalize_symbol(symbol)
    client = _client(http_client)
    url = _FORECAST_URL.format(symbol=normalized.lower())
    try:
        response = client.request(
            "GET",
            url,
            headers={"Accept": "text/html", "Accept-Encoding": "gzip, deflate"},
            timeout=_FETCH_TIMEOUT_SECONDS,
            browser=True,
        )
        html = response.content.decode("utf-8")
        return parse_forecast_html(html, normalized)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None:
            raise ValueError(
                f"forecast fetch failed for {normalized}: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
            ) from exc
        raise ValueError(f"forecast fetch failed for {normalized}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"forecast fetch failed for {normalized}: {exc}") from exc
