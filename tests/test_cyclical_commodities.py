import pytest

from app.tools import cyclical_commodities as 

COT_ROWS = [
    {
        "commodity_id": "crude_oil_wti",
        "report_date": "2026-07-14",
        "manager_longs": 180000.0,
        "manager_shorts": 200000.0,
        "open_interest": 1000000.0,
        "publication_date": "2026-07-17",
    },
    {
        "commodity_id": "crude_oil_wti",
        "report_date": "2026-07-21",
        "manager_longs": 200000.0,
        "manager_shorts": 150000.0,
        "open_interest": 1000000.0,
        "publication_date": "2026-07-24",
    },
    {
        "commodity_id": "copper",
        "report_date": "2026-07-21",
        "manager_longs": 100000.0,
        "manager_shorts": 90000.0,
        "open_interest": 500000.0,
        "publication_date": "2026-07-24",
    },
]

USD_ROWS = {
    "usd_broad": [
        {"date": "2026-07-13", "value": 118.0, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-14", "value": 118.5, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-15", "value": 119.0, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-16", "value": 119.2, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-17", "value": 119.3, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-20", "value": 119.5, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-21", "value": 120.0, "source_identifier": "DTWEXBGS"},
    ],
    "usd_afe": [
        {"date": "2026-07-13", "value": 104.0, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-14", "value": 104.2, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-15", "value": 104.5, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-16", "value": 104.6, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-17", "value": 104.8, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-20", "value": 105.0, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-21", "value": 105.5, "source_identifier": "DTWEXAFEGS"},
    ],
    "usd_eme": [
        {"date": "2026-07-13", "value": 94.0, "source_identifier": "DTWEXEMEGS"},
        {"date": "2026-07-14", "value": 94.1, "source_identifier": "DTWEXEMEGS"},
        {"date": "2026-07-15", "value": 94.3, "source_identifier": "DTWEXEMEGS"},
        {"date": "2026-07-16", "value": 94.5, "source_identifier": "DTWEXEMEGS"},
        {"date": "2026-07-17", "value": 94.7, "source_identifier": "DTWEXEMEGS"},
        {"date": "2026-07-20", "value": 95.0, "source_identifier": "DTWEXEMEGS"},
        {"date": "2026-07-21", "value": 95.2, "source_identifier": "DTWEXEMEGS"},
    ],
    "cpi_all_items": [
        {"date": "2026-06-01", "value": 330.0, "source_identifier": "CPIAUCSL"},
        {"date": "2026-07-01", "value": 332.568, "source_identifier": "CPIAUCSL"},
    ],
    "core_cpi": [
        {"date": "2026-06-01", "value": 310.0, "source_identifier": "CPILFESL"},
        {"date": "2026-07-01", "value": 312.0, "source_identifier": "CPILFESL"},
    ],
    "ppi_all_commodities": [
        {"date": "2026-06-01", "value": 200.0, "source_identifier": "PPIACO"},
        {"date": "2026-07-01", "value": 201.5, "source_identifier": "PPIACO"},
    ],
}


def test_normalized_manager_position_and_positive_flip_are_computed_from_adjacent_weeks():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    wti = payload["cot"]["crude_oil_wti"]

    assert wti["normalized_manager_net_position"] == 0.05
    assert wti["flip"] == "positive"


def test_never_exposes_extreme_or_distribution_conclusions():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )

    assert payload["cot"]["crude_oil_wti"]["extreme"] == "not_configured"
    assert payload["usd"]["usd_broad"]["distribution_status"] == "not_configured"
    assert (
        payload["inflation"]["cpi_all_items"]["distribution_status"]
        == "not_configured"
    )


def test_commodity_attribution_is_unavailable():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )

    assert payload["commodity_attribution"]["status"] == "unavailable"


def test_card_is_always_present_even_without_data():
    payload = .build_cyclical_commodities_payload([], {}, None, "2026-07-25")
    card = .build_cyclical_commodities_headline(payload)

    assert card["id"] == "cyclical_commodities"
    assert card["status"] == "partial_official_evidence"


def test_card_includes_freshness_metadata_with_available_evidence():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    card = .build_cyclical_commodities_headline(payload)

    assert "cftc_latest" in card["freshness"]
    assert "usd_latest" in card["freshness"]
    assert "inflation_latest" in card["freshness"]


def test_detail_has_five_steps_in_correct_order():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["detail_id"] == "cyclical_commodities"
    assert len(detail["steps"]) == 7
    assert detail["steps"][0]["title"] == "Oil Observation"
    assert detail["steps"][1]["title"] == "Oil Attribution"
    assert detail["steps"][2]["title"] == "Commodity Returns"
    assert detail["steps"][3]["title"] == "Commodity Attribution"
    assert detail["steps"][4]["title"] == "CFTC COT Positioning"
    assert detail["steps"][5]["title"] == "Trade-Weighted USD"
    assert detail["steps"][6]["title"] == "CPI/PPI Confirmation"


def test_cot_display_names_include_exchange():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )

    assert "(ICE Futures Europe)" in payload["cot"]["crude_oil_wti"]["display_name"]
    assert "(COMEX)" in payload["cot"]["copper"]["display_name"]


def test_natural_gas_contract_note_explains_not_henry_hub():
    payload = .build_cyclical_commodities_payload(
        [
            {
                "commodity_id": "natural_gas",
                "report_date": "2026-07-21",
                "manager_longs": 100000.0,
                "manager_shorts": 90000.0,
                "open_interest": 500000.0,
                "publication_date": "2026-07-24",
            }
        ],
        {},
        None,
        "2026-07-25",
    )

    assert "NYMEX Henry Hub" in payload["cot"]["natural_gas"]["contract_note"]


def test_available_cot_usd_inflation_drive_step_availability():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["steps"][4]["status"] == "available"
    assert detail["steps"][5]["status"] == "available"
    assert detail["steps"][6]["status"] == "available"


def test_step_status_is_unavailable_when_cot_has_no_data():
    payload = .build_cyclical_commodities_payload([], {}, None, "2026-07-25")
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["steps"][4]["status"] == "unavailable"
    assert detail["steps"][5]["status"] == "unavailable"
    assert detail["steps"][6]["status"] == "unavailable"


def test_detail_process_read_is_insufficient_without_commodity_observation_and_attribution():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["process_read"] == {
        "status": "insufficient_for_commodity_narrative",
        "label": "Commodity narrative cannot be assessed",
        "reason": "commodity price observation and demand, supply, inventory attribution are unavailable",
        "next_action": "configure official commodity price and attribution sources",
    }


def test_process_read_insufficient_when_only_attribution_missing():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    payload["commodity_returns"] = {"status": "available"}
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["process_read"]["status"] == "insufficient_for_commodity_narrative"


def test_process_read_insufficient_when_only_returns_missing():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    payload["commodity_attribution"] = {"status": "available"}
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["process_read"]["status"] == "insufficient_for_commodity_narrative"


def test_detail_corroboration_summarizes_raw_evidence_without_trade_bias():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["corroboration"]["cot"]["available_contract_count"] == 2
    assert detail["corroboration"]["cot"]["positive_flip_count"] == 1
    assert detail["corroboration"]["usd"]["weekly_direction"] == "rising"
    assert detail["corroboration"]["inflation"]["available_series_count"] == 3
    assert "trade_bias" not in detail["corroboration"]["cot"]


def test_freshness_includes_per_source_latest_observation_date():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, None, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    f = detail["freshness"]
    assert f["cftc_latest_report_date"] == "2026-07-21"
    assert f["usd_latest_observation_date"] == "2026-07-21"
    assert f["inflation_latest_observation_date"] == "2026-07-01"
    assert f["as_of_date"] == "2026-07-25"


_OIL_ROWS = {
    "oil_wti_spot": [
        {"date": "2026-07-17", "value": 63.0, "source_identifier": "RWTC"},
        {"date": "2026-07-20", "value": 64.0, "source_identifier": "RWTC"},
        {"date": "2026-07-21", "value": 65.0, "source_identifier": "RWTC"},
        {"date": "2026-07-22", "value": 66.0, "source_identifier": "RWTC"},
        {"date": "2026-07-23", "value": 67.0, "source_identifier": "RWTC"},
        {"date": "2026-07-24", "value": 68.0, "source_identifier": "RWTC"},
    ],
    "oil_brent_spot": [
        {"date": "2026-07-24", "value": 71.0, "source_identifier": "RBRTE"},
    ],
    "oil_commercial_crude_stocks": [
        {"date": "2026-07-17", "value": 450000.0, "source_identifier": "WCESTUS1"},
    ],
    "oil_commercial_crude_imports": [
        {"date": "2026-07-17", "value": 3200.0, "source_identifier": "WCEIMUS2"},
    ],
    "oil_crude_production": [
        {"date": "2026-07-17", "value": 13100.0, "source_identifier": "WCRFPUS2"},
    ],
    "oil_refinery_crude_input": [
        {"date": "2026-07-17", "value": 16900.0, "source_identifier": "WCRRIUS2"},
    ],
    "oil_petroleum_products_supplied": [
        {"date": "2026-07-17", "value": 20500.0, "source_identifier": "WRPUPUS2"},
    ],
}


def test_oil_observation_reports_raw_daily_and_weekly_returns_without_distribution_label():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, _OIL_ROWS, "2026-07-25"
    )
    wti = payload["oil_observation"]["benchmarks"]["oil_wti_spot"]

    assert wti["daily_return"] == pytest.approx(68.0 / 67.0 - 1)
    assert wti["weekly_return"] == pytest.approx(68.0 / 63.0 - 1)
    assert wti["distribution_status"] == "not_configured"
    assert "signal" not in wti


def test_process_read_requires_price_and_all_five_attribution_inputs():
    oil_rows = dict(_OIL_ROWS)
    del oil_rows["oil_refinery_crude_input"]
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, oil_rows, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    read = detail["process_read"]
    assert read["status"] == "insufficient_for_commodity_narrative"
    assert read["next_action"] == "load official oil attribution inputs"


def test_process_read_is_pending_review_when_prices_and_inputs_are_present():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, _OIL_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    read = detail["process_read"]
    assert read["status"] == "attribution_pending_review"
    assert read["label"] == "Oil attribution is ready for review"
    assert "demand-led" not in read["reason"].lower()
    assert "supply-led" not in read["reason"].lower()


def test_oil_payload_excludes_observations_after_as_of_date():
    oil_rows = {
        "oil_wti_spot": [
            {"date": "2026-07-24", "value": 64.89, "source_identifier": "RWTC"},
            {"date": "2026-07-25", "value": 65.0, "source_identifier": "RWTC"},
            {"date": "2026-07-26", "value": 66.0, "source_identifier": "RWTC"},
        ],
    }
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, oil_rows, "2026-07-24"
    )
    assert (
        payload["oil_observation"]["benchmarks"]["oil_wti_spot"]["latest_date"]
        == "2026-07-24"
    )


def test_attribution_data_never_creates_demand_or_supply_conclusion():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, _OIL_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)
    assert detail["commodity_attribution"]["status"] == "attribution_pending_review"
    assert "conclusion" not in detail["commodity_attribution"]
    assert "trade" not in detail["process_read"]["label"].lower()
