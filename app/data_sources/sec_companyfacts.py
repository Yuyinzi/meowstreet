import json
from datetime import date

import httpx

from app.data_sources.sec_edgar import _EDGAR_HEADERS
from app.http_client import HttpClient


_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_FETCH_ATTEMPTS = 3
_FETCH_TIMEOUT_SECONDS = 60

_TAG_CHAINS = {
    "ebit": ("OperatingIncomeLoss",),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating", "InterestAndDebtExpense"),
    "assets_current": ("AssetsCurrent",),
    "liabilities_current": ("LiabilitiesCurrent",),
    "assets": ("Assets",),
}

_QUARTERLY_MIN_DAYS = 60
_QUARTERLY_MAX_DAYS = 130
_ANNUAL_MIN_DAYS = 300
_ANNUAL_MAX_DAYS = 400


def _client(http_client):
    return http_client or HttpClient(max_attempts=_FETCH_ATTEMPTS)


def _normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def _raise_fetch(context, exc):
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        raise ValueError(
            f"{context} fetch failed: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
        ) from exc
    raise ValueError(f"{context} fetch failed: {exc}") from exc


def _dedupe_latest(entries, key_fields):
    best = {}
    for entry in entries:
        key = tuple(entry.get(field) for field in key_fields)
        current = best.get(key)
        if current is None or entry["filed"] > current["filed"]:
            best[key] = entry
    return sorted(best.values(), key=lambda item: item["end"], reverse=True)


def _classify_entries(entries):
    quarterly = []
    annual = []
    instants = []
    for entry in entries:
        end = entry.get("end")
        val = entry.get("val")
        filed = entry.get("filed")
        if not end or val is None or not filed:
            continue
        normalized = {
            "end": str(end),
            "val": float(val),
            "filed": str(filed),
            "form": str(entry.get("form") or ""),
        }
        start = entry.get("start")
        if not start:
            instants.append(normalized)
            continue
        try:
            days = (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days
        except ValueError:
            continue
        normalized["start"] = str(start)
        if _QUARTERLY_MIN_DAYS <= days <= _QUARTERLY_MAX_DAYS:
            quarterly.append(normalized)
        elif _ANNUAL_MIN_DAYS <= days <= _ANNUAL_MAX_DAYS:
            annual.append(normalized)
    return {
        "quarterly": _dedupe_latest(quarterly, ("start", "end")),
        "annual": _dedupe_latest(annual, ("start", "end")),
        "instant": _dedupe_latest(instants, ("end",)),
    }


def parse_company_facts(json_text, symbol):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    gaap = data.get("facts", {}).get("us-gaap")
    if not isinstance(gaap, dict):
        raise ValueError(f"companyfacts payload malformed for {normalized}")
    facts = {}
    for key, chain in _TAG_CHAINS.items():
        for tag in chain:
            node = gaap.get(tag)
            if not isinstance(node, dict):
                continue
            units = node.get("units", {}).get("USD")
            if not isinstance(units, list) or not units:
                continue
            facts[key] = {"tag": tag, **_classify_entries(units)}
            break
    if not facts:
        raise ValueError(f"no usable us-gaap facts for {normalized}")
    return {"symbol": normalized, "facts": facts}


def fetch_company_facts(cik, http_client=None):
    client = _client(http_client)
    url = _COMPANYFACTS_URL.format(cik=str(int(cik)).zfill(10))
    try:
        response = client.request(
            "GET",
            url,
            headers=_EDGAR_HEADERS,
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        return response.content.decode("utf-8")
    except httpx.HTTPError as exc:
        _raise_fetch(f"companyfacts CIK{cik}", exc)
