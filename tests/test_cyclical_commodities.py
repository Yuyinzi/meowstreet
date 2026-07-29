from app.tools import cyclical_commodities as 

COT_ROWS = [
    {
        "commodity_id": "crude_oil_wti",
        "report_date": "2026-07-14",
        "manager_longs": 180000.0,
        "manager_shorts": 200000.0,
        "open_interest": 1000000.0,
    },
    {
        "commodity_id": "crude_oil_wti",
        "report_date": "2026-07-21",
        "manager_longs": 200000.0,
        "manager_shorts": 150000.0,
        "open_interest": 1000000.0,
    },
    {
        "commodity_id": "copper",
        "report_date": "2026-07-21",
        "manager_longs": 100000.0,
        "manager_shorts": 90000.0,
        "open_interest": 500000.0,
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
        {"date": "2026-05-01", "value": 330.0, "source_identifier": "CPIAUCSL"},
        {"date": "2026-06-01", "value": 332.568, "source_identifier": "CPIAUCSL"},
    ],
    "core_cpi": [
        {"date": "2026-05-01", "value": 310.0, "source_identifier": "CPILFESL"},
        {"date": "2026-06-01", "value": 312.0, "source_identifier": "CPILFESL"},
    ],
    "ppi_all_commodities": [
        {"date": "2026-05-01", "value": 200.0, "source_identifier": "PPIACO"},
        {"date": "2026-06-01", "value": 201.5, "source_identifier": "PPIACO"},
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


def test_card_status_is_partial_official_evidence():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    card = .build_cyclical_commodities_headline(payload)

    assert card["status"] == "partial_official_evidence"
    assert "commodity attribution" in card["reason"]


def test_detail_has_five_steps():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["detail_id"] == "cyclical_commodities"
    assert len(detail["steps"]) == 5
    assert detail["steps"][0]["title"] == "CFTC COT Positioning"
    assert detail["steps"][2]["status"] == "unavailable"
    assert detail["steps"][3]["status"] == "unavailable"
    assert detail["steps"][4]["title"] == "CPI/PPI Confirmation"


def test_cot_crude_oil_wti_normalized_position_and_flip():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, "2026-07-25"
    )
    wti = payload["cot"]["crude_oil_wti"]

    assert wti["normalized_manager_net_position"] == 0.05
    assert wti["flip"] == "positive"
    assert wti["manager_longs"] == 200000.0
    assert wti["manager_shorts"] == 150000.0
    assert wti["open_interest"] == 1000000.0
