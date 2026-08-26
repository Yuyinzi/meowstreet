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

_FUNDAMENTAL_KEYS = [
    ("forwardPE", "forward_pe"),
    ("forwardEps", "forward_eps"),
    ("trailingEps", "trailing_eps"),
    ("marketCap", "market_cap"),
    ("sharesShort", "shares_short"),
    ("shortRatio", "short_ratio"),
    ("shortPercentOfFloat", "short_percent_of_float"),
    ("dividendYield", "dividend_yield"),
    ("debtToEquity", "debt_to_equity"),
    ("currentRatio", "current_ratio"),
    ("quickRatio", "quick_ratio"),
    ("returnOnEquity", "return_on_equity"),
    ("returnOnAssets", "return_on_assets"),
    ("bookValue", "book_value"),
    ("totalDebt", "total_debt"),
    ("totalCash", "total_cash"),
    ("freeCashflow", "free_cashflow"),
    ("enterpriseValue", "enterprise_value"),
    ("ebitda", "ebitda"),
]

_FUNDAMENTAL_RAW_RE = {
    key: re.compile(
        r'\\?"' + re.escape(key) + r'\\?"\s*:\s*\\?\{\s*\\?"raw\\?"\s*:\s*(-?[\d.eE+]+)'
    )
    for key, _ in _FUNDAMENTAL_KEYS
}


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


def _extract_raw_float(html, regex):
    match = regex.search(html)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_quote_fundamentals(html):
    fundamentals = {"provider": "yahoo"}
    for key, field_name in _FUNDAMENTAL_KEYS:
        fundamentals[field_name] = _extract_raw_float(html, _FUNDAMENTAL_RAW_RE[key])
    return fundamentals


def fetch_quote_fundamentals(symbol, http_client=None):
    normalized = _normalize_symbol(symbol)
    html = _fetch_quote_page_html(normalized, http_client=http_client)
    fundamentals = parse_quote_fundamentals(html)
    values = [value for key, value in fundamentals.items() if key != "provider"]
    if all(value is None for value in values):
        raise ValueError(f"quote fundamentals unavailable for {normalized}")
    return fundamentals
