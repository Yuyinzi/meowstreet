import re
from html import unescape

import httpx

from app.http_client import HttpClient


_YAHOO_QUOTE_PAGE_URL = "https://finance.yahoo.com/quote/{symbol}/"
_YAHOO_FETCH_ATTEMPTS = 3
_YAHOO_TIMEOUT_SECONDS = 45

_HEADING_RE = re.compile(r'<h1 class="heading[^"]*">(?P<name>.+?)\s*\([A-Z0-9.]+\)</h1>')
_OVERVIEW_FIELD_RE = re.compile(
    r'<p title="(?P<value>[^"]+)"[^>]*><a[^>]*href="/sectors/[^"]+"[^>]*>[^<]*</a></p>'
    r"\s*<h3[^>]*>(?P<label>Sector|Industry)</h3>"
)


def _normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def _fetch_quote_page_html(symbol, http_client=None):
    client = http_client or HttpClient(max_attempts=_YAHOO_FETCH_ATTEMPTS)
    url = _YAHOO_QUOTE_PAGE_URL.format(symbol=symbol)
    try:
        response = client.request(
            "GET",
            url,
            headers={"Accept": "text/html"},
            timeout=_YAHOO_TIMEOUT_SECONDS,
            browser=True,
        )
        return response.content.decode("utf-8")
    except httpx.HTTPStatusError as exc:
        if exc.response is not None:
            raise ValueError(
                f"asset profile fetch failed for {symbol}: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
            ) from exc
        raise ValueError(f"asset profile fetch failed for {symbol}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"asset profile fetch failed for {symbol}: {exc}") from exc


def parse_quote_page_html(html, symbol):
    heading = _HEADING_RE.search(html)
    if heading is None:
        raise ValueError(f"asset profile unavailable for {symbol}")
    fields = {}
    for match in _OVERVIEW_FIELD_RE.finditer(html):
        label = match.group("label").lower()
        fields.setdefault(label, unescape(match.group("value")))
    return {
        "symbol": symbol,
        "company_name": unescape(heading.group("name")),
        "provider": "yahoo",
        "provider_sector": fields.get("sector"),
        "provider_industry": fields.get("industry"),
    }


def fetch_asset_profile(symbol, http_client=None):
    normalized = _normalize_symbol(symbol)
    html = _fetch_quote_page_html(normalized, http_client=http_client)
    return parse_quote_page_html(html, normalized)
