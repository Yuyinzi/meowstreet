import math

import pytest

from app.db import macro_indicators
from app.services import oil_import


def _fake_fetcher(api_key, **kwargs):
    return {
        "oil_wti_spot": {
            "series": {
                "series_id": "oil_wti_spot",
                "title": "WTI Spot Price",
                "units": "$/BBL",
                "source": "eia",
            },
            "observations": [
                {
                    "date": "2026-07-24",
                    "value": 64.89,
                    "source": "eia",
                    "release_date": None,
                    "publication_date_basis": "unavailable",
                    "revision_status": "not_supplied",
                    "source_url": "https://api.eia.gov/v2/petroleum/pri/spt/data/",
                    "source_identifier": "RWTC",
                }
            ],
        },
        "oil_commercial_crude_stocks": {
            "series": {
                "series_id": "oil_commercial_crude_stocks",
                "title": "Inventory",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_commercial_crude_imports": {
            "series": {
                "series_id": "oil_commercial_crude_imports",
                "title": "Commercial crude imports",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_crude_production": {
            "series": {
                "series_id": "oil_crude_production",
                "title": "U.S. crude production",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_refinery_crude_input": {
            "series": {
                "series_id": "oil_refinery_crude_input",
                "title": "Refinery crude input",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_brent_spot": {
            "series": {
                "series_id": "oil_brent_spot",
                "title": "Brent Spot Price",
                "units": "$/BBL",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_petroleum_products_supplied": {
            "series": {
                "series_id": "oil_petroleum_products_supplied",
                "title": "Petroleum products supplied",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
    }


def _partial_write_fetcher(api_key, **kwargs):
    return {
        "oil_wti_spot": {
            "series": {
                "series_id": "oil_wti_spot",
                "title": "WTI Spot Price",
                "units": "$/BBL",
                "source": "eia",
            },
            "observations": [
                {
                    "date": "2026-07-24",
                    "value": 64.89,
                    "source": "eia",
                    "release_date": None,
                    "publication_date_basis": "unavailable",
                    "revision_status": "not_supplied",
                    "source_url": "https://api.eia.gov/v2/petroleum/pri/spt/data/",
                    "source_identifier": "RWTC",
                }
            ],
        },
        "oil_brent_spot": {
            "series": {
                "series_id": "oil_brent_spot",
                "title": "Brent Spot Price",
                "units": "$/BBL",
                "source": "eia",
            },
            "observations": [
                {
                    "date": "2026-07-24",
                    "value": 71.0,
                    "source": "eia",
                    "release_date": None,
                    "publication_date_basis": "unavailable",
                    "revision_status": "not_supplied",
                    "source_url": "https://api.eia.gov/v2/petroleum/pri/spt/data/",
                    "source_identifier": "RBRTE",
                }
            ],
        },
        "oil_commercial_crude_stocks": {
            "series": {
                "series_id": "oil_commercial_crude_stocks",
                "title": "Inventory",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_commercial_crude_imports": {
            "series": {
                "series_id": "oil_commercial_crude_imports",
                "title": "Commercial crude imports",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_crude_production": {
            "series": {
                "series_id": "oil_crude_production",
                "title": "U.S. crude production",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_refinery_crude_input": {
            "series": {
                "series_id": "oil_refinery_crude_input",
                "title": "Refinery crude input",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [],
        },
        "oil_petroleum_products_supplied": {
            "series": {
                "series_id": "oil_petroleum_products_supplied",
                "title": "Petroleum products supplied",
                "units": "eia_units",
                "source": "eia",
            },
            "observations": [
                {
                    "date": "2026-07-17",
                    "value": math.nan,
                    "source": "eia",
                    "release_date": None,
                    "publication_date_basis": "unavailable",
                    "revision_status": "not_supplied",
                    "source_url": "https://api.eia.gov/v2/petroleum/sum/sndw/data/",
                    "source_identifier": "WRPUPUS2",
                }
            ],
        },
    }


def _invalid_fetcher(api_key, **kwargs):
    raise ValueError("eia observation value is invalid")


def test_refresh_official_oil_merges_metadata_and_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    result = oil_import.refresh_official_oil(
        con, "test-key", fetcher=_fake_fetcher
    )

    assert result == {"series": 7, "observations": 1}
    rows = macro_indicators.load_macro_indicator_observations(con, "oil_wti_spot")
    assert rows[0]["source_identifier"] == "RWTC"
    assert rows[0]["release_date"] is None
    assert rows[0]["publication_date_basis"] == "unavailable"


def test_refresh_official_oil_rolls_back_all_rows_on_invalid_series(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")

    with pytest.raises(ValueError, match="eia observation value is invalid"):
        oil_import.refresh_official_oil(
            con, "test-key", fetcher=_invalid_fetcher
        )

    assert macro_indicators.load_macro_indicator_points(con, "oil_wti_spot") == []


def test_refresh_official_oil_rolls_back_after_partial_write(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")

    with pytest.raises(Exception):
        oil_import.refresh_official_oil(
            con, "test-key", fetcher=_partial_write_fetcher
        )

    first_series_points = macro_indicators.load_macro_indicator_points(
        con, "oil_wti_spot"
    )
    assert first_series_points == [], "wti observations should be rolled back"
    last_series_points = macro_indicators.load_macro_indicator_points(
        con, "oil_petroleum_products_supplied"
    )
    assert last_series_points == [], (
        "products supplied observations should be rolled back"
    )


def test_incremental_refresh_passes_price_start_date_for_fourteen_day_overlap(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "oil_wti_spot",
            "title": "WTI Spot Price",
            "units": "$/BBL",
            "source": "eia",
        },
        [{"date": "2026-07-24", "value": 70.0, "source": "eia"}],
    )
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "oil_brent_spot",
            "title": "Brent Spot Price",
            "units": "$/BBL",
            "source": "eia",
        },
        [{"date": "2026-07-24", "value": 71.0, "source": "eia"}],
    )

    captured_kwargs = {}

    def spy_fetcher(api_key, **kwargs):
        captured_kwargs.update(kwargs)
        return _fake_fetcher(api_key, **kwargs)

    oil_import.refresh_official_oil(
        con, "test-key", fetcher=spy_fetcher, full_price_history=False
    )

    assert captured_kwargs.get("price_start_date") == "2026-07-10"
    assert "full_price_history" not in captured_kwargs


def test_full_history_refresh_passes_full_price_history_flag(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")

    captured_kwargs = {}

    def spy_fetcher(api_key, **kwargs):
        captured_kwargs.update(kwargs)
        return _fake_fetcher(api_key, **kwargs)

    oil_import.refresh_official_oil(
        con, "test-key", fetcher=spy_fetcher, full_price_history=True
    )

    assert captured_kwargs.get("full_price_history") is True
    assert "price_start_date" not in captured_kwargs
