from urllib.error import HTTPError

import pytest

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


def test_fetch_market_data_returns_observation_fields_from_chart_payload():
    payload = market_data.fetch_market_data(
        " xyz ",
        fetch_json=lambda symbol, period, interval: chart_payload(),
    )

    assert payload == {
        "symbol": "XYZ",
        "metrics": {
            "price": 12.34,
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
        market_data.fetch_market_data("", fetch_json=lambda symbol, period, interval: {})


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


def test_main_reports_provider_http_errors_without_traceback(capsys):
    def fetch_json(symbol, period, interval):
        raise HTTPError(
            url="https://example.test",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    exit_code = market_data.main(["AAPL"], fetch_json=fetch_json)

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "market data fetch failed for AAPL: HTTP 429 Too Many Requests\n"


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
