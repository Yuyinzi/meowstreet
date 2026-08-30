import json

import httpx
import pytest

from app.data_sources import stockanalysis_screener
from app.http_client import HttpClient


def _mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def _universe_json():
    payload = {
        "type": "data",
        "nodes": [
            {
                "type": "data",
                "data": [
                    {"session": 1},
                    None,
                    False,
                ],
            },
            {
                "type": "data",
                "data": [
                    {"count": 3, "data": 2},
                    3,
                    [3, 12, 21],
                    {"s": 4, "n": 5, "marketCap": 6, "price": 7, "change": 8, "industry": 9, "volume": 10, "peRatio": 11},
                    "AAPL",
                    "Apple Inc.",
                    3500000000000,
                    220.5,
                    1.2,
                    "Consumer Electronics",
                    50000000,
                    28.5,
                    {"s": 13, "n": 14, "marketCap": 15, "price": 16, "change": 17, "industry": 18, "volume": 19, "peRatio": 20},
                    "NVDA",
                    "NVIDIA Corporation",
                    5000000000000,
                    210.25,
                    2.3,
                    "Semiconductors",
                    120000000,
                    32.6,
                    {"s": 22, "n": 23, "marketCap": 24, "price": 25, "change": 26, "industry": 27, "volume": 28, "peRatio": 29},
                    "TSLA",
                    "Tesla Inc.",
                    800000000000,
                    300.0,
                    -0.5,
                    "Auto Manufacturers",
                    90000000,
                    45.2,
                ],
            },
        ],
    }
    return json.dumps(payload)


def test_parse_universe_data_extracts_rows():
    rows = stockanalysis_screener.parse_universe_data(_universe_json())

    assert len(rows) == 3
    assert rows[0] == {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "market_cap": 3500000000000.0,
        "price": 220.5,
        "industry": "Consumer Electronics",
    }
    assert rows[1]["symbol"] == "NVDA"
    assert rows[1]["price"] == 210.25
    assert rows[1]["industry"] == "Semiconductors"
    assert rows[2]["symbol"] == "TSLA"
    assert rows[2]["market_cap"] == 800000000000.0


def test_parse_universe_data_raises_on_malformed_node():
    with pytest.raises(ValueError, match="universe data node not found"):
        stockanalysis_screener.parse_universe_data('{"type":"other","nodes":[]}')


def test_parse_universe_data_raises_on_invalid_json():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        stockanalysis_screener.parse_universe_data("not json")


def test_parse_universe_data_skips_rows_with_missing_market_cap_or_price():
    payload = {
        "type": "data",
        "nodes": [
            {"type": "data", "data": []},
            {
                "type": "data",
                "data": [
                    {"count": 2, "data": 2},
                    2,
                    [3, 12],
                    {"s": 4, "n": 5, "marketCap": 6, "price": 7, "change": 8, "industry": 9, "volume": 10, "peRatio": 11},
                    "A",
                    "A Inc",
                    1e9,
                    10.0,
                    0.5,
                    "Software",
                    1000,
                    20.0,
                    {"s": 13, "n": 14, "marketCap": 15, "price": 16, "change": 17, "industry": 18, "volume": 19, "peRatio": 20},
                    "B",
                    "B Inc",
                    None,
                    5.0,
                    0.1,
                    "Software",
                    500,
                    15.0,
                ],
            },
        ],
    }
    rows = stockanalysis_screener.parse_universe_data(json.dumps(payload))

    assert len(rows) == 1
    assert rows[0]["symbol"] == "A"


def _forecast_html(this_year_value="9.02", this_year_from="4.77", next_year_value="13.04"):
    next_card = ""
    if next_year_value is not None:
        next_card = (
            f'<div class="border-b"><div class="text-base">EPS Next Year</div>'
            f'<div class="mt-1"><div class="flex items-baseline text-2xl font-semibold">{next_year_value} </div>'
            f'</div></div>'
        )
    return (
        f'<div class="border-b"><div class="text-base">EPS This Year</div>'
        f'<div class="mt-1"><div class="flex items-baseline text-2xl font-semibold">{this_year_value} '
        f'<div class="ml-2 text-sm">from {this_year_from}</div></div></div></div>'
        f"{next_card}"
    )


def test_parse_forecast_html_extracts_both_cards():
    result = stockanalysis_screener.parse_forecast_html(_forecast_html(), "NVDA")

    assert result == {
        "symbol": "NVDA",
        "eps_fy0": 4.77,
        "eps_fy1": 9.02,
        "eps_fy2": 13.04,
        "provider": "stockanalysis",
    }


def test_parse_forecast_html_tolerates_missing_next_year():
    result = stockanalysis_screener.parse_forecast_html(
        _forecast_html(next_year_value=None), "NVDA"
    )

    assert result["eps_fy0"] == 4.77
    assert result["eps_fy1"] == 9.02
    assert result["eps_fy2"] is None
    assert result["provider"] == "stockanalysis"


def test_parse_forecast_html_raises_when_no_cards():
    with pytest.raises(ValueError, match="forecast estimates unavailable for NVDA"):
        stockanalysis_screener.parse_forecast_html("<html><body>no data</body></html>", "NVDA")


def test_fetch_universe_requests_screener_data_with_browser_headers():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["user_agent"] = request.headers.get("user-agent", "")
        seen["accept"] = request.headers.get("accept", "")
        seen["accept_encoding"] = request.headers.get("accept-encoding", "")
        return httpx.Response(200, text=_universe_json())

    rows = stockanalysis_screener.fetch_universe(http_client=_mock_client(handler))

    assert seen["url"] == "https://stockanalysis.com/stocks/screener/__data.json"
    assert "Mozilla" in seen["user_agent"]
    assert "json" in seen["accept"]
    assert "br" not in seen["accept_encoding"]
    assert len(rows) == 3
    assert rows[0]["symbol"] == "AAPL"


def test_fetch_forecast_eps_requests_lower_case_symbol():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["user_agent"] = request.headers.get("user-agent", "")
        seen["accept"] = request.headers.get("accept", "")
        seen["accept_encoding"] = request.headers.get("accept-encoding", "")
        return httpx.Response(200, text=_forecast_html())

    result = stockanalysis_screener.fetch_forecast_eps(
        " NVDA ", http_client=_mock_client(handler)
    )

    assert seen["url"] == "https://stockanalysis.com/stocks/nvda/forecast/"
    assert "Mozilla" in seen["user_agent"]
    assert "text/html" in seen["accept"]
    assert "br" not in seen["accept_encoding"]
    assert result["symbol"] == "NVDA"
    assert result["eps_fy1"] == 9.02


def test_fetch_universe_raises_on_404():
    def handler(request):
        return httpx.Response(404, text="Not Found")

    with pytest.raises(ValueError, match="universe fetch failed: HTTP 404"):
        stockanalysis_screener.fetch_universe(http_client=_mock_client(handler))


def test_fetch_forecast_eps_raises_on_404():
    def handler(request):
        return httpx.Response(404, text="Not Found")

    with pytest.raises(ValueError, match="forecast fetch failed for NVDA: HTTP 404"):
        stockanalysis_screener.fetch_forecast_eps("NVDA", http_client=_mock_client(handler))


def test_fetch_forecast_eps_requires_symbol():
    with pytest.raises(ValueError, match="symbol is required"):
        stockanalysis_screener.fetch_forecast_eps("   ")


def _forecast_data_json():
    flat_array = [
        {"estimates": 1, "estimatesCharts": 2, "estimatesSource": 3},
        {"stats": 4, "table": 5},
        {"eps": 6, "revenue": 7},
        {"name": "source"},
        {"annual": 8},
        [],
        {"2026-12-31": 9, "2027-12-31": 10, "2028-12-31": 11},
        {"2026-12-31": 11},
        {"epsNext": 12},
        {"no": 13, "avg": 14, "low": 15, "high": 16},
        "[PRO]",
        {"no": 17, "avg": 18, "low": 19, "high": 20},
        None,
        38,
        1.5129,
        1.12,
        1.69,
        25,
        1.8,
        1.4,
        2.1,
    ]
    return json.dumps({"type": "data", "nodes": [{"type": "data", "data": flat_array}]})


def test_parse_forecast_data_extracts_nearest_future_fiscal_year():
    result = stockanalysis_screener.parse_forecast_data(_forecast_data_json(), "INTC", today="2026-08-28")

    assert result == {
        "fiscal_year_end": "2026-12-31",
        "analyst_count": 38,
        "avg": 1.5129,
        "low": 1.12,
        "high": 1.69,
    }


def test_parse_forecast_data_skips_pro_entries():
    result = stockanalysis_screener.parse_forecast_data(_forecast_data_json(), "INTC", today="2027-01-01")

    assert result["fiscal_year_end"] == "2028-12-31"
    assert result["analyst_count"] == 25


def test_parse_forecast_data_raises_when_all_eps_pro():
    flat_array = [
        {"estimates": 1, "estimatesCharts": 2},
        {"stats": 3},
        {"eps": 4},
        {"annual": 5},
        {"2026-12-31": 6, "2027-12-31": 6},
        "[PRO]",
    ]
    payload = json.dumps({"type": "data", "nodes": [{"type": "data", "data": flat_array}]})

    with pytest.raises(ValueError, match="estimate consensus unavailable for INTC"):
        stockanalysis_screener.parse_forecast_data(payload, "INTC")


def test_parse_forecast_data_raises_when_estimates_charts_missing():
    payload = json.dumps({"type": "data", "nodes": [{"type": "data", "data": []}]})

    with pytest.raises(ValueError, match="estimate consensus unavailable for INTC"):
        stockanalysis_screener.parse_forecast_data(payload, "INTC")


def test_parse_forecast_data_tolerates_out_of_range_indexes():
    flat_array = [
        {"estimates": 1, "estimatesCharts": 2},
        {"stats": 3},
        {"eps": 4},
        {"annual": 5},
        {"2026-12-31": 5},
        None,
    ]
    payload = json.dumps({"type": "data", "nodes": [{"type": "data", "data": flat_array}]})

    with pytest.raises(ValueError, match="estimate consensus unavailable for INTC"):
        stockanalysis_screener.parse_forecast_data(payload, "INTC")


def test_fetch_estimate_consensus_requests_data_json_without_brotli():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["accept"] = request.headers.get("accept", "")
        seen["accept_encoding"] = request.headers.get("accept-encoding", "")
        return httpx.Response(200, text=_forecast_data_json())

    result = stockanalysis_screener.fetch_estimate_consensus(
        " INTC ", http_client=_mock_client(handler)
    )

    assert seen["url"] == "https://stockanalysis.com/stocks/intc/forecast/__data.json"
    assert "json" in seen["accept"]
    assert "br" not in seen["accept_encoding"]
    assert result["fiscal_year_end"] == "2026-12-31"


def test_fetch_estimate_consensus_raises_on_404():
    def handler(request):
        return httpx.Response(404, text="Not Found")

    with pytest.raises(ValueError, match="estimate consensus fetch failed for INTC: HTTP 404"):
        stockanalysis_screener.fetch_estimate_consensus("INTC", http_client=_mock_client(handler))


def test_fetch_estimate_consensus_requires_symbol():
    with pytest.raises(ValueError, match="symbol is required"):
        stockanalysis_screener.fetch_estimate_consensus("   ")
