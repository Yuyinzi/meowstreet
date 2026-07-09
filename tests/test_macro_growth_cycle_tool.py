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
    assert growth_cycle["services_pmi"] == 53.0
    assert growth_cycle["m2_money_stock"] == 21210
    assert growth_cycle["initial_jobless_claims"] == 245000


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
    assert result["headline"][0]["id"] == "m2_money_supply"
    assert result["headline"][0]["state"]["m2_money_stock"] == 21210.0
    assert result["missing"] is None


@pytest.mark.parametrize(
    "growth_cycle,expected",
    [
        (
            {
                "m2_yoy_pct_change": 0.05,
                "m2_3m_momentum": 0.02,
                "m2_mom_percent_rank": 0.50,
            },
            "expanding",
        ),
        (
            {
                "m2_yoy_pct_change": -0.02,
                "m2_3m_momentum": -0.01,
                "m2_mom_percent_rank": 0.50,
            },
            "contracting",
        ),
        (
            {
                "m2_yoy_pct_change": 0.05,
                "m2_3m_momentum": -0.01,
                "m2_mom_percent_rank": 0.50,
            },
            "contracting",
        ),
        (
            {
                "m2_yoy_pct_change": 0.05,
                "m2_3m_momentum": 0.02,
                "m2_mom_percent_rank": 0.96,
            },
            "shock",
        ),
        (
            {
                "m2_yoy_pct_change": 0.05,
                "m2_3m_momentum": 0.02,
                "m2_mom_percent_rank": 0.04,
            },
            "shock",
        ),
        (
            {
                "m2_yoy_pct_change": 0.05,
                "m2_3m_momentum": 0.00,
                "m2_mom_percent_rank": 0.50,
            },
            "mixed",
        ),
        (
            {
                "m2_yoy_pct_change": None,
                "m2_3m_momentum": 0.02,
                "m2_mom_percent_rank": 0.50,
            },
            "missing",
        ),
        ({}, "missing"),
    ],
)
def test_m2_status_classification(growth_cycle, expected):
    assert macro_growth_cycle._m2_status(growth_cycle) == expected


def test_m2_interpretation_snapshot_is_stable_and_hashable():
    headline = {
        "id": "m2_money_supply",
        "period": "2021-01-01",
        "status": "shock",
        "status_label": "Shock",
        "state": {
            "m2_yoy_pct_change": 0.258,
            "m2_yoy_percent_rank": 1.0,
            "m2_money_stock": 19394.6,
        },
        "change": {
            "m2_3m_momentum": 0.034,
        },
        "shock": {
            "m2_mom_pct_change": 0.016,
            "m2_mom_percent_rank": 0.9866,
        },
    }
    detail_payload = {
        "source": "US_M2_Money_Supply_Template.xlsx",
        "charts": [
            {
                "title": "M2 YoY Growth",
                "series": [{"date": "2021-01-01", "value": 25.8}],
            },
            {"title": "M2 3M Change", "series": [{"date": "2021-01-01", "value": 3.4}]},
            {
                "title": "M2 MoM Shock Events",
                "series": [
                    {
                        "date": "2021-01-01",
                        "value": 1,
                        "mom_growth": 1.6,
                        "percentile": 98.66,
                        "signal": "strong_injection",
                    }
                ],
            },
        ],
    }

    snapshot = macro_growth_cycle.m2_interpretation_snapshot(headline, detail_payload)
    same_snapshot = macro_growth_cycle.m2_interpretation_snapshot(
        headline, detail_payload
    )

    assert snapshot == same_snapshot
    assert snapshot["scope"] == "m2_money_supply"
    assert snapshot["prompt_version"] == "m2-cat-v1"
    assert snapshot["as_of"] == "2021-01-01"
    assert snapshot["status"] == "shock"
    assert snapshot["metrics"]["state"]["yoy_growth"] == 0.258
    assert snapshot["metrics"]["state"]["yoy_percent_rank"] == 1.0
    assert snapshot["metrics"]["state"]["level_billions_usd"] == 19394.6
    assert snapshot["metrics"]["change"]["three_month_change"] == 0.034
    assert snapshot["metrics"]["shock"]["mom_growth"] == 0.016
    assert snapshot["metrics"]["shock"]["mom_percent_rank"] == 0.9866
    assert (
        snapshot["metric_context"]["state"]["label"] == "historically_extreme_expansion"
    )
    assert snapshot["metric_context"]["state"]["meaning"] == (
        "M2 growth is near the top of its own history, so liquidity is unusually abundant."
    )
    assert snapshot["metric_context"]["change"]["label"] == "positive_momentum"
    assert snapshot["metric_context"]["shock"]["label"] == "unusual_monthly_injection"
    assert snapshot["interpretation_constraints"] == {
        "cause_policy": "do_not_name_causes_without_sourced_event_context",
        "signal_role": "liquidity_confirmation_not_standalone_timing",
        "number_style": "interpret_numbers_before_repeating_them",
    }
    assert snapshot["latest_shock_event"]["signal"] == "strong_injection"
    assert snapshot["coverage"]["source"] == "US_M2_Money_Supply_Template.xlsx"
    assert len(snapshot["hash"]) == 64


def test_m2_metric_context_does_not_hardcode_event_causes():
    headline = {
        "period": "2021-01-01",
        "status": "shock",
        "state": {
            "m2_yoy_pct_change": 0.258,
            "m2_yoy_percent_rank": 1.0,
            "m2_money_stock": 19394.6,
        },
        "change": {
            "m2_3m_momentum": 0.034,
        },
        "shock": {
            "m2_mom_pct_change": 0.016,
            "m2_mom_percent_rank": 0.9866,
        },
    }

    snapshot = macro_growth_cycle.m2_interpretation_snapshot(
        headline,
        {"source": "m2.xlsx", "charts": []},
    )
    encoded = json.dumps(snapshot, sort_keys=True).lower()

    assert "covid" not in encoded
    assert "fiscal" not in encoded
    assert "stimulus" not in encoded
    assert "federal reserve" not in encoded
    assert "policy response" not in encoded


def test_m2_fallback_interpretation_returns_bilingual_text_by_status():
    headline = {"status": "shock"}
    result = macro_growth_cycle.m2_fallback_interpretation(headline)
    assert "text_en" in result
    assert "text_zh" in result
    assert "shock" in result["text_en"].lower()

    headline = {"status": "expanding"}
    result = macro_growth_cycle.m2_fallback_interpretation(headline)
    assert "expanding" in result["text_en"].lower()

    headline = {"status": "contracting"}
    result = macro_growth_cycle.m2_fallback_interpretation(headline)
    assert "contracting" in result["text_en"].lower()

    headline = {"status": "mixed"}
    result = macro_growth_cycle.m2_fallback_interpretation(headline)
    assert "mixed" in result["text_en"].lower()

    headline = {"status": "missing"}
    result = macro_growth_cycle.m2_fallback_interpretation(headline)
    assert "generate" in result["text_en"]

    headline = {}
    result = macro_growth_cycle.m2_fallback_interpretation(headline)
    assert "generate" in result["text_en"]


def test_m2_detail_state_chart_includes_core_pce_yoy_and_fed_target():
    m2_rows = [
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
        "fed_target": "Fed 2% Target (since 2012)",
    }
    assert chart["series"] == [
        {
            "date": "2026-01-01",
            "m2_yoy": 25.0,
            "core_pce_yoy": 4.6154,
            "fed_target": 2.0,
        }
    ]


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
        "m2_money_supply",
        "gdp_expectations",
    ]
    assert payload["headline"][1]["status"] == "pending_inputs"


def test_build_gdp_expectations_headline_returns_pending_inputs_card():
    card = macro_growth_cycle.build_gdp_expectations_headline({})

    assert card == {
        "id": "gdp_expectations",
        "label": "GDP Expectations",
        "period": None,
        "status": "pending_inputs",
        "status_label": "Pending Inputs",
        "expected_direction": None,
        "required_inputs": [
            "ISM Manufacturing",
            "ISM Services",
            "Labor trend",
            "Consumer indicators",
        ],
        "supporting_context": "GDP / Market Relationship validates why GDP direction matters, but it does not replace a forward GDP expectation signal.",
        "description": "Growth outlook context is needed to judge whether liquidity support is preemptive or defensive. Wait for leading indicators before producing a GDP direction signal.",
    }


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
        fed_treasury_rows=treasury_rows,
        fed_mbs_rows=mbs_rows,
    )

    state_chart = payload["charts"][0]
    assert state_chart["title"] == "M2 YoY Growth vs Inflation Constraint"
    assert state_chart["keys"] == [
        "m2_yoy",
        "core_pce_yoy",
        "fed_target",
    ]
    assert state_chart["labels"] == {
        "m2_yoy": "M2 YoY Growth",
        "core_pce_yoy": "Core PCE YoY",
        "fed_target": "Fed 2% Target (since 2012)",
    }

    fed_chart = payload["charts"][1]
    assert fed_chart["title"] == "Fed Total Assets YoY"
    assert fed_chart["keys"] == ["fed_total_assets_yoy"]
    assert fed_chart["labels"] == {
        "fed_total_assets_yoy": "Fed Total Assets YoY",
    }

    composition_chart = payload["charts"][3]
    assert composition_chart["title"] == "Fed Balance Sheet 13W Composition"
    assert composition_chart["keys"] == ["treasury_13w_change", "mbs_13w_change"]


def test_m2_detail_resamples_weekly_fed_yoy_to_monthly_state_dates():
    m2_rows = [
        {"date": f"2025-{month:02d}-01", "value": 100.0 + month, "source": "FRED"}
        for month in range(1, 13)
    ] + [
        {"date": "2026-01-01", "value": 125.0, "source": "FRED"},
        {"date": "2026-02-01", "value": 128.0, "source": "FRED"},
    ]
    fed_rows = [
        {"date": "2025-01-08", "value": 1000.0, "source": "FRED weekly"},
        {"date": "2025-02-05", "value": 1100.0, "source": "FRED weekly"},
        {"date": "2025-03-05", "value": 1200.0, "source": "FRED weekly"},
        {"date": "2025-04-09", "value": 1300.0, "source": "FRED weekly"},
        {"date": "2025-05-07", "value": 1400.0, "source": "FRED weekly"},
        {"date": "2025-06-04", "value": 1500.0, "source": "FRED weekly"},
        {"date": "2025-07-09", "value": 1600.0, "source": "FRED weekly"},
        {"date": "2025-08-06", "value": 1700.0, "source": "FRED weekly"},
        {"date": "2025-09-10", "value": 1800.0, "source": "FRED weekly"},
        {"date": "2025-10-08", "value": 1900.0, "source": "FRED weekly"},
        {"date": "2025-11-05", "value": 2000.0, "source": "FRED weekly"},
        {"date": "2025-12-10", "value": 2100.0, "source": "FRED weekly"},
        {"date": "2026-01-07", "value": 2200.0, "source": "FRED weekly"},
        {"date": "2026-02-04", "value": 2420.0, "source": "FRED weekly"},
    ]

    payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
        m2_rows,
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
        {
            "date": "2026-02-01",
            "m2_yoy": 25.4902,
            "core_pce_yoy": None,
            "fed_target": 2.0,
        },
    ]
    fed_series = payload["charts"][1]["series"]
    assert fed_series == [
        {
            "date": "2026-01-01",
            "fed_total_assets_yoy": 120.0,
        },
        {
            "date": "2026-02-01",
            "fed_total_assets_yoy": 120.0,
        },
    ]
