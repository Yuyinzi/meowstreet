import math
from datetime import date
from datetime import datetime
from datetime import timezone


CLAIMS_CONFIRMATION_VERSION = "claims_confirmation_v1.0"

_METHOD_COVERAGE = {
    "initial_claims": "included",
    "continuing_claims": "included",
    "payrolls": "context_only",
    "unemployment_rate": "context_only",
    "average_weekly_hours": "context_only",
    "average_hourly_earnings": "context_only",
    "payroll_revisions": "context_only",
}

_INITIAL_METRIC_ID = "initial_claims_trend"
_CONTINUING_METRIC_ID = "continuing_claims_trend"
_CLAIMS_METHOD_VERSION = "claims_trend_v1"

_MIN_OBSERVATIONS = 17
_WINDOW_WEEKS = 4
_COMPARISON_OFFSET_WEEKS = 13
_IMPROVING_THRESHOLD = -0.03
_DETERIORATING_THRESHOLD = 0.03
_STALENESS_CEILING_DAYS = 30

_VALID_DIRECTIONAL_THESES = frozenset({"growth_decelerating", "growth_accelerating"})
_NON_DIRECTIONAL_THESES = frozenset({"mixed"})

_CLAIMS_DIRECTION_TABLE = {
    ("deteriorating", "deteriorating"): "deteriorating",
    ("improving", "improving"): "improving",
    ("stable", "stable"): "stable",
    ("deteriorating", "stable"): "partially_deteriorating",
    ("stable", "deteriorating"): "partially_deteriorating",
    ("improving", "stable"): "partially_improving",
    ("stable", "improving"): "partially_improving",
    ("improving", "deteriorating"): "conflicting",
    ("deteriorating", "improving"): "conflicting",
}

_THESIS_MAPPING = {
    "growth_decelerating": {
        "deteriorating": "confirming",
        "partially_deteriorating": "partial",
        "stable": "not_confirming",
        "improving": "conflicting",
        "partially_improving": "conflicting",
        "conflicting": "conflicting",
    },
    "growth_accelerating": {
        "improving": "confirming",
        "partially_improving": "partial",
        "stable": "not_confirming",
        "deteriorating": "conflicting",
        "partially_deteriorating": "conflicting",
        "conflicting": "conflicting",
    },
}

_THESIS_ADJECTIVES = {
    "growth_decelerating": "decelerating",
    "growth_accelerating": "accelerating",
}

_DIRECTION_DESCRIPTORS = {
    "deteriorating": "deteriorating",
    "improving": "improving",
    "stable": "stable",
    "partially_deteriorating": "partially deteriorating",
    "partially_improving": "partially improving",
    "conflicting": "sending conflicting signals",
}

_UNAVAILABLE_EXPLANATIONS = {
    "data_missing": "Claims confirmation is unavailable because no claims data is available.",
    "release_not_yet_available": "Claims confirmation is unavailable because the latest required claims week has not been officially released.",
    "insufficient_history": "Claims confirmation is unavailable because there is insufficient claims observation history.",
    "stale_data": "Claims confirmation is unavailable because the latest claims observation is stale.",
    "calculation_error": "Claims confirmation is unavailable because of a calculation error.",
    "macro_growth_thesis_not_directional": "Claims confirmation is unavailable because the macro growth thesis is not directional.",
    "method_not_approved": "Claims confirmation is unavailable because the method is not approved.",
}


def build_claims_confirmation(
    initial_rows, continuing_rows, macro_growth_regime, as_of_timestamp
):
    as_of = _parse_as_of_timestamp(as_of_timestamp)
    initial_trend = _trend_record(initial_rows, _INITIAL_METRIC_ID, as_of)
    continuing_trend = _trend_record(continuing_rows, _CONTINUING_METRIC_ID, as_of)
    claims_direction, direction_reason = _aggregate_direction(
        initial_trend, continuing_trend
    )
    regime = _normalize_regime(macro_growth_regime)
    status, status_reason = _confirmation_status(
        claims_direction, direction_reason, regime
    )
    supports, conflicts, explanation = _reasoning(
        claims_direction, status, regime, status_reason
    )
    return {
        "initial_claims": initial_trend,
        "continuing_claims": continuing_trend,
        "claims_direction": claims_direction,
        "confirmation_status": status,
        "unavailable_reason": status_reason if status == "unavailable" else None,
        "macro_growth_regime": macro_growth_regime,
        "supports": supports,
        "conflicts": conflicts,
        "explanation": explanation,
        "vintages": _all_vintages(initial_rows, continuing_rows),
        "method_coverage": dict(_METHOD_COVERAGE),
        "method_version": CLAIMS_CONFIRMATION_VERSION,
    }


def _parse_as_of_timestamp(value):
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of_timestamp is required to be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def _normalize_regime(macro_growth_regime):
    if macro_growth_regime is None:
        return None
    value = str(macro_growth_regime).strip()
    return value or None


def _trend_record(rows, metric_id, as_of):
    if not rows:
        return _unavailable_trend(metric_id, "data_missing", [], None)
    vintages = _vintage_refs(rows)
    parsed = _parse_for_calculation(rows)
    if parsed is None:
        return _unavailable_trend(metric_id, "calculation_error", vintages, None)
    sa_rows = [
        row for row in parsed if row["seasonal_adjustment"] == "seasonally_adjusted"
    ]
    if not sa_rows:
        return _unavailable_trend(metric_id, "data_missing", vintages, None)
    latest_period = sa_rows[-1]["reference_period"]
    if latest_period > as_of:
        return _unavailable_trend(
            metric_id, "release_not_yet_available", vintages, latest_period
        )
    if _is_stale(latest_period, as_of):
        return _unavailable_trend(metric_id, "stale_data", vintages, latest_period)
    if len(sa_rows) < _MIN_OBSERVATIONS:
        return _unavailable_trend(
            metric_id, "insufficient_history", vintages, latest_period
        )
    latest_mean, comparison_mean = _trend_means(sa_rows)
    if comparison_mean == 0:
        return _unavailable_trend(
            metric_id, "calculation_error", vintages, latest_period
        )
    change_pct = (latest_mean - comparison_mean) / comparison_mean
    return {
        **_metric_contract(metric_id),
        "classification": _classify(change_pct),
        "observation_period": latest_period.isoformat(),
        "latest_4w_mean": latest_mean,
        "comparison_4w_mean": comparison_mean,
        "change_pct": change_pct,
        "vintages": vintages,
    }


def _parse_for_calculation(rows):
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        period = _parse_reference_period(row.get("reference_period"))
        if period is None:
            return None
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        parsed.append(
            {
                "reference_period": period,
                "value": value,
                "seasonal_adjustment": row.get("seasonal_adjustment"),
            }
        )
    parsed.sort(key=lambda item: item["reference_period"])
    return parsed


def _parse_reference_period(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _is_stale(latest_period, as_of):
    return (as_of - latest_period).days > _STALENESS_CEILING_DAYS


def _trend_means(sa_rows):
    latest_window = sa_rows[-_WINDOW_WEEKS:]
    comparison_window = sa_rows[
        -(_COMPARISON_OFFSET_WEEKS + _WINDOW_WEEKS) : -_COMPARISON_OFFSET_WEEKS
    ]
    latest_mean = sum(row["value"] for row in latest_window) / _WINDOW_WEEKS
    comparison_mean = sum(row["value"] for row in comparison_window) / _WINDOW_WEEKS
    return latest_mean, comparison_mean


def _classify(change_pct):
    if change_pct <= _IMPROVING_THRESHOLD:
        return "improving"
    if change_pct >= _DETERIORATING_THRESHOLD:
        return "deteriorating"
    return "stable"


def _metric_contract(metric_id):
    return {
        "metric_id": metric_id,
        "source": "DOL",
        "seasonal_adjustment": "seasonally_adjusted",
        "raw_frequency": "weekly",
        "aggregation": "four_week_moving_average",
        "comparison": {
            "method": "percent_change",
            "baseline": "thirteen_weeks_ago",
        },
        "classification": {
            "improving": "change <= -0.03",
            "stable": "-0.03 < change < 0.03",
            "deteriorating": "change >= 0.03",
        },
        "missing_data_policy": {
            "minimum_observations": _MIN_OBSERVATIONS,
            "otherwise": "unavailable",
        },
        "method_version": _CLAIMS_METHOD_VERSION,
    }


def _unavailable_trend(metric_id, reason, vintages, observation_period):
    return {
        **_metric_contract(metric_id),
        "classification": "unavailable",
        "unavailable_reason": reason,
        "observation_period": (
            observation_period.isoformat() if observation_period is not None else None
        ),
        "latest_4w_mean": None,
        "comparison_4w_mean": None,
        "change_pct": None,
        "vintages": vintages,
    }


def _vintage_refs(rows):
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "reference_period": row.get("reference_period"),
                "value": row.get("value"),
                "vintage_id": row.get("vintage_id"),
                "source_url": row.get("source_url"),
            }
        )
    return result


def _aggregate_direction(initial_trend, continuing_trend):
    initial_class = initial_trend["classification"]
    continuing_class = continuing_trend["classification"]
    if initial_class == "unavailable":
        return "unavailable", initial_trend["unavailable_reason"]
    if continuing_class == "unavailable":
        return "unavailable", continuing_trend["unavailable_reason"]
    return _CLAIMS_DIRECTION_TABLE[(initial_class, continuing_class)], None


def _confirmation_status(claims_direction, direction_reason, regime):
    if regime in _NON_DIRECTIONAL_THESES:
        return "unavailable", "macro_growth_thesis_not_directional"
    if regime not in _VALID_DIRECTIONAL_THESES:
        return "unavailable", "calculation_error"
    if claims_direction == "unavailable":
        return "unavailable", direction_reason
    return _THESIS_MAPPING[regime][claims_direction], None


def _reasoning(claims_direction, status, regime, status_reason):
    adjective = _THESIS_ADJECTIVES.get(regime)
    descriptor = _DIRECTION_DESCRIPTORS.get(claims_direction, claims_direction)
    if status == "confirming":
        supports = f"Claims are {descriptor}, supporting the {adjective} growth thesis"
        return supports, None, supports
    if status == "partial":
        supports = (
            f"Claims are {descriptor}, partly supporting the {adjective} growth thesis"
        )
        return supports, None, supports
    if status == "conflicting":
        if claims_direction == "conflicting":
            conflicts = (
                "Initial and continuing claims are moving in opposite directions, "
                f"conflicting with the {adjective} growth thesis"
            )
        else:
            conflicts = f"Claims are {descriptor}, conflicting with the {adjective} growth thesis"
        return None, conflicts, conflicts
    if status == "not_confirming":
        explanation = (
            f"Claims are {descriptor}, neither supporting nor conflicting with "
            f"the {adjective} growth thesis"
        )
        return None, None, explanation
    explanation = _UNAVAILABLE_EXPLANATIONS.get(
        status_reason, "Claims confirmation is unavailable."
    )
    return None, None, explanation


def _all_vintages(initial_rows, continuing_rows):
    result = []
    seen = set()
    for row in [*(initial_rows or []), *(continuing_rows or [])]:
        if isinstance(row, dict):
            key = (
                row.get("series_id"),
                row.get("reference_period"),
                row.get("vintage_id"),
            )
        else:
            key = ("__raw__", repr(row))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result
