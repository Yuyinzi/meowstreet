from datetime import date

import pytest

from app.data_sources.tracked_commodities import MARKET_SERIES
from app.tools import cross_market_spreads


def wti_row(day, value, **extra):
    return {"date": day, "value": value, **extra}


def brent_row(day, value, **extra):
    return {"date": day, "value": value, **extra}


def _oil_rows(days=("2026-07-22", "2026-07-23", "2026-07-24")):
    return {
        "wti": [wti_row(day, 64.89) for day in days],
        "brent": [brent_row(day, 70.5) for day in days],
    }


def _copper_metadata():
    return {
        "copper_comex": {
            "instrument": "Copper High Grade futures (HG)",
            "units": "USD/lb",
            "source_vendor": "Investing.com rendered-history",
            "field": "close",
            "price_basis": "vendor_continuous_series",
            "roll_rule_documented": False,
        },
        "copper_lme": {
            "instrument": "LME Copper Grade A",
            "units": "USD/tonne",
            "source_vendor": "Investing.com rendered-history",
            "field": "close",
            "price_basis": "vendor_continuous_series",
            "roll_rule_documented": False,
        },
        "copper_shanghai": {
            "instrument": "SHFE Copper main contract (OI-selected)",
            "units": "CNY/tonne",
        },
    }


def _copper_rows():
    return {
        "copper_comex": [wti_row("2026-07-24", 4.5)],
        "copper_lme": [wti_row("2026-07-24", 9500.0)],
        "copper_shanghai": [wti_row("2026-07-24", 78000.0)],
    }


def _build(**kwargs):
    rows = _oil_rows()
    defaults = {
        "wti_rows": rows["wti"],
        "brent_rows": rows["brent"],
        "copper_market_metadata": _copper_metadata(),
        "copper_market_rows": _copper_rows(),
        "as_of_date": "2026-07-25",
    }
    defaults.update(kwargs)
    return cross_market_spreads.build_cross_market_spreads(**defaults)


def _brent_wti(payload):
    return next(s for s in payload["spreads"] if s["spread_id"] == "brent_wti_spot")


def _copper_entry(payload, spread_id):
    return next(s for s in payload["spreads"] if s["spread_id"] == spread_id)


def test_method_version_and_fixed_spread_order():
    payload = _build()

    assert payload["method_version"] == "cross_market_spreads_v1"
    assert [s["spread_id"] for s in payload["spreads"]] == [
        "brent_wti_spot",
        "lme_comex_copper",
        "shfe_lme_copper",
        "shfe_comex_copper",
    ]


def test_available_brent_wti_returns_positive_spread_with_provenance():
    payload = _build()

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(5.61)
    assert spread["unit"] == "USD/BBL"
    assert spread["expression"] == "brent_price - wti_price"
    assert spread["label"] == "Date-aligned daily price spread"
    assert spread["common_observation_date"] == "2026-07-24"
    assert spread["legs"]["brent"]["value"] == 70.5
    assert spread["legs"]["brent"]["source_series"] == "oil_brent_spot"
    assert spread["legs"]["brent"]["price_type"] == "spot"
    assert spread["legs"]["brent"]["unit"] == "USD/BBL"
    assert spread["legs"]["wti"]["value"] == 64.89
    assert spread["legs"]["wti"]["source_series"] == "oil_wti_spot"
    assert spread["legs"]["wti"]["price_type"] == "spot"
    assert spread["legs"]["wti"]["unit"] == "USD/BBL"


def test_available_brent_wti_preserves_source_identifier_and_url():
    payload = _build(
        wti_rows=[
            wti_row(
                "2026-07-24",
                64.89,
                source_identifier="RWTC",
                source_url="https://eia.test",
            )
        ],
        brent_rows=[
            brent_row(
                "2026-07-24",
                70.5,
                source_identifier="RBRTE",
                source_url="https://eia.test",
            )
        ],
    )

    spread = _brent_wti(payload)
    assert spread["legs"]["wti"]["source_identifier"] == "RWTC"
    assert spread["legs"]["wti"]["source_url"] == "https://eia.test"
    assert spread["legs"]["brent"]["source_identifier"] == "RBRTE"
    assert spread["legs"]["brent"]["source_url"] == "https://eia.test"


def test_available_brent_wti_returns_negative_spread():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 75.0)],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(-5.0)


def test_available_brent_wti_returns_zero_spread():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 70.0)],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(0.0)


def test_exact_date_selection_uses_latest_shared_date():
    payload = _build(
        wti_rows=[
            wti_row("2026-07-21", 63.0),
            wti_row("2026-07-22", 64.0),
            wti_row("2026-07-23", 65.0),
        ],
        brent_rows=[
            brent_row("2026-07-21", 68.0),
            brent_row("2026-07-22", 69.0),
            brent_row("2026-07-23", 71.0),
        ],
    )

    spread = _brent_wti(payload)
    assert spread["common_observation_date"] == "2026-07-23"
    assert spread["value"] == pytest.approx(6.0)
    assert spread["legs"]["brent"]["value"] == 71.0
    assert spread["legs"]["wti"]["value"] == 65.0


def test_as_of_filtering_discards_observations_after_as_of():
    payload = _build(
        wti_rows=[
            wti_row("2026-07-23", 64.0),
            wti_row("2026-07-26", 66.0),
        ],
        brent_rows=[
            brent_row("2026-07-23", 70.0),
            brent_row("2026-07-26", 72.0),
        ],
        as_of_date="2026-07-25",
    )

    spread = _brent_wti(payload)
    assert spread["common_observation_date"] == "2026-07-23"
    assert spread["value"] == pytest.approx(6.0)


def test_future_rows_are_discarded_never_become_common_date():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 64.0), wti_row("2026-07-28", 66.0)],
        brent_rows=[brent_row("2026-07-24", 70.0)],
        as_of_date="2026-07-25",
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["common_observation_date"] == "2026-07-24"
    assert spread["value"] == pytest.approx(6.0)


def test_missing_wti_rows_is_unavailable_with_reason():
    payload = _build(
        wti_rows=[],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "missing_wti_price"
    assert "value" not in spread
    assert spread["legs"]["wti"]["source_series"] == "oil_wti_spot"
    assert "value" not in spread["legs"]["wti"]


def test_missing_brent_rows_is_unavailable_with_reason():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 64.0)],
        brent_rows=[],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "missing_brent_price"


def test_no_exact_common_date_is_unavailable():
    payload = _build(
        wti_rows=[wti_row("2026-07-23", 64.0)],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "no_common_observation_date"
    assert "value" not in spread
    assert "common_observation_date" not in spread


def test_duplicate_rows_keep_last_observation_per_date():
    payload = _build(
        wti_rows=[
            wti_row("2026-07-24", 60.0),
            wti_row("2026-07-24", 64.0),
        ],
        brent_rows=[
            brent_row("2026-07-24", 66.0),
            brent_row("2026-07-24", 70.0),
        ],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(6.0)
    assert spread["legs"]["wti"]["value"] == 64.0
    assert spread["legs"]["brent"]["value"] == 70.0


def test_invalid_rows_are_discarded():
    payload = _build(
        wti_rows=[
            {"date": "not-a-date", "value": 64.0},
            {"date": "2026-07-24", "value": "not-numeric"},
            wti_row("2026-07-24", 64.0),
        ],
        brent_rows=[
            {"date": "2026-07-24", "value": None},
            brent_row("2026-07-24", 70.0),
        ],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(6.0)


def test_non_finite_wti_rows_are_discarded():
    payload = _build(
        wti_rows=[
            {"date": "2026-07-24", "value": "nan"},
            {"date": "2026-07-24", "value": "inf"},
            wti_row("2026-07-24", 64.0),
        ],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(6.0)


def test_non_finite_brent_rows_are_discarded():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 64.0)],
        brent_rows=[
            {"date": "2026-07-24", "value": "nan"},
            brent_row("2026-07-24", 70.0),
        ],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "available"
    assert spread["value"] == pytest.approx(6.0)


def test_leg_with_only_non_finite_rows_is_missing():
    payload = _build(
        wti_rows=[{"date": "2026-07-24", "value": "inf"}],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "missing_wti_price"


def test_never_exposes_non_finite_spread_value():
    payload = _build(
        wti_rows=[{"date": "2026-07-24", "value": "nan"}],
        brent_rows=[{"date": "2026-07-24", "value": "inf"}],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "missing_brent_price"
    assert "value" not in spread
    assert "common_observation_date" not in spread


def test_unit_mismatch_is_unavailable():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 64.0, units="CNY/tonne")],
        brent_rows=[brent_row("2026-07-24", 70.0)],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "unit_mismatch"


def test_price_type_mismatch_is_unavailable():
    payload = _build(
        wti_rows=[wti_row("2026-07-24", 64.0)],
        brent_rows=[brent_row("2026-07-24", 70.0, price_type="futures")],
    )

    spread = _brent_wti(payload)
    assert spread["status"] == "unavailable"
    assert spread["reason"] == "price_type_mismatch"


def test_invalid_as_of_date_raises_value_error():
    with pytest.raises(ValueError, match="invalid as-of date"):
        _build(as_of_date="not-a-date")


def test_repeated_inputs_produce_byte_identical_payload():
    kwargs = {
        "wti_rows": _oil_rows()["wti"],
        "brent_rows": _oil_rows()["brent"],
        "copper_market_metadata": _copper_metadata(),
        "copper_market_rows": _copper_rows(),
        "as_of_date": "2026-07-25",
    }

    first = cross_market_spreads.build_cross_market_spreads(**kwargs)
    second = cross_market_spreads.build_cross_market_spreads(**kwargs)

    assert first == second


def test_lme_comex_copper_is_fixed_unavailable():
    payload = _build()

    entry = _copper_entry(payload, "lme_comex_copper")
    assert entry["status"] == "unavailable"
    assert entry["reason"] == "incomparable_price_basis"
    assert "value" not in entry
    legs = {leg["side"]: leg for leg in entry["legs"]}
    assert legs["lme"]["source_series"] == "copper_lme"
    assert legs["lme"]["unit"] == "USD/tonne"
    assert legs["comex"]["source_series"] == "copper_comex"
    assert legs["comex"]["unit"] == "USD/lb"


def test_shfe_pairs_are_fixed_unavailable_with_fx_reason():
    payload = _build()

    for spread_id in ("shfe_lme_copper", "shfe_comex_copper"):
        entry = _copper_entry(payload, spread_id)
        assert entry["status"] == "unavailable"
        assert entry["reason"] == "fx_source_not_approved"
        assert "value" not in entry
        legs = {leg["side"]: leg for leg in entry["legs"]}
        assert legs["shfe"]["source_series"] == "copper_shanghai"
        assert legs["shfe"]["unit"] == "CNY/tonne"


def test_copper_entries_include_latest_date_when_rows_available():
    payload = _build()

    entry = _copper_entry(payload, "lme_comex_copper")
    legs = {leg["side"]: leg for leg in entry["legs"]}
    assert legs["lme"]["latest_date"] == "2026-07-24"
    assert legs["comex"]["latest_date"] == "2026-07-24"


def test_copper_entries_omit_latest_date_without_rows():
    payload = _build(copper_market_rows={})

    entry = _copper_entry(payload, "lme_comex_copper")
    legs = {leg["side"]: leg for leg in entry["legs"]}
    assert "latest_date" not in legs["lme"]
    assert "latest_date" not in legs["comex"]


def test_copper_entries_keep_series_ids_without_metadata():
    payload = _build(copper_market_metadata=None)

    entry = _copper_entry(payload, "lme_comex_copper")
    legs = {leg["side"]: leg for leg in entry["legs"]}
    assert legs["lme"]["source_series"] == "copper_lme"
    assert "unit" not in legs["lme"]
    assert "instrument" not in legs["lme"]


def test_copper_entries_never_expose_numerical_spread():
    payload = _build()

    for spread_id in ("lme_comex_copper", "shfe_lme_copper", "shfe_comex_copper"):
        entry = _copper_entry(payload, spread_id)
        assert "value" not in entry
        for leg in entry["legs"]:
            assert "value" not in leg


def test_copper_metadata_exposes_frozen_source_contract():
    for series_id in ("copper_comex", "copper_lme"):
        entry = MARKET_SERIES[series_id]
        assert entry["source_vendor"] == "Investing.com rendered-history"
        assert entry["field"] == "close"
        assert entry["price_basis"] == "vendor_continuous_series"
        assert entry["roll_rule_documented"] is False

    metadata = _copper_metadata()
    assert metadata["copper_comex"]["units"] == "USD/lb"
    assert metadata["copper_lme"]["units"] == "USD/tonne"
