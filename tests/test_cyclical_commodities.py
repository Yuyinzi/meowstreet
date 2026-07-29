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
        {"date": "2026-07-20", "value": 119.5, "source_identifier": "DTWEXBGS"},
        {"date": "2026-07-21", "value": 120.0, "source_identifier": "DTWEXBGS"},
    ],
    "usd_afe": [
        {"date": "2026-07-20", "value": 105.0, "source_identifier": "DTWEXAFEGS"},
        {"date": "2026-07-21", "value": 105.5, "source_identifier": "DTWEXAFEGS"},
    ],
    "usd_eme": [
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
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    wti = payload["cot"]["crude_oil_wti"]

    assert wti["normalized_manager_net_position"] == 0.05
    assert wti["flip"] == "positive"


def test_never_exposes_extreme_or_distribution_conclusions():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )

    assert payload["cot"]["crude_oil_wti"]["extreme"] == "not_configured"
    assert payload["usd"]["usd_broad"]["distribution_status"] == "not_configured"
    assert (
        payload["inflation"]["cpi_all_items"]["distribution_status"]
        == "not_configured"
    )


def test_commodity_attribution_is_unavailable():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )

    assert payload["commodity_attribution"]["status"] == "unavailable"


def test_card_is_always_present_even_without_data():
    payload = .build_cyclical_commodities_payload([], {}, "2026-07-25")
    card = .build_cyclical_commodities_headline(payload)

    assert card["id"] == "cyclical_commodities"
    assert card["status"] == "partial_official_evidence"


def test_card_includes_freshness_metadata_with_available_evidence():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    card = .build_cyclical_commodities_headline(payload)

    assert "cftc_latest" in card["freshness"]
    assert "usd_latest" in card["freshness"]
    assert "inflation_latest" in card["freshness"]


def test_detail_has_five_steps_in_correct_order():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["detail_id"] == "cyclical_commodities"
    assert len(detail["steps"]) == 5
    assert detail["steps"][0]["title"] == "Commodity Returns"
    assert detail["steps"][1]["title"] == "Commodity Attribution"
    assert detail["steps"][2]["title"] == "CFTC COT Positioning"
    assert detail["steps"][3]["title"] == "Trade-Weighted USD"
    assert detail["steps"][4]["title"] == "CPI/PPI Confirmation"


def test_cot_display_names_include_exchange():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
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
        "2026-07-25",
    )

    assert "NYMEX Henry Hub" in payload["cot"]["natural_gas"]["contract_note"]


def test_available_cot_usd_inflation_drive_step_availability():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["steps"][2]["status"] == "available"
    assert detail["steps"][3]["status"] == "available"
    assert detail["steps"][4]["status"] == "available"


def test_step_status_is_unavailable_when_cot_has_no_data():
    payload = .build_cyclical_commodities_payload([], {}, "2026-07-25")
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["steps"][2]["status"] == "unavailable"
    assert detail["steps"][3]["status"] == "unavailable"
    assert detail["steps"][4]["status"] == "unavailable"


def test_freshness_includes_per_source_latest_observation_date():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    f = detail["freshness"]
    assert f["cftc_latest_report_date"] == "2026-07-21"
    assert f["usd_latest_observation_date"] == "2026-07-21"
    assert f["inflation_latest_observation_date"] == "2026-07-01"
    assert f["as_of_date"] == "2026-07-25"
