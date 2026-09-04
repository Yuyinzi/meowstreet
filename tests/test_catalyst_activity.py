import json
from datetime import date, timedelta

import httpx

from app.db import market_data as market_data_db
from app.http_client import HttpClient
from app.services import catalyst_activity


def _mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def _tickers_payload():
    return json.dumps({
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    })


def _submissions_payload():
    return json.dumps({
        "filings": {
            "recent": {
                "form": ["8-K", "8-K"],
                "filingDate": [
                    (date.today() - timedelta(days=30)).isoformat(),
                    (date.today() - timedelta(days=120)).isoformat(),
                ],
                "accessionNumber": ["0001045810-26-000073", "0001045810-26-000050"],
                "primaryDocument": ["nvda-earnings.htm", "nvda-other.htm"],
            },
            "files": [],
        }
    })


def _seed_prices(db_path, symbol, days=45):
    con = market_data_db.connect(db_path)
    try:
        today = date.today()
        rows = []
        for index in range(days):
            day = today - timedelta(days=days - 1 - index)
            close = 100.0 * (1.15 if index == days - 1 else 1.0)
            rows.append({
                "date": day.isoformat(),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "adjusted_close": close,
                "volume": 1000000,
            })
        market_data_db.save_price_rows(con, symbol, "1d", rows)
    finally:
        con.close()


def _happy_handler(request):
    url = str(request.url)
    if "company_tickers" in url:
        return httpx.Response(200, text=_tickers_payload())
    if "data.sec.gov/submissions" in url:
        return httpx.Response(200, text=_submissions_payload())
    if "nvda-earnings.htm" in url:
        return httpx.Response(200, text="<p>Item 2.02 Results of Operations</p>")
    if "nvda-other.htm" in url:
        return httpx.Response(200, text="<p>Item 5.07 Submission of Matters</p>")
    return httpx.Response(404, text="Not Found")


class TestCatalystActivity:
    def test_happy_path_frequency_and_moves(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        _seed_prices(db_path, "NVDA")
        result = catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(_happy_handler)
        )
        assert result["status"] == "ok"
        assert result["cik"] == 1045810
        frequency = result["filing_frequency"]
        assert frequency["total"] == 2
        assert frequency["earnings"] == 1
        assert frequency["non_earnings"] == 1
        moves = result["large_moves"]
        assert moves["status"] == "ok"
        assert len(moves["moves"]) == 1
        assert moves["moves"][0]["filing_within_window"] in (True, False)
        assert "8-K filings only" in result["caveat"]
        calendar = result["calendar"]
        assert len(calendar["days"]) == moves["sample_days"]
        assert calendar["days"][0]["date"] < calendar["days"][-1]["date"]
        assert set(calendar["filing_dates"]) == {
            (date.today() - timedelta(days=30)).isoformat(),
            (date.today() - timedelta(days=120)).isoformat(),
        }
        assert calendar["stdev"] == moves["stdev"]
        assert calendar["mean_return"] == moves["mean_return"]

    def test_second_call_uses_cached_cik_and_items(self, tmp_path):
        requests = []

        def counting_handler(request):
            requests.append(str(request.url))
            return _happy_handler(request)

        db_path = tmp_path / "market_data.sqlite"
        _seed_prices(db_path, "NVDA")
        catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(counting_handler)
        )
        first_call_count = len(requests)
        assert first_call_count == 4

        result = catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(counting_handler)
        )
        assert result["status"] == "ok"
        new_requests = requests[first_call_count:]
        assert [url for url in new_requests if "company_tickers" in url] == []
        assert [url for url in new_requests if "Archives" in url] == []

    def test_unmapped_symbol_returns_insufficient_data(self, tmp_path):
        def handler(request):
            return httpx.Response(200, text=json.dumps({
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            }))

        result = catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=tmp_path / "market_data.sqlite", http_client=_mock_client(handler)
        )
        assert result == {"status": "insufficient_data"}

    def test_edgar_failure_returns_insufficient_data(self, tmp_path):
        def handler(request):
            return httpx.Response(500, text="Server Error")

        result = catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=tmp_path / "market_data.sqlite", http_client=_mock_client(handler)
        )
        assert result == {"status": "insufficient_data"}

    def test_refresh_failure_falls_back_to_cached_filings(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        _seed_prices(db_path, "NVDA")
        catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(_happy_handler)
        )

        def failing_sec_handler(request):
            url = str(request.url)
            if "sec.gov" in url:
                return httpx.Response(500, text="Server Error")
            return _happy_handler(request)

        result = catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(failing_sec_handler)
        )
        assert result["status"] == "ok"
        assert result["filing_frequency"]["total"] == 2
        assert result["calendar"] is not None
        assert len(result["calendar"]["days"]) == 44

    def test_price_failure_keeps_frequency(self, tmp_path):
        def handler(request):
            url = str(request.url)
            if "yahoo" in url or "finance" in url:
                return httpx.Response(500, text="Server Error")
            return _happy_handler(request)

        db_path = tmp_path / "market_data.sqlite"
        result = catalyst_activity.get_catalyst_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(handler)
        )
        assert result["status"] == "ok"
        assert result["filing_frequency"]["total"] == 2
        assert result["large_moves"]["status"] == "insufficient_data"
        assert result["calendar"] is None
