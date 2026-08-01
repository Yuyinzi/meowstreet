import pandas as pd
import pytest

from app.data_sources import dce_iron_ore_sina as sina


def valid_i0_frame():
    return pd.DataFrame(
        [
            {"date": "2026-07-30", "close": 715.0},
            {"date": "2026-07-31", "close": 716.0},
        ]
    )


def test_normalize_sina_i0_daily_emits_close_observations_with_vendor_provenance():
    frame = pd.DataFrame(
        [
            {"date": "2026-07-30", "close": 715.0},
            {"date": "2026-07-31", "close": 716.0},
        ]
    )

    rows = sina.normalize_dce_iron_ore_sina_daily(frame, "2026-08-01T00:00:00+00:00")

    assert rows == [
        {
            "date": "2026-07-30",
            "value": 715.0,
            "source": "sina_finance",
            "source_url": sina.SINA_I0_DAILY_URL,
            "source_identifier": "I0",
            "source_class": "vendor_free_market_data",
            "retrieved_at": "2026-08-01T00:00:00+00:00",
        },
        {
            "date": "2026-07-31",
            "value": 716.0,
            "source": "sina_finance",
            "source_url": sina.SINA_I0_DAILY_URL,
            "source_identifier": "I0",
            "source_class": "vendor_free_market_data",
            "retrieved_at": "2026-08-01T00:00:00+00:00",
        },
    ]
    assert sina._DCE_IRON_ORE_SINA_SERIES["source_contract"]["roll_rule"] == (
        "undocumented"
    )


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(columns=["date"]),
        pd.DataFrame([{"date": "bad-date", "close": 715.0}]),
        pd.DataFrame([{"date": "2026-07-31", "close": None}]),
    ],
)
def test_normalize_sina_i0_daily_rejects_invalid_or_empty_close_data(frame):
    with pytest.raises(ValueError):
        sina.normalize_dce_iron_ore_sina_daily(frame, "2026-08-01T00:00:00+00:00")


def test_fetch_sina_i0_calls_injected_adapter_with_i0():
    calls = []
    payload = sina.fetch_dce_iron_ore_sina(
        adapter=lambda symbol: calls.append(symbol) or valid_i0_frame()
    )

    assert calls == ["I0"]
    assert payload["series"]["series_id"] == "iron_ore_dce"
    assert [row["value"] for row in payload["observations"]] == [715.0, 716.0]
