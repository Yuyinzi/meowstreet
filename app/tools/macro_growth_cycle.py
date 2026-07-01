GROWTH_CYCLE_SOURCES = [
    {
        "id": "ism_manufacturing",
        "title": "ISM Manufacturing",
        "frequency": "monthly",
        "fields": [
            {"id": "ism_pmi", "field": "macro.growth_cycle.ism_pmi"},
            {"id": "ism_new_orders", "field": "macro.growth_cycle.ism_new_orders"},
            {"id": "ism_production", "field": "macro.growth_cycle.ism_production"},
            {"id": "ism_employment", "field": "macro.growth_cycle.ism_employment"},
            {"id": "ism_supplier_deliveries", "field": "macro.growth_cycle.ism_supplier_deliveries"},
            {"id": "ism_inventories", "field": "macro.growth_cycle.ism_inventories"},
        ],
    },
    {
        "id": "ism_services",
        "title": "ISM Services",
        "frequency": "monthly",
        "fields": [
            {"id": "services_pmi", "field": "macro.growth_cycle.services_pmi"},
            {"id": "services_business_activity", "field": "macro.growth_cycle.services_business_activity"},
            {"id": "services_new_orders", "field": "macro.growth_cycle.services_new_orders"},
            {"id": "services_employment", "field": "macro.growth_cycle.services_employment"},
            {"id": "services_supplier_deliveries", "field": "macro.growth_cycle.services_supplier_deliveries"},
            {"id": "services_backlog_orders", "field": "macro.growth_cycle.services_backlog_orders"},
        ],
    },
    {
        "id": "m2_money_stock",
        "title": "M2 Money Stock",
        "frequency": "monthly",
        "fields": [
            {"id": "m2_money_stock", "field": "macro.growth_cycle.m2_money_stock"},
            {"id": "m2_mom_pct_change", "field": "macro.growth_cycle.m2_mom_pct_change"},
            {"id": "m2_yoy_pct_change", "field": "macro.growth_cycle.m2_yoy_pct_change"},
            {"id": "m2_mom_percent_rank", "field": "macro.growth_cycle.m2_mom_percent_rank"},
            {"id": "m2_yoy_percent_rank", "field": "macro.growth_cycle.m2_yoy_percent_rank"},
        ],
    },
    {
        "id": "jobless_claims",
        "title": "Jobless Claims",
        "frequency": "weekly",
        "fields": [
            {"id": "initial_jobless_claims", "field": "macro.growth_cycle.initial_jobless_claims"},
            {"id": "continuing_jobless_claims", "field": "macro.growth_cycle.continuing_jobless_claims"},
            {"id": "labor_trend", "field": "macro.growth_cycle.labor_trend"},
        ],
    },
]


def _float_value(payload, key):
    value = payload.get(key)
    if value in (None, ""):
        return None
    return float(value)


def normalize_ism_manufacturing(payload):
    return {
        "macro": {
            "growth_cycle": {
                "ism_period": payload.get("period"),
                "ism_pmi": _float_value(payload, "pmi"),
                "ism_new_orders": _float_value(payload, "new_orders"),
                "ism_production": _float_value(payload, "production"),
                "ism_employment": _float_value(payload, "employment"),
                "ism_supplier_deliveries": _float_value(payload, "supplier_deliveries"),
                "ism_inventories": _float_value(payload, "inventories"),
            }
        }
    }
