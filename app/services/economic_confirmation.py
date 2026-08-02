from app.db import economic_confirmation
from app.tools import claims_confirmation

ECONOMIC_CONFIRMATION_VERSION = "economic_confirmation_v1.0"

_CLAIMS_SERIES_IDS = ["initial_claims_sa", "continuing_claims_sa"]
_ESR_SERIES_IDS = [
    "nonfarm_payrolls",
    "payrolls_3m_average",
    "unemployment_rate",
    "average_weekly_hours",
    "average_hourly_earnings",
]
_REAL_ACTIVITY_SERIES_IDS = [
    "manufacturing_production",
    "total_industrial_production",
    "capacity_utilization",
]
_ALL_SERIES_IDS = [
    *_CLAIMS_SERIES_IDS,
    *_ESR_SERIES_IDS,
    *_REAL_ACTIVITY_SERIES_IDS,
]

_EMPLOYMENT_SITUATION_EVENT_ID = "bls_employment_situation"
_EMPLOYMENT_SITUATION_VOLATILITY_WARNING = (
    "Employment Situation releases can move markets sharply"
)

_DECELERATING_DIRECTIONS = frozenset({"slowing", "falling"})
_ACCELERATING_DIRECTIONS = frozenset({"rising", "improving"})
_NON_DIRECTIONAL_DIRECTIONS = frozenset({"stable", "mixed"})
_THESIS_VALUES = frozenset({"growth_decelerating", "growth_accelerating", "mixed"})


def load_overview(con, macro_growth_context, as_of_timestamp):
    thesis = _translate_thesis(_expected_gdp_direction(macro_growth_context))
    series = economic_confirmation.load_current_series(con, _ALL_SERIES_IDS)
    claims = claims_confirmation.build_claims_confirmation(
        series["initial_claims_sa"],
        series["continuing_claims_sa"],
        thesis,
        as_of_timestamp,
    )
    return _compose(
        claims,
        series,
        economic_confirmation.load_scheduled_events(con),
        macro_growth_context,
        as_of_timestamp,
        "latest_official_vintage",
    )


def load_detail(con, macro_growth_context, as_of_timestamp):
    thesis = _translate_thesis(_expected_gdp_direction(macro_growth_context))
    series = economic_confirmation.load_series_as_of(
        con, _ALL_SERIES_IDS, as_of_timestamp
    )
    claims = claims_confirmation.build_claims_confirmation(
        series["initial_claims_sa"],
        series["continuing_claims_sa"],
        thesis,
        as_of_timestamp,
    )
    return _compose(
        claims,
        series,
        economic_confirmation.load_scheduled_events(con),
        macro_growth_context,
        as_of_timestamp,
        "point_in_time",
    )


def _compose(
    claims,
    series,
    events,
    macro_growth_context,
    as_of_timestamp,
    vintage_policy,
):
    return {
        "as_of": as_of_timestamp,
        "method_version": ECONOMIC_CONFIRMATION_VERSION,
        "vintage_policy": vintage_policy,
        "claims_confirmation": claims,
        "labor_context": _labor_context(series),
        "real_activity": _real_activity(series),
        "event_risk": _event_risk(events),
        "economic_confirmation": _economic_confirmation(),
        "macro_growth_context": macro_growth_context,
    }


def _expected_gdp_direction(macro_growth_context):
    if not isinstance(macro_growth_context, dict):
        return None
    return macro_growth_context.get("expected_gdp_direction")


def _translate_thesis(expected_gdp_direction):
    if expected_gdp_direction is None:
        return "mixed"
    value = str(expected_gdp_direction).strip()
    if not value:
        return "mixed"
    if value in _THESIS_VALUES:
        return value
    if value in _DECELERATING_DIRECTIONS:
        return "growth_decelerating"
    if value in _ACCELERATING_DIRECTIONS:
        return "growth_accelerating"
    if value in _NON_DIRECTIONAL_DIRECTIONS:
        return "mixed"
    return value


def _labor_context(series):
    metrics = {}
    for series_id in _ESR_SERIES_IDS:
        rows = series.get(series_id) or []
        if not rows:
            continue
        metrics[series_id] = _metric_snapshot(rows[-1])
    return {
        "role": "context_only",
        "method_status": "pending_approval",
        "confirmation_status": "unavailable",
        "unavailable_reason": "method_not_approved",
        "data_status": "available" if metrics else "missing",
        "metrics": metrics,
        "wage_pressure_context": metrics.get("average_hourly_earnings"),
        "payroll_revisions": _payroll_revisions(series),
    }


def _payroll_revisions(series):
    rows = series.get("nonfarm_payrolls") or []
    return [_metric_snapshot(row) for row in rows if row.get("revision_number", 0) > 0]


def _metric_snapshot(row):
    return {
        "series_id": row["series_id"],
        "reference_period": row["reference_period"],
        "value": row["value"],
        "value_at_release": row["value_at_release"],
        "latest_revised_value": row["latest_revised_value"],
        "revision_number": row["revision_number"],
        "release_date": row["release_date"],
        "source_url": row["source_url"],
    }


def _real_activity(series):
    available = any(rows for rows in series.values() if rows)
    return {
        "data_status": "available" if available else "missing",
        "method_status": "pending_approval",
        "confirmation_status": "unavailable",
        "unavailable_reason": "method_not_approved",
    }


def _event_risk(events):
    next_event = next(
        (
            event
            for event in events
            if event.get("event_id") == _EMPLOYMENT_SITUATION_EVENT_ID
        ),
        None,
    )
    return {
        "direction": "unknown",
        "high_volatility_warning": _EMPLOYMENT_SITUATION_VOLATILITY_WARNING,
        "next_event": next_event,
        "data_status": "available" if next_event else "missing",
    }


def _economic_confirmation():
    return {
        "status": "limited_coverage",
        "based_on": [claims_confirmation.CLAIMS_CONFIRMATION_VERSION],
        "excluded_modules": [
            {"module": "esr_labor_context", "reason": "method_not_approved"},
            {"module": "real_activity", "reason": "method_not_approved"},
        ],
        "coverage": "claims_only",
        "approved_directional_modules": 1,
        "context_only_modules": 2,
    }
