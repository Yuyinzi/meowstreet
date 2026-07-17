import json

import pytest

from app.tools import macro_growth_cycle


def test_growth_cycle_source_fields_are_grouped_by_source():
    source_ids = [source["id"] for source in macro_growth_cycle.GROWTH_CYCLE_SOURCES]

    assert source_ids == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_stock",
        "inflation_context",
        "gdp_expectations",
        "fed_balance_sheet",
        "jobless_claims",
    ]

    fields = [
        field["field"]
        for source in macro_growth_cycle.GROWTH_CYCLE_SOURCES
        for field in source["fields"]
    ]

    assert "macro.growth_cycle.ism_pmi" in fields
    assert "macro.growth_cycle.ism_customer_inventories" in fields
    assert "macro.growth_cycle.ism_prices" in fields
    assert "macro.growth_cycle.ism_order_backlog" in fields
    assert "macro.growth_cycle.ism_exports" in fields
    assert "macro.growth_cycle.ism_imports" in fields
    assert "macro.growth_cycle.services_business_activity" in fields
    assert "macro.growth_cycle.m2_money_stock" in fields
    assert "macro.growth_cycle.core_pce_yoy" in fields
    assert "macro.growth_cycle.gdp_expectations" in fields
    assert "macro.growth_cycle.initial_jobless_claims" in fields


def test_normalize_ism_manufacturing_maps_components_to_growth_cycle_fields():
    payload = {
        "period": "2026-06",
        "pmi": "51.2",
        "new_orders": "52.0",
        "production": "50.4",
        "employment": "49.8",
        "supplier_deliveries": "50.1",
        "inventories": "48.6",
        "customer_inventories": "47.5",
        "prices": "55.3",
        "order_backlog": "49.0",
        "exports": "51.8",
        "imports": "50.2",
    }

    assert macro_growth_cycle.normalize_ism_manufacturing(payload) == {
        "macro": {
            "growth_cycle": {
                "ism_period": "2026-06",
                "ism_pmi": 51.2,
                "ism_new_orders": 52.0,
                "ism_production": 50.4,
                "ism_employment": 49.8,
                "ism_supplier_deliveries": 50.1,
                "ism_inventories": 48.6,
                "ism_customer_inventories": 47.5,
                "ism_prices": 55.3,
                "ism_order_backlog": 49.0,
                "ism_exports": 51.8,
                "ism_imports": 50.2,
            }
        }
    }


def test_normalize_ism_services_maps_components_to_growth_cycle_fields():
    payload = {
        "period": "2026-06",
        "pmi": "53.0",
        "business_activity": "54.1",
        "new_orders": "52.7",
        "employment": "50.6",
        "supplier_deliveries": "49.9",
        "backlog_orders": "51.3",
    }

    assert macro_growth_cycle.normalize_ism_services(payload) == {
        "macro": {
            "growth_cycle": {
                "services_period": "2026-06",
                "services_pmi": 53.0,
                "services_business_activity": 54.1,
                "services_new_orders": 52.7,
                "services_employment": 50.6,
                "services_supplier_deliveries": 49.9,
                "services_backlog_orders": 51.3,
            }
        }
    }


def test_normalize_m2_computes_latest_growth_rates_and_percent_ranks():
    payload = {
        "series": [
            {"date": "2025-06-01", "value": 100},
            {"date": "2025-07-01", "value": 100},
            {"date": "2025-08-01", "value": 100},
            {"date": "2025-09-01", "value": 100},
            {"date": "2025-10-01", "value": 100},
            {"date": "2025-11-01", "value": 100},
            {"date": "2025-12-01", "value": 100},
            {"date": "2026-01-01", "value": 100},
            {"date": "2026-02-01", "value": 100},
            {"date": "2026-03-01", "value": 100},
            {"date": "2026-04-01", "value": 100},
            {"date": "2026-05-01", "value": 100},
            {"date": "2026-06-01", "value": 120},
        ]
    }

    result = macro_growth_cycle.normalize_m2_money_stock(payload)

    growth_cycle = result["macro"]["growth_cycle"]
    assert growth_cycle["m2_period"] == "2026-06-01"
    assert growth_cycle["m2_money_stock"] == 120
    assert round(growth_cycle["m2_mom_pct_change"], 4) == 0.2
    assert round(growth_cycle["m2_yoy_pct_change"], 4) == 0.2
    assert growth_cycle["m2_mom_percent_rank"] == 1.0
    assert growth_cycle["m2_yoy_percent_rank"] == 1.0


def test_normalize_m2_requires_thirteen_rows_for_yoy_fields():
    payload = {
        "series": [
            {"date": "2026-05-01", "value": 100},
            {"date": "2026-06-01", "value": 120},
        ]
    }

    result = macro_growth_cycle.normalize_m2_money_stock(payload)

    growth_cycle = result["macro"]["growth_cycle"]
    assert growth_cycle["m2_mom_pct_change"] == 0.19999999999999996
    assert growth_cycle["m2_yoy_pct_change"] is None
    assert growth_cycle["m2_yoy_percent_rank"] is None


def test_normalize_jobless_claims_classifies_labor_trend_from_four_week_average():
    payload = {
        "initial_claims": [
            {"date": "2026-06-01", "value": 220000},
            {"date": "2026-06-06", "value": 222000},
            {"date": "2026-06-13", "value": 223000},
            {"date": "2026-06-20", "value": 225000},
            {"date": "2026-06-27", "value": 230000},
            {"date": "2026-07-04", "value": 235000},
            {"date": "2026-07-11", "value": 240000},
            {"date": "2026-07-18", "value": 245000},
        ],
        "continuing_claims": [
            {"date": "2026-06-01", "value": 1800000},
            {"date": "2026-06-06", "value": 1810000},
            {"date": "2026-06-13", "value": 1820000},
            {"date": "2026-06-20", "value": 1830000},
            {"date": "2026-06-27", "value": 1840000},
            {"date": "2026-07-04", "value": 1850000},
            {"date": "2026-07-11", "value": 1860000},
            {"date": "2026-07-18", "value": 1880000},
        ],
    }

    result = macro_growth_cycle.normalize_jobless_claims(payload)

    growth_cycle = result["macro"]["growth_cycle"]
    assert growth_cycle["jobless_claims_period"] == "2026-07-18"
    assert growth_cycle["initial_jobless_claims"] == 245000
    assert growth_cycle["continuing_jobless_claims"] == 1880000
    assert growth_cycle["initial_claims_4w_avg"] == 237500
    assert growth_cycle["labor_trend"] == "weakening"


def test_normalize_jobless_claims_requires_previous_window_for_labor_trend():
    payload = {
        "initial_claims": [
            {"date": "2026-06-06", "value": 220000},
            {"date": "2026-06-13", "value": 225000},
            {"date": "2026-06-20", "value": 235000},
            {"date": "2026-06-27", "value": 245000},
        ],
        "continuing_claims": [
            {"date": "2026-06-27", "value": 1880000},
        ],
    }

    result = macro_growth_cycle.normalize_jobless_claims(payload)

    assert result["macro"]["growth_cycle"]["initial_claims_4w_avg"] == 231250
    assert result["macro"]["growth_cycle"]["labor_trend"] == "unknown"


def test_build_growth_cycle_dashboard_merges_normalized_sources():
    result = macro_growth_cycle.build_growth_cycle_dashboard(
        ism_manufacturing={
            "period": "2026-06",
            "pmi": 51.2,
            "new_orders": 52.0,
            "production": 50.4,
            "employment": 49.8,
            "supplier_deliveries": 50.1,
            "inventories": 48.6,
            "customer_inventories": 47.5,
            "prices": 55.3,
            "order_backlog": 49.0,
            "exports": 51.8,
            "imports": 50.2,
        },
        ism_services={
            "period": "2026-06",
            "pmi": 53.0,
            "business_activity": 54.1,
            "new_orders": 52.7,
            "employment": 50.6,
            "supplier_deliveries": 49.9,
            "backlog_orders": 51.3,
        },
        m2_money_stock={
            "series": [
                {"date": "2025-06-01", "value": 20000},
                {"date": "2026-04-01", "value": 20900},
                {"date": "2026-05-01", "value": 21000},
                {"date": "2026-06-01", "value": 21210},
            ]
        },
        jobless_claims={
            "initial_claims": [
                {"date": "2026-06-06", "value": 220000},
                {"date": "2026-06-13", "value": 225000},
                {"date": "2026-06-20", "value": 235000},
                {"date": "2026-06-27", "value": 245000},
            ],
            "continuing_claims": [
                {"date": "2026-06-27", "value": 1880000},
            ],
        },
    )

    growth_cycle = result["macro"]["growth_cycle"]
    assert growth_cycle["ism_pmi"] == 51.2
    assert growth_cycle["ism_customer_inventories"] == 47.5
    assert growth_cycle["ism_prices"] == 55.3
    assert growth_cycle["ism_order_backlog"] == 49.0
    assert growth_cycle["ism_exports"] == 51.8
    assert growth_cycle["ism_imports"] == 50.2
    assert growth_cycle["services_pmi"] == 53.0
    assert growth_cycle["m2_money_stock"] == 21210
    assert growth_cycle["initial_jobless_claims"] == 245000


def test_normalize_ism_manufacturing_with_missing_extended_fields_does_not_break():
    payload = {
        "period": "2026-06",
        "pmi": "51.2",
        "new_orders": "52.0",
    }

    result = macro_growth_cycle.normalize_ism_manufacturing(payload)
    growth_cycle = result["macro"]["growth_cycle"]

    assert growth_cycle["ism_pmi"] == 51.2
    assert growth_cycle["ism_customer_inventories"] is None
    assert growth_cycle["ism_prices"] is None
    assert growth_cycle["ism_order_backlog"] is None
    assert growth_cycle["ism_exports"] is None
    assert growth_cycle["ism_imports"] is None


def test_build_ism_manufacturing_payload_from_latest_points_maps_series_to_payload():
    points_by_series_id = {
        "ism_manufacturing_pmi": [
            {"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_new_orders": [
            {"date": "2026-06-01", "value": 52.0, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_production": [
            {"date": "2026-06-01", "value": 50.4, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_employment": [
            {"date": "2026-06-01", "value": 49.8, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_supplier_deliveries": [
            {"date": "2026-06-01", "value": 50.1, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_inventories": [
            {"date": "2026-06-01", "value": 48.6, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_customer_inventories": [
            {"date": "2026-06-01", "value": 47.5, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_prices": [
            {"date": "2026-06-01", "value": 55.3, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_order_backlog": [
            {"date": "2026-06-01", "value": 49.0, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_exports": [
            {"date": "2026-06-01", "value": 51.8, "source": "ISM.xlsx"}
        ],
        "ism_manufacturing_imports": [
            {"date": "2026-06-01", "value": 50.2, "source": "ISM.xlsx"}
        ],
    }

    result = macro_growth_cycle.build_ism_manufacturing_payload_from_latest_points(
        points_by_series_id,
    )

    assert result == {
        "period": "2026-06-01",
        "pmi": 51.2,
        "new_orders": 52.0,
        "production": 50.4,
        "employment": 49.8,
        "supplier_deliveries": 50.1,
        "inventories": 48.6,
        "customer_inventories": 47.5,
        "prices": 55.3,
        "order_backlog": 49.0,
        "exports": 51.8,
        "imports": 50.2,
    }


def test_build_ism_manufacturing_payload_with_missing_series_returns_none_values():
    result = macro_growth_cycle.build_ism_manufacturing_payload_from_latest_points({})

    assert result["period"] is None
    assert result["pmi"] is None
    assert result["customer_inventories"] is None
    assert len(result) == 12


def test_build_ism_manufacturing_payload_uses_latest_date_across_series():
    points_by_series_id = {
        "ism_manufacturing_pmi": [
            {"date": "2026-05-01", "value": 50.0, "source": "ISM.xlsx"},
            {"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"},
        ],
        "ism_manufacturing_new_orders": [
            {"date": "2026-04-01", "value": 49.0, "source": "ISM.xlsx"},
        ],
    }

    result = macro_growth_cycle.build_ism_manufacturing_payload_from_latest_points(
        points_by_series_id,
    )

    assert result["period"] == "2026-06-01"
    assert result["pmi"] == 51.2
    assert result["new_orders"] == 49.0


def test_growth_cycle_bias_is_long_when_manufacturing_and_services_expand():
    growth_cycle = {
        "ism_pmi": 51.2,
        "ism_new_orders": 52.0,
        "services_pmi": 53.0,
        "services_business_activity": 54.1,
        "services_new_orders": 52.7,
        "labor_trend": "stable",
    }

    assert macro_growth_cycle.compute_growth_cycle_bias(growth_cycle) == "long"


def test_growth_cycle_bias_is_short_when_both_surveys_contract_and_labor_weakens():
    growth_cycle = {
        "ism_pmi": 48.0,
        "ism_new_orders": 47.0,
        "services_pmi": 49.0,
        "services_business_activity": 48.5,
        "services_new_orders": 48.0,
        "labor_trend": "weakening",
    }

    assert macro_growth_cycle.compute_growth_cycle_bias(growth_cycle) == "short"


def test_fetch_m2_money_stock_source_not_configured():
    with pytest.raises(ValueError, match="m2 money stock source is not configured"):
        macro_growth_cycle.fetch_m2_money_stock_from_source()


def test_fetch_jobless_claims_source_not_configured():
    with pytest.raises(ValueError, match="jobless claims source is not configured"):
        macro_growth_cycle.fetch_jobless_claims_from_source()


def test_fetch_ism_manufacturing_source_not_configured():
    with pytest.raises(ValueError, match="ism manufacturing source is not configured"):
        macro_growth_cycle.fetch_ism_manufacturing_from_source()


def test_fetch_ism_services_source_not_configured():
    with pytest.raises(ValueError, match="ism services source is not configured"):
        macro_growth_cycle.fetch_ism_services_from_source()


def test_fetch_growth_cycle_dashboard_uses_injected_fetchers():
    calls = []

    def fetch_ism_manufacturing():
        calls.append("ism_manufacturing")
        return {
            "period": "2026-06",
            "pmi": 51.2,
            "new_orders": 52.0,
            "production": 50.4,
            "employment": 49.8,
            "supplier_deliveries": 50.1,
            "inventories": 48.6,
        }

    def fetch_ism_services():
        calls.append("ism_services")
        return {"period": "2026-06", "pmi": 53.0}

    def fetch_m2_money_stock():
        calls.append("m2_money_stock")
        return {"series": [{"date": "2026-06-01", "value": 21210}]}

    def fetch_jobless_claims():
        calls.append("jobless_claims")
        return {"initial_claims": [], "continuing_claims": []}

    result = macro_growth_cycle.fetch_growth_cycle_dashboard(
        fetch_ism_manufacturing=fetch_ism_manufacturing,
        fetch_ism_services=fetch_ism_services,
        fetch_m2_money_stock=fetch_m2_money_stock,
        fetch_jobless_claims=fetch_jobless_claims,
    )

    assert calls == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_stock",
        "jobless_claims",
    ]
    assert result["macro"]["growth_cycle"]["ism_pmi"] == 51.2


def test_growth_cycle_bias_is_neutral_when_only_one_survey_expands():
    growth_cycle = {
        "ism_pmi": 51.0,
        "ism_new_orders": 52.0,
        "services_pmi": 49.0,
        "services_business_activity": 48.0,
        "labor_trend": "stable",
    }
    result = macro_growth_cycle.compute_growth_cycle_bias(growth_cycle)
    assert result == "neutral"


def test_normalize_jobless_claims_classifies_strengthening_labor_trend():
    payload = {
        "initial_claims": [
            {"date": "2026-05-06", "value": "250"},
            {"date": "2026-05-13", "value": "248"},
            {"date": "2026-05-20", "value": "245"},
            {"date": "2026-05-27", "value": "242"},
            {"date": "2026-06-03", "value": "230"},
            {"date": "2026-06-10", "value": "225"},
            {"date": "2026-06-17", "value": "222"},
            {"date": "2026-06-24", "value": "220"},
        ],
        "continuing_claims": [{"date": "2026-06-17", "value": "1800000"}],
    }
    result = macro_growth_cycle.normalize_jobless_claims(payload)
    assert result["macro"]["growth_cycle"]["labor_trend"] == "strengthening"


def test_normalize_jobless_claims_classifies_stable_labor_trend():
    payload = {
        "initial_claims": [
            {"date": "2026-05-06", "value": "250"},
            {"date": "2026-05-13", "value": "248"},
            {"date": "2026-05-20", "value": "252"},
            {"date": "2026-05-27", "value": "249"},
            {"date": "2026-06-03", "value": "251"},
            {"date": "2026-06-10", "value": "247"},
            {"date": "2026-06-17", "value": "253"},
            {"date": "2026-06-24", "value": "248"},
        ],
        "continuing_claims": [{"date": "2026-06-17", "value": "1800000"}],
    }
    result = macro_growth_cycle.normalize_jobless_claims(payload)
    assert result["macro"]["growth_cycle"]["labor_trend"] == "stable"


def test_normalize_m2_computes_three_month_momentum():
    payload = {
        "series": [
            {"date": "2026-01-01", "value": 100},
            {"date": "2026-02-01", "value": 104},
            {"date": "2026-03-01", "value": 108},
            {"date": "2026-04-01", "value": 110},
            {"date": "2026-05-01", "value": 112},
            {"date": "2026-06-01", "value": 121},
        ]
    }

    result = macro_growth_cycle.normalize_m2_money_stock(payload)

    growth_cycle = result["macro"]["growth_cycle"]
    assert round(growth_cycle["m2_3m_momentum"], 4) == 0.1204


def test_build_m2_money_supply_detail_payload_returns_four_chart_series():
    rows = [
        {"date": "2025-01-01", "value": 100.0, "source": "m2.xlsx"},
        {"date": "2025-02-01", "value": 101.0, "source": "m2.xlsx"},
        {"date": "2025-03-01", "value": 102.0, "source": "m2.xlsx"},
        {"date": "2025-04-01", "value": 103.0, "source": "m2.xlsx"},
        {"date": "2025-05-01", "value": 104.0, "source": "m2.xlsx"},
        {"date": "2025-06-01", "value": 105.0, "source": "m2.xlsx"},
        {"date": "2025-07-01", "value": 106.0, "source": "m2.xlsx"},
        {"date": "2025-08-01", "value": 107.0, "source": "m2.xlsx"},
        {"date": "2025-09-01", "value": 108.0, "source": "m2.xlsx"},
        {"date": "2025-10-01", "value": 109.0, "source": "m2.xlsx"},
        {"date": "2025-11-01", "value": 110.0, "source": "m2.xlsx"},
        {"date": "2025-12-01", "value": 111.0, "source": "m2.xlsx"},
        {"date": "2026-01-01", "value": 125.0, "source": "m2.xlsx"},
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(rows)
    assert [chart["title"] for chart in payload["charts"]] == [
        "M2 YoY Growth vs Inflation Constraint",
        "Fed Total Assets YoY",
        "M2 3M Change",
        "Fed Balance Sheet 13W Composition",
        "M2 MoM Shock Events",
    ]
    assert payload["charts"][0]["series"] == [
        {
            "date": "2026-01-01",
            "m2_yoy": 25.0,
            "core_pce_yoy": None,
            "fed_target": 2.0,
        },
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(rows)

    assert payload["detail_id"] == "m2_money_supply"
    assert payload["title"] == "M2 Money Supply"
    assert payload["source"] == "m2.xlsx"
    assert [chart["title"] for chart in payload["charts"]] == [
        "M2 YoY Growth vs Inflation Constraint",
        "Fed Total Assets YoY",
        "M2 3M Change",
        "Fed Balance Sheet 13W Composition",
        "M2 MoM Shock Events",
    ]
    assert payload["charts"][0]["series"] == [
        {
            "date": "2026-01-01",
            "m2_yoy": 25.0,
            "core_pce_yoy": None,
            "fed_target": 2.0,
        },
    ]
    assert round(payload["charts"][2]["series"][-1]["value"], 4) == 14.6789
    assert payload["charts"][4]["series"][-1] == {
        "date": "2026-01-01",
        "value": 2,
        "mom_growth": 12.6126,
        "percentile": 100.0,
        "signal": "extreme_injection",
    }


def test_build_m2_money_supply_detail_payload_handles_short_history():
    rows = [
        {"date": "2026-01-01", "value": 100.0, "source": "m2.xlsx"},
        {"date": "2026-02-01", "value": 102.0, "source": "m2.xlsx"},
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(rows)

    assert payload["charts"][0]["series"] == []
    assert payload["charts"][1]["series"] == []
    assert payload["charts"][2]["series"] == []
    assert payload["charts"][3]["series"] == []
    assert payload["charts"][4]["series"] == [
        {
            "date": "2026-02-01",
            "value": 2,
            "mom_growth": 2.0,
            "percentile": 100.0,
            "signal": "extreme_injection",
        }
    ]


def test_build_m2_money_supply_headline_groups_state_change_and_shock():
    growth_cycle = {
        "m2_period": "2026-06-01",
        "m2_money_stock": 21210.0,
        "m2_yoy_pct_change": 0.042,
        "m2_yoy_percent_rank": 0.72,
        "m2_3m_momentum": 0.011,
        "m2_mom_pct_change": 0.004,
        "m2_mom_percent_rank": 0.63,
    }

    headline = macro_growth_cycle.build_m2_money_supply_headline(growth_cycle)

    assert headline == {
        "id": "m2_money_supply",
        "label": "M2 Money Supply",
        "period": "2026-06-01",
        "status": "expanding",
        "status_label": "Expanding",
        "state": {
            "m2_yoy_pct_change": 0.042,
            "m2_yoy_percent_rank": 0.72,
            "m2_money_stock": 21210.0,
        },
        "change": {
            "m2_3m_momentum": 0.011,
        },
        "shock": {
            "m2_mom_pct_change": 0.004,
            "m2_mom_percent_rank": 0.63,
        },
    }


def test_build_growth_cycle_dashboard_payload_wraps_headline():
    growth_cycle = {
        "m2_period": "2026-06-01",
        "m2_money_stock": 21210.0,
        "m2_yoy_pct_change": 0.042,
        "m2_yoy_percent_rank": 0.72,
        "m2_3m_momentum": 0.011,
        "m2_mom_pct_change": 0.004,
        "m2_mom_percent_rank": 0.63,
    }
    result = macro_growth_cycle.build_growth_cycle_dashboard_payload(
        {"macro": {"growth_cycle": growth_cycle}}
    )
    assert result["headline"][1]["state"]["m2_money_stock"] == 21210.0
    assert result["missing"] is None
    assert result["growth_cycle"]["m2_money_stock"] == 21210.0


def test_build_growth_cycle_dashboard_payload_groups_headline_cards_into_sections():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
        ism_manufacturing={
            "period": "2026-06-01",
            "pmi": 51.2,
            "new_orders": 52.0,
        },
        m2_money_stock={
            "series": [
                {"date": "2025-06-01", "value": 100},
                {"date": "2025-07-01", "value": 101},
                {"date": "2025-08-01", "value": 102},
                {"date": "2025-09-01", "value": 103},
                {"date": "2025-10-01", "value": 104},
                {"date": "2025-11-01", "value": 105},
                {"date": "2025-12-01", "value": 106},
                {"date": "2026-01-01", "value": 107},
                {"date": "2026-02-01", "value": 108},
                {"date": "2026-03-01", "value": 109},
                {"date": "2026-04-01", "value": 110},
                {"date": "2026-05-01", "value": 111},
                {"date": "2026-06-01", "value": 112},
            ]
        },
        core_pce_price_index={
            "series": [
                {"date": "2025-06-01", "value": 100},
                {"date": "2025-07-01", "value": 100},
                {"date": "2025-08-01", "value": 100},
                {"date": "2025-09-01", "value": 100},
                {"date": "2025-10-01", "value": 100},
                {"date": "2025-11-01", "value": 100},
                {"date": "2025-12-01", "value": 100},
                {"date": "2026-01-01", "value": 100},
                {"date": "2026-02-01", "value": 100},
                {"date": "2026-03-01", "value": 100},
                {"date": "2026-04-01", "value": 100},
                {"date": "2026-05-01", "value": 100},
                {"date": "2026-06-01", "value": 103},
            ]
        },
    )

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)

    sections = {section["id"]: section for section in payload["sections"]}
    assert list(sections) == [
        "ism_manufacturing",
        "m2_liquidity",
        "inflation_context",
        "services_labor",
        "gdp_expectations",
        "fomc_context",
    ]
    assert sections["ism_manufacturing"]["status"] == "available"
    assert sections["ism_manufacturing"]["period"] == "2026-06-01"
    assert sections["ism_manufacturing"]["cards"] == ["ism_manufacturing"]
    assert sections["m2_liquidity"]["cards"] == ["m2_money_supply"]
    assert sections["inflation_context"]["cards"] == ["inflation_context"]
    assert sections["gdp_expectations"]["cards"] == ["gdp_expectations"]
    assert sections["fomc_context"]["cards"] == []


def test_build_growth_cycle_dashboard_payload_marks_ism_missing_without_ism_values():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
        m2_money_stock={
            "series": [
                {"date": "2025-06-01", "value": 100},
                {"date": "2026-06-01", "value": 112},
            ]
        },
    )

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)

    sections = {section["id"]: section for section in payload["sections"]}
    assert sections["ism_manufacturing"]["status"] == "missing"
    assert sections["ism_manufacturing"]["period"] is None
    assert sections["ism_manufacturing"]["cards"] == ["ism_manufacturing"]
    core_pce_rows = [
        {"date": "2025-01-01", "value": 130.0, "source": "FRED monthly"},
        {"date": "2025-02-01", "value": 130.5, "source": "FRED monthly"},
        {"date": "2025-03-01", "value": 131.0, "source": "FRED monthly"},
        {"date": "2025-04-01", "value": 131.5, "source": "FRED monthly"},
        {"date": "2025-05-01", "value": 132.0, "source": "FRED monthly"},
        {"date": "2025-06-01", "value": 132.5, "source": "FRED monthly"},
        {"date": "2025-07-01", "value": 133.0, "source": "FRED monthly"},
        {"date": "2025-08-01", "value": 133.5, "source": "FRED monthly"},
        {"date": "2025-09-01", "value": 134.0, "source": "FRED monthly"},
        {"date": "2025-10-01", "value": 134.5, "source": "FRED monthly"},
        {"date": "2025-11-01", "value": 135.0, "source": "FRED monthly"},
        {"date": "2025-12-01", "value": 135.5, "source": "FRED monthly"},
        {"date": "2026-01-01", "value": 136.0, "source": "FRED monthly"},
    ]

    m2_rows = [
        {"date": f"2025-{month:02d}-01", "value": 100.0} for month in range(1, 13)
    ] + [{"date": "2026-01-01", "value": 125.0}]
    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
        m2_rows,
        core_pce_rows,
    )
    chart = payload["charts"][0]

    assert chart["title"] == "M2 YoY Growth vs Inflation Constraint"
    assert chart["keys"] == ["m2_yoy", "core_pce_yoy", "fed_target"]
    assert chart["labels"] == {
        "m2_yoy": "M2 YoY Growth",
        "core_pce_yoy": "Core PCE YoY",
        "fed_target": "Fed Target (since 2012)",
    }
    assert len(chart["series"]) >= 1
    assert chart["series"][0]["m2_yoy"] == 25.0


def test_m2_detail_state_chart_starts_fed_target_in_2012():
    m2_rows = [
        {"date": f"{year}-01-01", "value": value, "source": "m2.xlsx"}
        for year, value in [
            (1999, 100.0),
            (2000, 102.0),
            (2001, 104.0),
            (2002, 106.0),
            (2003, 108.0),
            (2004, 110.0),
            (2005, 112.0),
            (2006, 114.0),
            (2007, 116.0),
            (2008, 118.0),
            (2009, 120.0),
            (2010, 122.0),
            (2011, 124.0),
            (2012, 126.0),
        ]
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(m2_rows)
    state_series = payload["charts"][0]["series"]

    assert state_series[-2]["date"] == "2011-01-01"
    assert state_series[-2]["fed_target"] is None
    assert state_series[-1]["date"] == "2012-01-01"
    assert state_series[-1]["fed_target"] == 2.0


def test_normalize_inflation_context_computes_core_pce_yoy_and_target_gap():
    payload = {
        "series": [
            {"date": "2025-01-01", "value": 130.0},
            {"date": "2025-02-01", "value": 130.0},
            {"date": "2025-03-01", "value": 130.0},
            {"date": "2025-04-01", "value": 130.0},
            {"date": "2025-05-01", "value": 130.0},
            {"date": "2025-06-01", "value": 130.0},
            {"date": "2025-07-01", "value": 130.0},
            {"date": "2025-08-01", "value": 130.0},
            {"date": "2025-09-01", "value": 130.0},
            {"date": "2025-10-01", "value": 130.0},
            {"date": "2025-11-01", "value": 130.0},
            {"date": "2025-12-01", "value": 130.0},
            {"date": "2026-01-01", "value": 134.0},
        ]
    }

    result = macro_growth_cycle.normalize_core_pce_price_index(payload)
    growth_cycle = result["macro"]["growth_cycle"]

    assert growth_cycle["inflation_context_period"] == "2026-01-01"
    assert growth_cycle["core_pce_price_index"] == 134.0
    assert round(growth_cycle["core_pce_yoy"], 4) == 0.0308
    assert round(growth_cycle["inflation_target_gap"], 4) == 0.0108
    assert growth_cycle["inflation_context_status"] == "above_target"


def test_inflation_context_status_thresholds():
    assert macro_growth_cycle._inflation_context_status(0.006) == "above_target"
    assert macro_growth_cycle._inflation_context_status(0.0049) == "near_target"
    assert macro_growth_cycle._inflation_context_status(-0.0049) == "near_target"
    assert macro_growth_cycle._inflation_context_status(-0.006) == "below_target"
    assert macro_growth_cycle._inflation_context_status(None) == "missing"


def test_build_inflation_context_headline_returns_card_shape():
    growth_cycle = {
        "inflation_context_period": "2026-01-01",
        "core_pce_yoy": 0.0308,
        "inflation_target_gap": 0.0108,
        "inflation_context_status": "above_target",
    }

    card = macro_growth_cycle.build_inflation_context_headline(growth_cycle)

    assert card == {
        "id": "inflation_context",
        "label": "Inflation Context",
        "period": "2026-01-01",
        "status": "above_target",
        "status_label": "Above Target",
        "core_pce_yoy": 0.0308,
        "target": 0.02,
        "target_label": "Fed 2% Target",
        "gap": 0.0108,
        "description": "Inflation is above the Fed target, which can constrain liquidity support.",
    }


def test_growth_cycle_dashboard_payload_includes_gdp_expectations_placeholder():
    dashboard = {
        "macro": {
            "growth_cycle": {
                "m2_period": "2026-01-01",
                "m2_money_stock": 100.0,
                "m2_mom_pct_change": 0.01,
                "m2_yoy_pct_change": 0.04,
                "m2_3m_momentum": 0.02,
                "m2_mom_percent_rank": 0.50,
                "m2_yoy_percent_rank": 0.60,
            }
        }
    }

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)

    assert [card["id"] for card in payload["headline"]] == [
        "ism_manufacturing",
        "m2_money_supply",
        "gdp_expectations",
    ]
    assert payload["headline"][2]["status"] == "pending_inputs"


def test_build_gdp_expectations_headline_returns_pending_inputs_card():
    card = macro_growth_cycle.build_gdp_expectations_headline({})

    assert card == {
        "id": "gdp_expectations",
        "label": "GDP Expectations",
        "period": None,
        "status": "pending_inputs",
        "status_label": "Pending Inputs",
        "expected_direction": None,
        "components": [
            {"id": "ism_manufacturing", "status": "pending"},
            {"id": "ism_services", "status": "pending"},
            {"id": "labor_trend", "status": "pending"},
            {"id": "consumer_indicators", "status": "pending"},
        ],
        "missing_inputs": [
            "ISM Services",
            "Labor trend",
            "Consumer indicators",
        ],
        "evidence": [],
        "supporting_context": "GDP / Market Relationship validates why GDP direction matters, but it does not replace a forward GDP expectation signal.",
    }


def test_build_gdp_expectations_headline_with_supportive_ism():
    signal = {
        "status": "available",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "growth_impulse": "supports_growth",
        "evidence": [
            "PMI is above 50 and rising month over month",
            "New Orders are above 50 and rising month over month",
            "Growth impulse supports continued expansion",
        ],
    }
    card = macro_growth_cycle.build_gdp_expectations_headline(
        {"gdp_expectations_period": "2026-06-01"},
        ism_macro_signal=signal,
    )

    assert card["id"] == "gdp_expectations"
    assert card["status"] == "partial_inputs"
    assert card["status_label"] == "Partial Inputs"
    assert card["expected_direction"] is None
    assert card["components"][0] == {
        "id": "ism_manufacturing",
        "status": "available",
        "direction": "supports_growth",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "growth_impulse": "supports_growth",
    }
    assert card["components"][1:] == [
        {"id": "ism_services", "status": "pending"},
        {"id": "labor_trend", "status": "pending"},
        {"id": "consumer_indicators", "status": "pending"},
    ]
    assert "PMI is above 50" in card["evidence"][0]
    assert "Growth impulse supports continued expansion" in card["evidence"][2]
    assert "ISM Services" in card["missing_inputs"]


def test_build_gdp_expectations_headline_with_cautionary_ism():
    signal = {
        "status": "available",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "growth_impulse": "growth_caution",
        "evidence": [
            "PMI is above 50 but falling month over month",
            "Growth impulse signals caution in expansion",
        ],
    }
    card = macro_growth_cycle.build_gdp_expectations_headline(
        {},
        ism_macro_signal=signal,
    )

    assert card["status"] == "partial_inputs"
    assert card["components"][0]["direction"] == "growth_caution"
    assert card["components"][0]["growth_impulse"] == "growth_caution"
    assert "Growth impulse signals caution" in card["evidence"][1]


def test_build_gdp_expectations_headline_with_contraction_ism():
    signal = {
        "status": "available",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "growth_impulse": "supports_contraction",
        "evidence": [
            "PMI is below 50 and falling month over month",
            "Growth impulse supports continued contraction",
        ],
    }
    card = macro_growth_cycle.build_gdp_expectations_headline(
        {},
        ism_macro_signal=signal,
    )

    assert card["status"] == "partial_inputs"
    assert card["components"][0]["direction"] == "supports_contraction"
    assert "supports continued contraction" in card["evidence"][1]


def test_build_gdp_expectations_headline_with_unavailable_ism():
    signal = {
        "status": "unavailable",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "growth_impulse": None,
        "evidence": [],
    }
    card = macro_growth_cycle.build_gdp_expectations_headline(
        {},
        ism_macro_signal=signal,
    )

    assert card["status"] == "pending_inputs"
    assert card["status_label"] == "Pending Inputs"
    assert card["components"][0]["status"] == "unavailable"
    assert "ISM Manufacturing" in card["missing_inputs"]
    assert card["evidence"] == []


def test_build_gdp_expectations_headline_with_partial_ism():
    signal = {
        "status": "partial",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "growth_impulse": "mixed",
        "evidence": ["New Orders are missing or unavailable"],
    }
    card = macro_growth_cycle.build_gdp_expectations_headline(
        {},
        ism_macro_signal=signal,
    )

    assert card["status"] == "partial_inputs"
    assert card["components"][0]["status"] == "partial"
    assert card["components"][0]["direction"] == "mixed"
    assert "New Orders are missing" in card["evidence"][0]


def test_normalize_fed_balance_sheet_computes_card_metrics_without_status():
    total_assets = {
        "series": [
            {"date": f"2025-{week:02d}-01", "value": 6000000.0} for week in range(1, 40)
        ]
        + [
            {"date": f"2025-{week:02d}-01", "value": 6650000.0}
            for week in range(40, 53)
        ]
        + [{"date": "2026-01-14", "value": 6710000.0}]
    }
    treasury = {
        "series": [
            {"date": f"2025-{week:02d}-01", "value": 4190000.0} for week in range(1, 40)
        ]
        + [
            {"date": f"2025-{week:02d}-01", "value": 4190000.0}
            for week in range(40, 53)
        ]
        + [{"date": "2026-01-14", "value": 4210000.0}]
    }
    mbs = {
        "series": [
            {"date": f"2025-{week:02d}-01", "value": 2210000.0} for week in range(1, 40)
        ]
        + [
            {"date": f"2025-{week:02d}-01", "value": 2210000.0}
            for week in range(40, 53)
        ]
        + [{"date": "2026-01-14", "value": 2195000.0}]
    }

    result = macro_growth_cycle.normalize_fed_balance_sheet(
        total_assets,
        treasury,
        mbs,
    )
    growth_cycle = result["macro"]["growth_cycle"]

    assert growth_cycle["fed_balance_sheet_period"] == "2026-01-14"
    assert growth_cycle["fed_total_assets"] == 6710000.0
    assert round(growth_cycle["fed_total_assets_yoy"], 4) == 0.1183
    assert growth_cycle["fed_total_assets_13w_change"] == 60000.0
    assert growth_cycle["fed_treasury_13w_change"] == 20000.0
    assert growth_cycle["fed_mbs_13w_change"] == -15000.0

    card = macro_growth_cycle.build_fed_balance_sheet_headline(growth_cycle)
    assert card["id"] == "fed_balance_sheet"
    assert card["status"] == "context"
    assert card["status_label"] == "Liquidity Context"
    assert card["total_assets"] == 6710000.0
    assert card["total_assets_yoy"] == growth_cycle["fed_total_assets_yoy"]
    assert card["total_assets_13w_change"] == 60000.0
    assert card["treasury_13w_change"] == 20000.0
    assert card["mbs_13w_change"] == -15000.0


def test_m2_detail_includes_fed_balance_sheet_comparison_charts():
    m2_rows = [
        {"date": f"2025-{month:02d}-01", "value": 100.0 + month, "source": "FRED"}
        for month in range(1, 13)
    ] + [{"date": "2026-01-01", "value": 125.0, "source": "FRED"}]
    fed_rows = [
        {
            "date": f"2025-{month:02d}-01",
            "value": 6000000.0 + month * 1000,
            "source": "FRED weekly",
        }
        for month in range(1, 13)
    ] + [{"date": "2026-01-01", "value": 6200000.0, "source": "FRED weekly"}]
    treasury_rows = [
        {"date": "2025-10-01", "value": 4200000.0, "source": "FRED weekly"},
        {"date": "2026-01-01", "value": 4215000.0, "source": "FRED weekly"},
    ]
    mbs_rows = [
        {"date": "2025-10-01", "value": 2200000.0, "source": "FRED weekly"},
        {"date": "2026-01-01", "value": 2190000.0, "source": "FRED weekly"},
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
        m2_rows,
        core_pce_rows=None,
        fed_total_assets_rows=fed_rows,
    )
    state_series = payload["charts"][0]["series"]

    assert state_series == [
        {
            "date": "2026-01-01",
            "m2_yoy": 23.7624,
            "core_pce_yoy": None,
            "fed_target": 2.0,
        },
    ]
    fed_series = payload["charts"][1]["series"]
    assert len(fed_series) == 1
    assert fed_series[0]["date"] == "2026-01-01"
    assert fed_series[0]["fed_total_assets_yoy"] == pytest.approx(3.3161, abs=1e-4)


def test_growth_cycle_payload_includes_next_fomc_card():
    dashboard = {"macro": {"growth_cycle": {}}}
    next_meeting = {
        "event_id": "fomc_2026_07_28",
        "event_type": "fomc_meeting",
        "start_date": "2026-07-28",
        "end_date": "2026-07-29",
        "display_month": "2026-07-01",
        "title": "FOMC Meeting",
        "source": "Federal Reserve",
        "policy_tone": "unknown",
        "has_sep": 0,
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(
        dashboard,
        next_fomc_meeting=next_meeting,
    )

    card = next(item for item in payload["headline"] if item["id"] == "fomc_calendar")
    assert card == {
        "id": "fomc_calendar",
        "label": "FOMC Calendar",
        "period": "2026-07-28",
        "status": "timing_context",
        "status_label": "Policy Timing",
        "next_meeting": {
            "start_date": "2026-07-28",
            "end_date": "2026-07-29",
            "display_month": "2026-07-01",
            "title": "FOMC Meeting",
            "policy_tone": "unknown",
            "has_sep": False,
            "source": "Federal Reserve",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        },
        "description": "FOMC dates are policy-timing context for reading liquidity, inflation, and balance-sheet changes. They are not buy/sell signals.",
    }


def test_m2_state_chart_includes_fomc_month_markers():
    m2_rows = [
        {"date": "2025-01-01", "value": 100.0, "source": "m2.csv"},
        {"date": "2025-02-01", "value": 101.0, "source": "m2.csv"},
        {"date": "2025-03-01", "value": 102.0, "source": "m2.csv"},
        {"date": "2025-04-01", "value": 103.0, "source": "m2.csv"},
        {"date": "2025-05-01", "value": 104.0, "source": "m2.csv"},
        {"date": "2025-06-01", "value": 105.0, "source": "m2.csv"},
        {"date": "2025-07-01", "value": 106.0, "source": "m2.csv"},
        {"date": "2025-08-01", "value": 107.0, "source": "m2.csv"},
        {"date": "2025-09-01", "value": 108.0, "source": "m2.csv"},
        {"date": "2025-10-01", "value": 109.0, "source": "m2.csv"},
        {"date": "2025-11-01", "value": 110.0, "source": "m2.csv"},
        {"date": "2025-12-01", "value": 111.0, "source": "m2.csv"},
        {"date": "2026-01-01", "value": 120.0, "source": "m2.csv"},
        {"date": "2026-02-01", "value": 121.0, "source": "m2.csv"},
    ]
    events = [
        {
            "event_id": "fomc_2026_01_27",
            "event_type": "fomc_meeting",
            "start_date": "2026-01-27",
            "end_date": "2026-01-28",
            "display_month": "2026-01-01",
            "title": "FOMC Meeting",
            "source": "Federal Reserve",
            "policy_tone": "unknown",
            "has_sep": 0,
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        }
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
        m2_rows,
        fomc_events=events,
    )

    assert payload["charts"][0]["events"] == [
        {
            "date": "2026-01-01",
            "event_date": "2026-01-27",
            "end_date": "2026-01-28",
            "label": "FOMC",
            "title": "FOMC Meeting",
            "kind": "fomc_meeting",
            "policy_tone": "unknown",
            "has_sep": False,
            "statement_tone": "unknown",
            "tone_change": "unknown",
            "confidence": None,
            "reason": None,
            "minutes_status": "pending",
            "minutes_tone": "unknown",
            "minutes_confirmation": "pending",
            "risk_focus": "unknown",
            "risk_bias": "unknown",
            "divergence_level": "unknown",
            "uncertainty_level": "unknown",
            "policy_conviction": "unknown",
            "minutes_confidence": None,
            "minutes_generated_at": None,
        }
    ]
    assert "events" not in payload["charts"][1]


def test_build_fomc_tone_headline_includes_minutes_structure_when_available():
    card = macro_growth_cycle.build_fomc_tone_headline(
        {
            "event_id": "fomc_2026_06_16",
            "start_date": "2026-06-16",
            "end_date": "2026-06-17",
            "statement_marker_tone": "hawkish",
            "statement_policy_action": "hold",
            "statement_guidance_bias": "neutral",
            "statement_language_tone": "hawkish",
            "statement_overall_bias": "mild_hawkish",
            "statement_tone_change": "more_hawkish",
            "statement_confidence": "medium",
            "statement_reason": "statement reason",
            "minutes_status": "available",
            "minutes_confirmation": "confirmed_but_divided",
            "risk_focus": "inflation",
            "risk_bias": "hawkish",
            "divergence_level": "medium",
            "uncertainty_level": "medium",
            "policy_conviction": "moderate",
            "minutes_confidence": "medium",
            "minutes_reason": "minutes reason",
        }
    )

    assert card["id"] == "fomc_tone"
    assert card["latest_tone"]["marker_tone"] == "hawkish"
    assert card["latest_tone"]["minutes_status"] == "available"
    assert card["latest_tone"]["minutes_confirmation"] == "confirmed_but_divided"
    assert card["latest_tone"]["risk_focus"] == "inflation"
    assert card["latest_tone"]["policy_conviction"] == "moderate"


def test_build_fomc_tone_headline_with_ism_policy_context():
    tone = {
        "event_id": "fomc_2026_06_16",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "statement_marker_tone": "hawkish",
        "statement_policy_action": "hold",
        "statement_guidance_bias": "neutral",
        "statement_language_tone": "hawkish",
        "statement_overall_bias": "mild_hawkish",
        "statement_tone_change": "more_hawkish",
        "statement_confidence": "medium",
        "statement_reason": "statement reason",
    }
    ism_context = {
        "combined_pressure": "inflation_caution",
        "growth_pressure": "less_easing_pressure",
        "inflation_pressure": "elevated",
        "supply_pressure": "normal",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "source_url": "https://example.com/june",
    }
    card = macro_growth_cycle.build_fomc_tone_headline(
        tone, ism_policy_context=ism_context
    )

    assert card["id"] == "fomc_tone"
    assert card["latest_tone"]["marker_tone"] == "hawkish"
    assert card["latest_tone"]["minutes_status"] == "pending"
    assert card["ism_policy_context"] == ism_context


def test_build_fomc_tone_headline_without_ism_context_is_unchanged():
    tone = {
        "event_id": "fomc_2026_06_16",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "statement_marker_tone": "dovish",
        "statement_policy_action": "cut",
    }
    card_with = macro_growth_cycle.build_fomc_tone_headline(
        tone, ism_policy_context=None
    )
    card_without = macro_growth_cycle.build_fomc_tone_headline(tone)

    assert card_with == card_without
    assert "ism_policy_context" not in card_with


def test_build_fomc_tone_missing_with_ism_context_stays_visible():
    ism_context = {
        "combined_pressure": "inflation_caution",
        "growth_pressure": "less_easing_pressure",
        "inflation_pressure": "elevated",
        "supply_pressure": "normal",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
        "source_url": "https://example.com/june",
    }
    card = macro_growth_cycle.build_fomc_tone_headline(
        None, ism_policy_context=ism_context
    )

    assert card["status"] == "context"
    assert card["status_label"] == "ISM Policy Context"
    assert card["latest_tone"] is None
    assert card["ism_policy_context"] == ism_context


def test_build_fomc_tone_ism_context_does_not_change_marker_tone():
    tone = {
        "event_id": "fomc_2026_06_16",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "statement_marker_tone": "hawkish",
        "statement_policy_action": "hold",
    }
    ism_context = {
        "combined_pressure": "stagflationary_tension",
        "growth_pressure": "more_easing_pressure",
        "inflation_pressure": "elevated",
        "supply_pressure": "elevated",
        "period": "2026-06-01",
        "version": "ism_macro_signal_v1",
    }
    card = macro_growth_cycle.build_fomc_tone_headline(
        tone, ism_policy_context=ism_context
    )

    assert card["latest_tone"]["marker_tone"] == "hawkish"
    assert card["ism_policy_context"]["combined_pressure"] == "stagflationary_tension"


def test_m2_fomc_chart_events_use_reviewed_statement_tone():
    events = [
        {
            "event_id": "fomc_2026_01_27",
            "event_type": "fomc_meeting",
            "start_date": "2026-01-27",
            "end_date": "2026-01-28",
            "display_month": "2026-01-01",
            "title": "FOMC Meeting",
            "source": "Federal Reserve",
            "policy_tone": "unknown",
            "statement_tone": "hawkish",
            "marker_tone": "hawkish",
            "tone_change": "more_hawkish",
            "tone_confidence": "medium",
            "tone_reason": "Inflation language became firmer.",
            "has_sep": 0,
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        }
    ]
    rows = [
        {"date": f"2025-{month:02d}-01", "value": 100 + month, "source": "m2.csv"}
        for month in range(1, 13)
    ] + [{"date": "2026-01-01", "value": 120, "source": "m2.csv"}]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
        rows,
        fomc_events=events,
    )

    event = payload["charts"][0]["events"][0]
    assert event["policy_tone"] == "hawkish"
    assert event["statement_tone"] == "hawkish"
    assert event["tone_change"] == "more_hawkish"
    assert event["confidence"] == "medium"


def test_m2_fomc_chart_events_include_minutes_policy_track_fields():
    rows = [
        {"date": f"2025-{month:02d}-01", "value": 1000.0 + month, "source": "m2.csv"}
        for month in range(1, 13)
    ] + [
        {"date": f"2026-{month:02d}-01", "value": 1100.0 + month, "source": "m2.csv"}
        for month in range(1, 7)
    ]
    events = [
        {
            "event_id": "fomc_2026_06_16",
            "display_month": "2026-06-01",
            "start_date": "2026-06-16",
            "end_date": "2026-06-17",
            "title": "FOMC Meeting",
            "marker_tone": "hawkish",
            "statement_tone": "hawkish",
            "tone_change": "more_hawkish",
            "tone_confidence": "medium",
            "minutes_status": "available",
            "minutes_tone": "hawkish",
            "minutes_confirmation": "confirmed_but_divided",
            "risk_focus": "inflation",
            "risk_bias": "hawkish",
            "divergence_level": "high",
            "uncertainty_level": "high",
            "policy_conviction": "divided",
            "minutes_generated_at": "2026-07-13T04:31:29Z",
        }
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
        rows,
        fomc_events=events,
    )

    event = payload["charts"][0]["events"][0]
    assert event["policy_tone"] == "hawkish"
    assert event["minutes_status"] == "available"
    assert event["minutes_confirmation"] == "confirmed_but_divided"
    assert event["risk_focus"] == "inflation"
    assert event["policy_conviction"] == "divided"
    assert event["minutes_generated_at"] == "2026-07-13T04:31:29Z"


def test_build_growth_cycle_dashboard_payload_adds_ism_overview_cards():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
        ism_manufacturing={
            "period": "2026-06-01",
            "pmi": 51.2,
            "new_orders": 52.0,
            "production": 50.4,
            "employment": 49.8,
            "supplier_deliveries": 50.1,
            "inventories": 48.6,
            "customer_inventories": 47.5,
            "prices": 55.3,
            "order_backlog": 49.0,
            "exports": 51.8,
            "imports": 50.2,
        },
        m2_money_stock={
            "series": [
                {"date": "2025-06-01", "value": 100},
                {"date": "2026-06-01", "value": 112},
            ]
        },
    )

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)
    cards = {card["id"]: card for card in payload["headline"]}

    assert cards["ism_manufacturing"]["pmi"] == 51.2
    assert cards["ism_manufacturing"]["above_50_count"] == 4
    assert cards["ism_manufacturing"]["segments"]["business_cycle"]["pmi"] == 51.2
    assert (
        cards["ism_manufacturing"]["segments"]["growth_drivers"]["above_50_count"] == 4
    )
    assert cards["ism_manufacturing"]["segments"]["inflation_supply"]["prices"] == 55.3
    assert (
        cards["ism_manufacturing"]["segments"]["industry_breadth"]["status"]
        == "pending_inputs"
    )

    sections = {section["id"]: section for section in payload["sections"]}
    assert sections["ism_manufacturing"]["cards"] == ["ism_manufacturing"]


def test_build_growth_cycle_dashboard_payload_marks_ism_cards_missing_without_pmi():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard()

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)
    cards = {card["id"]: card for card in payload["headline"]}

    assert cards["ism_manufacturing"]["pmi"] is None
    assert (
        cards["ism_manufacturing"]["segments"]["industry_breadth"]["status"]
        == "pending_inputs"
    )


def test_build_ism_manufacturing_detail_payload_returns_pmi_and_heat_maps():
    points_by_series_id = {
        "ism_manufacturing_pmi": [
            {"date": "2026-04-01", "value": 49.2, "source": "workbook"},
            {"date": "2026-05-01", "value": 51.4, "source": "workbook"},
        ],
        "ism_manufacturing_new_orders": [
            {"date": "2026-04-01", "value": 50.1},
            {"date": "2026-05-01", "value": 53.2},
        ],
        "ism_manufacturing_production": [
            {"date": "2026-05-01", "value": 52.0},
        ],
        "ism_manufacturing_employment": [
            {"date": "2026-05-01", "value": 48.8},
        ],
        "ism_manufacturing_order_backlog": [
            {"date": "2026-05-01", "value": 47.9},
        ],
        "ism_manufacturing_exports": [
            {"date": "2026-05-01", "value": 51.1},
        ],
        "ism_manufacturing_imports": [
            {"date": "2026-05-01", "value": 49.5},
        ],
        "ism_manufacturing_prices": [
            {"date": "2026-05-01", "value": 56.4},
        ],
        "ism_manufacturing_supplier_deliveries": [
            {"date": "2026-05-01", "value": 50.6},
        ],
        "ism_manufacturing_inventories": [
            {"date": "2026-05-01", "value": 46.8},
        ],
        "ism_manufacturing_customer_inventories": [
            {"date": "2026-05-01", "value": 44.9},
        ],
    }

    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        points_by_series_id
    )

    assert payload["detail_id"] == "ism_manufacturing"
    assert payload["title"] == "ISM Manufacturing"
    assert payload["source"] == "workbook"
    assert [chart["id"] for chart in payload["charts"]] == [
        "ism_manufacturing_heat_map"
    ]

    heat_map = payload["charts"][0]
    assert heat_map["kind"] == "heat_map"
    assert len(heat_map["keys"]) == 11
    assert "pmi" in heat_map["keys"]
    assert "new_orders" in heat_map["keys"]
    assert "prices" in heat_map["keys"]
    assert heat_map["series"][-1]["pmi"] == 51.4
    assert heat_map["series"][-1]["new_orders"] == 53.2
    assert heat_map["series"][-1]["prices"] == 56.4

    assert payload["latest"]["pmi"] == 51.4
    assert payload["latest"]["new_orders"] == 53.2
    assert payload["latest"]["prices"] == 56.4
    assert payload["latest"]["customer_inventories"] == 44.9
    assert len(payload["detail_groups"]) == 4
    assert payload["detail_groups"][0]["label"] == "Business Cycle"
    assert payload["detail_groups"][1]["label"] == "Growth Drivers"
    assert payload["detail_groups"][2]["label"] == "Inflation & Supply"
    assert payload["detail_groups"][3]["label"] == "Industry Breadth"
    assert "required_inputs" in payload["detail_groups"][3]


def test_build_ism_manufacturing_detail_payload_handles_missing_series():
    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload({})

    assert payload["detail_id"] == "ism_manufacturing"
    assert payload["source"] is None
    assert payload["charts"][0]["series"] == []
    assert payload["latest"] is None


def test_build_ism_industry_breadth_summary_from_latest_rankings():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Computer & Electronic Products",
            "direction": "growth",
            "rank": 16,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
        {
            "date": "2026-06-01",
            "industry": "Wood Products",
            "direction": "growth",
            "rank": 14,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
        {
            "date": "2026-06-01",
            "industry": "Furniture & Related Products",
            "direction": "contraction",
            "rank": -1,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
        {
            "date": "2026-06-01",
            "industry": "Machinery",
            "direction": "contraction",
            "rank": -2,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
    ]

    summary = macro_growth_cycle.build_ism_industry_breadth_summary(rankings)

    assert summary == {
        "date": "2026-06-01",
        "growth_count": 2,
        "contraction_count": 2,
        "total_count": 4,
        "top_growth": [
            {"industry": "Computer & Electronic Products", "rank": 16},
            {"industry": "Wood Products", "rank": 14},
        ],
        "top_contraction": [
            {"industry": "Machinery", "rank": -2},
            {"industry": "Furniture & Related Products", "rank": -1},
        ],
    }


def test_build_growth_cycle_payload_uses_ism_industry_breadth_summary():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
        ism_manufacturing={
            "date": "2026-06-01",
            "pmi": 51.2,
            "new_orders": 52.0,
        }
    )
    summary = {
        "date": "2026-06-01",
        "growth_count": 2,
        "contraction_count": 1,
        "total_count": 3,
        "top_growth": [{"industry": "Computer & Electronic Products", "rank": 16}],
        "top_contraction": [{"industry": "Machinery", "rank": -1}],
    }

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(
        dashboard,
        ism_industry_breadth=summary,
    )

    card = next(
        card for card in payload["headline"] if card["id"] == "ism_manufacturing"
    )
    assert card["segments"]["industry_breadth"] == {
        "status": "available",
        "period": "2026-06-01",
        "growth_count": 2,
        "contraction_count": 1,
        "total_count": 3,
        "top_growth": [{"industry": "Computer & Electronic Products", "rank": 16}],
        "top_contraction": [{"industry": "Machinery", "rank": -1}],
    }


def test_build_ism_detail_payload_includes_industry_ranking_group():
    points = {
        "ism_manufacturing_pmi": [
            {"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"}
        ]
    }
    summary = {
        "date": "2026-06-01",
        "growth_count": 2,
        "contraction_count": 1,
        "total_count": 3,
        "top_growth": [{"industry": "Computer & Electronic Products", "rank": 16}],
        "top_contraction": [{"industry": "Machinery", "rank": -1}],
    }

    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        points,
        ism_industry_breadth=summary,
    )

    industry_group = payload["detail_groups"][3]
    assert industry_group == {
        "label": "Industry Breadth",
        "keys": [],
        "industry_breadth": summary,
    }


def test_build_ism_detail_payload_computes_small_multiple_relationship_context():
    ism_points = {
        "ism_manufacturing_pmi": [
            {"date": "2025-10-01", "value": 47.0},
            {"date": "2025-11-01", "value": 47.5},
            {"date": "2025-12-01", "value": 48.0},
            {"date": "2026-01-01", "value": 49.5},
            {"date": "2026-02-01", "value": 52.0},
            {"date": "2026-03-01", "value": 52.5},
            {"date": "2026-04-01", "value": 53.0},
            {"date": "2026-05-01", "value": 53.5},
            {"date": "2026-06-01", "value": 54.0},
        ],
    }
    gdp_level_rows = [
        {"date": "2025-06-30", "gdp_level": 100.0, "index_level": 4900.0},
        {"date": "2025-09-30", "gdp_level": 100.0, "index_level": 5000.0},
        {"date": "2025-12-31", "gdp_level": 100.0, "index_level": 5100.0},
        {"date": "2026-03-31", "gdp_level": 95.0, "index_level": 5200.0},
        {"date": "2026-06-30", "gdp_level": 90.0, "index_level": 5300.0},
    ]
    sp500_price_rows = [
        {"date": "2026-01-31", "close": 5000.0},
        {"date": "2026-02-28", "close": 5100.0},
        {"date": "2026-03-31", "close": 5300.0},
        {"date": "2026-04-30", "close": 5500.0},
        {"date": "2026-05-31", "close": 5700.0},
        {"date": "2026-06-30", "close": 5900.0},
    ]

    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        ism_points,
        gdp_level_rows=gdp_level_rows,
        sp500_price_rows=sp500_price_rows,
    )

    assert [chart["id"] for chart in payload["charts"]] == [
        "ism_manufacturing_heat_map",
        "ism_macro_context",
    ]
    chart = payload["charts"][1]
    assert chart["kind"] == "small_multiples"
    assert chart["title"] == "Macro Confirmation"
    assert [panel["id"] for panel in chart["panels"]] == [
        "ism_pmi",
        "gdp_growth",
        "sp500_index",
    ]
    assert chart["panels"][0]["reference_lines"] == [
        {"value": 50, "label": "Expansion / Contraction threshold"}
    ]
    assert chart["panels"][0]["subtitle"] == "Monthly"
    assert chart["panels"][1]["title"] == "Real GDP QoQ Annualized"
    assert chart["panels"][1]["subtitle"] == "Quarterly, shown as step series"
    assert chart["panels"][1]["line_shape"] == "step_after"
    assert chart["panels"][2]["title"] == "S&P 500"
    assert chart["panels"][2]["subtitle"] == "Base = 100"
    assert chart["series"][-1] == {
        "date": "2026-06-30",
        "ism_pmi": 54.0,
        "gdp_growth": -19.4481,
        "gdp_period": None,
        "sp500_index": 118.0,
        "sp500_close": 5900.0,
    }
    assert chart["contexts"] == [
        {
            "id": "gdp_context",
            "state": "early_recovery",
            "label": "Early Recovery",
            "ism_direction": "up",
            "comparison_direction": "down",
            "description": "ISM is improving while GDP growth is still weakening.",
        },
        {
            "id": "market_context",
            "state": "growth_priced",
            "label": "Growth Priced",
            "ism_direction": "up",
            "comparison_direction": "up",
            "description": "ISM is improving and S&P 500 is rising with the growth signal.",
        },
    ]
    assert payload["relationship_summary"] == {
        "shared_months": 6,
        "gdp_observations": 6,
        "sp500_observations": 6,
    }


def test_build_ism_detail_payload_does_not_forward_fill_stale_pmi():
    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        {
            "ism_manufacturing_pmi": [
                {"date": "2020-12-01", "value": 60.5},
            ],
        },
        gdp_level_rows=[],
        sp500_price_rows=[
            {"date": "2021-01-29", "close": 100.0},
            {"date": "2021-02-26", "close": 101.0},
            {"date": "2021-03-31", "close": 102.0},
        ],
    )

    chart = payload["charts"][1]

    assert chart["series"] == [
        {
            "date": "2021-01-29",
            "ism_pmi": 60.5,
            "gdp_growth": None,
            "gdp_period": None,
            "sp500_index": 100.0,
            "sp500_close": 100.0,
        },
        {
            "date": "2021-02-26",
            "ism_pmi": None,
            "gdp_growth": None,
            "gdp_period": None,
            "sp500_index": 101.0,
            "sp500_close": 101.0,
        },
        {
            "date": "2021-03-31",
            "ism_pmi": None,
            "gdp_growth": None,
            "gdp_period": None,
            "sp500_index": 102.0,
            "sp500_close": 102.0,
        },
    ]


def test_gdp_qoq_growth_skips_source_boundary_discontinuity():
    rows = [
        {
            "date": "2016-12-31",
            "gdp_level": 17876.179,
            "source_workbook": "GDP_Correlations.xlsx",
            "source_sheet": "S&P500_US_Quadnomial",
        },
        {
            "date": "2017-03-31",
            "gdp_level": 19398.343,
            "source_workbook": "GDPC1.csv+SP500.csv",
            "source_sheet": "computed",
        },
        {
            "date": "2017-06-30",
            "gdp_level": 19506.949,
            "source_workbook": "GDPC1.csv+SP500.csv",
            "source_sheet": "computed",
        },
    ]

    assert macro_growth_cycle._gdp_qoq_annualized_rows(rows) == [
        {"date": "2017-06-30", "value": 2.2584, "period_label": None}
    ]


def test_build_ism_detail_payload_skips_small_multiple_without_existing_sources():
    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        {},
        gdp_level_rows=[],
        sp500_price_rows=[],
    )

    assert [chart["id"] for chart in payload["charts"]] == [
        "ism_manufacturing_heat_map"
    ]
    assert payload["relationship_summary"] == {
        "shared_months": 0,
        "gdp_observations": 0,
        "sp500_observations": 0,
    }


def test_ism_at_a_glance_tone_growing_faster_is_green():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "Growing",
                "rate_of_change": "Faster",
            }
        )
        == "green"
    )


def test_ism_at_a_glance_tone_growing_slower_is_amber():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "Growing",
                "rate_of_change": "Slower",
            }
        )
        == "amber"
    )


def test_ism_at_a_glance_tone_contracting_is_red():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "Contracting",
                "rate_of_change": "Slower",
            }
        )
        == "red"
    )


def test_ism_at_a_glance_tone_prices_series_is_amber():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_prices",
                "direction": "Increasing",
                "rate_of_change": "",
            }
        )
        == "amber"
    )


def test_ism_at_a_glance_tone_supplier_deliveries_is_amber():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_supplier_deliveries",
                "direction": "Growing",
                "rate_of_change": "Faster",
            }
        )
        == "amber"
    )


def test_ism_at_a_glance_tone_customer_inventories_too_low_or_high_is_amber():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_customer_inventories",
                "direction": "Too Low",
                "rate_of_change": "",
            }
        )
        == "amber"
    )
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_customer_inventories",
                "direction": "Too High",
                "rate_of_change": "",
            }
        )
        == "amber"
    )


def test_ism_at_a_glance_tone_missing_or_unknown_direction_is_muted():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "",
                "rate_of_change": "",
            }
        )
        == "muted"
    )
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "N/A",
                "rate_of_change": "",
            }
        )
        == "muted"
    )


def test_ism_at_a_glance_tone_transition_direction_is_amber():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "From Contracting",
                "rate_of_change": "",
            }
        )
        == "amber"
    )
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "From Growing",
                "rate_of_change": "",
            }
        )
        == "amber"
    )


def test_ism_at_a_glance_tone_mixed_direction_is_amber():
    assert (
        macro_growth_cycle.ism_at_a_glance_tone(
            {
                "series_id": "ism_manufacturing_pmi",
                "direction": "Mixed",
                "rate_of_change": "",
            }
        )
        == "amber"
    )


def test_ism_at_a_glance_by_key_converts_rows_to_metadata_dict():
    rows = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 53.3,
            "previous_value": 54.0,
            "point_change": -0.7,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 6,
            "source_url": "https://example.com",
            "source_hash": "abc123",
        },
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_new_orders",
            "label": "New Orders",
            "current_value": 52.0,
            "previous_value": 51.5,
            "point_change": 0.5,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 4,
            "source_url": "https://example.com",
            "source_hash": "abc123",
        },
    ]

    result = macro_growth_cycle._ism_at_a_glance_by_key(rows)

    assert "pmi" in result
    assert "new_orders" in result
    assert result["pmi"]["label"] == "Manufacturing PMI"
    assert result["pmi"]["point_change"] == -0.7
    assert result["pmi"]["direction"] == "Growing"
    assert result["pmi"]["rate_of_change"] == "Slower"
    assert result["pmi"]["tone"] == "amber"
    assert result["new_orders"]["tone"] == "green"
    assert result["new_orders"]["current_value"] == 52.0


def test_build_ism_manufacturing_detail_payload_with_at_a_glance_metadata():
    points = {
        "ism_manufacturing_pmi": [
            {"date": "2026-06-01", "value": 51.2, "source": "workbook"},
        ],
        "ism_manufacturing_new_orders": [
            {"date": "2026-06-01", "value": 52.0, "source": "workbook"},
        ],
    }
    at_a_glance = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 53.3,
            "previous_value": 54.0,
            "point_change": -0.7,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 6,
            "source_url": "https://example.com",
            "source_hash": "abc123",
        },
    ]

    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        points,
        ism_at_a_glance=at_a_glance,
    )

    assert "latest_metadata" in payload
    assert payload["latest_metadata"]["pmi"]["point_change"] == -0.7
    assert payload["latest_metadata"]["pmi"]["tone"] == "amber"


def test_build_ism_manufacturing_detail_payload_includes_official_report_summary():
    points = {
        "ism_manufacturing_pmi": [
            {"date": "2026-06-01", "value": 53.3, "source": "ISM"}
        ]
    }
    at_a_glance = [
        {
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 53.3,
            "previous_value": 54.0,
            "point_change": -0.7,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 6,
        },
        {
            "series_id": "ism_manufacturing_prices",
            "label": "Prices",
            "current_value": 73.0,
            "previous_value": 82.1,
            "point_change": -9.1,
            "direction": "Increasing",
            "rate_of_change": "Slower",
            "trend_months": 21,
        },
    ]
    official_summary = macro_growth_cycle.build_ism_official_report_summary(
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Manufacturing PMI Report",
            "source_url": "https://example.com/june.html",
        },
        at_a_glance,
        [
            {
                "industry": "Machinery",
                "comment_text": "Demand remains uneven.",
            }
        ],
    )

    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(
        points,
        ism_at_a_glance=at_a_glance,
        ism_official_summary=official_summary,
    )

    assert payload["official_report_summary"] == {
        "source_type": "report_extracted",
        "report_id": "ism_manufacturing_2026_06",
        "period": "2026-06-01",
        "title": "June 2026 ISM Manufacturing PMI Report",
        "source_url": "https://example.com/june.html",
        "headline": "Manufacturing PMI 53.3, -0.7 points from prior month; Growing / Slower.",
        "comment_preview_count": 3,
        "major_changes": [
            "Prices: 73.0, -9.1 points; Increasing / Slower.",
            "Manufacturing PMI: 53.3, -0.7 points; Growing / Slower.",
        ],
        "respondent_comments": [
            {
                "industry": "Machinery",
                "comment_text": "Demand remains uneven.",
            }
        ],
    }


def test_build_ism_official_report_summary_keeps_all_comments_with_preview_count():
    at_a_glance = [
        {
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 53.3,
            "previous_value": 54.0,
            "point_change": -0.7,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 6,
        },
    ]
    comments = [
        {
            "industry": f"Industry {index}",
            "comment_text": f"Official comment {index}.",
        }
        for index in range(1, 6)
    ]

    summary = macro_growth_cycle.build_ism_official_report_summary(
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Manufacturing PMI Report",
            "source_url": "https://example.com/june.html",
        },
        at_a_glance,
        comments,
    )

    assert summary["comment_preview_count"] == 3
    assert len(summary["respondent_comments"]) == 5
    assert summary["respondent_comments"][-1] == {
        "industry": "Industry 5",
        "comment_text": "Official comment 5.",
    }


def test_build_ism_manufacturing_detail_payload_skips_metadata_when_not_provided():
    points = {
        "ism_manufacturing_pmi": [
            {"date": "2026-06-01", "value": 51.2, "source": "workbook"},
        ],
    }

    payload = macro_growth_cycle.build_ism_manufacturing_detail_payload(points)

    assert "latest_metadata" not in payload


def test_build_growth_cycle_dashboard_payload_headline_includes_trend_metadata():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
        ism_manufacturing={
            "period": "2026-06-01",
            "pmi": 53.3,
            "new_orders": 52.0,
            "production": 50.4,
            "employment": 49.8,
            "supplier_deliveries": 50.1,
            "inventories": 48.6,
            "customer_inventories": 47.5,
            "prices": 55.3,
            "order_backlog": 49.0,
            "exports": 51.8,
            "imports": 50.2,
        },
    )
    at_a_glance = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 53.3,
            "previous_value": 54.0,
            "point_change": -0.7,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 6,
            "source_url": "https://example.com",
            "source_hash": "abc123",
        },
    ]

    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(
        dashboard,
        ism_at_a_glance=at_a_glance,
    )

    card = next(
        card for card in payload["headline"] if card["id"] == "ism_manufacturing"
    )
    assert card["segments"]["business_cycle"]["trend"]["tone"] == "amber"
    assert card["segments"]["business_cycle"]["trend"]["point_change"] == -0.7


def test_build_growth_cycle_dashboard_payload_skips_trend_when_not_provided():
    growth_cycle = {
        "m2_period": "2026-06-01",
        "m2_money_stock": 21210.0,
        "m2_yoy_pct_change": 0.042,
        "m2_yoy_percent_rank": 0.72,
        "m2_3m_momentum": 0.011,
        "m2_mom_pct_change": 0.004,
        "m2_mom_percent_rank": 0.63,
    }
    result = macro_growth_cycle.build_growth_cycle_dashboard_payload(
        {"macro": {"growth_cycle": growth_cycle}}
    )
    card = next(
        card for card in result["headline"] if card["id"] == "ism_manufacturing"
    )
    assert "trend" not in card["segments"]["business_cycle"]


def _bias_growth_cycle(**overrides):
    base = {}
    base.update(overrides)
    return base


def _bias_ism_signal(
    growth_impulse="supports_growth", cycle_state="expansion_rising", status="available"
):
    return {
        "status": status,
        "growth_impulse": growth_impulse,
        "cycle_state": cycle_state,
        "version": "ism_macro_signal_v1",
    }


def test_build_growth_cycle_bias_evidence_long_scenario():
    growth_cycle = {
        "services_pmi": 53.0,
        "services_business_activity": 54.0,
        "services_new_orders": 52.0,
        "labor_trend": "stable",
    }
    signal = _bias_ism_signal("supports_growth")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["version"] == "growth_cycle_bias_v2"
    assert result["status"] == "available"
    assert result["bias"] == "long"
    assert result["ism_contribution"] == "supports_long"
    assert result["components"]["ism_manufacturing"] == "supports_growth"
    assert result["components"]["ism_services"] == "available"
    assert result["components"]["labor"] == "stable"
    assert result["missing_inputs"] == []


def test_build_growth_cycle_bias_evidence_short_scenario():
    growth_cycle = {
        "services_pmi": 48.0,
        "services_business_activity": 47.0,
        "services_new_orders": 47.5,
        "labor_trend": "weakening",
    }
    signal = _bias_ism_signal("supports_contraction")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "available"
    assert result["bias"] == "short"
    assert result["ism_contribution"] == "supports_short"
    assert result["missing_inputs"] == []


def test_build_growth_cycle_bias_evidence_peaking_is_neutral():
    growth_cycle = {
        "services_pmi": 53.0,
        "services_business_activity": 54.0,
        "services_new_orders": 52.0,
        "labor_trend": "stable",
    }
    signal = _bias_ism_signal("supports_growth", cycle_state="peaking")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "available"
    assert result["bias"] == "neutral"
    assert "peaking" in result["reasons"][0]


def test_build_growth_cycle_bias_evidence_troughing_is_neutral_not_short():
    growth_cycle = {
        "services_pmi": 48.0,
        "services_business_activity": 47.0,
        "services_new_orders": 47.5,
        "labor_trend": "weakening",
    }
    signal = _bias_ism_signal("supports_contraction", cycle_state="troughing")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "available"
    assert result["bias"] == "neutral"
    assert "troughing" in result["reasons"][0]


def test_build_growth_cycle_bias_evidence_contraction_deepening_is_short():
    growth_cycle = {
        "services_pmi": 48.0,
        "services_business_activity": 47.0,
        "services_new_orders": 47.5,
        "labor_trend": "weakening",
    }
    signal = _bias_ism_signal(
        "supports_contraction", cycle_state="contraction_deepening"
    )
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "available"
    assert result["bias"] == "short"


def test_build_growth_cycle_bias_evidence_pending_inputs_when_services_missing():
    growth_cycle = {
        "labor_trend": "stable",
    }
    signal = _bias_ism_signal("supports_growth")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "pending_inputs"
    assert result["bias"] is None
    assert "ISM Services" in result["missing_inputs"]


def test_build_growth_cycle_bias_evidence_pending_inputs_when_labor_missing():
    growth_cycle = {
        "services_pmi": 53.0,
        "services_business_activity": 54.0,
        "services_new_orders": 52.0,
    }
    signal = _bias_ism_signal("supports_growth")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "pending_inputs"
    assert result["bias"] is None
    assert "Labor trend" in result["missing_inputs"]


def test_build_growth_cycle_bias_evidence_unavailable_signal_is_pending():
    result = macro_growth_cycle.build_growth_cycle_bias_evidence({}, None)
    assert result["version"] == "growth_cycle_bias_v2"
    assert result["status"] == "pending_inputs"
    assert result["bias"] is None
    assert result["ism_contribution"] == "unavailable"
    assert result["components"]["ism_manufacturing"] == "unavailable"
    assert "ISM Manufacturing" in result["missing_inputs"]


def test_build_growth_cycle_bias_evidence_status_unavailable_is_pending():
    signal = _bias_ism_signal(status="unavailable")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence({}, signal)
    assert result["status"] == "pending_inputs"
    assert result["bias"] is None
    assert result["ism_contribution"] == "unavailable"


def test_build_growth_cycle_bias_evidence_expansion_slowing_missing_services():
    growth_cycle = {}
    signal = _bias_ism_signal("growth_caution", cycle_state="expansion_slowing")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["status"] == "pending_inputs"
    assert result["bias"] is None
    assert "ISM Services" in result["missing_inputs"]


def test_build_growth_cycle_dashboard_payload_includes_bias_evidence():
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard()
    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)
    assert "growth_cycle_bias_evidence" in payload["growth_cycle"]
    assert (
        payload["growth_cycle"]["growth_cycle_bias_evidence"]["version"]
        == "growth_cycle_bias_v2"
    )


def test_build_growth_cycle_bias_evidence_turning_supportive_maps_to_supports_long():
    growth_cycle = {
        "services_pmi": 53.0,
        "services_business_activity": 54.0,
        "services_new_orders": 52.0,
        "labor_trend": "strengthening",
    }
    signal = _bias_ism_signal("turning_supportive")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["ism_contribution"] == "supports_long"
    assert result["bias"] == "long"


def test_build_growth_cycle_bias_evidence_contraction_easing_maps_to_conflicting():
    growth_cycle = {
        "services_pmi": 53.0,
        "services_business_activity": 54.0,
        "services_new_orders": 52.0,
        "labor_trend": "stable",
    }
    signal = _bias_ism_signal("contraction_easing")
    result = macro_growth_cycle.build_growth_cycle_bias_evidence(growth_cycle, signal)
    assert result["ism_contribution"] == "conflicting"


def test_build_growth_cycle_bias_evidence_sets_scalar_to_none_when_pending():
    dashboard = {"macro": {"growth_cycle": {"growth_cycle_bias": "long"}}}
    payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(dashboard)
    assert payload["growth_cycle"]["growth_cycle_bias"] is None
    assert (
        payload["growth_cycle"]["growth_cycle_bias_evidence"]["status"]
        == "pending_inputs"
    )
