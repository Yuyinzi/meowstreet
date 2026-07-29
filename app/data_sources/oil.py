import json
import math

from app.http_client import HttpClient


EIA_BASE_URL = "https://api.eia.gov/v2"

PRICE_SERIES = {
    "oil_wti_spot": ("RWTC", "WTI Spot Price", "$/BBL"),
    "oil_brent_spot": ("RBRTE", "Brent Spot Price", "$/BBL"),
}

_INVENTORY_SERIES = {
    "oil_commercial_crude_stocks": (
        "WCESTUS1",
        "U.S. Commercial Crude Oil Stocks",
        "Thousand Barrels",
        "inventory",
    ),
}

_SUPPLY_SERIES = {
    "oil_commercial_crude_imports": (
        "WCEIMUS2",
        "Commercial Crude Oil Imports",
        "Thousand Barrels per Day",
        "supply_context",
    ),
    "oil_crude_production": (
        "WCRFPUS2",
        "U.S. Field Production of Crude Oil",
        "Thousand Barrels per Day",
        "supply_context",
    ),
    "oil_refinery_crude_input": (
        "WCRRIUS2",
        "Gross Input to Refineries",
        "Thousand Barrels per Day",
        "processing_activity",
    ),
    "oil_petroleum_products_supplied": (
        "WRPUPUS2",
        "U.S. Product Supplied of Crude Oil and Petroleum Products",
        "Thousand Barrels per Day",
        "demand_proxy",
    ),
}

PRICE_ROUTE = "petroleum/pri/spt/data/"
STOCK_ROUTE = "petroleum/stoc/wstk/data/"
SUPPLY_ROUTE = "petroleum/sum/sndw/data/"


def _build_params(
    series_id, api_key, frequency, start_date=None, end_date=None, offset=None
):
    params = {
        "api_key": api_key,
        "data[0]": "value",
        "facets[series][]": series_id,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
        "frequency": frequency,
    }
    if start_date:
        params["start[0]"] = start_date
    if end_date:
        params["end[0]"] = end_date
    if offset is not None:
        params["offset"] = offset
    return params


def _normalize_observation(point, series_id, route_url):
    raw_value = point.get("value")
    if raw_value is None:
        raise ValueError(f"eia observation value is invalid for {series_id}")
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if not raw_value:
            raise ValueError(f"eia observation value is invalid for {series_id}")
    try:
        value = float(raw_value)
    except (ValueError, TypeError):
        raise ValueError(f"eia observation value is invalid for {series_id}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"eia observation value is invalid for {series_id}")
    return {
        "date": point["period"],
        "value": value,
        "source": "eia",
        "release_date": None,
        "publication_date_basis": "unavailable",
        "revision_status": "not_supplied",
        "source_url": route_url,
        "source_identifier": series_id,
    }


def _build_route_url(route):
    return f"{EIA_BASE_URL}/{route}"


def _request_payload(client, route_url, params, series_id):
    request_failed = False
    try:
        response = client.request("GET", route_url, params=params, timeout=30)
    except Exception:
        request_failed = True
    if request_failed:
        raise ValueError(f"eia request failed for {series_id}")
    data = response.content
    return json.loads(data)


def _fetch_price_pages(series_id, api_key, client, route_url, price_start_date=None):
    observations = []
    offset = 0
    while True:
        params = _build_params(
            series_id, api_key, "daily", start_date=price_start_date, offset=offset
        )
        payload = _request_payload(client, route_url, params, series_id)
        page = payload.get("response", {}).get("data", [])
        total = int(payload.get("response", {}).get("total", len(page)))
        observations.extend(
            _normalize_observation(row, series_id, route_url) for row in page
        )
        offset += len(page)
        if offset >= total or not page:
            break
    return observations


def _fetch_route(
    route,
    series_map,
    api_key,
    http_client=None,
    frequency=None,
    start_date=None,
    end_date=None,
):
    result = {}
    client = http_client or HttpClient()
    route_url = _build_route_url(route)
    for internal_id, series_spec in series_map.items():
        series_id = series_spec[0]
        title = series_spec[1]
        units = series_spec[2] if len(series_spec) > 2 else "eia_units"
        role_val = series_spec[3] if len(series_spec) > 3 else None
        params = _build_params(series_id, api_key, frequency, start_date, end_date)
        payload = _request_payload(client, route_url, params, series_id)
        points = payload.get("response", {}).get("data", [])
        observations = [_normalize_observation(p, series_id, route_url) for p in points]
        series = {
            "series_id": internal_id,
            "title": title,
            "units": units,
            "source": "eia",
        }
        item = {
            "series": series,
            "observations": observations,
        }
        if role_val:
            item["role"] = role_val
        result[internal_id] = item
    return result


def _fetch_price_observations(
    api_key, http_client=None, price_start_date=None, full_price_history=False
):
    client = http_client or HttpClient()
    route_url = _build_route_url(PRICE_ROUTE)
    result = {}
    for internal_id, series_spec in PRICE_SERIES.items():
        series_id = series_spec[0]
        title = series_spec[1]
        units = series_spec[2]
        if full_price_history:
            observations = _fetch_price_pages(
                series_id, api_key, client, route_url, price_start_date=None
            )
        else:
            params = _build_params(
                series_id, api_key, "daily", start_date=price_start_date
            )
            payload = _request_payload(client, route_url, params, series_id)
            points = payload.get("response", {}).get("data", [])
            observations = [
                _normalize_observation(p, series_id, route_url) for p in points
            ]
        result[internal_id] = {
            "series": {
                "series_id": internal_id,
                "title": title,
                "units": units,
                "source": "eia",
            },
            "observations": observations,
        }
    return result


def _fetch_attribution_observations(
    api_key, http_client=None, start_date=None, end_date=None
):
    stock_result = _fetch_route(
        STOCK_ROUTE,
        _INVENTORY_SERIES,
        api_key,
        http_client,
        frequency="weekly",
        start_date=start_date,
        end_date=end_date,
    )
    supply_result = _fetch_route(
        SUPPLY_ROUTE,
        _SUPPLY_SERIES,
        api_key,
        http_client,
        frequency="weekly",
        start_date=start_date,
        end_date=end_date,
    )
    return {**stock_result, **supply_result}


def fetch_oil_observations(
    api_key,
    http_client=None,
    price_start_date=None,
    attribution_start_date=None,
    full_price_history=False,
):
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("eia api key is required")
    prices = _fetch_price_observations(
        key, http_client, price_start_date, full_price_history
    )
    attribution = _fetch_attribution_observations(
        key, http_client, start_date=attribution_start_date
    )
    return {**prices, **attribution}
