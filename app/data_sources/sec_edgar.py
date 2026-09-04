from datetime import date
import json
import re

import httpx

from app.http_client import HttpClient


_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession_flat}/{document}"
_FETCH_ATTEMPTS = 3
_FETCH_TIMEOUT_SECONDS = 45

_EDGAR_HEADERS = {
    "User-Agent": "Meowstreet/1.0 (local research; contact via repository)",
    "Accept-Encoding": "gzip, deflate",
}

_ITEM_RE = re.compile(r"Item\s+(\d+\.\d\d)", re.IGNORECASE)
_EARNINGS_ITEM = "2.02"


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


def parse_company_tickers(json_text):
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("company tickers payload is malformed")
    result = {}
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        ticker = str(entry.get("ticker") or "").strip().upper()
        cik = entry.get("cik_str")
        title = str(entry.get("title") or "").strip()
        if not ticker or cik is None:
            continue
        result[ticker] = {"cik": int(cik), "title": title}
    if not result:
        raise ValueError("company tickers payload is malformed")
    return result


def fetch_cik_map(http_client=None):
    client = _client(http_client)
    try:
        response = client.request(
            "GET",
            _COMPANY_TICKERS_URL,
            headers=_EDGAR_HEADERS,
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        return parse_company_tickers(response.content.decode("utf-8"))
    except httpx.HTTPError as exc:
        _raise_fetch("company tickers", exc)


def parse_submissions(json_text, symbol, since=None):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    filings = data.get("filings")
    if not isinstance(filings, dict) or not isinstance(filings.get("recent"), dict):
        raise ValueError(f"submissions payload malformed for {normalized}")
    since_date = date.fromisoformat(since) if since else None
    rows = _parse_filing_rows(filings["recent"], since_date)
    older_files = [
        str(entry["name"])
        for entry in filings.get("files", [])
        if isinstance(entry, dict) and entry.get("name")
    ]
    return {"filings": rows, "older_files": older_files}


def _parse_filing_rows(recent, since_date):
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []
    rows = []
    for index, form in enumerate(forms):
        if form != "8-K":
            continue
        try:
            filing_date = date.fromisoformat(dates[index])
        except (ValueError, TypeError, IndexError):
            continue
        if since_date is not None and filing_date < since_date:
            continue
        try:
            accession = accessions[index]
            document = documents[index]
        except IndexError:
            continue
        if not accession or not document:
            continue
        rows.append({
            "accession": str(accession),
            "filing_date": filing_date.isoformat(),
            "primary_document": str(document),
        })
    return rows


def parse_older_submissions(json_text, symbol, since=None):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    if not isinstance(data, dict) or not isinstance(data.get("form"), list):
        raise ValueError(f"older submissions payload malformed for {normalized}")
    since_date = date.fromisoformat(since) if since else None
    return _parse_filing_rows(data, since_date)


def parse_8k_items(html):
    seen = []
    for match in _ITEM_RE.finditer(html):
        item = match.group(1)
        if item not in seen:
            seen.append(item)
    return seen


def is_earnings_filing(items):
    return _EARNINGS_ITEM in items


def fetch_submissions(cik, http_client=None):
    client = _client(http_client)
    url = _SUBMISSIONS_URL.format(cik=str(int(cik)).zfill(10))
    try:
        response = client.request(
            "GET",
            url,
            headers=_EDGAR_HEADERS,
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        return response.content.decode("utf-8")
    except httpx.HTTPError as exc:
        _raise_fetch(f"submissions CIK{cik}", exc)


def fetch_older_submissions(cik, name, http_client=None):
    client = _client(http_client)
    url = f"https://data.sec.gov/submissions/{name}"
    try:
        response = client.request(
            "GET",
            url,
            headers=_EDGAR_HEADERS,
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        return response.content.decode("utf-8")
    except httpx.HTTPError as exc:
        _raise_fetch(f"older submissions {name}", exc)


def fetch_filing_document(cik, accession, document, http_client=None):
    client = _client(http_client)
    url = _FILING_DOC_URL.format(
        cik_number=int(cik),
        accession_flat=str(accession).replace("-", ""),
        document=document,
    )
    try:
        response = client.request(
            "GET",
            url,
            headers=_EDGAR_HEADERS,
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        return response.content.decode("utf-8", errors="replace")
    except httpx.HTTPError as exc:
        _raise_fetch(f"filing {accession}", exc)
