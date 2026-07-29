import math

import httpx
import pytest

from app.data_sources import oil
from app.http_client import HttpClient


def test_fetch_oil_observations_normalizes_official_eia_rows():
    def handler(request):
        url = str(request.url)
        if "pri/spt/data/" in url and "RWTC" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-24", "value": "64.89"}]}
                },
            )
        if "pri/spt/data/" in url and "RBRTE" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-24", "value": "67.50"}]}
                },
            )
        if "stoc/wstk/data/" in url and "WCESTUS1" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-17", "value": "450000"}]}
                },
            )
        if "sum/sndw/data/" in url and "WRPUPUS2" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-17", "value": "20500"}]}
                },
            )
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    payload = oil.fetch_oil_observations("test-key", http_client=client)

    assert payload["oil_wti_spot"]["series"] == {
        "series_id": "oil_wti_spot",
        "title": "WTI Spot Price",
        "units": "$/BBL",
        "source": "eia",
    }
    obs = payload["oil_wti_spot"]["observations"]
    assert len(obs) == 1
    assert obs[0]["date"] == "2026-07-24"
    assert obs[0]["value"] == 64.89
    assert obs[0]["source"] == "eia"
    assert obs[0]["release_date"] is None
    assert obs[0]["publication_date_basis"] == "unavailable"
    assert obs[0]["revision_status"] == "not_supplied"
    assert obs[0]["source_identifier"] == "RWTC"
    assert "test-key" not in obs[0]["source_url"]
    assert payload["oil_petroleum_products_supplied"]["role"] == "demand_proxy"


def test_fetch_oil_observations_rejects_missing_api_key():
    with pytest.raises(ValueError, match="eia api key is required"):
        oil.fetch_oil_observations("")


def test_fetch_oil_observations_rejects_non_numeric_eia_value():
    def handler(request):
        return httpx.Response(
            200, json={"response": {"data": [{"period": "2026-07-24", "value": "N/A"}]}}
        )

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    with pytest.raises(ValueError, match="eia observation value is invalid"):
        oil.fetch_oil_observations("test-key", http_client=client)


def test_eia_requests_use_the_documented_price_and_weekly_routes():
    captured_urls = []

    def handler(request):
        url = str(request.url)
        captured_urls.append(url)
        if "pri/spt/data/" in url and "RWTC" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-24", "value": "64.89"}]}
                },
            )
        if "pri/spt/data/" in url and "RBRTE" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-24", "value": "67.50"}]}
                },
            )
        if "stoc/wstk/data/" in url and "WCESTUS1" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-17", "value": "450000"}]}
                },
            )
        if "sum/sndw/data/" in url and "WRPUPUS2" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-17", "value": "20500"}]}
                },
            )
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    payload = oil.fetch_oil_observations("test-key", http_client=client)

    assert any(
        "/petroleum/pri/spt/data/" in url and "RWTC" in url for url in captured_urls
    )
    assert any(
        "/petroleum/pri/spt/data/" in url and "RBRTE" in url for url in captured_urls
    )
    assert any(
        "/petroleum/stoc/wstk/data/" in url and "WCESTUS1" in url
        for url in captured_urls
    )
    assert any(
        "/petroleum/sum/sndw/data/" in url and "WRPUPUS2" in url
        for url in captured_urls
    )
    assert all(
        "test-key" not in row["source_url"]
        for series in payload.values()
        for row in series["observations"]
    )


def test_imports_production_and_refinery_use_sum_sndw_not_stoc_wstk():
    captured_urls = []

    def handler(request):
        url = str(request.url)
        captured_urls.append(url)
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    oil.fetch_oil_observations("test-key", http_client=client)

    assert any(
        "/petroleum/sum/sndw/data/" in url and "WCEIMUS2" in url
        for url in captured_urls
    ), "imports should use sum/sndw"
    assert any(
        "/petroleum/sum/sndw/data/" in url and "WCRFPUS2" in url
        for url in captured_urls
    ), "production should use sum/sndw"
    assert any(
        "/petroleum/sum/sndw/data/" in url and "WCRRIUS2" in url
        for url in captured_urls
    ), "refinery input should use sum/sndw"
    assert any(
        "/petroleum/stoc/wstk/data/" in url and "WCESTUS1" in url
        for url in captured_urls
    ), "stocks should use stoc/wstk"


def test_price_requests_include_daily_frequency():
    captured_urls = []

    def handler(request):
        url = str(request.url)
        captured_urls.append(url)
        if "pri/spt" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-24", "value": "64.89"}]}
                },
            )
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    oil.fetch_oil_observations("test-key", http_client=client)

    for url in captured_urls:
        if "pri/spt" in url:
            assert "frequency=daily" in url, f"price url missing daily frequency: {url}"
        if "stoc/wstk" in url or "sum/sndw" in url:
            assert "frequency=weekly" in url, (
                f"attribution url missing weekly frequency: {url}"
            )


def test_fetch_rejects_nan_value():
    def handler(request):
        return httpx.Response(
            200,
            content=b'{"response": {"data": [{"period": "2026-07-24", "value": NaN}]}}',
        )

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    with pytest.raises(ValueError, match="eia observation value is invalid"):
        oil.fetch_oil_observations("test-key", http_client=client)


def test_fetch_rejects_inf_value():
    def handler(request):
        return httpx.Response(
            200,
            content=b'{"response": {"data": [{"period": "2026-07-24", "value": Infinity}]}}',
        )

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    with pytest.raises(ValueError, match="eia observation value is invalid"):
        oil.fetch_oil_observations("test-key", http_client=client)


def test_http_error_does_not_leak_api_key_in_exception():
    def handler(request):
        return httpx.Response(403, json={"error": "forbidden"})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    with pytest.raises(Exception) as exc_info:
        oil.fetch_oil_observations("test-key", http_client=client)

    exc = exc_info.value
    message = str(exc)
    assert "test-key" not in message, f"API key leaked in message: {message}"
    assert exc.__context__ is None, (
        f"exception chain must be severed; __context__ is {exc.__context__!r}"
    )
    assert exc.__cause__ is None

    for attr_name in ("request", "response"):
        obj = getattr(exc, attr_name, None)
        if obj is not None:
            url_str = str(obj.url) if hasattr(obj, "url") else str(obj)
            assert "test-key" not in url_str, (
                f"API key leaked in exception.{attr_name}.url: {url_str}"
            )


def test_oil_benchmark_payload_includes_source_provenance():
    import json

    captured_urls = []

    def handler(request):
        url = str(request.url)
        captured_urls.append(url)
        if "pri/spt" in url and "RWTC" in url:
            return httpx.Response(
                200,
                json={
                    "response": {"data": [{"period": "2026-07-24", "value": "64.89"}]}
                },
            )
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    raw = oil.fetch_oil_observations("test-key", http_client=client)

    from app.tools import cyclical_commodities as 

    payload = .build_cyclical_commodities_payload(
        [],
        {},
        {
            "oil_wti_spot": raw["oil_wti_spot"]["observations"],
        },
        "2026-07-25",
    )

    wti = payload["oil_observation"]["benchmarks"]["oil_wti_spot"]
    assert wti["source_identifier"] == "RWTC"
    assert "api.eia.gov" in wti["source_url"]
    assert "test-key" not in wti["source_url"]


def test_full_price_history_paginates_past_five_thousand_rows():
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if "pri/spt" in url:
            series = "RWTC" if "RWTC" in url else "RBRTE" if "RBRTE" in url else None
            if series is not None:
                has_offset = "offset=" in url
                if not has_offset:
                    data = [
                        {"period": "2026-07-24", "value": "70.00"} for _ in range(5000)
                    ]
                    return httpx.Response(
                        200,
                        json={"response": {"total": "5001", "data": data}},
                    )
                data = [{"period": "2026-07-23", "value": "71.00"}]
                return httpx.Response(
                    200,
                    json={"response": {"total": "5001", "data": data}},
                )
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    payload = oil.fetch_oil_observations(
        "test-key", http_client=client, full_price_history=True
    )

    wti = payload["oil_wti_spot"]["observations"]
    brent = payload["oil_brent_spot"]["observations"]
    assert len(wti) == 5001
    assert len(brent) == 5001

    for url in calls:
        if "stoc/wstk" in url or "sum/sndw" in url:
            assert "offset=" not in url, f"weekly url should not paginate: {url}"


def test_series_includes_actual_eia_units():
    def handler(request):
        url = str(request.url)
        if "pri/spt" in url and "RWTC" in url:
            return httpx.Response(
                200,
                json={
                    "response": {
                        "data": [
                            {
                                "period": "2026-07-24",
                                "value": "64.89",
                                "price-units": "dollars-per-barrel",
                            }
                        ]
                    }
                },
            )
        if "stoc/wstk" in url and "WCESTUS1" in url:
            return httpx.Response(
                200,
                json={
                    "response": {
                        "data": [
                            {
                                "period": "2026-07-17",
                                "value": "450000",
                                "units": "Thousand Barrels",
                            }
                        ]
                    }
                },
            )
        return httpx.Response(200, json={"response": {"data": []}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)
    payload = oil.fetch_oil_observations("test-key", http_client=client)

    assert payload["oil_wti_spot"]["series"]["units"] == "$/BBL"
    assert payload["oil_commercial_crude_stocks"]["series"]["units"] != "eia_units"
