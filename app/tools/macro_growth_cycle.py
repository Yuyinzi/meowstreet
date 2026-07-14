import hashlib
import json
from copy import deepcopy
from datetime import date

GROWTH_CYCLE_DASHBOARD_FIELDS = [
    {
        "id": "gdp_indicator",
        "title": "Gross Domestic Product",
        "field": "macro.growth_cycle.gdp",
        "kind": "query",
    },
    {
        "id": "gdp_direction",
        "title": "GDP Direction",
        "field": "macro.growth_cycle.gdp_direction",
        "kind": "compute",
    },
    {
        "id": "industrial_production",
        "title": "Industrial Production",
        "field": "macro.growth_cycle.industrial_production",
        "kind": "query",
    },
    {
        "id": "corporate_earnings",
        "title": "Corporate Earnings",
        "field": "macro.growth_cycle.corporate_earnings",
        "kind": "query",
    },
    {
        "id": "employment_situation_report",
        "title": "Employment Situation Report",
        "field": "macro.growth_cycle.employment_situation_report",
        "kind": "query",
    },
    {
        "id": "ism_pmi",
        "title": "ISM Manufacturing PMI",
        "field": "macro.growth_cycle.ism_pmi",
        "kind": "query",
    },
    {
        "id": "ism_new_orders",
        "title": "ISM New Orders",
        "field": "macro.growth_cycle.ism_new_orders",
        "kind": "query",
    },
    {
        "id": "ism_production",
        "title": "ISM Production",
        "field": "macro.growth_cycle.ism_production",
        "kind": "query",
    },
    {
        "id": "ism_employment",
        "title": "ISM Employment",
        "field": "macro.growth_cycle.ism_employment",
        "kind": "query",
    },
    {
        "id": "ism_supplier_deliveries",
        "title": "ISM Supplier Deliveries",
        "field": "macro.growth_cycle.ism_supplier_deliveries",
        "kind": "query",
    },
    {
        "id": "ism_inventories",
        "title": "ISM Inventories",
        "field": "macro.growth_cycle.ism_inventories",
        "kind": "query",
    },
    {
        "id": "ism_customer_inventories",
        "title": "ISM Customer Inventories",
        "field": "macro.growth_cycle.ism_customer_inventories",
        "kind": "query",
    },
    {
        "id": "ism_prices",
        "title": "ISM Prices",
        "field": "macro.growth_cycle.ism_prices",
        "kind": "query",
    },
    {
        "id": "ism_order_backlog",
        "title": "ISM Order Backlog",
        "field": "macro.growth_cycle.ism_order_backlog",
        "kind": "query",
    },
    {
        "id": "ism_exports",
        "title": "ISM Exports",
        "field": "macro.growth_cycle.ism_exports",
        "kind": "query",
    },
    {
        "id": "ism_imports",
        "title": "ISM Imports",
        "field": "macro.growth_cycle.ism_imports",
        "kind": "query",
    },
    {
        "id": "ism_sector_growth_ranking",
        "title": "ISM Sector Growth Ranking",
        "field": "macro.growth_cycle.ism_sector_growth_ranking",
        "kind": "query",
    },
    {
        "id": "services_pmi",
        "title": "ISM Services PMI",
        "field": "macro.growth_cycle.services_pmi",
        "kind": "query",
    },
    {
        "id": "services_business_activity",
        "title": "Services Business Activity",
        "field": "macro.growth_cycle.services_business_activity",
        "kind": "query",
    },
    {
        "id": "services_new_orders",
        "title": "Services New Orders",
        "field": "macro.growth_cycle.services_new_orders",
        "kind": "query",
    },
    {
        "id": "services_employment",
        "title": "Services Employment",
        "field": "macro.growth_cycle.services_employment",
        "kind": "query",
    },
    {
        "id": "services_supplier_deliveries",
        "title": "Services Supplier Deliveries",
        "field": "macro.growth_cycle.services_supplier_deliveries",
        "kind": "query",
    },
    {
        "id": "services_backlog_orders",
        "title": "Services Backlog Orders",
        "field": "macro.growth_cycle.services_backlog_orders",
        "kind": "query",
    },
    {
        "id": "m2_money_stock",
        "title": "M2 Money Stock",
        "field": "macro.growth_cycle.m2_money_stock",
        "kind": "query",
    },
    {
        "id": "m2_mom_pct_change",
        "title": "M2 Month-on-Month Change",
        "field": "macro.growth_cycle.m2_mom_pct_change",
        "kind": "compute",
    },
    {
        "id": "m2_yoy_pct_change",
        "title": "M2 Year-on-Year Change",
        "field": "macro.growth_cycle.m2_yoy_pct_change",
        "kind": "compute",
    },
    {
        "id": "m2_3m_momentum",
        "title": "M2 3M Momentum",
        "field": "macro.growth_cycle.m2_3m_momentum",
        "kind": "compute",
    },
    {
        "id": "m2_mom_percent_rank",
        "title": "M2 MoM Percent Rank",
        "field": "macro.growth_cycle.m2_mom_percent_rank",
        "kind": "compute",
    },
    {
        "id": "m2_yoy_percent_rank",
        "title": "M2 YoY Percent Rank",
        "field": "macro.growth_cycle.m2_yoy_percent_rank",
        "kind": "compute",
    },
    {
        "id": "core_pce_price_index",
        "title": "Core PCE Price Index",
        "field": "macro.growth_cycle.core_pce_price_index",
        "kind": "query",
    },
    {
        "id": "core_pce_yoy",
        "title": "Core PCE YoY",
        "field": "macro.growth_cycle.core_pce_yoy",
        "kind": "compute",
    },
    {
        "id": "inflation_target_gap",
        "title": "Inflation Target Gap",
        "field": "macro.growth_cycle.inflation_target_gap",
        "kind": "compute",
    },
    {
        "id": "inflation_context_status",
        "title": "Inflation Context",
        "field": "macro.growth_cycle.inflation_context_status",
        "kind": "compute",
    },
    {
        "id": "gdp_expectations",
        "title": "GDP Expectations",
        "field": "macro.growth_cycle.gdp_expectations",
        "kind": "compute",
    },
    {
        "id": "gdp_expectations_status",
        "title": "GDP Expectations Status",
        "field": "macro.growth_cycle.gdp_expectations_status",
        "kind": "compute",
    },
    {
        "id": "initial_jobless_claims",
        "title": "Initial Jobless Claims",
        "field": "macro.growth_cycle.initial_jobless_claims",
        "kind": "query",
    },
    {
        "id": "continuing_jobless_claims",
        "title": "Continuing Jobless Claims",
        "field": "macro.growth_cycle.continuing_jobless_claims",
        "kind": "query",
    },
    {
        "id": "initial_claims_4w_avg",
        "title": "Initial Claims 4-Week Average",
        "field": "macro.growth_cycle.initial_claims_4w_avg",
        "kind": "compute",
    },
    {
        "id": "labor_trend",
        "title": "Labor Trend",
        "field": "macro.growth_cycle.labor_trend",
        "kind": "compute",
    },
    {
        "id": "growth_cycle_bias",
        "title": "Growth Cycle Bias",
        "field": "macro.growth_cycle.growth_cycle_bias",
        "kind": "compute",
    },
    {
        "id": "fed_total_assets",
        "title": "Fed Total Assets",
        "field": "macro.growth_cycle.fed_total_assets",
        "kind": "query",
    },
    {
        "id": "fed_total_assets_yoy",
        "title": "Fed Total Assets YoY",
        "field": "macro.growth_cycle.fed_total_assets_yoy",
        "kind": "compute",
    },
    {
        "id": "fed_total_assets_13w_change",
        "title": "Fed Total Assets 13W Change",
        "field": "macro.growth_cycle.fed_total_assets_13w_change",
        "kind": "compute",
    },
    {
        "id": "fed_treasury_13w_change",
        "title": "Fed Treasury 13W Change",
        "field": "macro.growth_cycle.fed_treasury_13w_change",
        "kind": "compute",
    },
    {
        "id": "fed_mbs_13w_change",
        "title": "Fed MBS 13W Change",
        "field": "macro.growth_cycle.fed_mbs_13w_change",
        "kind": "compute",
    },
]


def _dashboard_fields_by_id(*field_ids):
    return [
        field for field in GROWTH_CYCLE_DASHBOARD_FIELDS if field["id"] in field_ids
    ]


GROWTH_CYCLE_SOURCES = [
    {
        "id": "ism_manufacturing",
        "title": "ISM Manufacturing",
        "frequency": "monthly",
        "fields": _dashboard_fields_by_id(
            "ism_pmi",
            "ism_new_orders",
            "ism_production",
            "ism_employment",
            "ism_supplier_deliveries",
            "ism_inventories",
            "ism_customer_inventories",
            "ism_prices",
            "ism_order_backlog",
            "ism_exports",
            "ism_imports",
        ),
    },
    {
        "id": "ism_services",
        "title": "ISM Services",
        "frequency": "monthly",
        "fields": _dashboard_fields_by_id(
            "services_pmi",
            "services_business_activity",
            "services_new_orders",
            "services_employment",
            "services_supplier_deliveries",
            "services_backlog_orders",
        ),
    },
    {
        "id": "m2_money_stock",
        "title": "M2 Money Stock",
        "frequency": "monthly",
        "fields": _dashboard_fields_by_id(
            "m2_money_stock",
            "m2_mom_pct_change",
            "m2_yoy_pct_change",
            "m2_3m_momentum",
            "m2_mom_percent_rank",
            "m2_yoy_percent_rank",
        ),
    },
    {
        "id": "inflation_context",
        "title": "Inflation Context",
        "frequency": "monthly",
        "fields": _dashboard_fields_by_id(
            "core_pce_price_index",
            "core_pce_yoy",
            "inflation_target_gap",
            "inflation_context_status",
        ),
    },
    {
        "id": "gdp_expectations",
        "title": "GDP Expectations",
        "frequency": "mixed",
        "fields": _dashboard_fields_by_id(
            "gdp_expectations",
            "gdp_expectations_status",
        ),
    },
    {
        "id": "fed_balance_sheet",
        "title": "Fed Balance Sheet",
        "frequency": "weekly",
        "fields": _dashboard_fields_by_id(
            "fed_total_assets",
            "fed_total_assets_yoy",
            "fed_total_assets_13w_change",
            "fed_treasury_13w_change",
            "fed_mbs_13w_change",
        ),
    },
    {
        "id": "jobless_claims",
        "title": "Jobless Claims",
        "frequency": "weekly",
        "fields": _dashboard_fields_by_id(
            "initial_jobless_claims",
            "continuing_jobless_claims",
            "initial_claims_4w_avg",
            "labor_trend",
        ),
    },
]


FED_INFLATION_TARGET = 0.02
FED_INFLATION_TARGET_EFFECTIVE_MONTH = "2012-01-01"
INFLATION_TARGET_BAND = 0.005

M2_INTERPRETATION_SCOPE = "m2_money_supply"
M2_INTERPRETATION_PROMPT_VERSION = "m2-cat-v1"


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
                "ism_customer_inventories": _float_value(
                    payload, "customer_inventories"
                ),
                "ism_prices": _float_value(payload, "prices"),
                "ism_order_backlog": _float_value(payload, "order_backlog"),
                "ism_exports": _float_value(payload, "exports"),
                "ism_imports": _float_value(payload, "imports"),
            }
        }
    }


def normalize_ism_services(payload):
    return {
        "macro": {
            "growth_cycle": {
                "services_period": payload.get("period"),
                "services_pmi": _float_value(payload, "pmi"),
                "services_business_activity": _float_value(
                    payload, "business_activity"
                ),
                "services_new_orders": _float_value(payload, "new_orders"),
                "services_employment": _float_value(payload, "employment"),
                "services_supplier_deliveries": _float_value(
                    payload, "supplier_deliveries"
                ),
                "services_backlog_orders": _float_value(payload, "backlog_orders"),
            }
        }
    }


ISM_MANUFACTURING_DETAIL_LABELS = {
    "pmi": "PMI",
    "new_orders": "New Orders",
    "production": "Production",
    "employment": "Employment",
    "order_backlog": "Order Backlog",
    "exports": "Exports",
    "imports": "Imports",
    "prices": "Prices",
    "supplier_deliveries": "Supplier Deliveries",
    "inventories": "Inventories",
    "customer_inventories": "Customer Inventories",
}

ISM_GROWTH_DRIVER_KEYS = [
    "new_orders",
    "production",
    "employment",
    "order_backlog",
    "exports",
    "imports",
]

ISM_INFLATION_SUPPLY_KEYS = [
    "prices",
    "supplier_deliveries",
    "inventories",
    "customer_inventories",
]

ISM_MANUFACTURING_SERIES_TO_PAYLOAD_KEY = {
    "ism_manufacturing_pmi": "pmi",
    "ism_manufacturing_new_orders": "new_orders",
    "ism_manufacturing_production": "production",
    "ism_manufacturing_employment": "employment",
    "ism_manufacturing_supplier_deliveries": "supplier_deliveries",
    "ism_manufacturing_inventories": "inventories",
    "ism_manufacturing_customer_inventories": "customer_inventories",
    "ism_manufacturing_prices": "prices",
    "ism_manufacturing_order_backlog": "order_backlog",
    "ism_manufacturing_exports": "exports",
    "ism_manufacturing_imports": "imports",
}


def _ism_at_a_glance_tone(row):
    series_id = row.get("series_id", "")
    direction = row.get("direction", "")
    rate_of_change = row.get("rate_of_change", "")
    if series_id == "ism_manufacturing_supplier_deliveries":
        return "amber"
    if series_id == "ism_manufacturing_prices":
        return "amber"
    if series_id == "ism_manufacturing_customer_inventories":
        if direction in ("Too Low", "Too High"):
            return "amber"
    if direction == "Contracting":
        return "red"
    if direction in ("From Contracting", "From Growing", "Mixed"):
        return "amber"
    if direction == "Growing":
        if rate_of_change == "Faster":
            return "green"
        return "amber"
    return "muted"


def _ism_at_a_glance_by_key(rows):
    result = {}
    for row in rows:
        payload_key = ISM_MANUFACTURING_SERIES_TO_PAYLOAD_KEY.get(
            row.get("series_id", "")
        )
        if payload_key is None:
            continue
        result[payload_key] = {
            "label": row["label"],
            "current_value": row["current_value"],
            "previous_value": row["previous_value"],
            "point_change": row["point_change"],
            "direction": row["direction"],
            "rate_of_change": row["rate_of_change"],
            "trend_months": row["trend_months"],
            "tone": _ism_at_a_glance_tone(row),
        }
    return result


def build_ism_manufacturing_payload_from_latest_points(points_by_series_id):
    period = None
    payload = {}
    for series_id, payload_key in ISM_MANUFACTURING_SERIES_TO_PAYLOAD_KEY.items():
        points = points_by_series_id.get(series_id, [])
        if not points:
            payload[payload_key] = None
            continue
        latest = points[-1]
        payload[payload_key] = latest["value"]
        if period is None or latest["date"] > period:
            period = latest["date"]
    return {"period": period, **payload}


def _ism_detail_source(points_by_series_id):
    for rows in points_by_series_id.values():
        for row in rows:
            if row.get("source"):
                return row["source"]
    return None


def _ism_points_by_payload_key(points_by_series_id):
    return {
        payload_key: points_by_series_id.get(series_id, [])
        for series_id, payload_key in ISM_MANUFACTURING_SERIES_TO_PAYLOAD_KEY.items()
    }


def _ism_aligned_rows(points_by_key, keys):
    rows_by_date = {}
    for key in keys:
        for point in points_by_key.get(key, []):
            if point.get("value") is None:
                continue
            row = rows_by_date.setdefault(point["date"], {"date": point["date"]})
            row[key] = float(point["value"])
    return [rows_by_date[date_key] for date_key in sorted(rows_by_date)]


def _ism_labels_for_keys(keys):
    return {key: ISM_MANUFACTURING_DETAIL_LABELS[key] for key in keys}


def _numeric_points(rows, value_key):
    return [
        {
            "date": row["date"],
            "value": float(row[value_key]),
            "period_label": row.get("period_label"),
            "source_workbook": row.get("source_workbook"),
            "source_sheet": row.get("source_sheet"),
        }
        for row in sorted(rows or [], key=lambda item: item["date"])
        if row.get("date") and row.get(value_key) is not None
    ]


def _date_from_iso(date_value):
    return date.fromisoformat(str(date_value)[:10])


def _latest_point_on_or_before(points, date_value, max_stale_days=None):
    candidates = [point for point in points if point["date"] <= date_value]
    if not candidates:
        return None
    point = sorted(candidates, key=lambda item: item["date"])[-1]
    if max_stale_days is None:
        return point
    stale_days = (_date_from_iso(date_value) - _date_from_iso(point["date"])).days
    if stale_days > max_stale_days:
        return None
    return point


def _latest_value_on_or_before(points, date_value, max_stale_days=None):
    point = _latest_point_on_or_before(points, date_value, max_stale_days)
    return point["value"] if point else None


def _source_signature(row):
    return (
        row.get("source_workbook"),
        row.get("source_sheet"),
    )


def _same_known_source(left, right):
    left_signature = _source_signature(left)
    right_signature = _source_signature(right)
    if not any(left_signature) or not any(right_signature):
        return True
    return left_signature == right_signature


def _gdp_qoq_annualized_rows(gdp_level_rows):
    rows = _numeric_points(gdp_level_rows, "gdp_level")
    result = []
    for index in range(1, len(rows)):
        if not _same_known_source(rows[index - 1], rows[index]):
            continue
        previous = rows[index - 1]["value"]
        current = rows[index]["value"]
        if previous == 0:
            continue
        result.append(
            {
                "date": rows[index]["date"],
                "value": round(((current / previous) ** 4 - 1) * 100, 4),
                "period_label": rows[index].get("period_label"),
            }
        )
    return result


def _monthly_last_close_rows(price_rows):
    monthly = {}
    for row in sorted(price_rows or [], key=lambda item: item["date"]):
        if row.get("close") is None:
            continue
        month_key = row["date"][:7]
        monthly[month_key] = {
            "date": row["date"],
            "value": float(row["close"]),
        }
    return [monthly[key] for key in sorted(monthly)]


def _direction(values):
    clean_values = [value for value in values if value is not None]
    if len(clean_values) < 2:
        return "flat"
    if clean_values[-1] > clean_values[0]:
        return "up"
    if clean_values[-1] < clean_values[0]:
        return "down"
    return "flat"


def _indexed_values(rows):
    if not rows:
        return []
    base = rows[0]["value"]
    return [
        {
            "date": row["date"],
            "value": round(row["value"] / base * 100, 4) if base else None,
            "raw_value": row["value"],
        }
        for row in rows
    ]


def _gdp_relationship_state(ism_direction, gdp_direction):
    states = {
        ("up", "down"): (
            "early_recovery",
            "Early Recovery",
            "ISM is improving while GDP growth is still weakening.",
        ),
        ("down", "up"): (
            "early_slowdown",
            "Early Slowdown",
            "ISM is weakening while GDP growth still looks firm.",
        ),
        ("up", "up"): (
            "expansion",
            "Expansion",
            "ISM and GDP growth are improving together.",
        ),
        ("down", "down"): (
            "contraction",
            "Contraction",
            "ISM and GDP growth are weakening together.",
        ),
    }
    state, label, description = states.get(
        (ism_direction, gdp_direction),
        (
            "mixed",
            "Mixed",
            "ISM and GDP trend directions are not decisive.",
        ),
    )
    return {
        "id": "gdp_context",
        "state": state,
        "label": label,
        "ism_direction": ism_direction,
        "comparison_direction": gdp_direction,
        "description": description,
    }


def _sp500_relationship_state(ism_direction, sp500_direction):
    states = {
        ("up", "up"): (
            "growth_priced",
            "Growth Priced",
            "ISM is improving and S&P 500 is rising with the growth signal.",
        ),
        ("up", "down"): (
            "market_skeptical",
            "Market Skeptical",
            "ISM is improving but S&P 500 is not pricing the growth signal.",
        ),
        ("down", "up"): (
            "liquidity_policy_rally",
            "Liquidity / Policy Rally",
            "S&P 500 is rising while ISM weakens; watch liquidity and rate-cut drivers.",
        ),
        ("down", "down"): (
            "slowdown_priced",
            "Slowdown Priced",
            "ISM is weakening and S&P 500 is falling with the slowdown signal.",
        ),
    }
    state, label, description = states.get(
        (ism_direction, sp500_direction),
        (
            "mixed",
            "Mixed",
            "ISM and S&P 500 trend directions are not decisive.",
        ),
    )
    return {
        "id": "market_context",
        "state": state,
        "label": label,
        "ism_direction": ism_direction,
        "comparison_direction": sp500_direction,
        "description": description,
    }


def _build_ism_macro_context_chart(ism_pmi_points, gdp_level_rows, sp500_price_rows):
    pmi_points = _numeric_points(ism_pmi_points, "value")
    gdp_growth_rows = _gdp_qoq_annualized_rows(gdp_level_rows)
    sp500_rows = _monthly_last_close_rows(sp500_price_rows)
    sp500_index_rows = _indexed_values(sp500_rows)
    if not pmi_points or not sp500_index_rows:
        return None
    shared_rows = []
    for sp500_row in sp500_index_rows:
        pmi_value = _latest_value_on_or_before(
            pmi_points,
            sp500_row["date"],
            max_stale_days=62,
        )
        gdp_point = _latest_point_on_or_before(gdp_growth_rows, sp500_row["date"])
        shared_rows.append(
            {
                "date": sp500_row["date"],
                "ism_pmi": pmi_value,
                "gdp_growth": gdp_point["value"] if gdp_point else None,
                "gdp_period": gdp_point.get("period_label") if gdp_point else None,
                "sp500_index": sp500_row["value"],
                "sp500_close": sp500_row["raw_value"],
            }
        )
    if not shared_rows:
        return None
    pmi_values = [row["ism_pmi"] for row in shared_rows]
    gdp_values = [
        row["gdp_growth"] for row in shared_rows if row["gdp_growth"] is not None
    ]
    sp500_values = [
        row["sp500_index"] for row in shared_rows if row["sp500_index"] is not None
    ]
    return {
        "id": "ism_macro_context",
        "kind": "small_multiples",
        "title": "Macro Confirmation",
        "series": shared_rows,
        "panels": [
            {
                "id": "ism_pmi",
                "title": "ISM PMI",
                "key": "ism_pmi",
                "unit": "index",
                "subtitle": "Monthly",
                "reference_lines": [
                    {"value": 50, "label": "Expansion / Contraction threshold"}
                ],
            },
            {
                "id": "gdp_growth",
                "title": "Real GDP QoQ Annualized",
                "key": "gdp_growth",
                "unit": "percent",
                "subtitle": "Quarterly, shown as step series",
                "cadence": "quarterly_forward_filled",
                "line_shape": "step_after",
            },
            {
                "id": "sp500_index",
                "title": "S&P 500",
                "key": "sp500_index",
                "unit": "base_100",
                "subtitle": "Base = 100",
            },
        ],
        "contexts": [
            _gdp_relationship_state(
                _direction(pmi_values[-3:]),
                _direction(gdp_values[-2:]),
            ),
            _sp500_relationship_state(
                _direction(pmi_values[-3:]),
                _direction(sp500_values[-3:]),
            ),
        ],
        "description": "Small multiples share one time axis. PMI and GDP keep raw units; S&P 500 is based to 100.",
    }


def build_ism_manufacturing_detail_payload(
    points_by_series_id,
    gdp_level_rows=None,
    sp500_price_rows=None,
    ism_industry_breadth=None,
    ism_at_a_glance=None,
):
    points_by_key = _ism_points_by_payload_key(points_by_series_id)
    all_keys = list(ISM_MANUFACTURING_DETAIL_LABELS)
    all_rows = _ism_aligned_rows(points_by_key, all_keys)
    latest = dict(all_rows[-1]) if all_rows else None
    if latest:
        latest.pop("date", None)
    pmi_points = points_by_series_id.get("ism_manufacturing_pmi", [])
    macro_context_chart = _build_ism_macro_context_chart(
        pmi_points,
        gdp_level_rows or [],
        sp500_price_rows or [],
    )
    relationship_charts = [macro_context_chart] if macro_context_chart else []
    result = {
        "detail_id": "ism_manufacturing",
        "title": "ISM Manufacturing",
        "source": _ism_detail_source(points_by_series_id),
        "charts": [
            {
                "id": "ism_manufacturing_heat_map",
                "kind": "heat_map",
                "title": "ISM Manufacturing Heat Map",
                "keys": all_keys,
                "labels": _ism_labels_for_keys(all_keys),
                "series": all_rows,
            },
            *relationship_charts,
        ],
        "latest": latest,
        "detail_groups": [
            {"label": "Business Cycle", "keys": ["pmi"]},
            {"label": "Growth Drivers", "keys": ISM_GROWTH_DRIVER_KEYS},
            {"label": "Inflation & Supply", "keys": ISM_INFLATION_SUPPLY_KEYS},
            _ism_industry_breadth_detail_group(ism_industry_breadth),
        ],
        "relationship_summary": {
            "shared_months": len(macro_context_chart["series"])
            if macro_context_chart
            else 0,
            "gdp_observations": len(
                [
                    row
                    for row in (
                        macro_context_chart["series"] if macro_context_chart else []
                    )
                    if row.get("gdp_growth") is not None
                ]
            ),
            "sp500_observations": len(
                [
                    row
                    for row in (
                        macro_context_chart["series"] if macro_context_chart else []
                    )
                    if row.get("sp500_index") is not None
                ]
            ),
        },
    }
    if ism_at_a_glance:
        result["latest_metadata"] = _ism_at_a_glance_by_key(ism_at_a_glance)
    return result


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
    three_month_ago_value = values[-4] if len(values) >= 4 else None
    year_ago_value = values[-13] if len(values) >= 13 else None
    mom_changes = [
        _pct_change(values[index], values[index - 1]) for index in range(1, len(values))
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
                "m2_3m_momentum": _pct_change(latest_value, three_month_ago_value),
                "m2_mom_percent_rank": _percent_rank(mom_changes, latest_mom),
                "m2_yoy_percent_rank": _percent_rank(yoy_changes, latest_yoy),
            }
        }
    }


def _inflation_context_status(gap):
    if gap is None:
        return "missing"
    if gap >= INFLATION_TARGET_BAND:
        return "above_target"
    if gap <= -INFLATION_TARGET_BAND:
        return "below_target"
    return "near_target"


def _inflation_context_status_label(status):
    labels = {
        "above_target": "Above Target",
        "near_target": "Near Target",
        "below_target": "Below Target",
        "missing": "Missing",
    }
    return labels.get(status, "Missing")


def _inflation_context_description(status):
    descriptions = {
        "above_target": "Inflation is above the Fed target, which can constrain liquidity support.",
        "near_target": "Inflation is near the Fed target, so liquidity support is less constrained by inflation.",
        "below_target": "Inflation is below the Fed target, giving the Fed more room to support liquidity if growth weakens.",
        "missing": "Core PCE inflation data is missing.",
    }
    return descriptions.get(status, descriptions["missing"])


def normalize_core_pce_price_index(payload):
    rows = payload.get("series", [])
    values = [float(row["value"]) for row in rows]
    latest_value = values[-1] if values else None
    year_ago_value = values[-13] if len(values) >= 13 else None
    latest_yoy = _pct_change(latest_value, year_ago_value)
    gap = latest_yoy - FED_INFLATION_TARGET if latest_yoy is not None else None
    latest_period = rows[-1]["date"] if rows else None
    return {
        "macro": {
            "growth_cycle": {
                "inflation_context_period": latest_period,
                "core_pce_price_index": latest_value,
                "core_pce_yoy": latest_yoy,
                "inflation_target_gap": gap,
                "inflation_context_status": _inflation_context_status(gap),
            }
        }
    }


def build_inflation_context_headline(growth_cycle):
    status = growth_cycle.get("inflation_context_status", "missing")
    return {
        "id": "inflation_context",
        "label": "Inflation Context",
        "period": growth_cycle.get("inflation_context_period"),
        "status": status,
        "status_label": _inflation_context_status_label(status),
        "core_pce_yoy": growth_cycle.get("core_pce_yoy"),
        "target": FED_INFLATION_TARGET,
        "target_label": "Fed 2% Target",
        "gap": growth_cycle.get("inflation_target_gap"),
        "description": _inflation_context_description(status),
    }


def _series_points(payload):
    return [
        {"date": row["date"], "value": float(row["value"])}
        for row in payload.get("series", [])
        if row.get("value") is not None
    ]


def _value_weeks_ago(points, weeks):
    if len(points) < weeks + 1:
        return None
    return points[-weeks - 1]["value"]


def normalize_fed_balance_sheet(total_assets, treasury_holdings, mbs_holdings):
    total_points = _series_points(total_assets)
    treasury_points = _series_points(treasury_holdings)
    mbs_points = _series_points(mbs_holdings)
    latest_total = total_points[-1]["value"] if total_points else None
    year_ago_total = _value_weeks_ago(total_points, 52)
    thirteen_week_total = _value_weeks_ago(total_points, 13)
    thirteen_week_treasury = _value_weeks_ago(treasury_points, 13)
    thirteen_week_mbs = _value_weeks_ago(mbs_points, 13)
    latest_treasury = treasury_points[-1]["value"] if treasury_points else None
    latest_mbs = mbs_points[-1]["value"] if mbs_points else None
    return {
        "macro": {
            "growth_cycle": {
                "fed_balance_sheet_period": total_points[-1]["date"]
                if total_points
                else None,
                "fed_total_assets": latest_total,
                "fed_total_assets_yoy": _pct_change(latest_total, year_ago_total),
                "fed_total_assets_13w_change": latest_total - thirteen_week_total
                if latest_total is not None and thirteen_week_total is not None
                else None,
                "fed_treasury_13w_change": latest_treasury - thirteen_week_treasury
                if latest_treasury is not None and thirteen_week_treasury is not None
                else None,
                "fed_mbs_13w_change": latest_mbs - thirteen_week_mbs
                if latest_mbs is not None and thirteen_week_mbs is not None
                else None,
            }
        }
    }


def build_fed_balance_sheet_headline(growth_cycle):
    if growth_cycle.get("fed_total_assets") is None:
        return {
            "id": "fed_balance_sheet",
            "label": "Fed Balance Sheet",
            "period": None,
            "status": "missing",
            "status_label": "Missing",
        }
    return {
        "id": "fed_balance_sheet",
        "label": "Fed Balance Sheet",
        "period": growth_cycle.get("fed_balance_sheet_period"),
        "status": "context",
        "status_label": "Liquidity Context",
        "total_assets": growth_cycle.get("fed_total_assets"),
        "total_assets_yoy": growth_cycle.get("fed_total_assets_yoy"),
        "total_assets_13w_change": growth_cycle.get("fed_total_assets_13w_change"),
        "treasury_13w_change": growth_cycle.get("fed_treasury_13w_change"),
        "mbs_13w_change": growth_cycle.get("fed_mbs_13w_change"),
        "description": "Balance sheet expansion supports liquidity; contraction drains liquidity. Use this with M2, inflation, credit spreads, and GDP expectations.",
    }


def _bool_event_flag(value):
    return bool(int(value or 0))


def build_fomc_calendar_headline(next_meeting):
    if not next_meeting:
        return {
            "id": "fomc_calendar",
            "label": "FOMC Calendar",
            "period": None,
            "status": "missing",
            "status_label": "Missing",
        }
    return {
        "id": "fomc_calendar",
        "label": "FOMC Calendar",
        "period": next_meeting.get("start_date"),
        "status": "timing_context",
        "status_label": "Policy Timing",
        "next_meeting": {
            "start_date": next_meeting.get("start_date"),
            "end_date": next_meeting.get("end_date"),
            "display_month": next_meeting.get("display_month"),
            "title": next_meeting.get("title"),
            "policy_tone": next_meeting.get("policy_tone", "unknown"),
            "has_sep": _bool_event_flag(next_meeting.get("has_sep")),
            "source": next_meeting.get("source"),
            "url": next_meeting.get("url"),
        },
        "description": "FOMC dates are policy-timing context for reading liquidity, inflation, and balance-sheet changes. They are not buy/sell signals.",
    }


def build_fomc_tone_headline(latest_tone):
    if not latest_tone:
        return {
            "id": "fomc_tone",
            "label": "FOMC Policy Read",
            "period": None,
            "status": "missing",
            "status_label": "Missing",
        }
    marker_tone = latest_tone.get("statement_marker_tone") or latest_tone.get(
        "marker_tone"
    )
    return {
        "id": "fomc_tone",
        "label": "FOMC Policy Read",
        "period": latest_tone.get("start_date"),
        "status": "context",
        "status_label": "Latest Policy Read",
        "latest_tone": {
            "event_id": latest_tone.get("event_id"),
            "start_date": latest_tone.get("start_date"),
            "end_date": latest_tone.get("end_date"),
            "marker_tone": marker_tone,
            "policy_action": latest_tone.get("statement_policy_action")
            or latest_tone.get("policy_action"),
            "guidance_bias": latest_tone.get("statement_guidance_bias")
            or latest_tone.get("guidance_bias"),
            "language_tone": latest_tone.get("statement_language_tone")
            or latest_tone.get("language_tone"),
            "overall_bias": latest_tone.get("statement_overall_bias")
            or latest_tone.get("overall_bias"),
            "tone_change": latest_tone.get("statement_tone_change")
            or latest_tone.get("tone_change"),
            "confidence": latest_tone.get("statement_confidence")
            or latest_tone.get("confidence"),
            "reason": latest_tone.get("statement_reason") or latest_tone.get("reason"),
            "minutes_status": latest_tone.get("minutes_status", "pending"),
            "minutes_confirmation": latest_tone.get("minutes_confirmation", "pending"),
            "risk_focus": latest_tone.get("risk_focus", "unknown"),
            "risk_bias": latest_tone.get("risk_bias", "unknown"),
            "divergence_level": latest_tone.get("divergence_level", "unknown"),
            "uncertainty_level": latest_tone.get("uncertainty_level", "unknown"),
            "policy_conviction": latest_tone.get("policy_conviction", "unknown"),
            "minutes_confidence": latest_tone.get("minutes_confidence"),
            "minutes_reason": latest_tone.get("minutes_reason"),
        },
    }


def _fomc_chart_events(events, available_dates):
    date_set = set(available_dates)
    return [
        {
            "date": event["display_month"],
            "event_date": event["start_date"],
            "end_date": event.get("end_date"),
            "label": "FOMC",
            "title": event.get("title", "FOMC Meeting"),
            "kind": "fomc_meeting",
            "policy_tone": event.get("marker_tone")
            or event.get("policy_tone", "unknown"),
            "has_sep": _bool_event_flag(event.get("has_sep")),
            "statement_tone": event.get("statement_tone", "unknown"),
            "tone_change": event.get("tone_change", "unknown"),
            "confidence": event.get("tone_confidence") or event.get("confidence"),
            "reason": event.get("tone_reason") or event.get("reason"),
            "minutes_status": event.get("minutes_status", "pending"),
            "minutes_tone": event.get("minutes_tone", "unknown"),
            "minutes_confirmation": event.get("minutes_confirmation", "pending"),
            "risk_focus": event.get("risk_focus", "unknown"),
            "risk_bias": event.get("risk_bias", "unknown"),
            "divergence_level": event.get("divergence_level", "unknown"),
            "uncertainty_level": event.get("uncertainty_level", "unknown"),
            "policy_conviction": event.get("policy_conviction", "unknown"),
            "minutes_confidence": event.get("minutes_confidence"),
            "minutes_generated_at": event.get("minutes_generated_at"),
        }
        for event in events or []
        if event.get("display_month") in date_set
    ]


def build_gdp_expectations_headline(growth_cycle):
    return {
        "id": "gdp_expectations",
        "label": "GDP Expectations",
        "period": growth_cycle.get("gdp_expectations_period"),
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


def _m2_status(growth_cycle):
    yoy = growth_cycle.get("m2_yoy_pct_change")
    momentum = growth_cycle.get("m2_3m_momentum")
    mom_rank = growth_cycle.get("m2_mom_percent_rank")
    if yoy is None or momentum is None or mom_rank is None:
        return "missing"
    if mom_rank >= 0.95 or mom_rank <= 0.05:
        return "shock"
    if yoy > 0 and momentum > 0:
        return "expanding"
    if yoy < 0 or momentum < 0:
        return "contracting"
    return "mixed"


def _m2_status_label(status):
    labels = {
        "expanding": "Expanding",
        "contracting": "Contracting",
        "shock": "Shock",
        "mixed": "Mixed",
        "missing": "Missing",
    }
    return labels.get(status, "Mixed")


def build_m2_money_supply_headline(growth_cycle):
    status = _m2_status(growth_cycle)
    return {
        "id": "m2_money_supply",
        "label": "M2 Money Supply",
        "period": growth_cycle.get("m2_period"),
        "status": status,
        "status_label": _m2_status_label(status),
        "state": {
            "m2_yoy_pct_change": growth_cycle.get("m2_yoy_pct_change"),
            "m2_yoy_percent_rank": growth_cycle.get("m2_yoy_percent_rank"),
            "m2_money_stock": growth_cycle.get("m2_money_stock"),
        },
        "change": {
            "m2_3m_momentum": growth_cycle.get("m2_3m_momentum"),
        },
        "shock": {
            "m2_mom_pct_change": growth_cycle.get("m2_mom_pct_change"),
            "m2_mom_percent_rank": growth_cycle.get("m2_mom_percent_rank"),
        },
    }


def _headline_card_ids(headline):
    return {card["id"] for card in headline}


def _growth_cycle_section(
    section_id, title, subtitle, cards, status="available", period=None
):
    return {
        "id": section_id,
        "title": title,
        "subtitle": subtitle,
        "kind": "cards" if cards else "status",
        "status": status,
        "period": period,
        "cards": cards,
    }


def _ism_metric_values(growth_cycle, field_ids):
    return [growth_cycle.get(field_id) for field_id in field_ids]


def _available_values(values):
    return [value for value in values if value is not None]


def _above_50_count(values):
    return len([value for value in values if value is not None and value > 50])


def _ism_phase(pmi):
    if pmi is None:
        return "missing"
    if pmi >= 60:
        return "late_expansion"
    if pmi > 50:
        return "expansion"
    if pmi >= 45:
        return "slowdown"
    return "contraction"


def _ism_phase_label(phase):
    labels = {
        "late_expansion": "Late Expansion",
        "expansion": "Expansion",
        "slowdown": "Slowdown",
        "contraction": "Contraction",
        "missing": "Missing",
    }
    return labels.get(phase, "Mixed")


def build_ism_business_cycle_headline(growth_cycle):
    pmi = growth_cycle.get("ism_pmi")
    phase = _ism_phase(pmi)
    if pmi is None:
        status = "missing"
        status_label = "Missing"
        description = "ISM Manufacturing PMI data is missing."
    elif pmi > 50:
        status = "expansion"
        status_label = "Expansion"
        description = "ISM PMI above 50 points to manufacturing expansion."
    elif pmi < 50:
        status = "contraction"
        status_label = "Contraction"
        description = "ISM PMI below 50 points to manufacturing contraction."
    else:
        status = "neutral"
        status_label = "Neutral"
        description = "ISM PMI is at the 50 expansion/contraction line."
    return {
        "id": "ism_business_cycle",
        "label": "ISM Business Cycle",
        "period": growth_cycle.get("ism_period"),
        "status": status,
        "status_label": status_label,
        "phase": phase,
        "phase_label": _ism_phase_label(phase),
        "pmi": pmi,
        "new_orders": growth_cycle.get("ism_new_orders"),
        "description": description,
    }


def build_ism_growth_drivers_headline(growth_cycle):
    fields = [
        "ism_new_orders",
        "ism_production",
        "ism_employment",
        "ism_order_backlog",
        "ism_exports",
        "ism_imports",
    ]
    values = _ism_metric_values(growth_cycle, fields)
    available = _available_values(values)
    new_orders = growth_cycle.get("ism_new_orders")
    production = growth_cycle.get("ism_production")
    if not available:
        status = "missing"
        status_label = "Missing"
        description = "ISM growth driver data is missing."
    elif (
        new_orders is not None
        and production is not None
        and new_orders > 50
        and production > 50
    ):
        status = "supportive"
        status_label = "Supportive"
        description = "New Orders and Production are both above 50."
    elif (new_orders is not None and new_orders < 50) or (
        production is not None and production < 50
    ):
        status = "warning"
        status_label = "Warning"
        description = "New Orders or Production is below 50."
    else:
        status = "mixed"
        status_label = "Mixed"
        description = "Growth driver signals are mixed."
    return {
        "id": "ism_growth_drivers",
        "label": "ISM Growth Drivers",
        "period": growth_cycle.get("ism_period"),
        "status": status,
        "status_label": status_label,
        "above_50_count": _above_50_count(values),
        "available_count": len(available),
        "metrics": {
            "new_orders": new_orders,
            "production": production,
            "employment": growth_cycle.get("ism_employment"),
            "order_backlog": growth_cycle.get("ism_order_backlog"),
            "exports": growth_cycle.get("ism_exports"),
            "imports": growth_cycle.get("ism_imports"),
        },
        "description": description,
    }


def build_ism_inflation_supply_headline(growth_cycle):
    fields = [
        "ism_prices",
        "ism_supplier_deliveries",
        "ism_inventories",
        "ism_customer_inventories",
    ]
    values = _ism_metric_values(growth_cycle, fields)
    available = _available_values(values)
    prices = growth_cycle.get("ism_prices")
    deliveries = growth_cycle.get("ism_supplier_deliveries")
    if not available:
        status = "missing"
        status_label = "Missing"
        description = "ISM inflation and supply data is missing."
    elif prices is not None and prices >= 60:
        status = "inflation_pressure"
        status_label = "Inflation Pressure"
        description = "ISM Prices are elevated."
    elif deliveries is not None and deliveries >= 55:
        status = "supply_pressure"
        status_label = "Supply Pressure"
        description = "Supplier Deliveries indicate supply pressure."
    elif prices is not None and prices < 50:
        status = "disinflationary"
        status_label = "Disinflationary"
        description = "ISM Prices are below 50."
    else:
        status = "neutral"
        status_label = "Neutral"
        description = "Inflation and supply signals are not extreme."
    return {
        "id": "ism_inflation_supply",
        "label": "ISM Inflation & Supply",
        "period": growth_cycle.get("ism_period"),
        "status": status,
        "status_label": status_label,
        "prices": prices,
        "supplier_deliveries": deliveries,
        "inventories": growth_cycle.get("ism_inventories"),
        "customer_inventories": growth_cycle.get("ism_customer_inventories"),
        "available_count": len(available),
        "description": description,
    }


def build_ism_industry_breadth_summary(rankings):
    if not rankings:
        return None
    latest_date = max(row["date"] for row in rankings)
    latest_rows = [row for row in rankings if row["date"] == latest_date]
    growth = sorted(
        [row for row in latest_rows if row["direction"] == "growth"],
        key=lambda row: row["rank"],
        reverse=True,
    )
    contraction = sorted(
        [row for row in latest_rows if row["direction"] == "contraction"],
        key=lambda row: row["rank"],
    )
    return {
        "date": latest_date,
        "growth_count": len(growth),
        "contraction_count": len(contraction),
        "total_count": len(latest_rows),
        "top_growth": [
            {"industry": row["industry"], "rank": row["rank"]} for row in growth[:3]
        ],
        "top_contraction": [
            {"industry": row["industry"], "rank": row["rank"]}
            for row in contraction[:3]
        ],
    }


def _ism_industry_breadth_segment(summary):
    if not summary:
        return {
            "status": "pending_inputs",
            "required_inputs": [
                "Sectors tab growth rankings",
                "Growth and contraction breadth",
            ],
        }
    return {
        "status": "available",
        "period": summary["date"],
        "growth_count": summary["growth_count"],
        "contraction_count": summary["contraction_count"],
        "total_count": summary["total_count"],
        "top_growth": summary["top_growth"],
        "top_contraction": summary["top_contraction"],
    }


def _ism_industry_breadth_detail_group(summary):
    if not summary:
        return {
            "label": "Industry Breadth",
            "keys": [],
            "required_inputs": [
                "Sectors tab growth rankings",
                "Growth and contraction breadth",
            ],
        }
    return {
        "label": "Industry Breadth",
        "keys": [],
        "industry_breadth": summary,
    }


def build_ism_industry_breadth_headline(growth_cycle):
    return {
        "id": "ism_industry_breadth",
        "label": "ISM Industry Breadth",
        "period": growth_cycle.get("ism_period"),
        "status": "pending_inputs",
        "status_label": "Pending Inputs",
        "required_inputs": [
            "Sectors tab growth rankings",
            "Industry comments",
            "Growth and contraction breadth",
        ],
        "description": "Industry breadth requires the Sectors and Industry Comments workbook tabs, which are handled in later steps.",
    }


def build_growth_cycle_sections(growth_cycle, headline):
    card_ids = _headline_card_ids(headline)
    ism_status = "available" if growth_cycle.get("ism_pmi") is not None else "missing"
    return [
        _growth_cycle_section(
            "ism_manufacturing",
            "ISM Manufacturing",
            "Manufacturing survey growth signal and heat-map inputs.",
            ["ism_manufacturing"],
            status=ism_status,
            period=growth_cycle.get("ism_period"),
        ),
        _growth_cycle_section(
            "m2_liquidity",
            "M2 Liquidity",
            "Money supply expansion and liquidity momentum.",
            ["m2_money_supply"] if "m2_money_supply" in card_ids else [],
            period=growth_cycle.get("m2_period"),
        ),
        _growth_cycle_section(
            "inflation_context",
            "Inflation Context",
            "Core PCE constraint and gap versus the Fed target.",
            ["inflation_context"] if "inflation_context" in card_ids else [],
            status="available" if "inflation_context" in card_ids else "missing",
            period=growth_cycle.get("inflation_context_period"),
        ),
        _growth_cycle_section(
            "services_labor",
            "Services / Labor",
            "Services survey and labor confirmation inputs.",
            [],
            status="pending_inputs",
            period=growth_cycle.get("services_period")
            or growth_cycle.get("jobless_claims_period"),
        ),
        _growth_cycle_section(
            "gdp_expectations",
            "GDP Expectations",
            "Forward growth direction once leading inputs are ready.",
            ["gdp_expectations"] if "gdp_expectations" in card_ids else [],
            status="available" if "gdp_expectations" in card_ids else "missing",
            period=growth_cycle.get("gdp_expectations_period"),
        ),
        _growth_cycle_section(
            "fomc_context",
            "FOMC",
            "Policy timing and latest policy-tone read.",
            [
                card_id
                for card_id in ["fomc_calendar", "fomc_tone"]
                if card_id in card_ids
            ],
            status="available"
            if {"fomc_calendar", "fomc_tone"} & card_ids
            else "missing",
        ),
    ]


def _build_ism_manufacturing_headline(
    growth_cycle, ism_industry_breadth=None, ism_at_a_glance=None
):
    pmi = growth_cycle.get("ism_pmi")
    growth_fields = [
        "ism_new_orders",
        "ism_production",
        "ism_employment",
        "ism_order_backlog",
        "ism_exports",
        "ism_imports",
    ]
    growth_values = _ism_metric_values(growth_cycle, growth_fields)
    available = _available_values(growth_values)
    phase = _ism_phase(pmi)
    by_key = _ism_at_a_glance_by_key(ism_at_a_glance) if ism_at_a_glance else None
    result = {
        "id": "ism_manufacturing",
        "label": "ISM Manufacturing",
        "period": growth_cycle.get("ism_period"),
        "status": phase,
        "phase": phase,
        "pmi": pmi,
        "above_50_count": _above_50_count(growth_values),
        "available_count": len(available),
        "segments": {
            "business_cycle": {
                "pmi": pmi,
                "phase": phase,
                "phase_label": _ism_phase_label(phase),
            },
            "growth_drivers": {
                "above_50_count": _above_50_count(growth_values),
                "available_count": len(available),
            },
            "inflation_supply": {
                "prices": growth_cycle.get("ism_prices"),
                "deliveries": growth_cycle.get("ism_supplier_deliveries"),
            },
            "industry_breadth": _ism_industry_breadth_segment(ism_industry_breadth),
        },
    }
    if by_key:
        result["segments"]["business_cycle"]["trend"] = by_key.get("pmi")
    return result


def build_growth_cycle_dashboard_payload(
    growth_cycle_dashboard,
    next_fomc_meeting=None,
    fomc_latest_tone=None,
    ism_industry_breadth=None,
    ism_at_a_glance=None,
):
    growth_cycle = growth_cycle_dashboard.get("macro", {}).get("growth_cycle", {})
    headline = [
        _build_ism_manufacturing_headline(
            growth_cycle, ism_industry_breadth, ism_at_a_glance
        ),
        build_m2_money_supply_headline(growth_cycle),
    ]
    inflation_card = build_inflation_context_headline(growth_cycle)
    if inflation_card["status"] != "missing":
        headline.append(inflation_card)
    balance_sheet_card = build_fed_balance_sheet_headline(growth_cycle)
    if balance_sheet_card["status"] != "missing":
        headline.append(balance_sheet_card)
    fomc_card = build_fomc_calendar_headline(next_fomc_meeting)
    if fomc_card["status"] != "missing":
        headline.append(fomc_card)
    tone_card = build_fomc_tone_headline(fomc_latest_tone)
    if tone_card["status"] != "missing":
        headline.append(tone_card)
    headline.append(build_gdp_expectations_headline(growth_cycle))
    sections = build_growth_cycle_sections(growth_cycle, headline)
    return {
        "headline": headline,
        "growth_cycle": growth_cycle,
        "sections": sections,
        "missing": None,
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
    previous_average = (
        _average(values[-8:-4]) if len(values) >= 8 else _average(values[:-4])
    )
    if previous_average is None:
        return "unknown"
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
    if (
        manufacturing_contracting
        and services_contracting
        and growth_cycle.get("labor_trend") == "weakening"
    ):
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
    core_pce_price_index=None,
    fed_total_assets=None,
    fed_treasury_holdings=None,
    fed_mbs_holdings=None,
    jobless_claims=None,
):
    result = {"macro": {"growth_cycle": {}}}
    if ism_manufacturing:
        result = _deep_merge(result, normalize_ism_manufacturing(ism_manufacturing))
    if ism_services:
        result = _deep_merge(result, normalize_ism_services(ism_services))
    if m2_money_stock:
        result = _deep_merge(result, normalize_m2_money_stock(m2_money_stock))
    if core_pce_price_index:
        result = _deep_merge(
            result, normalize_core_pce_price_index(core_pce_price_index)
        )
    if fed_total_assets and fed_treasury_holdings and fed_mbs_holdings:
        result = _deep_merge(
            result,
            normalize_fed_balance_sheet(
                fed_total_assets,
                fed_treasury_holdings,
                fed_mbs_holdings,
            ),
        )
    if jobless_claims:
        result = _deep_merge(result, normalize_jobless_claims(jobless_claims))
    growth_cycle = result["macro"]["growth_cycle"]
    growth_cycle["growth_cycle_bias"] = compute_growth_cycle_bias(growth_cycle)
    return result


def _m2_level_points(rows):
    return [
        {"date": row["date"], "value": float(row["value"]), "source": row.get("source")}
        for row in rows
        if row.get("value") is not None
    ]


def _m2_growth_series(points, lookback_months):
    return [
        {
            "date": points[index]["date"],
            "value": round(
                _pct_change(
                    points[index]["value"], points[index - lookback_months]["value"]
                )
                * 100,
                4,
            ),
        }
        for index in range(lookback_months, len(points))
        if _pct_change(points[index]["value"], points[index - lookback_months]["value"])
        is not None
    ]


def _core_pce_yoy_series(points):
    return [
        {
            "date": points[index]["date"],
            "value": round(
                _pct_change(points[index]["value"], points[index - 12]["value"]) * 100,
                4,
            ),
        }
        for index in range(12, len(points))
        if _pct_change(points[index]["value"], points[index - 12]["value"]) is not None
    ]


def _value_by_date(points):
    return {point["date"]: point["value"] for point in points}


def _monthly_last_points(points):
    monthly_points = {}
    for point in sorted(points, key=lambda row: row["date"]):
        month_key = f"{point['date'][:7]}-01"
        monthly_points[month_key] = {
            "date": month_key,
            "value": point["value"],
            "source": point.get("source"),
        }
    return [monthly_points[date_key] for date_key in sorted(monthly_points)]


def _weekly_change_series(points, weeks):
    return [
        {
            "date": points[index]["date"],
            "value": round(points[index]["value"] - points[index - weeks]["value"], 4),
        }
        for index in range(weeks, len(points))
    ]


def _m2_mom_shock_event_series(points):
    mom_values = []
    series = []
    for index in range(1, len(points)):
        value = _pct_change(points[index]["value"], points[index - 1]["value"])
        if value is None:
            continue
        mom_values.append(value)
        rank = _percent_rank(mom_values, value)
        percentile = round(rank * 100, 4)
        signal = 0
        signal_label = "normal"
        if percentile > 99:
            signal = 2
            signal_label = "extreme_injection"
        elif percentile >= 95:
            signal = 1
            signal_label = "strong_injection"
        elif percentile < 1:
            signal = -2
            signal_label = "extreme_contraction"
        elif percentile <= 5:
            signal = -1
            signal_label = "strong_contraction"
        series.append(
            {
                "date": points[index]["date"],
                "value": signal,
                "mom_growth": round(value * 100, 4),
                "percentile": percentile,
                "signal": signal_label,
            }
        )
    return series


def build_m2_money_supply_detail_payload(
    rows,
    core_pce_rows=None,
    fed_total_assets_rows=None,
    fed_treasury_rows=None,
    fed_mbs_rows=None,
    fomc_events=None,
):
    points = _m2_level_points(rows)
    core_pce_points = _m2_level_points(core_pce_rows or [])
    fed_total_points = _m2_level_points(fed_total_assets_rows or [])
    fed_treasury_points = _m2_level_points(fed_treasury_rows or [])
    fed_mbs_points = _m2_level_points(fed_mbs_rows or [])
    source = points[-1].get("source") if points else None
    m2_yoy_series = _m2_growth_series(points, 12)
    core_pce_yoy_by_date = _value_by_date(_core_pce_yoy_series(core_pce_points))
    fed_total_yoy_by_date = _value_by_date(
        _m2_growth_series(_monthly_last_points(fed_total_points), 12)
    )
    treasury_change_by_date = _value_by_date(
        _weekly_change_series(fed_treasury_points, 13)
    )
    mbs_change_by_date = _value_by_date(_weekly_change_series(fed_mbs_points, 13))
    composition_dates = sorted(set(treasury_change_by_date) | set(mbs_change_by_date))
    fed_composition_series = [
        {
            "date": date_key,
            "treasury_13w_change": treasury_change_by_date.get(date_key),
            "mbs_13w_change": mbs_change_by_date.get(date_key),
        }
        for date_key in composition_dates
    ]
    state_series = [
        {
            "date": point["date"],
            "m2_yoy": point["value"],
            "core_pce_yoy": core_pce_yoy_by_date.get(point["date"]),
            "fed_target": FED_INFLATION_TARGET * 100
            if point["date"] >= FED_INFLATION_TARGET_EFFECTIVE_MONTH
            else None,
        }
        for point in m2_yoy_series
    ]
    fed_total_assets_yoy_series = [
        {
            "date": point["date"],
            "fed_total_assets_yoy": fed_total_yoy_by_date.get(point["date"]),
        }
        for point in m2_yoy_series
        if fed_total_yoy_by_date.get(point["date"]) is not None
    ]
    state_chart_events = _fomc_chart_events(
        fomc_events,
        [point["date"] for point in state_series],
    )
    return {
        "detail_id": "m2_money_supply",
        "title": "M2 Money Supply",
        "source": source,
        "charts": [
            {
                "kind": "time_series",
                "title": "M2 YoY Growth vs Inflation Constraint",
                "keys": [
                    "m2_yoy",
                    "core_pce_yoy",
                    "fed_target",
                ],
                "labels": {
                    "m2_yoy": "M2 YoY Growth",
                    "core_pce_yoy": "Core PCE YoY",
                    "fed_target": "Fed Target (since 2012)",
                },
                "series": state_series,
                "events": state_chart_events,
            },
            {
                "kind": "time_series",
                "title": "Fed Total Assets YoY",
                "keys": ["fed_total_assets_yoy"],
                "labels": {
                    "fed_total_assets_yoy": "Fed Total Assets YoY",
                },
                "series": fed_total_assets_yoy_series,
            },
            {
                "kind": "time_series",
                "title": "M2 3M Change",
                "keys": ["value"],
                "labels": {"value": "3M Change"},
                "series": _m2_growth_series(points, 3),
            },
            {
                "kind": "time_series",
                "title": "Fed Balance Sheet 13W Composition",
                "keys": ["treasury_13w_change", "mbs_13w_change"],
                "labels": {
                    "treasury_13w_change": "Treasury 13W Change",
                    "mbs_13w_change": "MBS 13W Change",
                },
                "unit": "raw",
                "series": fed_composition_series,
            },
            {
                "kind": "time_series",
                "title": "M2 MoM Shock Events",
                "keys": ["value"],
                "labels": {"value": "Shock Signal"},
                "series": _m2_mom_shock_event_series(points),
                "y_domain": [-2, 2],
                "unit": "raw",
                "tooltip_extra": [
                    {"key": "mom_growth", "label": "MoM Growth", "format": "percent"},
                    {"key": "percentile", "label": "Percentile", "format": "number"},
                ],
            },
        ],
    }


def _metric_context_label_for_state(yoy_growth, yoy_percent_rank):
    if yoy_growth is None or yoy_percent_rank is None:
        return {
            "label": "missing_state",
            "meaning": "The M2 state cannot be read because YoY growth or percentile is missing.",
        }
    if yoy_percent_rank >= 0.95:
        return {
            "label": "historically_extreme_expansion",
            "meaning": "M2 growth is near the top of its own history, so liquidity is unusually abundant.",
        }
    if yoy_growth > 0:
        return {
            "label": "positive_expansion",
            "meaning": "M2 is expanding versus a year ago, so the liquidity backdrop is not contracting.",
        }
    return {
        "label": "contraction",
        "meaning": "M2 is below its year-ago level, which points to a tighter liquidity backdrop.",
    }


def _metric_context_label_for_change(three_month_change):
    if three_month_change is None:
        return {
            "label": "missing_change",
            "meaning": "The 3-month change cannot be read because there is not enough recent history.",
        }
    if three_month_change > 0:
        return {
            "label": "positive_momentum",
            "meaning": "M2 is still rising over the last 3 months, so liquidity momentum is positive.",
        }
    if three_month_change < 0:
        return {
            "label": "negative_momentum",
            "meaning": "M2 has fallen over the last 3 months, so liquidity momentum is deteriorating.",
        }
    return {
        "label": "flat_momentum",
        "meaning": "M2 is roughly flat over the last 3 months, so liquidity momentum is neutral.",
    }


def _metric_context_label_for_shock(mom_growth, mom_percent_rank):
    if mom_growth is None or mom_percent_rank is None:
        return {
            "label": "missing_shock",
            "meaning": "The monthly shock signal cannot be read because MoM growth or percentile is missing.",
        }
    if mom_percent_rank >= 0.95:
        return {
            "label": "unusual_monthly_injection",
            "meaning": "The latest monthly M2 increase is unusually large versus history, so this is an event signal.",
        }
    if mom_percent_rank <= 0.05:
        return {
            "label": "unusual_monthly_contraction",
            "meaning": "The latest monthly M2 move is unusually weak versus history, so this is a contraction event signal.",
        }
    return {
        "label": "normal_monthly_move",
        "meaning": "The latest monthly M2 move is not extreme versus history.",
    }


def _m2_metric_context(state, change, shock):
    return {
        "state": _metric_context_label_for_state(
            state.get("m2_yoy_pct_change"),
            state.get("m2_yoy_percent_rank"),
        ),
        "change": _metric_context_label_for_change(
            change.get("m2_3m_momentum"),
        ),
        "shock": _metric_context_label_for_shock(
            shock.get("m2_mom_pct_change"),
            shock.get("m2_mom_percent_rank"),
        ),
    }


def _latest_chart_point(detail_payload, chart_title):
    for chart in detail_payload.get("charts", []):
        if chart.get("title") == chart_title and chart.get("series"):
            return chart["series"][-1]
    return None


def m2_interpretation_snapshot(headline, detail_payload):
    state = headline.get("state", {})
    change = headline.get("change", {})
    shock = headline.get("shock", {})
    latest_shock_event = _latest_chart_point(detail_payload, "M2 MoM Shock Events")
    payload = {
        "scope": M2_INTERPRETATION_SCOPE,
        "prompt_version": M2_INTERPRETATION_PROMPT_VERSION,
        "as_of": headline.get("period"),
        "status": headline.get("status", "missing"),
        "metrics": {
            "state": {
                "yoy_growth": state.get("m2_yoy_pct_change"),
                "yoy_percent_rank": state.get("m2_yoy_percent_rank"),
                "level_billions_usd": state.get("m2_money_stock"),
            },
            "change": {
                "three_month_change": change.get("m2_3m_momentum"),
            },
            "shock": {
                "mom_growth": shock.get("m2_mom_pct_change"),
                "mom_percent_rank": shock.get("m2_mom_percent_rank"),
            },
        },
        "latest_shock_event": latest_shock_event or {},
        "metric_context": _m2_metric_context(state, change, shock),
        "interpretation_constraints": {
            "cause_policy": "do_not_name_causes_without_sourced_event_context",
            "signal_role": "liquidity_confirmation_not_standalone_timing",
            "number_style": "interpret_numbers_before_repeating_them",
        },
        "coverage": {
            "source": detail_payload.get("source"),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {**payload, "hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def m2_fallback_interpretation(headline):
    status = headline.get("status", "missing")
    fallbacks = {
        "expanding": {
            "text_en": "M2 liquidity state is expanding, serving as a confirmation tailwind. Run the M2 AI generator for a detailed CaiCai explanation.",
            "text_zh": "M2流动性环境处于扩张状态，可作为确认性顺风。运行M2 AI生成器获取详细的财财解读。",
        },
        "contracting": {
            "text_en": "M2 liquidity state is contracting, suggesting a cautionary liquidity environment. Run the M2 AI generator for a detailed CaiCai explanation.",
            "text_zh": "M2流动性环境处于收缩状态，提示需谨慎对待流动性环境。运行M2 AI生成器获取详细的财财解读。",
        },
        "shock": {
            "text_en": "M2 liquidity shows an abnormal monthly shock event. Run the M2 AI generator for a detailed CaiCai explanation.",
            "text_zh": "M2流动性出现异常月度冲击事件。运行M2 AI生成器获取详细的财财解读。",
        },
        "mixed": {
            "text_en": "M2 liquidity signals are mixed. Run the M2 AI generator for a detailed CaiCai explanation.",
            "text_zh": "M2流动性信号不一致。运行M2 AI生成器获取详细的财财解读。",
        },
    }
    return fallbacks.get(
        status,
        {
            "text_en": "M2 liquidity interpretation is not yet available. Run scripts/generate_m2_ai_interpretation.py to generate one.",
            "text_zh": "M2流动性解读尚未生成。运行 scripts/generate_m2_ai_interpretation.py 生成解读。",
        },
    )


def fetch_m2_money_stock_from_source():
    raise ValueError("m2 money stock source is not configured")


def fetch_jobless_claims_from_source():
    raise ValueError("jobless claims source is not configured")


def fetch_ism_manufacturing_from_source():
    raise ValueError("ism manufacturing source is not configured")


def fetch_ism_services_from_source():
    raise ValueError("ism services source is not configured")


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
