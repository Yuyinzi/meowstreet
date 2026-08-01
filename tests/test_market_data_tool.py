from urllib.error import HTTPError

import httpx
import pytest

from app.http_client import HttpClient
from app.tools import market_data


def chart_payload():
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "XYZ",
                        "regularMarketPrice": 12.34,
                    },
                    "timestamp": [1719792000, 1719878400, 1719964800],
                    "indicators": {
                        "adjclose": [
                            {
                                "adjclose": [10.0, 10.5, 11.0],
                            }
                        ],
                    },
                }
            ],
            "error": None,
        }
    }


def test_fetch_market_data_returns_observation_fields_from_chart_payload(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    payload = market_data.fetch_market_data(
        " xyz ",
        db_path=db_path,
        fetch_json=lambda symbol, period, interval: chart_payload(),
    )

    assert payload == {
        "symbol": "XYZ",
        "metrics": {
            "price": 11.0,
        },
        "prices": {
            "dates": ["2024-07-01", "2024-07-02", "2024-07-03"],
            "adjusted_close": [10.0, 10.5, 11.0],
        },
        "data": {
            "price_series_current": True,
            "uses_adjusted_close": True,
            "no_missing_required_fields": True,
        },
    }


def test_fetch_market_data_rejects_blank_symbol():
    with pytest.raises(ValueError, match="symbol is required"):
        market_data.fetch_market_data(
            "", fetch_json=lambda symbol, period, interval: {}
        )


def test_fetch_market_data_reports_missing_adjusted_close():
    def fetch_json(symbol, period, interval):
        payload = chart_payload()
        payload["chart"]["result"][0]["indicators"] = {"quote": [{}]}
        return payload

    with pytest.raises(ValueError, match="adjusted close data is missing for XYZ"):
        market_data.fetch_market_data("XYZ", fetch_json=fetch_json)


def test_main_prints_market_data_json(capsys):
    exit_code = market_data.main(
        ["xyz", "--period", "1mo", "--interval", "1d"],
        fetch_json=lambda symbol, period, interval: chart_payload(),
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"symbol": "XYZ"' in captured.out
    assert '"adjusted_close": [' in captured.out
    assert captured.err == ""


def test_main_reports_errors(capsys):
    exit_code = market_data.main([""], fetch_json=lambda symbol, period, interval: {})

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "symbol is required\n"


def test_main_reports_provider_http_errors_without_traceback(tmp_path, capsys):
    def fetch_json(symbol, period, interval):
        raise HTTPError(
            url="https://example.test",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    exit_code = market_data.main(
        ["AAPL", "--db-path", str(tmp_path / "market_data.sqlite")],
        fetch_json=fetch_json,
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert (
        captured.err
        == "market data fetch failed for AAPL: HTTP 429 Too Many Requests\n"
    )


def test_chart_payload_to_price_rows_includes_ohlcv_and_adjusted_close():
    rows = market_data.chart_payload_to_price_rows(chart_payload(), "XYZ")

    assert rows == [
        {
            "date": "2024-07-01",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "adjusted_close": 10.0,
            "volume": None,
        },
        {
            "date": "2024-07-02",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "adjusted_close": 10.5,
            "volume": None,
        },
        {
            "date": "2024-07-03",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "adjusted_close": 11.0,
            "volume": None,
        },
    ]


def test_chart_payload_to_price_rows_uses_final_index_metadata_close():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "^GSPC",
                        "instrumentType": "INDEX",
                        "exchangeTimezoneName": "America/New_York",
                        "regularMarketTime": 1784062596,
                        "regularMarketPrice": 7543.59,
                        "currentTradingPeriod": {
                            "regular": {
                                "start": 1784122200,
                                "end": 1784145600,
                            },
                        },
                    },
                    "timestamp": [1783949400, 1784035800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [7547.53, 7536.70],
                                "high": [7565.37, 7557.44],
                                "low": [7506.41, 7513.23],
                                "close": [7515.34, None],
                                "volume": [0, 0],
                            }
                        ],
                        "adjclose": [
                            {
                                "adjclose": [7515.34, None],
                            }
                        ],
                    },
                },
            ],
            "error": None,
        },
    }

    rows = market_data.chart_payload_to_price_rows(payload, "^GSPC")

    assert rows[-1] == {
        "date": "2026-07-14",
        "open": 7536.70,
        "high": 7557.44,
        "low": 7513.23,
        "close": 7543.59,
        "adjusted_close": 7543.59,
        "volume": 0,
    }


def test_fetch_yahoo_chart_json_for_dates_passes_period_timestamps():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"chart": {"result": [], "error": None}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport)

    payload = market_data.fetch_yahoo_chart_json_for_dates(
        "AAPL",
        start_date="2026-06-25",
        end_date="2026-07-02",
        interval="1d",
        http_client=client,
    )

    assert payload == {"chart": {"result": [], "error": None}}
    assert "period1=1782345600" in captured["url"]
    assert "period2=1782950400" in captured["url"]
    assert "interval=1d" in captured["url"]
    assert "events=history" in captured["url"]


def test_fetch_yahoo_chart_json_for_dates_retries_timeouts():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, json={"chart": {"result": [], "error": None}})

    transport = httpx.MockTransport(handler)
    client = HttpClient(transport=transport, sleep=lambda _: None)

    payload = market_data.fetch_yahoo_chart_json_for_dates(
        "AAPL",
        start_date="2026-06-25",
        end_date="2026-07-02",
        interval="1d",
        http_client=client,
    )

    assert payload == {"chart": {"result": [], "error": None}}
    assert len(calls) == 3


def test_fetch_market_data_saves_and_returns_cached_price_rows(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    payload = market_data.fetch_market_data(
        "xyz",
        period="max",
        interval="1d",
        db_path=db_path,
        fetch_json=lambda symbol, period, interval: chart_payload(),
    )

    assert payload["symbol"] == "XYZ"
    assert payload["metrics"]["price"] == 11.0
    assert payload["prices"]["dates"] == ["2024-07-01", "2024-07-02", "2024-07-03"]
    assert payload["prices"]["adjusted_close"] == [10.0, 10.5, 11.0]
    assert payload["data"] == {
        "price_series_current": True,
        "uses_adjusted_close": True,
        "no_missing_required_fields": True,
    }


def test_fetch_market_data_uses_cache_when_recent(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    market_data.fetch_market_data(
        "XYZ",
        period="max",
        interval="1d",
        db_path=db_path,
        fetch_json=lambda symbol, period, interval: chart_payload(),
    )

    def fail_fetch(symbol, period, interval):
        raise AssertionError("fetch_json should not be called for recent cache")

    payload = market_data.fetch_market_data(
        "XYZ",
        period="max",
        interval="1d",
        db_path=db_path,
        today_date="2024-07-04",
        refresh_days=1,
        fetch_json=fail_fetch,
    )

    assert payload["prices"]["dates"] == ["2024-07-01", "2024-07-02", "2024-07-03"]


def test_main_accepts_db_path_and_refresh_options(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"

    exit_code = market_data.main(
        [
            "xyz",
            "--period",
            "max",
            "--interval",
            "1d",
            "--db-path",
            str(db_path),
            "--today-date",
            "2024-07-04",
            "--refresh-days",
            "1",
            "--overlap-days",
            "5",
        ],
        fetch_json=lambda symbol, period, interval: chart_payload(),
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"symbol": "XYZ"' in captured.out
    assert db_path.exists()
    assert captured.err == ""
