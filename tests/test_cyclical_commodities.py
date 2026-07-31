from pathlib import Path

import pytest

from app.tools import cyclical_commodities as 
from app.tools import oil_distribution

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
    assert read["status"] == "review_required"
    assert read["label"] == "Oil attribution is ready for review"
    assert "demand-led" not in read["reason"].lower()
    assert "supply-led" not in read["reason"].lower()
    assert detail["commodity_attribution"]["review_label"] == (
        "Official attribution inputs loaded — review required before forming a narrative."
    )


def test_oil_attribution_exposes_change_from_previous_weekly_observation():
    oil_rows = {
        **_OIL_ROWS,
        "oil_commercial_crude_stocks": [
            {"date": "2026-07-10", "value": 452000.0},
            {"date": "2026-07-17", "value": 450000.0},
        ],
        "oil_commercial_crude_imports": [
            {"date": "2026-07-10", "value": 3100.0},
            {"date": "2026-07-17", "value": 3200.0},
        ],
    }
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, oil_rows, "2026-07-25"
    )
    metrics = {
        item["series_id"]: item for item in payload["commodity_attribution"]["metrics"]
    }

    assert metrics["oil_commercial_crude_stocks"]["weekly_change"] == -2000.0
    assert metrics["oil_commercial_crude_imports"]["weekly_change"] == 100.0
    assert metrics["oil_crude_production"]["weekly_change"] is None


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


def test_oil_state_contract_labels_raw_changes_without_trade_conclusion():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, _OIL_ROWS, "2026-07-25"
    )
    detail = .build_cyclical_commodities_detail(payload)
    review = detail["oil_attribution_review"]

    assert review["method_version"] == "oil_attribution_review_states_v1"
    assert review["status"] == "review_required"
    assert review["label"] == (
        "Attribution inputs complete — review whether the price move is "
        "demand-, supply-, or inventory-driven."
    )
    assert "no automatic attribution" in review["reason"]
    assert "trade" not in review["label"].lower()
    assert "demand-led" not in review["label"].lower()
    assert "supply-led" not in review["label"].lower()


def test_oil_payload_marks_price_and_physical_changes_with_raw_states():
    oil_rows = {
        **_OIL_ROWS,
        "oil_wti_spot": [
            {"date": "2026-07-14", "value": 65.0, "source_identifier": "RWTC"},
            {"date": "2026-07-15", "value": 66.0, "source_identifier": "RWTC"},
            {"date": "2026-07-16", "value": 67.0, "source_identifier": "RWTC"},
            {"date": "2026-07-17", "value": 68.0, "source_identifier": "RWTC"},
            {"date": "2026-07-20", "value": 69.0, "source_identifier": "RWTC"},
            {"date": "2026-07-21", "value": 70.0, "source_identifier": "RWTC"},
        ],
        "oil_commercial_crude_stocks": [
            {"date": "2026-07-10", "value": 452000.0},
            {"date": "2026-07-17", "value": 450000.0},
        ],
        "oil_commercial_crude_imports": [
            {"date": "2026-07-10", "value": 3100.0},
            {"date": "2026-07-17", "value": 3200.0},
        ],
        "oil_crude_production": [
            {"date": "2026-07-10", "value": 13000.0},
            {"date": "2026-07-17", "value": 13100.0},
        ],
        "oil_refinery_crude_input": [
            {"date": "2026-07-10", "value": 17000.0},
            {"date": "2026-07-17", "value": 16900.0},
        ],
        "oil_petroleum_products_supplied": [
            {"date": "2026-07-10", "value": 20000.0},
            {"date": "2026-07-17", "value": 20500.0},
        ],
    }
    meta = {
        "oil_wti_spot": {
            "series_id": "oil_wti_spot",
            "units": "USD/BBL",
            "source": "eia",
        },
        "oil_brent_spot": {
            "series_id": "oil_brent_spot",
            "units": "USD/BBL",
            "source": "eia",
        },
        "oil_commercial_crude_stocks": {
            "series_id": "oil_commercial_crude_stocks",
            "units": "MBBL",
            "source": "eia",
        },
        "oil_commercial_crude_imports": {
            "series_id": "oil_commercial_crude_imports",
            "units": "MBBL/D",
            "source": "eia",
        },
        "oil_crude_production": {
            "series_id": "oil_crude_production",
            "units": "MBBL/D",
            "source": "eia",
        },
        "oil_refinery_crude_input": {
            "series_id": "oil_refinery_crude_input",
            "units": "MBBL/D",
            "source": "eia",
        },
        "oil_petroleum_products_supplied": {
            "series_id": "oil_petroleum_products_supplied",
            "units": "MBBL/D",
            "source": "eia",
        },
    }
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        oil_rows,
        "2026-07-25",
        oil_series_metadata_by_id=meta,
    )
    benchmarks = payload["oil_observation"]["benchmarks"]
    metrics = {
        item["series_id"]: item for item in payload["commodity_attribution"]["metrics"]
    }

    assert benchmarks["oil_wti_spot"]["weekly_return_state"] == "up"
    assert benchmarks["oil_wti_spot"]["units"] == "USD/BBL"
    assert metrics["oil_commercial_crude_stocks"]["weekly_change_state"] == "draw"
    assert metrics["oil_commercial_crude_stocks"]["units"] == "MBBL"
    assert metrics["oil_commercial_crude_imports"]["weekly_change_state"] == "up"


def test_oil_payload_marks_missing_prior_observation_unavailable():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, _OIL_ROWS, "2026-07-25"
    )
    metric = next(
        item
        for item in payload["commodity_attribution"]["metrics"]
        if item["series_id"] == "oil_crude_production"
    )

    assert metric["weekly_change"] is None
    assert metric["weekly_change_state"] == "unavailable"


def test_oil_benchmark_daily_and_weekly_distribution_are_exposed():
    import datetime

    daily_rows = []
    for i in range(253):
        d = datetime.date(2025, 1, 2) + datetime.timedelta(days=i)
        daily_rows.append({"date": d.isoformat(), "value": 100.0 + i * 0.1})

    weekly_rows = []
    d = datetime.date(2025, 1, 6)
    for i in range(53):
        friday = d + datetime.timedelta(days=4)
        weekly_rows.append({"date": friday.isoformat(), "value": 100.0 + i * 0.5})
        d += datetime.timedelta(days=7)

    oil_rows = {
        "oil_wti_spot": daily_rows + weekly_rows,
        "oil_brent_spot": daily_rows + weekly_rows,
        "oil_commercial_crude_stocks": [
            {"date": "2026-07-17", "value": 450000.0},
        ],
        "oil_commercial_crude_imports": [
            {"date": "2026-07-17", "value": 3200.0},
        ],
        "oil_crude_production": [
            {"date": "2026-07-17", "value": 13100.0},
        ],
        "oil_refinery_crude_input": [
            {"date": "2026-07-17", "value": 16900.0},
        ],
        "oil_petroleum_products_supplied": [
            {"date": "2026-07-17", "value": 20500.0},
        ],
    }

    payload = .build_cyclical_commodities_payload([], {}, oil_rows, "2026-12-31")
    benchmark = payload["oil_observation"]["benchmarks"]["oil_wti_spot"]

    assert (
        benchmark["daily_distribution"]["method_version"] == "oil_distribution_v2"
    )
    assert benchmark["daily_distribution"]["standard_deviation"] == "sample"
    assert (
        benchmark["weekly_distribution"]["week_definition"]
        == "iso_calendar_week_last_available_trading_day"
    )
    assert benchmark["daily_distribution"]["classification"] in {
        "normal",
        "abnormal_1sigma",
        "abnormal_2sigma",
        "abnormal_3sigma",
    }
    assert "trade" not in benchmark["daily_distribution"]


def test_oil_benchmark_distribution_is_unavailable_when_insufficient_history():
    payload = .build_cyclical_commodities_payload(
        [], {}, _OIL_ROWS, "2026-07-25"
    )
    benchmark = payload["oil_observation"]["benchmarks"]["oil_wti_spot"]

    assert benchmark["daily_distribution"]["classification"] == "unavailable"
    assert benchmark["weekly_distribution"]["classification"] == "unavailable"
    assert benchmark["status"] == "available"
    detail = .build_cyclical_commodities_detail(payload)
    assert detail["process_read"]["status"] == "review_required"


def _payload_with_distribution_states(wti_daily, wti_weekly, brent_daily, brent_weekly):
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, _OIL_ROWS, "2026-07-25"
    )
    benchmarks = payload["oil_observation"]["benchmarks"]
    for series_id, daily, weekly in (
        ("oil_wti_spot", wti_daily, wti_weekly),
        ("oil_brent_spot", brent_daily, brent_weekly),
    ):
        benchmarks[series_id]["daily_distribution"]["classification"] = daily
        benchmarks[series_id]["weekly_distribution"]["classification"] = weekly
    return payload


def test_oil_distribution_summary_is_normal_only_when_all_four_horizons_are_normal():
    detail = .build_cyclical_commodities_detail(
        _payload_with_distribution_states(
            wti_daily="normal",
            wti_weekly="normal",
            brent_daily="normal",
            brent_weekly="normal",
        )
    )

    summary = detail["oil_price_distribution_summary"]
    assert summary["status"] == "normal"
    assert summary["abnormal_observations"] == []
    assert (
        "within 1σ of their 2016-to-latest available distributions" in summary["label"]
    )
    assert "physical-market attribution remains required" in summary["detail"]


def test_oil_distribution_summary_lists_only_abnormal_benchmark_horizons():
    detail = .build_cyclical_commodities_detail(
        _payload_with_distribution_states(
            wti_daily="abnormal_2sigma",
            wti_weekly="normal",
            brent_daily="normal",
            brent_weekly="abnormal_1sigma",
        )
    )

    summary = detail["oil_price_distribution_summary"]
    assert summary["status"] == "abnormal"
    assert summary["abnormal_observations"] == [
        "WTI daily (2σ abnormal)",
        "Brent weekly (1σ abnormal)",
    ]
    assert "WTI daily" in summary["label"]
    assert "Brent weekly" in summary["label"]


def test_oil_distribution_summary_is_incomplete_when_any_horizon_is_unavailable():
    detail = .build_cyclical_commodities_detail(
        _payload_with_distribution_states(
            wti_daily="normal",
            wti_weekly="unavailable",
            brent_daily="abnormal_3sigma",
            brent_weekly="normal",
        )
    )

    summary = detail["oil_price_distribution_summary"]
    assert summary["status"] == "incomplete"
    assert summary["abnormal_observations"] == []


def test_oil_distribution_summary_does_not_change_process_read():
    normal_payload = _payload_with_distribution_states(
        wti_daily="normal",
        wti_weekly="normal",
        brent_daily="normal",
        brent_weekly="normal",
    )
    abnormal_payload = _payload_with_distribution_states(
        wti_daily="abnormal_3sigma",
        wti_weekly="normal",
        brent_daily="normal",
        brent_weekly="normal",
    )

    normal_detail = .build_cyclical_commodities_detail(normal_payload)
    abnormal_detail = .build_cyclical_commodities_detail(abnormal_payload)

    assert normal_detail["process_read"] == abnormal_detail["process_read"]


def test_oil_distribution_v2_excludes_pre_2016_observations_from_returns():
    all_rows = [
        {"date": "2015-12-31", "value": 10.0},
        {"date": "2016-01-01", "value": 100.0},
        {"date": "2016-01-04", "value": 110.0},
        {"date": "2016-01-05", "value": 121.0},
    ]

    result = oil_distribution.build_distribution(
        all_rows, "daily", minimum_samples=2
    )
    expected = oil_distribution.build_distribution(
        all_rows[1:], "daily", minimum_samples=2
    )

    assert result["method_version"] == "oil_distribution_v2"
    assert result["distribution_window"] == "2016-01-01_to_latest_available"
    assert result["sample_start_date"] == "2016-01-04"
    assert result["sample_end_date"] == "2016-01-05"
    assert result["sample_count"] == expected["sample_count"]
    assert result["sample_mean"] == expected["sample_mean"]
    assert result["sample_standard_deviation"] == expected["sample_standard_deviation"]


_method_ROWS = {
    "copper_comex": [
        {"date": "2026-07-22", "value": 5.66},
        {"date": "2026-07-23", "value": 5.68},
        {"date": "2026-07-24", "value": 5.70},
    ],
    "copper_lme": [
        {"date": "2026-07-22", "value": 10400.0},
        {"date": "2026-07-23", "value": 10380.0},
        {"date": "2026-07-24", "value": 10420.0},
    ],
    "lumber": [],
}


def test_detail_builds_method_market_observation_without_attribution_conclusion():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-25",
        commodity_observations=_method_ROWS,
    )
    detail = .build_cyclical_commodities_detail(payload)
    copper = detail["non_oil_observation"]["copper_comex"]
    assert copper["daily_return"] == pytest.approx(0.0035, abs=1e-4)
    assert copper["source_class"] == "free_web"
    assert "Method-specified market data" in copper["source_label"]
    assert copper["status"] == "available"
    assert "attribution" not in copper


def test_static_labels_method_market_source_without_claiming_official_settlement():
    source = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "cyclical-commodities-ui.js"
    ).read_text()

    assert "Commodity Market Data" in source
    assert (
        "Reference market data sourced from Investing.com. Not official exchange settlement."
        not in source
    )
    assert "Source: Investing.com" in source
    assert "Investing.com reference data" not in source
    assert "Method-Specified Commodity Markets" not in source
    assert "Method-specified market data from Investing.com" not in source
    assert "method-market data not yet fetched" not in source
    assert "series.source_label" not in source


def _shfe_main_rows():
    return [
        {
            "date": "2026-07-29",
            "selected_contract": "CU2609",
            "previous_selected_contract": None,
            "close": 79000.0,
            "settlement": 79000.0,
            "volume": 100000.0,
            "open_interest": 200000.0,
            "contract_roll": False,
            "roll_from": None,
            "roll_to": None,
            "roll_gap": None,
            "unadjusted_continuous_return": None,
            "same_contract_return": None,
            "roll_affected": False,
            "selection_rule_version": "shfe_cu_main_oi_v1",
            "price_series_version": "shfe_cu_oi_main_unadjusted_v1",
            "return_method_version": "shfe_cu_oi_main_return_v1",
            "source_url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
            "retrieved_at": "2026-07-31T00:00:00+00:00",
        },
        {
            "date": "2026-07-30",
            "selected_contract": "CU2610",
            "previous_selected_contract": "CU2609",
            "close": 80500.0,
            "settlement": 80400.0,
            "volume": 100000.0,
            "open_interest": 200000.0,
            "contract_roll": True,
            "roll_from": "CU2609",
            "roll_to": "CU2610",
            "roll_gap": 1500.0,
            "unadjusted_continuous_return": 80500 / 79000 - 1,
            "same_contract_return": 80500 / 80200 - 1,
            "roll_affected": True,
            "selection_rule_version": "shfe_cu_main_oi_v1",
            "price_series_version": "shfe_cu_oi_main_unadjusted_v1",
            "return_method_version": "shfe_cu_oi_main_return_v1",
            "source_url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
            "retrieved_at": "2026-07-31T00:00:00+00:00",
        },
    ]


def test_shanghai_detail_exposes_official_source_and_separated_returns():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-31",
        commodity_observations={},
        shfe_cu_main_observations=_shfe_main_rows(),
    )
    detail = .build_cyclical_commodities_detail(payload)
    shanghai = detail["non_oil_observation"]["copper_shanghai"]

    assert shanghai["source_class"] == "official_exchange"
    assert shanghai["source_label"] == "SHFE official public data · AKShare adapter"
    assert shanghai["selected_contract"] == "CU2610"
    assert shanghai["daily_return"] == pytest.approx(80500 / 80200 - 1)
    assert shanghai["return_method_version"] == "shfe_cu_oi_main_return_v1"
    assert shanghai["contract_roll"] is True
    assert shanghai["unadjusted_continuous_return"] == pytest.approx(80500 / 79000 - 1)
    assert shanghai["roll_gap"] == 1500.0
    assert "buy" not in shanghai["summary"].lower()
    assert "sell" not in shanghai["summary"].lower()


def test_shanghai_is_unavailable_when_derived_series_is_missing():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-31",
        commodity_observations={},
        shfe_cu_main_observations=None,
    )
    detail = .build_cyclical_commodities_detail(payload)
    shanghai = detail["non_oil_observation"]["copper_shanghai"]

    assert shanghai["status"] == "unavailable"
    assert shanghai["source_class"] == "official_exchange"


def test_shanghai_weekly_return_is_roll_neutral():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-31",
        commodity_observations={},
        shfe_cu_main_observations=_shfe_main_rows(),
    )
    detail = .build_cyclical_commodities_detail(payload)
    shanghai = detail["non_oil_observation"]["copper_shanghai"]

    assert shanghai["weekly_return"] == pytest.approx(80500 / 80200 - 1)
    assert shanghai["weekly_return_label"] == "roll-neutral"


def test_shanghai_summary_keeps_roll_note_out_of_headline_classification():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-31",
        commodity_observations={},
        shfe_cu_main_observations=_shfe_main_rows(),
    )
    detail = .build_cyclical_commodities_detail(payload)
    shanghai = detail["non_oil_observation"]["copper_shanghai"]

    assert "Contract changed CU2609 \u2192 CU2610" in shanghai["summary"]
    assert "unadjusted price gap is shown for audit only" in shanghai["summary"]
    assert "bullish" not in shanghai["summary"].lower()
    assert "bearish" not in shanghai["summary"].lower()


def test_static_renders_shfe_shanghai_official_source_and_roll_marker():
    source = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "cyclical-commodities-ui.js"
    ).read_text()

    assert "SHFE official data via AKShare" in source
    assert "same-contract" in source
    assert "roll-neutral" in source
    assert "unadjusted price gap is shown for audit only" in source
    assert "shfe-roll-note" in source
    assert 'source_class === "official_exchange"' in source
