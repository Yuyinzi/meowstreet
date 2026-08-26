import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data_sources import stockanalysis_screener
from app.db import quant_screen as quant_screen_db
from app.http_client import HttpClient
from app.routers import quant_screen as quant_screen_router
from app.services import quant_screen as quant_screen_service
from app.tools import quant_screen as quant_screen_tool

app = FastAPI()
app.include_router(quant_screen_router.router)
client = TestClient(app)


def _mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def _forecast_html(symbol, value="9.02", from_value="4.77", next_value="13.04"):
    return (
        f'<div><div class="text-base">EPS This Year</div>'
        f'<div class="mt-1"><div class="flex items-baseline text-2xl font-semibold">{value} '
        f'<div class="ml-2 text-sm">from {from_value}</div></div></div></div>'
        f'<div><div class="text-base">EPS Next Year</div>'
        f'<div class="mt-1"><div class="flex items-baseline text-2xl font-semibold">{next_value} </div></div></div>'
    )


def _universe_json(stocks):
    data_array = [{"count": len(stocks), "data": 2}, len(stocks)]
    stock_indices = []
    current_index = len(data_array) + 1
    for stock in stocks:
        stock_indices.append(current_index)
        mapping = {
            "s": current_index + 1,
            "n": current_index + 2,
            "marketCap": current_index + 3,
            "price": current_index + 4,
            "change": current_index + 5,
            "industry": current_index + 6,
            "volume": current_index + 7,
            "peRatio": current_index + 8,
        }
        data_array.extend([
            mapping,
            stock["symbol"],
            stock["name"],
            stock["market_cap"],
            stock["price"],
            1.0,
            stock["industry"],
            1000000,
            20.0,
        ])
        current_index += 9
    data_array.insert(2, stock_indices)
    payload = {
        "type": "data",
        "nodes": [
            {"type": "data", "data": []},
            {"type": "data", "data": data_array},
        ],
    }
    return json.dumps(payload)


def _three_semiconductor_stocks():
    return [
        {"symbol": "NVDA", "name": "NVIDIA Corporation", "market_cap": 5e12, "price": 210.0, "industry": "Semiconductors"},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "market_cap": 2e11, "price": 150.0, "industry": "Semiconductors"},
        {"symbol": "INTC", "name": "Intel Corporation", "market_cap": 1e11, "price": 25.0, "industry": "Semiconductors"},
    ]


def _handler_for_universe_and_forecasts(stocks, fail_symbols=None):
    fail_symbols = fail_symbols or set()
    universe_sent = {"count": 0}

    def handler(request):
        url = str(request.url)
        if url == "https://stockanalysis.com/stocks/screener/__data.json":
            universe_sent["count"] += 1
            return httpx.Response(200, text=_universe_json(stocks))
        for stock in stocks:
            if url == f"https://stockanalysis.com/stocks/{stock['symbol'].lower()}/forecast/":
                if stock["symbol"] in fail_symbols:
                    return httpx.Response(404, text="Not Found")
                return httpx.Response(200, text=_forecast_html(stock["symbol"]))
        return httpx.Response(404, text="Not Found")

    return handler, universe_sent


def test_list_industries_fetches_and_caches_universe(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = _three_semiconductor_stocks()
    handler, universe_sent = _handler_for_universe_and_forecasts(stocks)
    http_client = _mock_client(handler)

    industries = quant_screen_service.list_industries(
        db_path=db_path, http_client=http_client
    )

    assert universe_sent["count"] == 1
    assert industries == [{"industry": "Semiconductors", "stock_count": 3}]

    industries_again = quant_screen_service.list_industries(
        db_path=db_path, http_client=http_client
    )

    assert universe_sent["count"] == 1
    assert industries_again == industries


def test_run_industry_screen_builds_payload(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = _three_semiconductor_stocks()
    handler, _ = _handler_for_universe_and_forecasts(stocks)
    http_client = _mock_client(handler)

    payload = quant_screen_service.run_industry_screen(
        "semiconductors", db_path=db_path, http_client=http_client
    )

    expected_rows = [
        {
            "symbol": stock["symbol"],
            "price": stock["price"],
            "market_cap": stock["market_cap"],
            "eps_fy0": 4.77,
            "eps_fy1": 9.02,
            "eps_fy2": 13.04,
        }
        for stock in stocks
    ]
    expected_payload = quant_screen_tool.build_screen_payload(expected_rows, [])

    assert payload["rows"] == expected_payload["rows"]
    assert payload["row_count"] == expected_payload["row_count"]
    assert payload["sector"] == expected_payload["sector"]
    assert payload["row_errors"] == []
    assert payload["source"] == {
        "mode": "auto",
        "provider": "stockanalysis",
        "industry": "Semiconductors",
        "stock_count": 3,
        "estimate_failures": 0,
    }


def test_run_industry_screen_uses_fresh_cached_estimates(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = _three_semiconductor_stocks()
    handler, _ = _handler_for_universe_and_forecasts(stocks)
    http_client = _mock_client(handler)
    quant_screen_service.run_industry_screen(
        "semiconductors", db_path=db_path, http_client=http_client
    )

    con = quant_screen_db.connect(db_path)
    quant_screen_db.save_estimate(con, {
        "symbol": "NVDA",
        "eps_fy0": 1.0,
        "eps_fy1": 2.0,
        "eps_fy2": 3.0,
        "provider": "stockanalysis",
    })

    payload = quant_screen_service.run_industry_screen(
        "semiconductors", db_path=db_path, http_client=http_client
    )

    nvda_row = next(row for row in payload["rows"] if row["symbol"] == "NVDA")
    assert nvda_row["eps_fy0"] == 1.0
    assert nvda_row["eps_fy1"] == 2.0
    assert nvda_row["eps_fy2"] == 3.0


def test_run_industry_screen_rejects_unknown_industry(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = _three_semiconductor_stocks()
    handler, _ = _handler_for_universe_and_forecasts(stocks)

    with pytest.raises(ValueError, match="industry BioTech not found in screener universe"):
        quant_screen_service.run_industry_screen(
            "BioTech", db_path=db_path, http_client=_mock_client(handler)
        )


def test_run_industry_screen_rejects_too_large_industry(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = [
        {"symbol": f"S{i:03d}", "name": f"Stock {i}", "market_cap": 1e9, "price": 10.0, "industry": "Huge Industry"}
        for i in range(251)
    ]
    handler, _ = _handler_for_universe_and_forecasts(stocks)

    with pytest.raises(ValueError, match="industry Huge Industry has 251 stocks; too large for automatic fetch"):
        quant_screen_service.run_industry_screen(
            "Huge Industry", db_path=db_path, http_client=_mock_client(handler)
        )


def test_run_industry_screen_collects_failed_estimates(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = _three_semiconductor_stocks()
    handler, _ = _handler_for_universe_and_forecasts(stocks, fail_symbols={"AMD"})
    http_client = _mock_client(handler)

    payload = quant_screen_service.run_industry_screen(
        "semiconductors", db_path=db_path, http_client=http_client
    )

    assert payload["source"]["estimate_failures"] == 1
    assert payload["source"]["stock_count"] == 3
    assert len(payload["rows"]) == 2
    symbols = {row["symbol"] for row in payload["rows"]}
    assert symbols == {"NVDA", "INTC"}
    amd_error = next(
        (error for error in payload["row_errors"] if error["symbol"] == "AMD"), None
    )
    assert amd_error is not None
    assert "HTTP 404" in amd_error["reason"]


def test_run_industry_screen_caches_failed_estimates(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    stocks = _three_semiconductor_stocks()
    amd_requests = {"count": 0}

    def handler(request):
        url = str(request.url)
        if url == "https://stockanalysis.com/stocks/screener/__data.json":
            return httpx.Response(200, text=_universe_json(stocks))
        if url == "https://stockanalysis.com/stocks/amd/forecast/":
            amd_requests["count"] += 1
            return httpx.Response(404, text="Not Found")
        for stock in stocks:
            if url == f"https://stockanalysis.com/stocks/{stock['symbol'].lower()}/forecast/":
                return httpx.Response(200, text=_forecast_html(stock["symbol"]))
        return httpx.Response(404, text="Not Found")

    http_client = _mock_client(handler)

    first = quant_screen_service.run_industry_screen(
        "semiconductors", db_path=db_path, http_client=http_client
    )
    second = quant_screen_service.run_industry_screen(
        "semiconductors", db_path=db_path, http_client=http_client
    )

    assert amd_requests["count"] == 1
    assert second["source"]["estimate_failures"] == 1
    amd_error = next(
        (error for error in second["row_errors"] if error["symbol"] == "AMD"), None
    )
    assert amd_error is not None
    assert "HTTP 404" in amd_error["reason"]
    assert {row["symbol"] for row in second["rows"]} == {
        row["symbol"] for row in first["rows"]
    }


def test_api_get_industries(monkeypatch):
    def fake_list_industries():
        return [{"industry": "Semiconductors", "stock_count": 3}]

    monkeypatch.setattr(quant_screen_service, "list_industries", fake_list_industries)

    response = client.get("/api/quant-screen/industries")

    assert response.status_code == 200
    assert response.json() == {"industries": [{"industry": "Semiconductors", "stock_count": 3}]}


def test_api_post_auto_success(monkeypatch):
    def fake_run_industry_screen(industry):
        return {
            "row_count": 2,
            "source": {"industry": industry, "stock_count": 2},
        }

    monkeypatch.setattr(quant_screen_service, "run_industry_screen", fake_run_industry_screen)

    response = client.post("/api/quant-screen/auto", json={"industry": "Semiconductors"})

    assert response.status_code == 200
    assert response.json()["source"]["industry"] == "Semiconductors"


def test_api_post_auto_rejects_missing_industry():
    response = client.post("/api/quant-screen/auto", json={})

    assert response.status_code == 400
    assert "industry" in response.json()["detail"]


def test_api_post_auto_rejects_non_string_industry():
    response = client.post("/api/quant-screen/auto", json={"industry": 123})

    assert response.status_code == 400
    assert "industry" in response.json()["detail"]


def test_api_post_auto_converts_value_error_to_400(monkeypatch):
    def fake_run_industry_screen(industry):
        raise ValueError("industry BioTech not found in screener universe")

    monkeypatch.setattr(quant_screen_service, "run_industry_screen", fake_run_industry_screen)

    response = client.post("/api/quant-screen/auto", json={"industry": "BioTech"})

    assert response.status_code == 400
    assert "BioTech" in response.json()["detail"]
