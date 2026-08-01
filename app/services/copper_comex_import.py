import math
import statistics
from datetime import date, timedelta

from app.data_sources.copper_comex import (
    _COPPER_COMEX_SERIES_ID,
    _COPPER_COMEX_START_DATE,
    fetch_copper_comex_series,
)
from app.db import macro_indicators

COPPER_COMEX_OVERLAP_TEST_VERSION = "copper_comex_hg_overlap_v1"
ARCHIVED_COPPER_COMEX_SERIES_ID = "copper_comex"
_OVERLAP_WINDOW_DAYS = 13
_MIN_SHARED_DATES = 60
_MIN_PRICE_CORRELATION = 0.99
_MIN_RETURN_CORRELATION = 0.95
_MAX_P95_ABS_RETURN_DIFFERENCE = 0.01

_THRESHOLDS = {
    "min_shared_dates": _MIN_SHARED_DATES,
    "min_price_correlation": _MIN_PRICE_CORRELATION,
    "min_return_correlation": _MIN_RETURN_CORRELATION,
    "max_p95_absolute_return_difference": _MAX_P95_ABS_RETURN_DIFFERENCE,
}


def _by_date(rows):
    return {row["date"]: row["value"] for row in rows}


def _daily_returns(rows):
    sorted_rows = sorted(rows, key=lambda row: row["date"])
    return [
        (row["date"], row["value"] / sorted_rows[index - 1]["value"] - 1)
        for index, row in enumerate(sorted_rows)
        if index > 0 and sorted_rows[index - 1]["value"]
    ]


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _correlation(x_values, y_values):
    count = len(x_values)
    mean_x = sum(x_values) / count
    mean_y = sum(y_values) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    variance_x = sum((x - mean_x) ** 2 for x in x_values)
    variance_y = sum((y - mean_y) ** 2 for y in y_values)
    if variance_x == 0 or variance_y == 0:
        raise ValueError("copper comex overlap audit failed")
    return covariance / (variance_x * variance_y) ** 0.5


def audit_copper_comex_overlap(archived_rows, yahoo_rows):
    archived_by_date = _by_date(archived_rows)
    yahoo_by_date = _by_date(yahoo_rows)
    shared_dates = sorted(set(archived_by_date) & set(yahoo_by_date))
    if len(shared_dates) < _MIN_SHARED_DATES:
        raise ValueError("copper comex overlap audit failed")
    archived_only_dates = sorted(set(archived_by_date) - set(yahoo_by_date))
    yahoo_only_dates = sorted(set(yahoo_by_date) - set(archived_by_date))
    shared_archived_values = [archived_by_date[day] for day in shared_dates]
    shared_yahoo_values = [yahoo_by_date[day] for day in shared_dates]
    price_percent_differences = [
        abs(yahoo_value - archived_value) / archived_value
        for archived_value, yahoo_value in zip(
            shared_archived_values, shared_yahoo_values
        )
    ]
    archived_returns_by_date = dict(_daily_returns(archived_rows))
    yahoo_returns_by_date = dict(_daily_returns(yahoo_rows))
    shared_return_dates = sorted(
        set(archived_returns_by_date) & set(yahoo_returns_by_date)
    )
    return_differences = [
        abs(yahoo_returns_by_date[day] - archived_returns_by_date[day])
        for day in shared_return_dates
    ]
    price_correlation = _correlation(shared_archived_values, shared_yahoo_values)
    return_correlation = _correlation(
        [archived_returns_by_date[day] for day in shared_return_dates],
        [yahoo_returns_by_date[day] for day in shared_return_dates],
    )
    p95_return_difference = _percentile(return_differences, 0.95)
    passed = (
        price_correlation >= _MIN_PRICE_CORRELATION
        and return_correlation >= _MIN_RETURN_CORRELATION
        and p95_return_difference <= _MAX_P95_ABS_RETURN_DIFFERENCE
    )
    audit = {
        "overlap_test_version": COPPER_COMEX_OVERLAP_TEST_VERSION,
        "archived_count": len(archived_rows),
        "yahoo_count": len(yahoo_rows),
        "shared_date_count": len(shared_dates),
        "archived_only_count": len(archived_only_dates),
        "yahoo_only_count": len(yahoo_only_dates),
        "archived_only_dates": archived_only_dates,
        "yahoo_only_dates": yahoo_only_dates,
        "shared_price_percent_difference_min": min(price_percent_differences),
        "shared_price_percent_difference_median": statistics.median(
            price_percent_differences
        ),
        "shared_price_percent_difference_p95": _percentile(
            price_percent_differences, 0.95
        ),
        "shared_price_percent_difference_max": max(price_percent_differences),
        "shared_return_difference_min": min(return_differences)
        if return_differences
        else 0.0,
        "shared_return_difference_median": statistics.median(return_differences)
        if return_differences
        else 0.0,
        "shared_return_difference_p95": p95_return_difference,
        "shared_return_difference_max": max(return_differences)
        if return_differences
        else 0.0,
        "price_correlation": price_correlation,
        "return_correlation": return_correlation,
        "thresholds": _THRESHOLDS,
        "passed": passed,
    }
    if not passed:
        raise ValueError("copper comex overlap audit failed")
    return audit


def _default_fetcher(start_date, end_date):
    return fetch_copper_comex_series(start_date, end_date)


def refresh_copper_comex(con, today_date=None, fetcher=None, initial=False):
    if fetcher is None:
        fetcher = _default_fetcher
    effective_today = today_date or date.today().isoformat()
    try:
        stored_rows = macro_indicators.load_macro_indicator_observations(
            con, _COPPER_COMEX_SERIES_ID
        )
        recorded_audit = macro_indicators.load_vendor_series_overlap_audit(
            con, _COPPER_COMEX_SERIES_ID, COPPER_COMEX_OVERLAP_TEST_VERSION
        )
        if initial and (recorded_audit is not None or stored_rows):
            raise ValueError("copper comex initial migration is already recorded")
        if initial or not stored_rows:
            start_date = _COPPER_COMEX_START_DATE
        else:
            latest_active_date = stored_rows[-1]["date"]
            start_date = (
                date.fromisoformat(latest_active_date)
                - timedelta(days=_OVERLAP_WINDOW_DAYS)
            ).isoformat()
        end_date = (date.fromisoformat(effective_today) + timedelta(days=1)).isoformat()
        payload = fetcher(start_date, end_date)
        observations = payload["observations"]
        if start_date == _COPPER_COMEX_START_DATE:
            archived_rows = macro_indicators.load_macro_indicator_observations(
                con, ARCHIVED_COPPER_COMEX_SERIES_ID
            )
            audit = audit_copper_comex_overlap(archived_rows, observations)
            macro_indicators.merge_vendor_series_overlap_audit(
                con, _COPPER_COMEX_SERIES_ID, audit, commit=False
            )
        macro_indicators.merge_macro_indicator_observations(
            con, payload["series"], observations, commit=False
        )
        con.commit()
        return {
            "series": payload["series"]["series_id"],
            "observations": len(observations),
            "start_date": start_date,
            "end_date": end_date,
        }
    except Exception:
        con.rollback()
        raise
