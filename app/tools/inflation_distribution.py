from datetime import date
from math import isfinite

from app.tools import price_distribution

METHOD_VERSION = "inflation_price_distribution_v1"
DISTRIBUTION_WINDOW = "2016-01-01_to_latest_available"
DISTRIBUTION_START_DATE = "2016-01-01"
MINIMUM_MONTHLY_RETURNS = 36
RETURN_DEFINITION = "arithmetic_month_over_month"

_NO_OBSERVATIONS_REASON = "no monthly observations are available"
_INVALID_LATEST_VALUE_REASON = "the latest monthly observation has no valid value"
_MISSING_PRIOR_MONTH_REASON = (
    "the latest monthly observation has no adjacent prior month"
)


def _month_index(value):
    parsed = date.fromisoformat(value)
    return parsed.year * 12 + parsed.month


def _observations_as_of(observations, as_of_date, start_date):
    eligible = [
        row
        for row in observations
        if row.get("date")
        and row["date"] >= start_date
        and (as_of_date is None or row["date"] <= as_of_date)
    ]
    by_date = {}
    for row in sorted(eligible, key=lambda row: row["date"]):
        by_date[row["date"]] = row
    return [by_date[key] for key in sorted(by_date)]


def _is_valid_value(value):
    return isinstance(value, (int, float)) and isfinite(value)


def _valid_monthly_rows(rows):
    by_date = {}
    for row in rows:
        if _is_valid_value(row.get("value")):
            by_date[row["date"]] = row
    return [by_date[key] for key in sorted(by_date)]


def valid_monthly_observations(observations, as_of_date=None):
    rows = _observations_as_of(observations, as_of_date, DISTRIBUTION_START_DATE)
    return _valid_monthly_rows(rows)


def _row_at_month_offset(rows, month_index, offset):
    target = month_index - offset
    for row in reversed(rows):
        if _month_index(row["date"]) == target:
            return row
    return None


def monthly_level_context(observations, as_of_date=None):
    rows = valid_monthly_observations(observations, as_of_date)
    if not rows:
        return None
    latest = rows[-1]
    latest_index = _month_index(latest["date"])
    mom_prior = _row_at_month_offset(rows, latest_index, 1)
    yoy_prior = _row_at_month_offset(rows, latest_index, 12)
    return {
        "latest_date": latest["date"],
        "latest_value": latest["value"],
        "mom_pct": _level_change(latest["value"], mom_prior),
        "yoy_pct": _level_change(latest["value"], yoy_prior),
    }


def _level_change(current, prior_row):
    if prior_row is None:
        return None
    prior = prior_row["value"]
    if prior == 0:
        return None
    return (current / prior) - 1


def _unavailable_result(minimum_samples, sample_count, reason):
    return {
        "method_version": METHOD_VERSION,
        "return_definition": RETURN_DEFINITION,
        "distribution_window": DISTRIBUTION_WINDOW,
        "standard_deviation": "sample",
        "frequency": "monthly",
        "week_definition": None,
        "minimum_samples": minimum_samples,
        "sample_count": sample_count,
        "sample_mean": None,
        "sample_standard_deviation": None,
        "current_return": None,
        "sample_start_date": None,
        "sample_end_date": None,
        "classification": "unavailable",
        "reason": reason,
    }


def _monthly_mom_returns(rows):
    sorted_rows = _valid_monthly_rows(rows)
    result = []
    for prior, current in zip(sorted_rows, sorted_rows[1:]):
        if _month_index(current["date"]) != _month_index(prior["date"]) + 1:
            continue
        change = _arithmetic_return(current["value"], prior["value"])
        if change is not None:
            result.append({"date": current["date"], "value": change})
    return result


def _arithmetic_return(current, prior):
    if prior == 0:
        return None
    return round((current / prior) - 1, 12)


def build_distribution(observations, as_of_date=None, minimum_samples=None):
    min_samples = (
        minimum_samples if minimum_samples is not None else MINIMUM_MONTHLY_RETURNS
    )
    rows = _observations_as_of(observations, as_of_date, DISTRIBUTION_START_DATE)
    if not rows:
        return _unavailable_result(min_samples, 0, _NO_OBSERVATIONS_REASON)
    latest = rows[-1]
    if not _is_valid_value(latest.get("value")):
        return _unavailable_result(min_samples, 0, _INVALID_LATEST_VALUE_REASON)
    returns = _monthly_mom_returns(rows)
    if not returns or returns[-1]["date"] != latest["date"]:
        return _unavailable_result(
            min_samples, len(returns), _MISSING_PRIOR_MONTH_REASON
        )
    return price_distribution.build_distribution_from_returns(
        returns,
        "monthly",
        method_version=METHOD_VERSION,
        distribution_window=DISTRIBUTION_WINDOW,
        return_definition=RETURN_DEFINITION,
        minimum_samples=min_samples,
    )
