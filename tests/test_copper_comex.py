import httpx
import pytest

from app.data_sources import copper_comex
from app.http_client import HttpClient


def yahoo_chart_payload():
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [967593600, 967680000, 967766400],
                    "indicators": {
                        "quote": [
                            {
                                "close": [0.84, 0.85, 0.85],
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
                    "timestamp": [967507200, 967593600],
                    "indicators": {
                        "quote": [
                            {
                                "close": [0.83, 0.84],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def all_null_close_chart_payload():
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [967593600, 967680000],
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


def test_fetch_copper_comex_series_requests_hg_daily_close():
    calls = []
    payload = copper_comex.fetch_copper_comex_series(
        "2000-08-30",
        "2000-09-02",
        fetch_chart=lambda symbol, start_date, end_date, interval, http_client: (
            calls.append((symbol, start_date, end_date, interval))
            or yahoo_chart_payload()
        ),
    )
    assert calls == [("HG=F", "2000-08-30", "2000-09-02", "1d")]
    assert payload["series"]["series_id"] == "copper_comex_hg_yahoo_v1"
    assert payload["observations"][0]["value"] == 0.84
    assert payload["observations"][0]["source"] == "yahoo_finance"


def test_normalize_copper_chart_rejects_pre_start_or_all_null_close_rows():
    with pytest.raises(ValueError, match="before 2000-08-30"):
        copper_comex.normalize_copper_comex_chart(
            pre_start_chart_payload(), "2026-08-01T00:00:00+00:00"
        )
    with pytest.raises(ValueError, match="close data is missing for HG=F"):
        copper_comex.normalize_copper_comex_chart(
            all_null_close_chart_payload(), "2026-08-01T00:00:00+00:00"
        )


def test_fetch_copper_comex_series_uses_http_client_compatible_yahoo_request():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json=yahoo_chart_payload())

    client = HttpClient(transport=httpx.MockTransport(handler))
    copper_comex.fetch_copper_comex_series(
        "2000-08-30", "2000-09-02", http_client=client
    )
    assert "HG%3DF" in captured["url"]
    assert "interval=1d" in captured["url"]


def test_normalize_copper_chart_requires_matching_timestamp_and_close_lengths():
    payload = yahoo_chart_payload()
    payload["chart"]["result"][0]["timestamp"] = [967593600]
    with pytest.raises(ValueError, match="lengths differ for HG=F"):
        copper_comex.normalize_copper_comex_chart(
            payload, "2026-08-01T00:00:00+00:00"
        )


def test_normalize_copper_chart_rejects_non_list_chart_result():
    payload = {"chart": {"result": None, "error": None}}
    with pytest.raises(ValueError, match="chart result is missing for HG=F"):
        copper_comex.normalize_copper_comex_chart(
            payload, "2026-08-01T00:00:00+00:00"
        )
