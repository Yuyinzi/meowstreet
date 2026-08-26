from datetime import UTC, datetime, timedelta

import httpx
import pytest

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


class TestCacheBehavior:
    def test_cache_hit_avoids_second_request(self, tmp_path):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        db_path = tmp_path / "market_data.sqlite"
        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["cache"] == "refreshed"
        assert len(requests) == 1

        payload2 = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload2["cache"] == "hit"
        assert len(requests) == 1

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
            return httpx.Response(200, text=_fundamentals_html("NVDA"))

        payload = ticker_quant_context_service.get_ticker_quant_context(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )

        assert payload["cache"] == "refreshed"
        assert payload["valuation"]["forward_pe"] == pytest.approx(16.34)


class TestDaysToCover:
    def test_days_to_cover_insufficient_when_prices_table_empty(self, tmp_path):
        def handler(request):
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
            symbol = str(request.url).split("/quote/")[-1].rstrip("/")
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
            symbol = str(request.url).split("/quote/")[-1].rstrip("/")
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
