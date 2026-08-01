import math
import statistics
from datetime import date as date_type
from datetime import timedelta

from app.data_sources.lme_copper import (
    _LME_COPPER_CUTOVER_DATE,
    _LME_COPPER_SERIES_ID,
    fetch_lme_copper_cad,
)
from app.db import macro_indicators

_LME_COPPER_OVERLAP_TEST_VERSION = "lme_copper_cad_overlap_v1"
ARCHIVED_LME_SERIES_ID = "copper_lme"
_OVERLAP_DAYS = 14


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
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _correlation(x_values, y_values):
    count = len(x_values)
    if count < 2:
        return None
    mean_x = sum(x_values) / count
    mean_y = sum(y_values) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    variance_x = sum((x - mean_x) ** 2 for x in x_values)
    variance_y = sum((y - mean_y) ** 2 for y in y_values)
    if variance_x == 0 or variance_y == 0:
        return None
    return covariance / (variance_x * variance_y) ** 0.5


def audit_lme_copper_overlap(archived_rows, cad_rows):
    archived_by_date = _by_date(archived_rows)
    cad_by_date = _by_date(cad_rows)
    shared_dates = sorted(set(archived_by_date) & set(cad_by_date))
    archived_only_dates = sorted(set(archived_by_date) - set(cad_by_date))
    cad_only_dates = sorted(set(cad_by_date) - set(archived_by_date))
    shared_archived_values = [archived_by_date[day] for day in shared_dates]
    shared_cad_values = [cad_by_date[day] for day in shared_dates]
    absolute_differences = [
        abs(cad_value - archived_value)
        for archived_value, cad_value in zip(shared_archived_values, shared_cad_values)
    ]
    price_percent_differences = [
        abs(cad_value - archived_value) / archived_value
        for archived_value, cad_value in zip(shared_archived_values, shared_cad_values)
        if archived_value
    ]
    archived_returns_by_date = dict(_daily_returns(archived_rows))
    cad_returns_by_date = dict(_daily_returns(cad_rows))
    shared_return_dates = sorted(
        set(archived_returns_by_date) & set(cad_returns_by_date)
    )
    return_differences = [
        abs(cad_returns_by_date[day] - archived_returns_by_date[day])
        for day in shared_return_dates
    ]
    return {
        "overlap_test_version": _LME_COPPER_OVERLAP_TEST_VERSION,
        "archived_count": len(archived_rows),
        "cad_count": len(cad_rows),
        "shared_date_count": len(shared_dates),
        "archived_only_count": len(archived_only_dates),
        "cad_only_count": len(cad_only_dates),
        "shared_dates": shared_dates,
        "archived_only_dates": archived_only_dates,
        "cad_only_dates": cad_only_dates,
        "mean_absolute_difference": statistics.mean(absolute_differences)
        if absolute_differences
        else None,
        "max_absolute_difference": max(absolute_differences)
        if absolute_differences
        else None,
        "shared_price_percent_difference_min": min(price_percent_differences)
        if price_percent_differences
        else None,
        "shared_price_percent_difference_median": statistics.median(
            price_percent_differences
        )
        if price_percent_differences
        else None,
        "shared_price_percent_difference_p95": _percentile(
            price_percent_differences, 0.95
        ),
        "shared_price_percent_difference_max": max(price_percent_differences)
        if price_percent_differences
        else None,
        "price_correlation": _correlation(shared_archived_values, shared_cad_values),
        "return_correlation": _correlation(
            [archived_returns_by_date[day] for day in shared_return_dates],
            [cad_returns_by_date[day] for day in shared_return_dates],
        ),
        "price_parity": bool(absolute_differences)
        and all(diff == 0 for diff in absolute_differences),
    }


def _default_fetcher(start_date, end_date):
    return fetch_lme_copper_cad()


def refresh_lme_copper(con, today_date=None, fetcher=None, initial=False):
    effective_today = today_date or date_type.today().isoformat()
    stored_rows = macro_indicators.load_macro_indicator_observations(
        con, _LME_COPPER_SERIES_ID
    )
    if initial and stored_rows:
        raise ValueError("sina CAD initial migration is already recorded")
    if initial or not stored_rows:
        start_date = _LME_COPPER_CUTOVER_DATE
    else:
        latest_date = stored_rows[-1]["date"]
        start_date = max(
            _LME_COPPER_CUTOVER_DATE,
            (
                date_type.fromisoformat(latest_date) - timedelta(days=_OVERLAP_DAYS)
            ).isoformat(),
        )
    end_date = (
        date_type.fromisoformat(effective_today) + timedelta(days=1)
    ).isoformat()
    fetch = fetcher or _default_fetcher
    try:
        payload = fetch(start_date, end_date)
        observations = [
            row
            for row in payload["observations"]
            if start_date <= row["date"] < end_date
        ]
        if not observations:
            raise ValueError("sina CAD returned no valid observations")
        if not stored_rows:
            archived_rows = macro_indicators.load_macro_indicator_observations(
                con, ARCHIVED_LME_SERIES_ID
            )
            audit = audit_lme_copper_overlap(archived_rows, payload["observations"])
            macro_indicators.merge_vendor_series_overlap_audit(
                con, _LME_COPPER_SERIES_ID, audit, commit=False
            )
        macro_indicators.merge_macro_indicator_observations(
            con, payload["series"], observations, commit=False
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {
        "series": payload["series"]["series_id"],
        "observations": len(observations),
        "start_date": start_date,
        "end_date": end_date,
    }
