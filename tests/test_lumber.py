import httpx
import pytest

from app.data_sources import lumber
from app.http_client import HttpClient


def yahoo_chart_payload():
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [1659916800, 1660003200, 1660089600],
                    "indicators": {
                        "quote": [
                            {
                                "close": [621.0, 622.0, 625.0],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def pre_start_chart_payload():
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [1659657600, 1659916800],
                    "indicators": {
                        "quote": [
                            {
                                "close": [610.0, 621.0],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def missing_close_chart_payload():
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [1659916800, 1660003200],
                    "indicators": {
                        "quote": [
                            {
                                "close": [None, None],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_fetch_lumber_series_requests_lbr_daily_history():
    calls = []
    payload = lumber.fetch_lumber_series(
        "2022-08-08",
        "2022-08-11",
        fetch_chart=lambda symbol, start_date, end_date, interval, http_client: (
            calls.append((symbol, start_date, end_date, interval))
            or yahoo_chart_payload()
        ),
    )
    assert calls == [("LBR=F", "2022-08-08", "2022-08-11", "1d")]
    assert payload["series"]["series_id"] == "lumber_cme_lbr_yahoo_v1"
    assert payload["observations"][0]["value"] == 621.0
    assert payload["observations"][0]["source"] == "yahoo_finance"


def test_normalize_lumber_chart_rejects_pre_lbr_or_missing_close_rows():
    with pytest.raises(ValueError, match="before 2022-08-08"):
        lumber.normalize_lumber_chart(
            pre_start_chart_payload(), "2026-07-31T00:00:00+00:00"
        )
    with pytest.raises(ValueError, match="close data is missing for LBR=F"):
        lumber.normalize_lumber_chart(
            missing_close_chart_payload(), "2026-07-31T00:00:00+00:00"
        )


def test_fetch_lumber_series_uses_http_client_compatible_yahoo_request():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=yahoo_chart_payload())

    client = HttpClient(transport=httpx.MockTransport(handler))
    lumber.fetch_lumber_series("2026-07-20", "2026-07-31", http_client=client)
    assert "LBR%3DF" in captured["url"]
    assert "interval=1d" in captured["url"]


def test_normalize_lumber_chart_requires_matching_timestamp_and_close_lengths():
    payload = yahoo_chart_payload()
    payload["chart"]["result"][0]["timestamp"] = [1659916800]
    with pytest.raises(ValueError, match="lengths differ for LBR=F"):
        lumber.normalize_lumber_chart(payload, "2026-07-31T00:00:00+00:00")


def test_normalize_lumber_chart_rejects_non_list_chart_result():
    payload = {"chart": {"result": None, "error": None}}
    with pytest.raises(ValueError, match="chart result is missing for LBR=F"):
        lumber.normalize_lumber_chart(payload, "2026-07-31T00:00:00+00:00")
