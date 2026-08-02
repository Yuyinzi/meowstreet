import io
from urllib.parse import unquote

import httpx
import pytest
from openpyxl import Workbook

from app.data_sources import non_oil_attribution_evidence as evidence
from app.http_client import HttpClient

_IWCC_PAGE_URL = "http://www.coppercouncil.org/iwcc-statistics-and-data"
_IWCC_WORKBOOK_URL = (
    "http://www.coppercouncil.org/files/Semis production and demand.xlsx"
)
_IWCC_PAGE_HTML = (
    "<html><body><ul>"
    '<li><a href="/files/Semis production and demand.xlsx">Semis production and demand.xlsx</a></li>'
    "</ul></body></html>"
)


def valid_fact():
    return {
        "commodity_id": "copper",
        "source_name": "International Wrought Copper Council",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "factor_category": "supply",
        "metric_name": "Production",
        "geography": "Global",
        "observation_date": "2024-12-31",
        "publication_date": None,
        "value": 24100.0,
        "units": "t",
    }


def _iwcc_workbook_bytes():
    wb = Workbook()
    production = wb.active
    production.title = "Production"
    production.append(["", 2012, 2013, 2020, 2024])
    production.append(["Global", 21400, 22000, 23000, 24100])
    production.append(["Europe", 5000, 5100, 5200, 5300])
    demand = wb.create_sheet("Demand")
    demand.append(["", 2012, 2013, 2020, 2024])
    demand.append(["Global", 21200, 21800, 22800, 23900])
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def iwcc_handler(request):
    if unquote(str(request.url)) == _IWCC_PAGE_URL:
        return httpx.Response(200, text=_IWCC_PAGE_HTML)
    if unquote(str(request.url)) == _IWCC_WORKBOOK_URL:
        return httpx.Response(200, content=_iwcc_workbook_bytes())
    return httpx.Response(404)


def _faostat_payload():
    return {
        "data": [
            {
                "area": "World",
                "item": "Sawnwood",
                "year": 2022,
                "element": "Production",
                "unit": "m3",
                "value": "251000000",
            },
            {
                "area": "World",
                "item": "Sawnwood",
                "year": 2023,
                "element": "Production",
                "unit": "m3",
                "value": "252000000",
            },
            {
                "area": "World",
                "item": "Sawnwood",
                "year": 2024,
                "element": "Production",
                "unit": "m3",
                "value": "254000000",
            },
            {
                "area": "World",
                "item": "Sawnwood",
                "year": 2023,
                "element": "Import Quantity",
                "unit": "m3",
                "value": "112000000",
            },
            {
                "area": "World",
                "item": "Sawnwood",
                "year": 2024,
                "element": "Import Quantity",
                "unit": "m3",
                "value": "114000000",
            },
            {
                "area": "World",
                "item": "Sawnwood",
                "year": 2024,
                "element": "Export Quantity",
                "unit": "m3",
                "value": "116000000",
            },
            {
                "area": "Europe",
                "item": "Sawnwood",
                "year": 2024,
                "element": "Production",
                "unit": "m3",
                "value": "50000000",
            },
        ]
    }


def faostat_handler(request):
    if str(request.url) == evidence.FAOSTAT_API_URL:
        return httpx.Response(200, json=_faostat_payload())
    return httpx.Response(404)


def test_fetch_iwcc_returns_latest_global_production_and_demand():
    facts = evidence.fetch_iwcc_copper_facts(
        HttpClient(transport=httpx.MockTransport(iwcc_handler))
    )
    assert {(row["factor_category"], row["observation_date"]) for row in facts} == {
        ("supply", "2024-12-31"),
        ("demand", "2024-12-31"),
    }


def test_fetch_faostat_returns_production_import_and_export_with_source_fields():
    facts = evidence.fetch_faostat_lumber_facts(
        HttpClient(transport=httpx.MockTransport(faostat_handler))
    )
    assert {row["metric_name"] for row in facts} == {
        "Production",
        "Import Quantity",
        "Export Quantity",
    }
    assert all(
        row["units"] and row["geography"] and row["observation_date"] for row in facts
    )


def test_normalize_rejects_missing_period_geography_unit_factor_or_numeric_value():
    for field, value in [
        ("observation_date", None),
        ("geography", ""),
        ("units", ""),
        ("factor_category", None),
        ("value", "x"),
    ]:
        raw = valid_fact()
        raw[field] = value
        with pytest.raises(ValueError, match=" non-oil attribution fact"):
            evidence.normalize_non_oil_attribution_fact(raw)


def test_fetch_iwcc_requests_source_page_then_same_origin_workbook():
    requested = []

    def handler(request):
        requested.append(unquote(str(request.url)))
        if requested[-1] == _IWCC_PAGE_URL:
            return httpx.Response(200, text=_IWCC_PAGE_HTML)
        return httpx.Response(200, content=_iwcc_workbook_bytes())

    facts = evidence.fetch_iwcc_copper_facts(
        HttpClient(transport=httpx.MockTransport(handler))
    )
    assert requested == [_IWCC_PAGE_URL, _IWCC_WORKBOOK_URL]
    assert len(facts) == 2


def test_fetch_faostat_requests_forestry_production_trade_surface():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, json=_faostat_payload())

    evidence.fetch_faostat_lumber_facts(
        HttpClient(transport=httpx.MockTransport(handler))
    )
    assert requested == [evidence.FAOSTAT_API_URL]


def test_fetch_iwcc_rejects_missing_semis_workbook_anchor():
    def handler(request):
        return httpx.Response(200, text="<html><body>no workbook links</body></html>")

    with pytest.raises(
        ValueError, match="iwcc semis production and demand workbook anchor is missing"
    ):
        evidence.fetch_iwcc_copper_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_iwcc_rejects_workbook_missing_a_factor():
    wb = Workbook()
    production = wb.active
    production.title = "Production"
    production.append(["", 2012, 2024])
    production.append(["Global", 21400, 24100])
    stream = io.BytesIO()
    wb.save(stream)
    content = stream.getvalue()

    def handler(request):
        if unquote(str(request.url)) == _IWCC_PAGE_URL:
            return httpx.Response(200, text=_IWCC_PAGE_HTML)
        return httpx.Response(200, content=content)

    with pytest.raises(
        ValueError,
        match="iwcc semis production and demand workbook is missing a factor",
    ):
        evidence.fetch_iwcc_copper_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_iwcc_rejects_non_numeric_global_cell():
    wb = Workbook()
    production = wb.active
    production.title = "Production"
    production.append(["", 2012, 2024])
    production.append(["Global", 21400, "x"])
    demand = wb.create_sheet("Demand")
    demand.append(["", 2012, 2024])
    demand.append(["Global", 21200, 23900])
    stream = io.BytesIO()
    wb.save(stream)
    content = stream.getvalue()

    def handler(request):
        if unquote(str(request.url)) == _IWCC_PAGE_URL:
            return httpx.Response(200, text=_IWCC_PAGE_HTML)
        return httpx.Response(200, content=content)

    with pytest.raises(
        ValueError,
        match="iwcc semis production and demand global supply value is not numeric",
    ):
        evidence.fetch_iwcc_copper_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_iwcc_rejects_duplicate_global_rows():
    wb = Workbook()
    production = wb.active
    production.title = "Production"
    production.append(["", 2012, 2024])
    production.append(["Global", 21400, 24100])
    production.append(["Global", 21450, 24150])
    demand = wb.create_sheet("Demand")
    demand.append(["", 2012, 2024])
    demand.append(["Global", 21200, 23900])
    stream = io.BytesIO()
    wb.save(stream)
    content = stream.getvalue()

    def handler(request):
        if unquote(str(request.url)) == _IWCC_PAGE_URL:
            return httpx.Response(200, text=_IWCC_PAGE_HTML)
        return httpx.Response(200, content=content)

    with pytest.raises(
        ValueError,
        match="iwcc semis production and demand workbook has duplicate global supply rows",
    ):
        evidence.fetch_iwcc_copper_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_iwcc_raises_on_non_200_source_page():
    with pytest.raises(httpx.HTTPStatusError):
        evidence.fetch_iwcc_copper_facts(
            HttpClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(404))
            )
        )


def test_fetch_faostat_rejects_row_missing_required_source_field():
    payload = _faostat_payload()
    del payload["data"][0]["area"]

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        ValueError,
        match="faostat forestry production and trade row is missing a required source field",
    ):
        evidence.fetch_faostat_lumber_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_faostat_rejects_non_numeric_selected_value():
    payload = _faostat_payload()
    for row in payload["data"]:
        if (
            row["item"] == "Sawnwood"
            and row["area"] == "World"
            and row["element"] == "Production"
            and row["year"] == 2024
        ):
            row["value"] = "x"

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        ValueError,
        match="faostat forestry production and trade Production value is not numeric",
    ):
        evidence.fetch_faostat_lumber_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_faostat_rejects_missing_export_quantity():
    payload = _faostat_payload()
    payload["data"] = [
        row for row in payload["data"] if row["element"] != "Export Quantity"
    ]

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        ValueError,
        match="faostat forestry production and trade is missing Export Quantity facts",
    ):
        evidence.fetch_faostat_lumber_facts(
            HttpClient(transport=httpx.MockTransport(handler))
        )


def test_fetch_faostat_raises_on_non_200_surface():
    with pytest.raises(httpx.HTTPStatusError):
        evidence.fetch_faostat_lumber_facts(
            HttpClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(404))
            )
        )


def test_fetch_facts_include_full_source_contract_fields():
    fetchers = [
        (
            evidence.fetch_iwcc_copper_facts,
            HttpClient(transport=httpx.MockTransport(iwcc_handler)),
            "http://www.coppercouncil.org/iwcc-statistics-and-data",
        ),
        (
            evidence.fetch_faostat_lumber_facts,
            HttpClient(transport=httpx.MockTransport(faostat_handler)),
            "https://www.fao.org/faostat/en/#data/FO",
        ),
    ]
    for fetch, client, source_url in fetchers:
        for fact in fetch(client):
            assert fact["method_version"] == "non_oil_attribution_evidence_v1"
            assert fact["source_url"] == source_url
            assert fact["factor_category"] in {"supply", "demand", "trade"}
            assert fact["value"] >= 0
            assert fact["status"] == "available"
            for field in (
                "commodity_id",
                "source_name",
                "metric_name",
                "geography",
                "observation_date",
                "units",
            ):
                assert fact.get(field) not in (None, "")


def test_fetch_facts_are_deterministic_for_same_source_fixture():
    fetchers = [
        (evidence.fetch_iwcc_copper_facts, iwcc_handler),
        (evidence.fetch_faostat_lumber_facts, faostat_handler),
    ]
    for fetch, handler in fetchers:
        first = fetch(HttpClient(transport=httpx.MockTransport(handler)))
        second = fetch(HttpClient(transport=httpx.MockTransport(handler)))
        assert first == second
