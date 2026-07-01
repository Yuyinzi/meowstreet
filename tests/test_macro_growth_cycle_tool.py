import pytest

from app.tools import macro_growth_cycle


def test_growth_cycle_source_fields_are_grouped_by_source():
    source_ids = [source["id"] for source in macro_growth_cycle.GROWTH_CYCLE_SOURCES]

    assert source_ids == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_stock",
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
        "ism_pmi": 51.0, "ism_new_orders": 52.0,
        "services_pmi": 49.0, "services_business_activity": 48.0,
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
