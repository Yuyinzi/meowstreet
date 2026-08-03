import csv
import hashlib
import io
import math
import re
from datetime import datetime
from datetime import timezone

import httpx

from app.http_client import HttpClient

_G17_SERIES_MAP = {
    "IP.B50001.S": "total_industrial_production",
    "IP.B00004.S": "manufacturing_production",
    "CAPUTL.B50001.S": "capacity_utilization",
}
_SERIES_ORDER = [
    "manufacturing_production",
    "total_industrial_production",
    "capacity_utilization",
]
_MONTH_COLUMN_RE = re.compile(r"\d{4}-\d{2}")
_RELEASE_DATE_RE = re.compile(r"Release Date:\s*(\w+ \d{1,2}, \d{4})", re.IGNORECASE)
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def fetch_g17_release(client, page_url, data_url):
    page = _fetch_bytes(client, page_url, "g17 release page")
    release_date = _extract_release_date(page)
    csv_value = _fetch_bytes(client, data_url, "g17 csv")
    result = parse_g17_release(
        {"release_date": release_date, "csv": csv_value}, page_url
    )
    result["csv"] = csv_value
    return result


def _fetch_bytes(client, url, label):
    if not isinstance(client, HttpClient):
        raise ValueError(f"g17 {label} requires an http client")
    try:
        response = client.request("GET", url, timeout=60)
    except httpx.HTTPError as exc:
        raise ValueError(f"failed to fetch {label} from {url}: {exc}") from exc
    return response.content


def _extract_release_date(page):
    text = _decode_text(page)
    match = _RELEASE_DATE_RE.search(text)
    if not match:
        raise ValueError("g17 release page is missing release date")
    return _parse_release_date(match.group(1))


def _parse_release_date(value):
    parts = value.split()
    if len(parts) != 3:
        raise ValueError(f"g17 release page has invalid release date {value!r}")
    month = _MONTH_NAMES.get(parts[0].lower())
    day = parts[1].rstrip(",")
    year = parts[2]
    if month is None:
        raise ValueError(f"g17 release page has invalid release date {value!r}")
    try:
        return (
            datetime.strptime(f"{year}-{month:02d}-{int(day):02d}", "%Y-%m-%d")
            .date()
            .isoformat()
        )
    except ValueError as exc:
        raise ValueError(
            f"g17 release page has invalid release date {value!r}"
        ) from exc


def parse_g17_release(payload, source_url):
    if not isinstance(payload, dict):
        raise ValueError("g17 payload is not an object")
    release_date = payload.get("release_date")
    if not release_date:
        raise ValueError("g17 payload is missing release date")
    _validate_release_date(release_date)
    csv_value = payload.get("csv")
    if not csv_value:
        raise ValueError("g17 payload is missing csv")
    text = _decode_text(csv_value)
    fieldnames, rows = _read_rows(text)
    columns = _month_columns(fieldnames)
    observations = _g17_observations(rows, columns, release_date, source_url, text)
    return {
        "source_url": source_url,
        "release_date": release_date,
        "reference_period": columns[-1],
        "observations": observations,
        "data_status": "available",
        "method_status": "pending_approval",
    }


def _read_rows(text):
    try:
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    except Exception as exc:
        raise ValueError("g17 csv could not be parsed") from exc
    if not fieldnames:
        raise ValueError("g17 csv has no header")
    return fieldnames, rows


def _month_columns(fieldnames):
    columns = [header for header in fieldnames if _MONTH_COLUMN_RE.fullmatch(header)]
    if not columns:
        raise ValueError("g17 csv has no month columns")
    return columns


def _g17_observations(rows, columns, release_date, source_url, text):
    reference_period = columns[-1]
    by_series = {}
    for row in rows:
        series_name = str(row.get("Series Name:") or "").strip()
        series_id = _G17_SERIES_MAP.get(series_name)
        if series_id is None:
            continue
        raw_value = str(row.get(reference_period) or "").strip()
        value = _parse_value(raw_value, series_id, reference_period)
        by_series[series_id] = _observation(
            series_id, reference_period, release_date, value, source_url, text
        )
    missing = [series_id for series_id in _SERIES_ORDER if series_id not in by_series]
    if missing:
        raise ValueError(f"g17 csv is missing {', '.join(missing)}")
    return [by_series[series_id] for series_id in _SERIES_ORDER]


def _parse_value(raw_value, series_id, reference_period):
    if not raw_value:
        raise ValueError(f"g17 {series_id} has invalid value for {reference_period}")
    try:
        value = float(raw_value.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"g17 {series_id} has invalid value {raw_value!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"g17 {series_id} has invalid value {raw_value!r}")
    return value


def _observation(series_id, reference_period, release_date, value, source_url, text):
    return {
        "series_id": series_id,
        "reference_period": reference_period,
        "release_date": release_date,
        "as_of_timestamp": datetime.now(timezone.utc).isoformat(),
        "value_at_release": value,
        "latest_revised_value": None,
        "revision_number": 0,
        "vintage_id": f"{series_id}:{reference_period}:{release_date}",
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": source_url,
        "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _validate_release_date(value):
    try:
        datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"g17 payload has invalid release date {value!r}") from exc


def _decode_text(csv_value):
    if isinstance(csv_value, (bytes, bytearray)):
        return csv_value.decode("utf-8-sig", errors="replace")
    if isinstance(csv_value, str):
        return csv_value
    raise ValueError("g17 csv is invalid")
