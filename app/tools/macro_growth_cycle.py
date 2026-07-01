from copy import deepcopy

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


def _latest_numeric(rows):
    if not rows:
        return None
    return int(rows[-1]["value"])


def _latest_date(rows):
    if not rows:
        return None
    return rows[-1]["date"]


def _average(values):
    if not values:
        return None
    return sum(values) / len(values)


def _labor_trend(initial_claims):
    if len(initial_claims) < 4:
        return "unknown"
    values = [int(row["value"]) for row in initial_claims]
    latest_average = _average(values[-4:])
    previous_average = _average(values[:4])
    if latest_average > previous_average * 1.03:
        return "weakening"
    if latest_average < previous_average * 0.97:
        return "strengthening"
    return "stable"


def normalize_jobless_claims(payload):
    initial_claims = payload.get("initial_claims", [])
    continuing_claims = payload.get("continuing_claims", [])
    initial_values = [int(row["value"]) for row in initial_claims[-4:]]
    return {
        "macro": {
            "growth_cycle": {
                "jobless_claims_period": _latest_date(initial_claims),
                "initial_jobless_claims": _latest_numeric(initial_claims),
                "continuing_jobless_claims": _latest_numeric(continuing_claims),
                "initial_claims_4w_avg": _average(initial_values),
                "labor_trend": _labor_trend(initial_claims),
            }
        }
    }


def _above_50(value):
    return value is not None and value > 50


def _below_50(value):
    return value is not None and value < 50


def compute_growth_cycle_bias(growth_cycle):
    manufacturing_expanding = _above_50(growth_cycle.get("ism_pmi")) and _above_50(
        growth_cycle.get("ism_new_orders")
    )
    services_expanding = _above_50(growth_cycle.get("services_pmi")) and (
        _above_50(growth_cycle.get("services_business_activity"))
        or _above_50(growth_cycle.get("services_new_orders"))
    )
    manufacturing_contracting = _below_50(growth_cycle.get("ism_pmi")) and _below_50(
        growth_cycle.get("ism_new_orders")
    )
    services_contracting = _below_50(growth_cycle.get("services_pmi")) and (
        _below_50(growth_cycle.get("services_business_activity"))
        or _below_50(growth_cycle.get("services_new_orders"))
    )
    if manufacturing_expanding and services_expanding:
        return "long"
    if manufacturing_contracting and services_contracting and growth_cycle.get("labor_trend") == "weakening":
        return "short"
    return "neutral"


def _deep_merge(base, incoming):
    merged = deepcopy(base)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def build_growth_cycle_dashboard(
    ism_manufacturing=None,
    ism_services=None,
    m2_money_stock=None,
    jobless_claims=None,
):
    result = {"macro": {"growth_cycle": {}}}
    if ism_manufacturing:
        result = _deep_merge(result, normalize_ism_manufacturing(ism_manufacturing))
    if ism_services:
        result = _deep_merge(result, normalize_ism_services(ism_services))
    if m2_money_stock:
        result = _deep_merge(result, normalize_m2_money_stock(m2_money_stock))
    if jobless_claims:
        result = _deep_merge(result, normalize_jobless_claims(jobless_claims))
    growth_cycle = result["macro"]["growth_cycle"]
    growth_cycle["growth_cycle_bias"] = compute_growth_cycle_bias(growth_cycle)
    return result


def fetch_m2_money_stock_from_source():
    raise ValueError("m2 money stock source is not configured")


def fetch_growth_cycle_dashboard(
    fetch_ism_manufacturing,
    fetch_ism_services,
    fetch_m2_money_stock,
    fetch_jobless_claims,
):
    return build_growth_cycle_dashboard(
        ism_manufacturing=fetch_ism_manufacturing(),
        ism_services=fetch_ism_services(),
        m2_money_stock=fetch_m2_money_stock(),
        jobless_claims=fetch_jobless_claims(),
    )
