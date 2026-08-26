import json
import re

import httpx

from app.http_client import HttpClient


_UNIVERSE_URL = "https://stockanalysis.com/stocks/screener/__data.json"
_FORECAST_URL = "https://stockanalysis.com/stocks/{symbol}/forecast/"
_FETCH_ATTEMPTS = 3
_FETCH_TIMEOUT_SECONDS = 45

_REQUIRED_UNIVERSE_KEYS = {"s", "n", "marketCap", "price", "industry"}

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
