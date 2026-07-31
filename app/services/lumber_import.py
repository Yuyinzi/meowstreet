from datetime import UTC, date, datetime, timedelta

from app.data_sources.lumber import (
    _LUMBER_SERIES_ID,
    _LUMBER_SERIES,
    _LUMBER_START_DATE,
    fetch_lumber_series,
)
from app.db import macro_indicators

LUMBER_OVERLAP_TEST_VERSION = "lumber_overlap_v1"
ARCHIVED_LUMBER_SERIES_ID = "lumber"
_OVERLAP_WINDOW_DAYS = 13


def _by_date(rows):
    return {row["date"]: row["value"] for row in rows}


def _daily_return(values):
    if len(values) < 2:
        return []
    return [
        values[index] / values[index - 1] - 1
        for index in range(1, len(values))
        if values[index - 1]
    ]


def _return_differences(shared_dates, archived_values, yahoo_values):
    archived_returns = _daily_return(archived_values)
    yahoo_returns = _daily_return(yahoo_values)
    return [
        abs(yahoo_return - archived_return)
        for archived_return, yahoo_return in zip(archived_returns, yahoo_returns)
    ]


def audit_lumber_overlap(archived_rows, yahoo_rows):
    archived_by_date = _by_date(archived_rows)
    yahoo_by_date = _by_date(yahoo_rows)
    shared_dates = sorted(set(archived_by_date) & set(yahoo_by_date))
    if not shared_dates:
        raise ValueError("lumber overlap has no shared dates")
    archived_only_dates = sorted(set(archived_by_date) - set(yahoo_by_date))
    yahoo_only_dates = sorted(set(yahoo_by_date) - set(archived_by_date))
    for shared_date in shared_dates:
        if archived_by_date[shared_date] != yahoo_by_date[shared_date]:
            raise ValueError(f"lumber overlap prices differ on {shared_date}")
    shared_archived_values = [archived_by_date[day] for day in shared_dates]
    shared_yahoo_values = [yahoo_by_date[day] for day in shared_dates]
    price_differences = [
        yahoo_value - archived_value
        for archived_value, yahoo_value in zip(
            shared_archived_values, shared_yahoo_values
        )
    ]
    return_differences = _return_differences(
        shared_dates, shared_archived_values, shared_yahoo_values
    )
    return {
        "overlap_test_version": LUMBER_OVERLAP_TEST_VERSION,
        "archived_count": len(archived_rows),
        "yahoo_count": len(yahoo_rows),
        "shared_date_count": len(shared_dates),
        "archived_only_count": len(archived_only_dates),
        "yahoo_only_count": len(yahoo_only_dates),
        "shared_price_difference_min": min(price_differences)
        if price_differences
        else 0.0,
        "shared_price_difference_max": max(price_differences)
        if price_differences
        else 0.0,
        "shared_return_difference_min": min(return_differences)
        if return_differences
        else 0.0,
        "shared_return_difference_max": max(return_differences)
        if return_differences
        else 0.0,
        "archived_only_dates": archived_only_dates,
        "yahoo_only_dates": yahoo_only_dates,
    }


def _default_fetcher(start_date, end_date):
    return fetch_lumber_series(start_date, end_date)


def refresh_lumber(con, today_date=None, fetcher=None, initial=False):
    if fetcher is None:
        fetcher = _default_fetcher
    effective_today = today_date or date.today().isoformat()
    try:
        stored_rows = macro_indicators.load_macro_indicator_observations(
            con, _LUMBER_SERIES_ID
        )
        if initial or not stored_rows:
            start_date = _LUMBER_START_DATE
        else:
            latest_active_date = stored_rows[-1]["date"]
            start_date = (
                date.fromisoformat(latest_active_date)
                - timedelta(days=_OVERLAP_WINDOW_DAYS)
            ).isoformat()
        end_date = (date.fromisoformat(effective_today) + timedelta(days=1)).isoformat()
        payload = fetcher(start_date, end_date)
        observations = payload["observations"]
        if start_date == _LUMBER_START_DATE:
            archived_rows = macro_indicators.load_macro_indicator_observations(
                con, ARCHIVED_LUMBER_SERIES_ID
            )
            audit_lumber_overlap(archived_rows, observations)
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
