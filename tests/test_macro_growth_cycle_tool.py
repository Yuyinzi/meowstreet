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
