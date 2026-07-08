import hashlib
import json
from copy import deepcopy

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


def build_growth_cycle_dashboard_payload(growth_cycle_dashboard):
    growth_cycle = growth_cycle_dashboard.get("macro", {}).get("growth_cycle", {})
    return {
        "headline": [build_m2_money_supply_headline(growth_cycle)],
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


def build_m2_money_supply_detail_payload(rows):
    points = _m2_level_points(rows)
    source = points[-1].get("source") if points else None
    return {
        "detail_id": "m2_money_supply",
        "title": "M2 Money Supply",
        "source": source,
        "charts": [
            {
                "kind": "time_series",
                "title": "M2 YoY Growth",
                "keys": ["value"],
                "labels": {"value": "YoY Growth"},
                "series": _m2_growth_series(points, 12),
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
