import hashlib
import json
import math
import unicodedata
from datetime import date
from datetime import timedelta
from pathlib import Path
from typing import Literal
from typing import NoReturn

from pydantic import BaseModel, ConfigDict, ValidationError

ROOT = Path(__file__).resolve().parents[2]
EXPLORATION_CATALOG_PATH = (
    ROOT / "data" / "local_system" / "market_assistant_exploration_catalog.v1.json"
)

QUERY_KINDS = (
    "indicator_current",
    "indicator_history",
    "period_comparison",
    "release_history",
)

STATISTIC_IDS = (
    "first_value",
    "last_value",
    "absolute_change",
    "percentage_change",
    "min",
    "max",
    "count",
    "adjacent_increases",
    "adjacent_decreases",
    "mean",
    "median",
    "gaps",
)

LOADERS = (
    "macro_indicator_points",
    "economic_confirmation_current",
    "benchmark_prices",
)

FREQUENCIES = ("daily", "weekly", "monthly")

GAP_POLICIES = ("missing_periods_reported", "not_applicable")


class _DateWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    start: str
    end: str


class _ExplorationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    indicator_id: str
    statistics: list[str] = []


class _IndicatorCurrentQuery(_ExplorationQuery):
    query_kind: Literal["indicator_current"]


class _IndicatorHistoryQuery(_ExplorationQuery):
    query_kind: Literal["indicator_history"]
    start: str
    end: str


class _PeriodComparisonQuery(_ExplorationQuery):
    query_kind: Literal["period_comparison"]
    period_a: _DateWindow
    period_b: _DateWindow


class _ReleaseHistoryQuery(_ExplorationQuery):
    query_kind: Literal["release_history"]
    start: str
    end: str


_QUERY_MODELS = {
    "indicator_current": _IndicatorCurrentQuery,
    "indicator_history": _IndicatorHistoryQuery,
    "period_comparison": _PeriodComparisonQuery,
    "release_history": _ReleaseHistoryQuery,
}


def load_exploration_catalog(path=EXPLORATION_CATALOG_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_exploration_catalog(payload)


def validate_exploration_catalog(payload):
    if not isinstance(payload, dict) or "version" not in payload:
        raise ValueError("exploration catalog version is required")
    indicators = payload.get("indicators")
    if not isinstance(indicators, list):
        raise ValueError("exploration catalog indicators are required")
    seen = set()
    for indicator in indicators:
        _validate_catalog_indicator(indicator, seen)
    return payload


def _validate_catalog_indicator(indicator, seen):
    if not isinstance(indicator, dict):
        raise ValueError("exploration indicator is not an object")
    indicator_id = indicator.get("indicator_id")
    if not isinstance(indicator_id, str) or not indicator_id:
        raise ValueError("exploration indicator id is required")
    if indicator_id in seen:
        raise ValueError(f"exploration indicator {indicator_id} is duplicated")
    seen.add(indicator_id)
    loader = indicator.get("loader")
    if loader not in LOADERS:
        raise ValueError(
            f"exploration indicator {indicator_id} has unknown loader: {loader}"
        )
    frequency = indicator.get("frequency")
    if frequency not in FREQUENCIES:
        raise ValueError(
            f"exploration indicator {indicator_id} has unknown frequency: {frequency}"
        )
    local_series = indicator.get("local_series")
    if not isinstance(local_series, str) or not local_series:
        raise ValueError(
            f"exploration indicator {indicator_id} local series is required"
        )
    unit = indicator.get("unit")
    if not isinstance(unit, str) or not unit:
        raise ValueError(f"exploration indicator {indicator_id} unit is required")
    query_kinds = indicator.get("query_kinds")
    if not isinstance(query_kinds, list) or not query_kinds:
        raise ValueError(
            f"exploration indicator {indicator_id} query kinds are required"
        )
    for query_kind in query_kinds:
        if query_kind not in QUERY_KINDS:
            raise ValueError(
                f"exploration indicator {indicator_id} has unknown query kind: {query_kind}"
            )
    maximum_rows = indicator.get("maximum_rows")
    if (
        not isinstance(maximum_rows, int)
        or isinstance(maximum_rows, bool)
        or maximum_rows <= 0
    ):
        raise ValueError(
            f"exploration indicator {indicator_id} maximum rows must be positive"
        )
    gap_policy = indicator.get("gap_policy")
    if gap_policy not in GAP_POLICIES:
        raise ValueError(
            f"exploration indicator {indicator_id} has unknown gap policy: {gap_policy}"
        )


def get_catalog_indicator(catalog, indicator_id):
    indicators = catalog.get("indicators") if isinstance(catalog, dict) else None
    if not isinstance(indicators, list):
        raise ValueError("exploration catalog indicators are required")
    for indicator in indicators:
        if indicator.get("indicator_id") == indicator_id:
            return indicator
    raise ValueError(f"indicator is not registered: {indicator_id}")


def validate_exploration_query(payload):
    if not isinstance(payload, dict):
        raise ValueError("exploration query is required")
    query_kind = payload.get("query_kind")
    model = _query_model(query_kind)
    try:
        validated = model.model_validate(payload)
    except ValidationError as exc:
        _raise_query_validation_error(exc)
    query = validated.model_dump()
    catalog = load_exploration_catalog()
    indicator = get_catalog_indicator(catalog, query["indicator_id"])
    if query["query_kind"] not in indicator["query_kinds"]:
        raise ValueError(
            f"query kind {query['query_kind']} is not supported for {query['indicator_id']}"
        )
    _validate_approved_statistics(query["statistics"])
    _validate_query_windows(query)
    return query


def _query_model(query_kind):
    model = _QUERY_MODELS.get(query_kind)
    if model is None:
        raise ValueError("query kind is not registered")
    return model


def _raise_query_validation_error(exc) -> NoReturn:
    errors = exc.errors()
    error_types = {error["type"] for error in errors}
    if "extra_forbidden" in error_types:
        raise ValueError("extra inputs are not permitted")
    missing = sorted(
        {str(error["loc"][0]) for error in errors if error["type"] == "missing"}
    )
    if missing:
        raise ValueError(f"exploration query is missing required field: {missing[0]}")
    raise ValueError("exploration query is invalid")


def _validate_approved_statistics(requested):
    for statistic_id in requested:
        if statistic_id not in STATISTIC_IDS:
            raise ValueError(f"statistic is not approved: {statistic_id}")


def _validate_query_windows(query):
    query_kind = query["query_kind"]
    if query_kind in ("indicator_history", "release_history"):
        _validate_date_window(query["start"], query["end"], query_kind)
    elif query_kind == "period_comparison":
        _validate_date_window(
            query["period_a"]["start"], query["period_a"]["end"], "period_a"
        )
        _validate_date_window(
            query["period_b"]["start"], query["period_b"]["end"], "period_b"
        )


def _validate_date_window(start, end, label):
    start_date = _parse_iso_date(start, label)
    end_date = _parse_iso_date(end, label)
    if start_date > end_date:
        raise ValueError(f"date window start is after end: {label}")


def _parse_iso_date(value, label):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"date is invalid: {label}") from exc


def compute_statistics(rows, requested, *, frequency=None, gap_policy="not_applicable"):
    if not isinstance(rows, list):
        raise ValueError("exploration rows are required")
    _validate_approved_statistics(requested)
    if frequency is not None and frequency not in FREQUENCIES:
        raise ValueError(f"frequency is not registered: {frequency}")
    if gap_policy not in GAP_POLICIES:
        raise ValueError(f"gap policy is not registered: {gap_policy}")
    normalized = [_normalize_row(row) for row in rows]
    values = [row["value"] for row in normalized]
    statistics = {}
    for statistic_id in requested:
        statistics[statistic_id] = _compute_statistic(
            statistic_id,
            normalized,
            values,
            frequency=frequency,
            gap_policy=gap_policy,
        )
    return statistics


def _normalize_row(row):
    if not isinstance(row, dict):
        raise ValueError("exploration row is required to be a dict")
    row_date = row.get("date")
    if not isinstance(row_date, str) or not row_date:
        raise ValueError("exploration row date is required")
    value = row.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("exploration row value is required")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("exploration row value is not finite")
    return {"date": row_date, "value": float(value)}


def _compute_statistic(statistic_id, rows, values, *, frequency, gap_policy):
    if statistic_id == "first_value":
        return values[0] if values else None
    if statistic_id == "last_value":
        return values[-1] if values else None
    if statistic_id == "absolute_change":
        if len(values) < 2:
            return None
        return values[-1] - values[0]
    if statistic_id == "percentage_change":
        if len(values) < 2:
            return None
        if values[0] == 0.0:
            return {"state": "unavailable", "reason_code": "zero_first_value"}
        return (values[-1] - values[0]) / values[0] * 100.0
    if statistic_id == "min":
        return min(values) if values else None
    if statistic_id == "max":
        return max(values) if values else None
    if statistic_id == "count":
        return len(rows)
    if statistic_id == "adjacent_increases":
        return sum(
            1 for index in range(len(values) - 1) if values[index + 1] > values[index]
        )
    if statistic_id == "adjacent_decreases":
        return sum(
            1 for index in range(len(values) - 1) if values[index + 1] < values[index]
        )
    if statistic_id == "mean":
        return sum(values) / len(values) if values else None
    if statistic_id == "median":
        return _median(values)
    if statistic_id == "gaps":
        return _missing_periods(rows, frequency=frequency, gap_policy=gap_policy)
    raise ValueError(f"statistic is not approved: {statistic_id}")


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _missing_periods(rows, *, frequency, gap_policy):
    if gap_policy == "not_applicable":
        return {"policy": gap_policy, "missing_periods": None}
    if frequency not in ("monthly", "weekly") or not rows:
        return {"policy": gap_policy, "missing_periods": None}
    row_dates = [row["date"] for row in rows]
    first = min(row_dates)
    last = max(row_dates)
    if frequency == "monthly":
        expected = _expected_monthly_periods(first, last)
        present = {row_date[:7] for row_date in row_dates}
    else:
        expected = _expected_weekly_periods(first, last)
        present = set(row_dates)
    missing = [period for period in expected if period not in present]
    return {"policy": gap_policy, "missing_periods": missing}


def _expected_monthly_periods(first, last):
    start = date.fromisoformat(first)
    end = date.fromisoformat(last)
    periods = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        periods.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return periods


def _expected_weekly_periods(first, last):
    start = date.fromisoformat(first)
    end = date.fromisoformat(last)
    periods = []
    current = start
    while current <= end:
        periods.append(current.isoformat())
        current = current + timedelta(days=7)
    return periods


def canonical_json(payload):
    if not isinstance(payload, dict):
        raise ValueError("canonical payload must be a dictionary")
    return json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonicalize(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("canonical payload contains a non-finite number")
        if isinstance(value, float) and value == 0.0:
            return 0.0
        return value
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _canonicalize(item)
            for key, item in value.items()
        }
    if value is None:
        return None
    raise ValueError("canonical payload contains an unsupported value type")


def sha256(payload):
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def compute_result_hash(result):
    if not isinstance(result, dict):
        raise ValueError("exploration result is required")
    payload = {key: value for key, value in result.items() if key != "result_hash"}
    return sha256(payload)
