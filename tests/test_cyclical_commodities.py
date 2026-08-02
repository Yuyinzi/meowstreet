from datetime import date, timedelta
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
    payload = _payload_with_distribution_states(
        wti_daily="abnormal_2sigma",
        wti_weekly="normal",
        brent_daily="normal",
        brent_weekly="normal",
        oil_rows=oil_rows,
    )
    detail = .build_cyclical_commodities_detail(payload)

    read = detail["process_read"]
    assert read["status"] == "insufficient_for_commodity_narrative"
    assert read["next_action"] == "load official oil attribution inputs"


def test_process_read_is_pending_review_when_prices_and_inputs_are_present():
    payload = _payload_with_distribution_states(
        wti_daily="abnormal_2sigma",
        wti_weekly="normal",
        brent_daily="normal",
        brent_weekly="normal",
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
    payload = _payload_with_distribution_states(
        wti_daily="normal",
        wti_weekly="normal",
        brent_daily="abnormal_1sigma",
        brent_weekly="normal",
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
    assert detail["process_read"]["status"] == "insufficient_for_commodity_narrative"
    assert detail["process_read"]["next_action"] == (
        "load complete oil price history for WTI and Brent"
    )


def _payload_with_distribution_states(
    wti_daily, wti_weekly, brent_daily, brent_weekly, oil_rows=None
):
    payload = .build_cyclical_commodities_payload(
        COT_ROWS, USD_ROWS, oil_rows or _OIL_ROWS, "2026-07-25"
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


def test_oil_distribution_summary_requires_attribution_review_only_for_abnormal_move():
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

    assert normal_detail["process_read"]["status"] == "observation_available"
    assert normal_detail["oil_attribution_review"] is None
    assert abnormal_detail["process_read"]["status"] == "review_required"
    assert abnormal_detail["oil_attribution_review"]["status"] == "review_required"


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
    "iron_ore_62_cfr_china": [
        {"date": "2026-07-22", "value": 10400.0},
        {"date": "2026-07-23", "value": 10380.0},
        {"date": "2026-07-24", "value": 10420.0},
    ],
}


def i0_rows():
    return [
        {
            "date": "2026-07-30",
            "value": 715.0,
            "source": "sina_finance",
            "source_url": "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_V21052021_4_12=/InnerFuturesNewService.getDailyKLine",
            "source_identifier": "I0",
            "source_class": "vendor_free_market_data",
            "retrieved_at": "2026-08-01T00:00:00+00:00",
        },
        {
            "date": "2026-07-31",
            "value": 716.0,
            "source": "sina_finance",
            "source_url": "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_V21052021_4_12=/InnerFuturesNewService.getDailyKLine",
            "source_identifier": "I0",
            "source_class": "vendor_free_market_data",
            "retrieved_at": "2026-08-01T00:00:00+00:00",
        },
    ]


def test_payload_presents_i0_as_raw_vendor_continuous_data():
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        as_of_date="2026-07-31",
        commodity_observations={"iron_ore_dce": i0_rows()},
    )

    dce = payload["commodity_observation"]["iron_ore_dce"]
    assert dce["latest_value"] == 716.0
    assert dce["daily_return"] == pytest.approx(716 / 715 - 1)
    assert dce["source_label"] == "Sina Finance I0 continuous series"


def payload_with_lbr_and_archive():
    return .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-25",
        commodity_observations={
            "lumber_cme_lbr_yahoo_v1": [
                {
                    "date": "2026-07-22",
                    "value": 628.0,
                    "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/LBR%3DF",
                    "source_identifier": "LBR=F",
                },
                {
                    "date": "2026-07-23",
                    "value": 631.0,
                    "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/LBR%3DF",
                    "source_identifier": "LBR=F",
                },
                {
                    "date": "2026-07-24",
                    "value": 634.0,
                    "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/LBR%3DF",
                    "source_identifier": "LBR=F",
                },
            ],
            "lumber": [
                {"date": "2026-07-24", "value": 620.0},
            ],
        },
    )


def test_detail_builds_method_market_observation_without_attribution_conclusion():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-25",
        commodity_observations=_method_ROWS,
    )
    detail = .build_cyclical_commodities_detail(payload)
    copper = detail["non_oil_observation"]["iron_ore_62_cfr_china"]
    assert copper["daily_return"] == pytest.approx(10420.0 / 10380.0 - 1)
    assert copper["source_class"] == "free_web"
    assert copper["source_label"] == "Investing.com"
    assert copper["status"] == "available"
    assert "attribution" not in copper


def test_detail_uses_active_yahoo_lbr_and_excludes_archived_lumber():
    detail = .build_cyclical_commodities_detail(payload_with_lbr_and_archive())
    lumber = detail["non_oil_observation"]["lumber_cme_lbr_yahoo_v1"]
    assert lumber["display_name"] == "Lumber (CME LBR)"
    assert lumber["source_label"] == "Yahoo Finance LBR=F"
    assert lumber["source_identifier"] == "LBR=F"
    assert "lumber" not in detail["non_oil_observation"]


def test_detail_uses_active_investing_comex_and_excludes_yahoo_archive():
    payload = .build_cyclical_commodities_payload(
        COT_ROWS,
        USD_ROWS,
        _OIL_ROWS,
        "2026-07-25",
        commodity_observations={
            "copper_comex": [
                {"date": "2026-07-22", "value": 4.35},
                {"date": "2026-07-23", "value": 4.40},
                {"date": "2026-07-24", "value": 4.45},
            ],
        },
    )
    detail = .build_cyclical_commodities_detail(payload)
    copper = detail["non_oil_observation"]["copper_comex"]
    assert copper["latest_date"] == "2026-07-24"
    assert copper["latest_value"] == 4.45
    assert copper["source_label"] == "Investing.com"
    assert copper["source_class"] == "free_web"
    assert copper["daily_return"] == pytest.approx(4.45 / 4.40 - 1)
    assert "copper_comex_hg_yahoo_v1" not in detail["non_oil_observation"]


def _six_investing_lme_rows():
    return [
        {"date": "2026-07-24", "value": 13700.0},
        {"date": "2026-07-27", "value": 13710.0},
        {"date": "2026-07-28", "value": 13720.0},
        {"date": "2026-07-29", "value": 13730.0},
        {"date": "2026-07-30", "value": 13745.72},
        {"date": "2026-07-31", "value": 13803.0},
    ]


def test_detail_uses_active_investing_lme_with_direct_returns():
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        as_of_date="2026-07-31",
        commodity_observations={
            "copper_lme": _six_investing_lme_rows(),
        },
    )
    detail = .build_cyclical_commodities_detail(payload)
    lme = detail["non_oil_observation"]["copper_lme"]
    assert lme["display_name"] == "Copper (LME)"
    assert lme["source_label"] == "Investing.com"
    assert lme["source_class"] == "free_web"
    assert lme["latest_date"] == "2026-07-31"
    assert lme["latest_value"] == 13803.0
    assert lme["daily_return"] == pytest.approx(13803.0 / 13745.72 - 1)
    assert lme["weekly_return"] == pytest.approx(13803.0 / 13700.0 - 1)
    assert "source_transition" not in lme
    assert "source_cutover_date" not in lme
    assert "return_transition_blocked" not in lme
    assert "copper_lme_sina_cad_v1" not in detail["non_oil_observation"]


def test_renderer_uses_backend_source_label_and_does_not_hard_code_investing_for_lbr():
    source = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "cyclical-commodities-ui.js"
    ).read_text()
    assert "series.source_label" in source
    assert "<span>Source: Investing.com</span>" not in source


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
    assert "Vendor market data; not official exchange settlement." not in source
    assert "series.source_label" in source
    assert "Investing.com reference data" not in source
    assert "Method-Specified Commodity Markets" not in source
    assert "Method-specified market data from Investing.com" not in source
    assert "method-market data not yet fetched" not in source
    assert "<span>Source: Investing.com</span>" not in source


def test_renderer_uses_backend_transition_flags_for_lme_source_change_note():
    source = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "cyclical-commodities-ui.js"
    ).read_text()
    assert "return_transition_blocked" in source
    assert "source_cutover_date" in source
    assert "Source changed on" in source
    assert "same-source history" in source
    assert "series.source_label" in source
    assert "<span>Source: Investing.com</span>" not in source


def _weekday_observation_rows(start, count, value_at):
    rows = []
    day = start
    while len(rows) < count:
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "value": value_at(len(rows))})
        day += timedelta(days=1)
    return rows


def _comex_normal_rows():
    return _weekday_observation_rows(
        date(2016, 1, 4), 265, lambda i: 100.0 * (1.0005**i)
    )


def _comex_abnormal_rows():
    def value_at(i):
        if i == 264:
            return 100.0 * (1.0005**263) * 1.5
        return 100.0 * (1.0005**i)

    return _weekday_observation_rows(date(2016, 1, 4), 265, value_at)


def _comex_payload(rows):
    return .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": rows},
    )


def test_commodity_distribution_classifies_abnormal_move_as_review_required():
    payload = _comex_payload(_comex_abnormal_rows())
    series = payload["commodity_observation"]["copper_comex"]

    assert (
        series["daily_distribution"]["method_version"]
        == "non_oil_price_distribution_v1"
    )
    assert series["daily_distribution"]["classification"] == "abnormal_3sigma"
    assert series["review_status"] == "review_required"
    assert "demand-led" not in series["review_label"].lower()
    assert "supply-led" not in series["review_label"].lower()
    assert "trade" not in series["review_label"].lower()
    assert payload["commodity_returns"]["status"] == "available"
    assert "market_bias" not in payload["commodity_returns"]


def test_commodity_distribution_marks_normal_move_as_observation_available():
    payload = _comex_payload(_comex_normal_rows())
    series = payload["commodity_observation"]["copper_comex"]

    assert series["daily_distribution"]["classification"] == "normal"
    assert series["weekly_distribution"]["classification"] == "normal"
    assert series["review_status"] == "observation_available"
    assert payload["commodity_returns"]["review_required_series_ids"] == []
    assert payload["commodity_returns"]["available_series_count"] == 1


def test_commodity_distribution_does_not_fall_back_across_copper_markets():
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2016-01-20",
        commodity_observations={
            "copper_lme": [
                {"date": "2016-01-15", "value": 4700.0},
                {"date": "2016-01-18", "value": 4750.0},
                {"date": "2016-01-19", "value": 4780.0},
                {"date": "2016-01-20", "value": 4800.0},
            ],
        },
    )
    comex = payload["commodity_observation"]["copper_comex"]
    lme = payload["commodity_observation"]["copper_lme"]

    assert comex["status"] == "unavailable"
    assert comex["review_status"] == "unavailable"
    assert comex["daily_distribution"]["classification"] == "unavailable"
    assert comex["daily_distribution"]["sample_count"] == 0
    assert comex["weekly_distribution"]["classification"] == "unavailable"
    assert "latest_value" not in comex

    assert lme["status"] == "available"
    assert lme["review_status"] == "unavailable"
    assert lme["daily_distribution"]["classification"] == "unavailable"
    assert lme["daily_distribution"]["sample_count"] == 3
    assert lme["weekly_distribution"]["classification"] == "unavailable"
    assert lme["weekly_distribution"]["sample_count"] == 1


def test_commodity_distribution_is_unavailable_with_insufficient_history():
    payload = _comex_payload(
        [
            {"date": "2016-01-14", "value": 100.0},
            {"date": "2016-01-15", "value": 100.5},
            {"date": "2016-01-18", "value": 101.0},
            {"date": "2016-01-19", "value": 101.5},
            {"date": "2016-01-20", "value": 102.0},
        ]
    )
    series = payload["commodity_observation"]["copper_comex"]

    assert series["daily_distribution"]["classification"] == "unavailable"
    assert series["daily_distribution"]["sample_count"] == 4
    assert series["weekly_distribution"]["classification"] == "unavailable"
    assert series["review_status"] == "unavailable"
    assert payload["commodity_returns"]["status"] == "unavailable"


def test_commodity_returns_summary_reports_availability_without_market_bias():
    payload = _comex_payload(_comex_abnormal_rows())
    summary = payload["commodity_returns"]

    assert summary["status"] == "available"
    assert summary["method_version"] == "non_oil_price_distribution_v1"
    assert summary["available_series_count"] == 1
    assert summary["review_required_series_ids"] == ["copper_comex"]
    assert "market_bias" not in summary
    assert "non-oil price distributions available" in summary["reason"]


def _shfe_main_rows(include_roll_day=True):
    rows = []
    current = date(2016, 1, 4)
    contracts = ("CU2601", "CU2602")
    for week_count in range(53):
        contract = contracts[week_count % 2]
        for offset in range(5):
            day = current + timedelta(days=offset)
            rows.append(
                {
                    "date": day.isoformat(),
                    "selected_contract": contract,
                    "close": 35000.0 + len(rows) * 1.0,
                    "settlement": 35000.0 + len(rows) * 1.0,
                    "volume": 1000.0,
                    "open_interest": 100000.0,
                    "contract_roll": False,
                    "roll_from": None,
                    "roll_to": None,
                    "roll_gap": None,
                    "unadjusted_continuous_return": 0.001,
                    "same_contract_return": 0.001,
                    "roll_affected": False,
                    "selection_rule_version": "test",
                    "price_series_version": "test",
                    "return_method_version": "test",
                }
            )
        current += timedelta(days=7)
    if include_roll_day:
        rows.append(
            {
                "date": current.isoformat(),
                "selected_contract": "CU2602",
                "close": 50000.0,
                "settlement": 50000.0,
                "volume": 1000.0,
                "open_interest": 100000.0,
                "contract_roll": True,
                "roll_from": "CU2601",
                "roll_to": "CU2602",
                "roll_gap": 12000.0,
                "unadjusted_continuous_return": 0.50,
                "same_contract_return": None,
                "roll_affected": True,
                "selection_rule_version": "test",
                "price_series_version": "test",
                "return_method_version": "test",
            }
        )
    return rows


def _shfe_payload(main_rows):
    return .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-10",
        commodity_observations={},
        shfe_cu_main_observations=main_rows,
    )


def test_shfe_distribution_excludes_unadjusted_roll_gap_return():
    payload = _shfe_payload(_shfe_main_rows(include_roll_day=True))
    shfe = payload["commodity_observation"]["copper_shanghai"]
    daily = shfe["daily_distribution"]
    weekly = shfe["weekly_distribution"]

    assert daily["sample_count"] == 265
    assert daily["current_return"] == pytest.approx(0.001)
    assert daily["current_return"] != 0.50
    assert daily["sample_end_date"] == "2017-01-06"
    assert weekly["sample_count"] == 53
    assert weekly["current_return"] != 0.50
    assert "unadjusted_continuous_return" not in daily


def test_shfe_distribution_is_normal_with_sufficient_same_contract_returns():
    payload = _shfe_payload(_shfe_main_rows(include_roll_day=False))
    shfe = payload["commodity_observation"]["copper_shanghai"]

    assert (
        shfe["daily_distribution"]["method_version"]
        == "non_oil_price_distribution_v1"
    )
    assert shfe["daily_distribution"]["classification"] == "normal"
    assert shfe["weekly_distribution"]["classification"] == "normal"
    assert shfe["review_status"] == "observation_available"
    assert shfe["daily_distribution"]["sample_count"] == 265
    assert shfe["weekly_distribution"]["sample_count"] == 53
    assert (
        shfe["daily_distribution"]["return_definition"]
        == "shfe_cu_same_contract_close_to_close"
    )
    assert (
        shfe["weekly_distribution"]["return_definition"]
        == "shfe_cu_same_contract_roll_neutral_iso_week"
    )


def _shfe_day_row(day, close_value):
    return {
        "date": day.isoformat(),
        "selected_contract": "CU2601",
        "close": close_value,
        "settlement": close_value,
        "volume": 1000.0,
        "open_interest": 100000.0,
        "contract_roll": False,
        "roll_from": None,
        "roll_to": None,
        "roll_gap": None,
        "unadjusted_continuous_return": 0.001,
        "same_contract_return": 0.001,
        "roll_affected": False,
        "selection_rule_version": "test",
        "price_series_version": "test",
        "return_method_version": "test",
    }


def _shfe_pre_2016_and_2016_rows():
    rows = []
    for week_start in (date(2015, 12, 7), date(2015, 12, 14), date(2015, 12, 21)):
        for offset in range(5):
            rows.append(
                _shfe_day_row(week_start + timedelta(days=offset), 35000.0 + len(rows))
            )
    current = date(2016, 1, 4)
    for week_count in range(53):
        for offset in range(5):
            rows.append(
                _shfe_day_row(current + timedelta(days=offset), 35000.0 + len(rows))
            )
        current += timedelta(days=7)
    return rows


def test_shfe_distribution_excludes_pre_2016_weeks_from_weekly_window():
    payload = _shfe_payload(_shfe_pre_2016_and_2016_rows())
    weekly = payload["commodity_observation"]["copper_shanghai"][
        "weekly_distribution"
    ]

    assert weekly["sample_start_date"] >= "2016-01-01"
    assert weekly["sample_count"] == 53

    baseline = _shfe_payload(_shfe_main_rows(include_roll_day=False))
    baseline_weekly = baseline["commodity_observation"]["copper_shanghai"][
        "weekly_distribution"
    ]
    assert weekly["sample_count"] == baseline_weekly["sample_count"]


def test_shfe_distribution_excludes_2015_w53_week_from_weekly_sample():
    rows = []
    for offset in range(4):
        rows.append(
            _shfe_day_row(
                date(2015, 12, 28) + timedelta(days=offset), 35000.0 + len(rows)
            )
        )
    current = date(2016, 1, 4)
    for week_count in range(53):
        for offset in range(5):
            rows.append(
                _shfe_day_row(current + timedelta(days=offset), 35000.0 + len(rows))
            )
        current += timedelta(days=7)

    payload = _shfe_payload(rows)
    weekly = payload["commodity_observation"]["copper_shanghai"][
        "weekly_distribution"
    ]

    baseline = _shfe_payload(_shfe_main_rows(include_roll_day=False))
    baseline_weekly = baseline["commodity_observation"]["copper_shanghai"][
        "weekly_distribution"
    ]
    assert weekly["sample_count"] == baseline_weekly["sample_count"]
    assert weekly["sample_count"] == 53


def test_review_labels_distinguish_no_observations_from_insufficient_history():
    no_rows = _comex_payload([])
    no_rows_label = no_rows["commodity_observation"]["copper_comex"][
        "review_label"
    ]
    insufficient = _comex_payload(
        [
            {"date": "2016-01-14", "value": 100.0},
            {"date": "2016-01-15", "value": 100.5},
            {"date": "2016-01-18", "value": 101.0},
            {"date": "2016-01-19", "value": 101.5},
            {"date": "2016-01-20", "value": 102.0},
        ]
    )
    insufficient_label = insufficient["commodity_observation"][
        "copper_comex"
    ]["review_label"]

    assert no_rows_label == (
        "No price observations are available for a distribution-based review."
    )
    assert insufficient_label == (
        "Insufficient price history for a distribution-based review."
    )
    assert no_rows_label != insufficient_label
    for label in (no_rows_label, insufficient_label):
        assert "demand-led" not in label.lower()
        assert "supply-led" not in label.lower()
        assert "trade" not in label.lower()


def _catalog_resource(commodity_id, source_name, source_url):
    return {
        "commodity_id": commodity_id,
        "source_name": source_name,
        "source_url": source_url,
        "source_type": "official_data",
        "coverage": ["production"],
        "source_ref": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        "status": "cataloged",
    }


def _copper_lumber_oil_catalog():
    return {
        "version": "commodity_attribution_evidence_catalog_v1",
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_document": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        "resources": [
            _catalog_resource(
                "copper", "International Copper Study Group", "https://www.icsg.org/"
            ),
            _catalog_resource(
                "lumber",
                "Food and Agriculture Organization of the United Nations",
                "https://www.fao.org/faostat/en/#data/FO",
            ),
            _catalog_resource(
                "oil",
                "Energy Information Administration",
                "https://www.eia.gov/petroleum/",
            ),
        ],
    }


def test_attribution_review_resources_expose_only_review_required_commodity():
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_abnormal_rows()},
        attribution_review_catalog=_copper_lumber_oil_catalog(),
    )
    detail = .build_cyclical_commodities_detail(payload)

    resources = detail["attribution_review_resources"]
    assert [r["source_name"] for r in resources] == ["International Copper Study Group"]
    assert all(r["commodity_id"] == "copper" for r in resources)
    assert all(r["status"] == "cataloged" for r in resources)


def test_attribution_review_resources_empty_for_normal_or_unavailable_distributions():
    normal = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_normal_rows()},
        attribution_review_catalog=_copper_lumber_oil_catalog(),
    )
    assert (
        .build_cyclical_commodities_detail(normal)[
            "attribution_review_resources"
        ]
        == []
    )

    unavailable = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        attribution_review_catalog=_copper_lumber_oil_catalog(),
    )
    assert (
        .build_cyclical_commodities_detail(unavailable)[
            "attribution_review_resources"
        ]
        == []
    )


def test_attribution_review_resources_empty_when_catalog_absent():
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_abnormal_rows()},
        attribution_review_catalog=None,
    )
    detail = .build_cyclical_commodities_detail(payload)

    assert detail["attribution_review_resources"] == []


def test_attribution_review_resources_never_add_conclusion_fields():
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_abnormal_rows()},
        attribution_review_catalog=_copper_lumber_oil_catalog(),
    )
    resources = .build_cyclical_commodities_detail(payload)[
        "attribution_review_resources"
    ]

    for resource in resources:
        for field in (
            "demand_led",
            "supply_led",
            "trade_bias",
            "market_setup",
            "ticker",
        ):
            assert field not in resource
        assert resource["source_url"]
        assert resource["coverage"]


def _audit_row(
    commodity_id,
    source_name,
    source_url,
    audit_status,
    factor_categories,
    access_method,
    geography,
    frequency,
    units,
    audit_basis,
):
    return {
        "commodity_id": commodity_id,
        "source_name": source_name,
        "source_url": source_url,
        "source_type": "official_data",
        "source_coverage": [],
        "audit_status": audit_status,
        "access_method": access_method,
        "factor_categories": factor_categories,
        "geography": geography,
        "frequency": frequency,
        "unit_status": "published",
        "units": units,
        "publication_date_status": "published",
        "stability": "manual",
        "audit_basis": audit_basis,
        "audited_at": "2026-08-02",
        "source_ref": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
    }


def audit_payload():
    return {
        "version": "non_oil_attribution_source_audit_v1",
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_catalog_version": "commodity_attribution_evidence_catalog_v1",
        "source_catalog": "data/local_system/commodity_attribution_evidence_catalog.v1.json",
        "audits": [
            _audit_row(
                "copper",
                "International Wrought Copper Council",
                "http://www.coppercouncil.org/iwcc-statistics-and-data",
                "structured_recurring_candidate",
                ["supply", "demand"],
                "xlsx_download",
                "Global (107 countries by region)",
                "annual",
                "t",
                "Page exposes direct public XLSX downloads for global semis production and demand.",
            ),
            _audit_row(
                "lumber",
                "Food and Agriculture Organization of the United Nations",
                "https://www.fao.org/faostat/en/#data/FO",
                "structured_recurring_candidate",
                ["supply", "trade"],
                "api",
                "Global by country",
                "annual",
                "t, m3, USD",
                "FAOSTAT Forestry Production and Trade bulk-download dataset (FO).",
            ),
            _audit_row(
                "iron_ore",
                "US Geological Survey",
                "https://www.usgs.gov/centers/nmic/iron-ore-statistics-and-information",
                "manual_review_only",
                ["supply", "demand"],
                "xlsx_download",
                "US and world",
                "monthly",
                "t",
                "Public MIS posting is paused pending a ScienceBase transition.",
            ),
            _audit_row(
                "iron_ore",
                "Government of Western Australia",
                "https://www.dmp.wa.gov.au/About-Us-Careers/Latest-Statistics-Release-4081.aspx",
                "manual_review_only",
                ["supply", "trade", "price"],
                "xlsx_download",
                "Western Australia",
                "annual",
                "kt, AUD m",
                "Method URL redirects to the WA Resources industry data page.",
            ),
            _audit_row(
                "iron_ore",
                "Government of Western Australia",
                "https://www.dmp.wa.gov.au/About-Us-Careers/Statistics-Digest-3962.aspx",
                "manual_review_only",
                ["supply", "trade", "price"],
                "manual_report_download",
                "Western Australia",
                "annual",
                "kt, AUD m",
                "Method URL redirects to the WA Mineral and Petroleum statistics digest page.",
            ),
            _audit_row(
                "iron_ore",
                "World Bank Commodity Markets",
                "https://www.worldbank.org/en/research/commodity-markets",
                "structured_recurring_candidate",
                ["price"],
                "xlsx_download",
                "Global",
                "monthly",
                "USD",
                "Monthly Pink Sheet commodity prices.",
            ),
        ],
    }


def global_fact():
    return {
        "commodity_id": "copper",
        "source_name": "International Wrought Copper Council",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "factor_category": "supply",
        "metric_name": "Semis production",
        "geography": "Global",
        "observation_date": "2024-12-31",
        "publication_date": None,
        "value": 12345678.0,
        "units": "t",
        "status": "available",
        "method_version": "non_oil_attribution_evidence_v1",
    }


def detail_for_review_required_iron(facts=None, audit=audit_payload()):
    if facts is None:
        facts = []
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={
            "iron_ore_62_cfr_china": _comex_abnormal_rows()
        },
        non_oil_attribution_facts=facts,
        non_oil_attribution_source_audit=audit,
    )
    return .build_cyclical_commodities_detail(payload)


def detail_for_review_required_copper(iwcc_facts=None):
    if iwcc_facts is None:
        iwcc_facts = []
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_abnormal_rows()},
        non_oil_attribution_facts=iwcc_facts,
        non_oil_attribution_source_audit=None,
    )
    return .build_cyclical_commodities_detail(payload)


def detail_for_review_required_copper_with_status(iwcc_facts=None, refresh_status=None):
    if iwcc_facts is None:
        iwcc_facts = []
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_abnormal_rows()},
        non_oil_attribution_facts=iwcc_facts,
        non_oil_attribution_source_audit=None,
        non_oil_attribution_refresh_status=refresh_status,
    )
    return .build_cyclical_commodities_detail(payload)


def detail_for_normal_copper(iwcc_facts=None):
    if iwcc_facts is None:
        iwcc_facts = [global_fact()]
    payload = .build_cyclical_commodities_payload(
        [],
        {},
        None,
        "2017-01-06",
        commodity_observations={"copper_comex": _comex_normal_rows()},
        non_oil_attribution_facts=iwcc_facts,
        non_oil_attribution_source_audit=None,
    )
    return .build_cyclical_commodities_detail(payload)


def test_review_required_iron_reports_usgs_unavailable_and_wa_manual_resources():
    detail = detail_for_review_required_iron(facts=[], audit=audit_payload())
    iron = detail["non_oil_attribution_evidence"]["iron_ore"]
    assert iron["status"] == "unavailable"
    assert "USGS" in iron["reason"]
    assert {row["source_name"] for row in iron["manual_review_resources"]} == {
        "Government of Western Australia"
    }


def test_normal_price_row_has_no_attribution_evidence():
    assert (
        detail_for_normal_copper(iwcc_facts=[global_fact()])[
            "non_oil_attribution_evidence"
        ]
        == {}
    )


def test_review_required_copper_emits_available_evidence_with_facts():
    detail = detail_for_review_required_copper(iwcc_facts=[global_fact()])
    copper = detail["non_oil_attribution_evidence"]["copper"]
    assert copper["status"] == "available"
    assert copper["commodity_id"] == "copper"
    assert copper["facts"] == [global_fact()]


def test_review_required_copper_without_facts_or_audit_emits_no_evidence():
    assert (
        detail_for_review_required_copper(iwcc_facts=[])["non_oil_attribution_evidence"]
        == {}
    )


def test_review_required_copper_with_unavailable_refresh_status_is_unavailable():
    status = {
        "commodity_id": "copper",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "status": "unavailable",
        "error_message": "faostat fetch failed",
        "refreshed_at": "2026-08-02T00:00:00+00:00",
    }
    detail = detail_for_review_required_copper_with_status(
        iwcc_facts=[global_fact()], refresh_status=[status]
    )
    copper = detail["non_oil_attribution_evidence"]["copper"]
    assert copper["status"] == "unavailable"
    assert "faostat fetch failed" in copper["reason"]
    assert copper["next_action"]


def test_review_required_copper_with_available_refresh_status_stays_available():
    status = {
        "commodity_id": "copper",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "status": "available",
        "error_message": None,
        "refreshed_at": "2026-08-02T00:00:00+00:00",
    }
    detail = detail_for_review_required_copper_with_status(
        iwcc_facts=[global_fact()], refresh_status=[status]
    )
    copper = detail["non_oil_attribution_evidence"]["copper"]
    assert copper["status"] == "available"
    assert copper["facts"] == [global_fact()]


def test_review_required_iron_without_audit_omits_evidence():
    detail = detail_for_review_required_iron(facts=[], audit=None)
    assert detail["non_oil_attribution_evidence"] == {}


def test_review_required_iron_reason_sources_text_from_usgs_audit_basis():
    detail = detail_for_review_required_iron(facts=[], audit=audit_payload())
    iron = detail["non_oil_attribution_evidence"]["iron_ore"]
    assert "USGS" in iron["reason"]
    assert "ScienceBase transition" in iron["reason"]


def test_review_required_iron_without_usgs_audit_row_still_emits_reason():
    audit = audit_payload()
    audit["audits"] = [
        row
        for row in audit["audits"]
        if not (
            row.get("commodity_id") == "iron_ore"
            and row.get("source_name") == "US Geological Survey"
        )
    ]
    detail = detail_for_review_required_iron(facts=[], audit=audit)
    iron = detail["non_oil_attribution_evidence"]["iron_ore"]
    assert iron["status"] == "unavailable"
    assert "USGS" in iron["reason"]
