import pandas as pd
import pytest

from app.data_sources import lme_copper


def valid_cad_frame():
    return pd.DataFrame(
        [
            {"date": "2026-07-30", "close": 13745.72, "volume": 1},
            {"date": "2026-07-31", "close": 13803.0, "volume": 2},
        ]
    )


def test_cad_series_contract_is_lme_three_month_vendor_close():
    series = lme_copper._LME_COPPER_SERIES
    assert series["series_id"] == "copper_lme_sina_cad_v1"
    assert series["units"] == "USD/tonne"
    assert series["source"] == "sina_finance"
    assert series["source_identifier"] == "CAD"
    assert series["source_contract"] == {
        "instrument": "LME Copper 3-month",
        "symbol": "CAD",
        "source_publisher": "Sina Finance",
        "access_adapter": "akshare",
        "series_type": "vendor_continuous_3_month_quote",
        "roll_rule": "undocumented",
        "price_field": "close",
        "price_adjustment": "none",
        "official_settlement": False,
        "cutover_date": "2026-07-31",
    }


def test_normalizer_keeps_only_valid_cad_close_rows():
    frame = pd.DataFrame(
        [
            {"date": "2026-07-30", "close": 13745.72, "volume": 1},
            {"date": "2026-07-31", "close": 13803.0, "volume": 2},
        ]
    )
    assert lme_copper.normalize_lme_copper_cad_daily(
        frame, "2026-08-01T00:00:00+00:00", "1.18.81"
    ) == [
        {
            "date": "2026-07-30",
            "value": 13745.72,
            "source": "sina_finance",
            "source_url": lme_copper.SINA_CAD_DAILY_URL,
            "source_identifier": "CAD",
            "source_class": "vendor_free_market_data",
            "retrieved_at": "2026-08-01T00:00:00+00:00",
            "access_adapter_version": "1.18.81",
        },
        {
            "date": "2026-07-31",
            "value": 13803.0,
            "source": "sina_finance",
            "source_url": lme_copper.SINA_CAD_DAILY_URL,
            "source_identifier": "CAD",
            "source_class": "vendor_free_market_data",
            "retrieved_at": "2026-08-01T00:00:00+00:00",
            "access_adapter_version": "1.18.81",
        },
    ]


@pytest.mark.parametrize(
    "frame, message",
    [
        (pd.DataFrame(), "sina CAD frame has no rows"),
        (pd.DataFrame([{"date": "2026-07-31", "close": None}]), "invalid close"),
        (
            pd.DataFrame(
                [{"date": "2026-07-31", "close": 1}, {"date": "2026-07-31", "close": 2}]
            ),
            "duplicates date",
        ),
    ],
)
def test_normalizer_rejects_invalid_frames(frame, message):
    with pytest.raises(ValueError, match=message):
        lme_copper.normalize_lme_copper_cad_daily(frame, "retrieved", "1.18.81")


def test_normalizer_accepts_pandas_datetime_dates():
    import numpy as np

    frame = pd.DataFrame(
        [
            {"date": pd.Timestamp("2026-07-31"), "close": 13803.0},
            {"date": np.datetime64("2026-08-03"), "close": 13810.0},
        ]
    )
    rows = lme_copper.normalize_lme_copper_cad_daily(frame, "retrieved", "1.18.81")
    assert [row["date"] for row in rows] == ["2026-07-31", "2026-08-03"]


def test_fetch_cad_calls_injected_adapter_with_cad_symbol():
    calls = []
    payload = lme_copper.fetch_lme_copper_cad(
        adapter=lambda symbol: calls.append(symbol) or valid_cad_frame()
    )

    assert calls == ["CAD"]
    assert payload["series"]["series_id"] == "copper_lme_sina_cad_v1"
    assert [row["value"] for row in payload["observations"]] == [13745.72, 13803.0]
    assert [row["access_adapter_version"] for row in payload["observations"]] == [
        "test-adapter",
        "test-adapter",
    ]


def test_fetch_cad_wraps_adapter_failures_as_value_error():
    class AdapterFailure(RuntimeError):
        pass

    with pytest.raises(ValueError, match="sina CAD fetch failed") as excinfo:
        lme_copper.fetch_lme_copper_cad(
            adapter=lambda symbol: (_ for _ in ()).throw(
                AdapterFailure("connection refused")
            )
        )

    assert isinstance(excinfo.value.__cause__, AdapterFailure)
