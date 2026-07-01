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


def normalize_ism_services(payload):
    return {
        "macro": {
            "growth_cycle": {
                "services_period": payload.get("period"),
                "services_pmi": _float_value(payload, "pmi"),
                "services_business_activity": _float_value(payload, "business_activity"),
                "services_new_orders": _float_value(payload, "new_orders"),
                "services_employment": _float_value(payload, "employment"),
                "services_supplier_deliveries": _float_value(payload, "supplier_deliveries"),
                "services_backlog_orders": _float_value(payload, "backlog_orders"),
            }
        }
    }


def _pct_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1


def _percent_rank(values, latest):
    clean_values = [value for value in values if value is not None]
    if latest is None or not clean_values:
        return None
    below_or_equal = len([value for value in clean_values if value <= latest])
    return below_or_equal / len(clean_values)


def normalize_m2_money_stock(payload):
    rows = payload.get("series", [])
    values = [float(row["value"]) for row in rows]
    latest_value = values[-1] if values else None
    previous_value = values[-2] if len(values) >= 2 else None
    year_ago_value = values[-13] if len(values) >= 13 else values[0] if values else None
    mom_changes = [
        _pct_change(values[index], values[index - 1])
        for index in range(1, len(values))
    ]
    yoy_changes = [
        _pct_change(values[index], values[index - 12])
        for index in range(12, len(values))
    ]
    latest_mom = _pct_change(latest_value, previous_value)
    latest_yoy = _pct_change(latest_value, year_ago_value)
    latest_period = rows[-1]["date"] if rows else None
    return {
        "macro": {
            "growth_cycle": {
                "m2_period": latest_period,
                "m2_money_stock": latest_value,
                "m2_mom_pct_change": latest_mom,
                "m2_yoy_pct_change": latest_yoy,
                "m2_mom_percent_rank": _percent_rank(mom_changes, latest_mom),
                "m2_yoy_percent_rank": _percent_rank(yoy_changes, latest_yoy),
            }
        }
    }
