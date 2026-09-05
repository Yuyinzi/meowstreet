from datetime import date
import json
import re
import xml.etree.ElementTree as ET

import httpx

from app.http_client import HttpClient


_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession_flat}/{document}"
_FETCH_ATTEMPTS = 3
_FETCH_TIMEOUT_SECONDS = 45

_EDGAR_HEADERS = {
    "User-Agent": "Meowstreet Research contact@meowstreet.local",
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


def parse_submissions(json_text, symbol, since=None, form="8-K"):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    filings = data.get("filings")
    if not isinstance(filings, dict) or not isinstance(filings.get("recent"), dict):
        raise ValueError(f"submissions payload malformed for {normalized}")
    since_date = date.fromisoformat(since) if since else None
    rows = _parse_filing_rows(filings["recent"], since_date, form)
    older_files = [
        str(entry["name"])
        for entry in filings.get("files", [])
        if isinstance(entry, dict) and entry.get("name")
    ]
    return {"filings": rows, "older_files": older_files}


def _parse_filing_rows(recent, since_date, form):
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []
    rows = []
    for index, row_form in enumerate(forms):
        if row_form != form:
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


def parse_older_submissions(json_text, symbol, since=None, form="8-K"):
    normalized = _normalize_symbol(symbol)
    data = json.loads(json_text)
    if not isinstance(data, dict) or not isinstance(data.get("form"), list):
        raise ValueError(f"older submissions payload malformed for {normalized}")
    since_date = date.fromisoformat(since) if since else None
    return _parse_filing_rows(data, since_date, form)


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


_FORM4_CODE_LABELS = {
    "P": "Open-market purchase",
    "S": "Open-market sale",
    "A": "Grant or award",
    "F": "Tax withholding",
    "M": "Option exercise",
    "G": "Gift",
}


def _xml_value(node, path):
    if node is None:
        return None
    target = node.find(path)
    if target is None:
        return None
    text = (target.text or "").strip()
    return text or None


def _xml_number(node, path):
    text = _xml_value(node, path)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _xml_flag(node, tag):
    text = _xml_value(node, tag)
    return text in ("1", "true")


def _insider_title(relationship):
    if relationship is None:
        return None
    officer_title = _xml_value(relationship, "officerTitle")
    if officer_title:
        return officer_title
    if _xml_flag(relationship, "isDirector"):
        return "Director"
    if _xml_flag(relationship, "isTenPercentOwner"):
        return "10% owner"
    return None


def parse_form4_document(xml_text, symbol):
    normalized = _normalize_symbol(symbol)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"form 4 document malformed for {normalized}") from exc
    if root.tag != "ownershipDocument":
        raise ValueError(f"form 4 document malformed for {normalized}")
    transactions = []
    owners = root.findall("reportingOwner")
    table = root.find("nonDerivativeTable")
    entries = table.findall("nonDerivativeTransaction") if table is not None else []
    for owner in owners:
        name = _xml_value(owner, "reportingOwnerId/rptOwnerName") or "Unknown insider"
        title = _insider_title(owner.find("reportingOwnerRelationship"))
        for entry in entries:
            transaction_date = _xml_value(entry, "transactionDate/value")
            code = _xml_value(entry, "transactionCoding/transactionCode")
            if transaction_date is None or code is None:
                continue
            try:
                date.fromisoformat(transaction_date)
            except ValueError:
                continue
            transactions.append({
                "insider_name": name,
                "insider_title": title,
                "transaction_date": transaction_date,
                "transaction_code": code,
                "code_label": _FORM4_CODE_LABELS.get(code, code),
                "shares": _xml_number(entry, "transactionAmounts/transactionShares/value"),
                "price": _xml_number(entry, "transactionAmounts/transactionPricePerShare/value"),
                "acquired_disposed": _xml_value(
                    entry, "transactionAmounts/transactionAcquiredDisposedCode/value"
                ),
                "shares_after": _xml_number(
                    entry, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"
                ),
            })
    return transactions


def form4_raw_document(primary_document):
    return str(primary_document).split("/")[-1]
