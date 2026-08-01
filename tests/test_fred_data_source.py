from datetime import date

import httpx
import pytest

from app.data_sources.fred import FredClient
from app.data_sources.fred import compute_yoy
from app.data_sources.fred import parse_fred_csv
from app.data_sources.fred import quarter_end_for_date
from app.data_sources.fred import resample_to_weekly_sundays
from app.http_client import HttpClient


def test_parse_fred_csv_returns_sorted_non_empty_float_rows(tmp_path):
    csv_path = tmp_path / "DGS10.csv"
    csv_path.write_text(
        "observation_date,DGS10\n2020-12-31,0.93\n2020-12-25,\n2020-12-24,0.94\n",
        encoding="utf-8",
    )

    rows = parse_fred_csv(csv_path, "DGS10")

    assert rows == {
        "2020-12-24": 0.94,
        "2020-12-31": 0.93,
    }


def test_parse_fred_csv_rejects_missing_path(tmp_path):
    with pytest.raises(ValueError, match="fred csv does not exist"):
        parse_fred_csv(tmp_path / "missing.csv", "DGS10")


def test_quarter_end_for_date_converts_fred_quarter_start_dates():
    assert quarter_end_for_date("2025-01-01") == "2025-03-31"
    assert quarter_end_for_date("2025-04-01") == "2025-06-30"
    assert quarter_end_for_date("2025-07-01") == "2025-09-30"
    assert quarter_end_for_date("2025-10-01") == "2025-12-31"


def test_resample_to_weekly_sundays_uses_latest_prior_observation():
    rows = {
        "2020-12-24": 0.94,
        "2020-12-31": 0.93,
        "2021-01-04": 0.92,
    }

    resampled = resample_to_weekly_sundays(rows)

    assert resampled == [
        {"date": "2020-12-27", "value": 0.94},
        {"date": "2021-01-03", "value": 0.93},
    ]


def test_resample_to_weekly_sundays_accepts_explicit_window():
    rows = {
        "2020-12-01": 1.48,
        "2020-12-31": 22.75,
    }

    resampled = resample_to_weekly_sundays(
        rows,
        start_date="2020-12-20",
        end_date="2021-01-03",
    )

    assert resampled == [
        {"date": "2020-12-20", "value": 1.48},
        {"date": "2020-12-27", "value": 1.48},
        {"date": "2021-01-03", "value": 22.75},
    ]


def test_compute_yoy_returns_percent_change_by_same_month_prior_year():
    rows = {
        "2019-12-01": 258.203,
        "2020-12-01": 262.035,
        "2021-01-01": 262.650,
    }

    computed = compute_yoy(rows)

    assert computed == {
        "2019-12-01": None,
        "2020-12-01": 1.48,
        "2021-01-01": None,
    }


def test_fred_client_uses_series_named_csv_path(tmp_path):
    client = FredClient(tmp_path)

    assert client.csv_path("DGS10") == tmp_path / "DGS10.csv"
    assert (
        client.csv_url("DGS10")
        == "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    )


def test_fetch_csv_with_injected_client(tmp_path):
    csv_content = b"observation_date,DGS10\n2020-12-31,0.93\n"

    def _handler(request):
        assert request.headers.get("User-Agent") == "Meowstreet/1.0"
        return httpx.Response(200, content=csv_content)

    transport = httpx.MockTransport(_handler)
    client = FredClient(tmp_path, http_client=HttpClient(transport=transport))
    result = client.fetch_csv("DGS10")

    assert result == tmp_path / "DGS10.csv"
    assert result.read_bytes() == csv_content
