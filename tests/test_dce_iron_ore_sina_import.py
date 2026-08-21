import pandas as pd
import pytest

from app.data_sources import dce_iron_ore_sina as sina
from app.db import macro_indicators
from app.services import dce_iron_ore_sina_import as importer


def valid_i0_frame():
    return pd.DataFrame(
        [
            {"date": "2026-07-30", "close": 715.0},
            {"date": "2026-07-31", "close": 716.0},
        ]
    )


def valid_payload():
    return sina.fetch_dce_iron_ore_sina(adapter=lambda symbol: valid_i0_frame())


def invalid_payload():
    return {
        "series": sina.DCE_IRON_ORE_SINA_SERIES,
        "observations": [],
    }


def seeded_connection(tmp_path, latest_date):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    payload = valid_payload()
    observations = [
        row for row in payload["observations"] if row["date"] == latest_date
    ]
    macro_indicators.merge_macro_indicator_observations(
        con, payload["series"], observations
    )
    return con


def latest_value(con, series_id):
    return macro_indicators.load_macro_indicator_observations(con, series_id)[-1][
        "value"
    ]


def test_initial_refresh_persists_i0_observations_and_contract(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")

    result = importer.refresh_dce_iron_ore_sina(
        con,
        today_date="2026-08-01",
        initial=True,
        fetcher=lambda start, end: valid_payload(),
    )

    assert result == {
        "series": "iron_ore_dce",
        "observations": 2,
        "start_date": "2013-10-18",
        "end_date": "2026-08-02",
    }
    assert (
        macro_indicators.load_macro_indicator_observations(con, "iron_ore_dce")[-1][
            "source_identifier"
        ]
        == "I0"
    )


def test_incremental_refresh_requests_a_fourteen_day_overlap(tmp_path):
    con = seeded_connection(tmp_path, latest_date="2026-07-31")
    received = []

    importer.refresh_dce_iron_ore_sina(
        con,
        today_date="2026-08-01",
        fetcher=lambda start, end: received.append((start, end)) or valid_payload(),
    )

    assert received == [("2026-07-17", "2026-08-02")]


def test_refresh_rolls_back_when_source_has_no_valid_observations(tmp_path):
    con = seeded_connection(tmp_path, latest_date="2026-07-31")

    with pytest.raises(ValueError, match="sina I0 returned no valid"):
        importer.refresh_dce_iron_ore_sina(
            con, fetcher=lambda start, end: invalid_payload()
        )

    assert latest_value(con, "iron_ore_dce") == 716.0
