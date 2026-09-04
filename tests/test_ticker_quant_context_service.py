from datetime import UTC, datetime, timedelta
import json

import httpx
import pytest

from app.db import edgar_filings as edgar_db
from app.db import market_data as market_data_db
from app.db import ticker_context as ticker_context_db
from app.http_client import HttpClient
from app.services import ticker_quant_context as ticker_quant_context_service


def _fundamentals_html(symbol, forward_pe=16.34):
    return f"""
    <html><body>
    <h1 class="heading yf-ndxd9a">{symbol} Inc ({symbol})</h1>
    "forwardPE":{{"raw":{forward_pe},"fmt":"{forward_pe}"}},
    "forwardEps":{{"raw":13.041,"fmt":"13.04"}},
    "trailingEps":{{"raw":6.67,"fmt":"6.67"}},
    "marketCap":{{"raw":5.16e12,"fmt":"5.16T"}},
    "sharesShort":{{"raw":292667375,"fmt":"292.67M"}},
    "shortRatio":{{"raw":2.23,"fmt":"2.23"}},
    "shortPercentOfFloat":{{"raw":0.0126,"fmt":"1.26%"}},
    "dividendYield":{{"raw":0.0048,"fmt":"0.48%"}},
    "debtToEquity":{{"raw":6.555,"fmt":"6.55%"}},
    "currentRatio":{{"raw":3.441,"fmt":"3.44"}},
    "quickRatio":{{"raw":2.139,"fmt":"2.14"}},
    "returnOnEquity":{{"raw":1.14288,"fmt":"114.29%"}},
    "returnOnAssets":{{"raw":0.52727,"fmt":"52.73%"}},
    "bookValue":{{"raw":8.07,"fmt":"8.07"}},
    "totalDebt":{{"raw":12.814e9,"fmt":"12.81B"}},
    "totalCash":{{"raw":53.17e9,"fmt":"53.17B"}},
    "freeCashflow":{{"raw":46.34e9,"fmt":"46.34B"}},
    "enterpriseValue":{{"raw":5.116e12,"fmt":"5.12T"}},
    "ebitda":{{"raw":165.5e9,"fmt":"165.5B"}}
    </body></html>
    """


def _mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def _seed_prices(con, symbol, days=30, volume=1000000):
    base = datetime(2026, 8, 26, tzinfo=UTC).date()
    rows = []
    for i in range(days):
        date_str = (base - timedelta(days=i)).isoformat()
        rows.append(
            {
                "date": date_str,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "adjusted_close": 100.0,
                "volume": volume,
            }
        )
    market_data_db.save_price_rows(con, symbol, "1d", rows)


def _forecast_data_json():
    flat_array = [
        {"estimates": 1, "estimatesCharts": 2, "estimatesSource": 3},
        {"stats": 4, "table": 5},
        {"eps": 6, "revenue": 7},
        {"name": "source"},
        {"annual": 8},
        [],
        {"2026-12-31": 9, "2027-12-31": 10, "2028-12-31": 10},
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


class TestCacheBehavior:
    def test_cache_hit_avoids_second_request(self, tmp_path):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["cache"] == "refreshed"
        quote_requests = [url for url in requests if "/quote/" in url]
        forecast_requests = [url for url in requests if "/forecast/__data.json" in url]
        assert len(quote_requests) == 1
        assert len(forecast_requests) == 1

        payload2 = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload2["cache"] == "hit"
        quote_requests = [url for url in requests if "/quote/" in url]
        forecast_requests = [url for url in requests if "/forecast/__data.json" in url]
        assert len(quote_requests) == 1
        assert len(forecast_requests) == 1

    def test_stale_cache_refreshes(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        con = ticker_context_db.connect(db_path)
        try:
            stale = {
                "symbol": "NVDA",
                "forward_pe": 10.0,
                "provider": "yahoo",
                "fetched_at": (datetime.now(UTC) - timedelta(seconds=80000)).isoformat(),
            }
            ticker_context_db.save_ticker_fundamentals(con, stale)
        finally:
            con.close()

        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["cache"] == "refreshed"
        assert payload["valuation"]["forward_pe"] == pytest.approx(16.34)

    def test_force_refresh_bypasses_fresh_cache_and_replaces_it(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        con = ticker_context_db.connect(db_path)
        try:
            ticker_context_db.save_ticker_fundamentals(
                con,
                {
                    "symbol": "NVDA",
                    "forward_pe": 10.0,
                    "provider": "yahoo",
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
            )
        finally:
            con.close()

        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            return httpx.Response(200, text=_fundamentals_html("NVDA", forward_pe=16.34))

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA",
            db_path=db_path,
            http_client=_mock_client(handler),
            force_refresh=True,
        )

        con = ticker_context_db.connect(db_path)
        try:
            cached = ticker_context_db.load_ticker_fundamentals(con, "NVDA")
        finally:
            con.close()

        assert payload["cache"] == "refreshed"
        assert payload["valuation"]["forward_pe"] == pytest.approx(16.34)
        assert cached["forward_pe"] == pytest.approx(16.34)

    def test_force_refresh_failure_preserves_fresh_cache(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        fetched_at = datetime.now(UTC).isoformat()
        con = ticker_context_db.connect(db_path)
        try:
            ticker_context_db.save_ticker_fundamentals(
                con,
                {
                    "symbol": "NVDA",
                    "forward_pe": 10.0,
                    "provider": "yahoo",
                    "fetched_at": fetched_at,
                },
            )
        finally:
            con.close()

        def handler(request):
            return httpx.Response(503, text="Unavailable")

        with pytest.raises(ValueError, match="HTTP 503"):
            ticker_quant_context_service.get_ticker_quant_context(
                "NVDA",
                db_path=db_path,
                http_client=_mock_client(handler),
                force_refresh=True,
            )

        con = ticker_context_db.connect(db_path)
        try:
            cached = ticker_context_db.load_ticker_fundamentals(con, "NVDA")
        finally:
            con.close()

        assert cached["forward_pe"] == pytest.approx(10.0)
        assert cached["fetched_at"] == fetched_at


class TestDaysToCover:
    def test_days_to_cover_insufficient_when_prices_table_empty(self, tmp_path):
        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["short_checks"]["days_to_cover"]["status"] == "insufficient_data"

    def test_days_to_cover_computed_with_prices(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        con = market_data_db.connect(db_path)
        try:
            _seed_prices(con, "NVDA", days=30, volume=1000000)
        finally:
            con.close()

        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["short_checks"]["days_to_cover"]["value"] == pytest.approx(292.667375)
        assert payload["short_checks"]["days_to_cover"]["status"] == "officially_dangerous"


class TestPeer:
    def test_peer_success_adds_pe_differential(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"

        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            symbol = url.split("/quote/")[-1].rstrip("/")
            if symbol == "NVDA":
                return httpx.Response(200, text=_fundamentals_html("NVDA", forward_pe=16.34))
            return httpx.Response(200, text=_fundamentals_html("AMD", forward_pe=20.0))

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", peer="AMD", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["peer"]["symbol"] == "AMD"
        assert payload["peer"]["forward_pe"] == pytest.approx(20.0)
        assert payload["peer"]["pe_differential"] == pytest.approx(16.34 / 20.0)

    def test_peer_failure_returns_error_without_breaking_main_payload(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"

        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            symbol = url.split("/quote/")[-1].rstrip("/")
            if symbol == "NVDA":
                return httpx.Response(200, text=_fundamentals_html("NVDA"))
            return httpx.Response(404, text="Not Found")

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", peer="NOPE", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["symbol"] == "NVDA"
        assert payload["peer"]["symbol"] == "NOPE"
        assert "error" in payload["peer"]
        assert "404" in payload["peer"]["error"]


class TestSymbolErrors:
    def test_unknown_symbol_raises_value_error(self, tmp_path):
        def handler(request):
            return httpx.Response(404, text="Not Found")

        db_path = tmp_path / "market_data.sqlite"
        with pytest.raises(ValueError, match="asset profile fetch failed for NOPE: HTTP 404"):
            ticker_quant_context_service.get_ticker_quant_context(
                "NOPE", db_path=db_path, http_client=_mock_client(handler)
            )


class TestEstimateConsensus:
    def _dispatching_handler(self, forecast_status=200, fundamentals_forward_pe=16.34):
        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                if forecast_status == 200:
                    return httpx.Response(200, text=_forecast_data_json())
                return httpx.Response(forecast_status, text="Not Found")
            return httpx.Response(200, text=_fundamentals_html("NVDA", forward_pe=fundamentals_forward_pe))
        return handler

    def test_payload_includes_estimate_consensus_and_revision_trend(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(self._dispatching_handler())
        )

        consensus = payload["estimate_consensus"]
        assert consensus["status"] == "ok"
        assert consensus["fiscal_year_end"] == "2026-12-31"
        assert consensus["analyst_count"] == 38
        assert consensus["avg"] == pytest.approx(1.5129)
        assert consensus["skew"] == "positive"
        trend = payload["estimate_revision_trend"]
        assert trend["status"] == "accumulating"

    def test_fetch_failure_with_no_snapshot_returns_insufficient_data(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(self._dispatching_handler(forecast_status=404))
        )

        assert payload["symbol"] == "NVDA"
        assert payload["estimate_consensus"] == {"status": "insufficient_data"}
        assert payload["estimate_revision_trend"]["status"] == "accumulating"

    def test_fetch_failure_with_stale_snapshot_uses_stale_snapshot(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        con = ticker_context_db.connect(db_path)
        try:
            stale = {
                "symbol": "NVDA",
                "fiscal_year_end": "2026-12-31",
                "avg": 0.95,
                "low": 0.5,
                "high": 1.5,
                "analyst_count": 12,
                "captured_at": (datetime.now(UTC) - timedelta(seconds=80000)).isoformat(),
            }
            ticker_context_db.save_estimate_consensus_snapshot(con, "NVDA", stale)
        finally:
            con.close()

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(self._dispatching_handler(forecast_status=404))
        )

        consensus = payload["estimate_consensus"]
        assert consensus["status"] == "ok"
        assert consensus["avg"] == pytest.approx(0.95)
        assert consensus["analyst_count"] == 12


def _forecast_data_json_with_ratings():
    flat = [None]

    def add(value):
        flat.append(value)
        return len(flat) - 1

    root = {
        "estimates": add({"stats": add({"annual": add([])}), "table": add([])}),
        "estimatesCharts": add({"eps": add({"2026-12-31": add({"no": add(38), "avg": add(1.5129), "low": add(1.12), "high": add(1.69)})}), "revenue": add({})}),
        "estimatesSource": add({"name": add("source")}),
        "currentRatings": add({
            "consensus": add("Strong Buy"),
            "score": add(8.583),
            "count": add(60),
            "strongBuy": add(48),
            "buy": add(9),
            "hold": add(2),
            "sell": add(0),
            "strongSell": add(1),
        }),
        "priceTargets": add({
            "avg": add(325.99),
            "median": add(315.0),
            "low": add(180.0),
            "high": add(515.0),
            "numPriceTargets": add(57),
        }),
        "recommendations": add([
            add({
                "date": add("2026-08-31"),
                "strongBuy": add(48),
                "buy": add(9),
                "hold": add(2),
                "sell": add(0),
                "strongSell": add(1),
                "total": add(60),
                "consensus": add("Strong Buy"),
            }),
        ]),
    }
    flat[0] = root
    return json.dumps({"type": "data", "nodes": [{"type": "data", "data": flat}]})


class TestAnalystRatings:
    def test_payload_includes_analyst_ratings(self, tmp_path):
        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json_with_ratings())
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        ratings = payload["analyst_ratings"]
        assert ratings["status"] == "ok"
        assert ratings["consensus"] == "Strong Buy"
        assert ratings["buy_total"] == 57
        assert ratings["sell_total"] == 1
        assert ratings["upgrade_room"] == "available"
        assert ratings["price_target"]["avg"] == pytest.approx(325.99)
        assert ratings["price_vs_target"] is None
        assert ratings["monthly_trend"][-1]["buy_total"] == 57

    def test_unavailable_ratings_negative_cached(self, tmp_path):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )
        assert payload["analyst_ratings"] == {"status": "insufficient_data"}
        assert payload["estimate_consensus"]["status"] == "ok"

        payload2 = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )
        assert payload2["analyst_ratings"] == {"status": "insufficient_data"}
        forecast_requests = [url for url in requests if "/forecast/__data.json" in url]
        assert len(forecast_requests) == 1

    def test_fetch_failure_with_stale_ratings_uses_stale_row(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        con = ticker_context_db.connect(db_path)
        try:
            ticker_context_db.save_analyst_ratings_snapshot(con, "NVDA", {
                "provider": "stockanalysis",
                "consensus": "Buy",
                "analyst_count": 12,
                "strong_buy": 5,
                "buy": 4,
                "hold": 2,
                "sell": 1,
                "strong_sell": 0,
                "captured_at": (datetime.now(UTC) - timedelta(seconds=80000)).isoformat(),
            })
        finally:
            con.close()

        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(500, text="Server Error")
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        ratings = payload["analyst_ratings"]
        assert ratings["status"] == "ok"
        assert ratings["analyst_count"] == 12
        assert payload["estimate_consensus"] == {"status": "insufficient_data"}


class TestCatalystActivitySection:
    def test_edgar_failure_degrades_to_insufficient_data(self, tmp_path):
        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            if "sec.gov" in url:
                return httpx.Response(500, text="Server Error")
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["symbol"] == "NVDA"
        assert payload["catalyst_activity"] == {"status": "insufficient_data"}


def _company_tickers_json():
    return json.dumps({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}})


def _companyfacts_json():
    def quarter(start, end, val):
        return {"start": start, "end": end, "val": val, "fy": 2026, "fp": "Q3", "form": "10-Q", "filed": "2026-08-20"}

    def instant(end, val):
        return {"end": end, "val": val, "fy": 2026, "fp": "Q3", "form": "10-Q", "filed": "2026-08-20"}

    gaap = {
        "OperatingIncomeLoss": {
            "units": {
                "USD": [
                    quarter("2025-08-01", "2025-10-31", 90.0),
                    quarter("2025-11-01", "2026-01-31", 100.0),
                    quarter("2026-02-01", "2026-04-30", 110.0),
                    quarter("2026-05-01", "2026-07-31", 120.0),
                ]
            }
        },
        "InterestExpense": {
            "units": {
                "USD": [
                    quarter("2025-08-01", "2025-10-31", 10.0),
                    quarter("2025-11-01", "2026-01-31", 10.0),
                    quarter("2026-02-01", "2026-04-30", 10.0),
                    quarter("2026-05-01", "2026-07-31", 10.0),
                ]
            }
        },
        "AssetsCurrent": {"units": {"USD": [instant("2026-07-31", 500.0)]}},
        "LiabilitiesCurrent": {"units": {"USD": [instant("2026-07-31", 200.0)]}},
        "Assets": {"units": {"USD": [instant("2026-07-31", 1000.0)]}},
    }
    return json.dumps({"cik": 1045810, "facts": {"us-gaap": gaap}})


def _sec_handler(request):
    url = str(request.url)
    if "company_tickers.json" in url:
        return httpx.Response(200, text=_company_tickers_json())
    if "companyfacts" in url:
        return httpx.Response(200, text=_companyfacts_json())
    return httpx.Response(500, text="Server Error")


class TestStatementFacts:
    def test_backward_ratios_computed_from_sec_facts(self, tmp_path):
        def handler(request):
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            if "sec.gov" in url:
                return _sec_handler(request)
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        ratios = {ratio["key"]: ratio for ratio in payload["backward_ratios"]["ratios"]}
        assert ratios["interest_coverage"]["value"] == pytest.approx(10.5)
        assert ratios["working_capital_to_total_assets"]["value"] == pytest.approx(0.3)
        assert ratios["ev_to_ebit"]["value"] == pytest.approx(5.116e12 / 420.0)
        assert payload["backward_ratios"]["missing_inputs"] == []

    def test_second_lookup_uses_cached_facts(self, tmp_path):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            if "sec.gov" in url:
                return _sec_handler(request)
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        client = _mock_client(handler)
        ticker_quant_context_service.get_ticker_quant_context("NVDA", db_path=db_path, http_client=client)
        ticker_quant_context_service.get_ticker_quant_context("NVDA", db_path=db_path, http_client=client)

        facts_requests = [url for url in requests if "companyfacts" in url]
        assert len(facts_requests) == 1

    def test_sec_failure_marks_missing_and_negative_caches(self, tmp_path):
        requests = []
        db_path = tmp_path / "market_data.sqlite"
        con = edgar_db.connect(db_path)
        try:
            edgar_db.save_cik(con, "NVDA", 1045810, "NVIDIA CORP")
        finally:
            con.close()

        def handler(request):
            requests.append(str(request.url))
            url = str(request.url)
            if "/forecast/__data.json" in url:
                return httpx.Response(200, text=_forecast_data_json())
            if "sec.gov" in url:
                return httpx.Response(500, text="Server Error")
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        client = _mock_client(handler)
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=client
        )
        assert payload["backward_ratios"]["missing_inputs"] == [
            "interest_coverage",
            "working_capital_to_total_assets",
            "ev_to_ebit",
        ]

        ticker_quant_context_service.get_ticker_quant_context("NVDA", db_path=db_path, http_client=client)
        facts_requests = [url for url in requests if "companyfacts" in url]
        assert len(facts_requests) == 3
