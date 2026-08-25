import calendar
from datetime import date as date_type
from datetime import timedelta

from app.data_sources import shfe_copper as shfe_copper_source
from app.db import macro_indicators
from app.tools import shfe_copper as shfe_copper_tools

_REBUILD_LOOKBACK_DAYS = 14


def _default_fetcher(progress_callback=None):
    return lambda start_date, end_date: shfe_copper_source.fetch_shfe_copper_contract_rows(
        start_date, end_date, progress_callback=progress_callback
    )


def _calendar_months(start_date, end_date):
    start = date_type.fromisoformat(start_date)
    end = date_type.fromisoformat(end_date)
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        last_day = calendar.monthrange(year, month)[1]
        months.append(
            (
                f"{year:04d}-{month:02d}-01",
                f"{year:04d}-{month:02d}-{last_day:02d}",
            )
        )
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


def incremental_window(con):
    raw = macro_indicators.load_shfe_cu_contract_observations(con)
    if not raw:
        start = date_type.today().isoformat()
    else:
        latest = max(row["trade_date"] for row in raw)
        start = (
            date_type.fromisoformat(latest) - timedelta(days=_REBUILD_LOOKBACK_DAYS)
        ).isoformat()
    return start, date_type.today().isoformat()


def _requested_dates(start_date, end_date):
    start = date_type.fromisoformat(start_date)
    end = date_type.fromisoformat(end_date)
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _rebuild_window_start(con, requested_start):
    main = macro_indicators.load_shfe_cu_main_observations(con)
    if not main:
        return requested_start
    latest_derived = max(row["date"] for row in main)
    lookback = (
        date_type.fromisoformat(latest_derived) - timedelta(days=_REBUILD_LOOKBACK_DAYS)
    ).isoformat()
    return min(requested_start, lookback)


def _prior_main_state(con, rebuild_start):
    prior = [
        row
        for row in macro_indicators.load_shfe_cu_main_observations(con)
        if row["date"] < rebuild_start
    ]
    if not prior:
        return None, None
    latest = prior[-1]
    return latest["selected_contract"], latest["close"]


def import_shfe_cu_dates(
    con, trade_dates, fetcher=None, dry_run=False, progress_callback=None
):
    if not trade_dates:
        raise ValueError("shfe cu trade dates are required")
    requested = sorted(set(trade_dates))
    requested_start = requested[0]
    requested_end = requested[-1]
    fetch = fetcher or _default_fetcher(progress_callback)
    fetched_rows = []
    for month_start, month_end in _calendar_months(requested_start, requested_end):
        fetched_rows.extend(fetch(month_start, month_end))
    in_range = [
        row
        for row in fetched_rows
        if requested_start <= row["trade_date"] <= requested_end
    ]
    rebuild_start = _rebuild_window_start(con, requested_start)
    initial_contract, initial_close = _prior_main_state(con, rebuild_start)
    if not dry_run:
        try:
            macro_indicators.merge_shfe_cu_contract_observations(
                con, fetched_rows, commit=False
            )
            rebuild_rows = macro_indicators.load_shfe_cu_contract_observations(
                con, start_date=rebuild_start, end_date=requested_end
            )
            main_rows = shfe_copper_tools.build_shfe_cu_main_series(
                rebuild_rows,
                initial_selected_contract=initial_contract,
                initial_close=initial_close,
            )
            macro_indicators.replace_shfe_cu_main_observations(
                con,
                main_rows,
                commit=False,
                rebuild_start_date=rebuild_start,
                rebuild_end_date=requested_end,
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
    else:
        rebuild_rows = [
            row
            for row in fetched_rows
            if rebuild_start <= row["trade_date"] <= requested_end
        ]
        main_rows = shfe_copper_tools.build_shfe_cu_main_series(
            rebuild_rows,
            initial_selected_contract=initial_contract,
            initial_close=initial_close,
        )
    published_dates = {row["trade_date"] for row in in_range}
    return {
        "raw_dates_requested": len(requested),
        "raw_dates_published": len(published_dates),
        "raw_observations": len(in_range),
        "derived_observations": len(main_rows),
        "rebuild_start_date": rebuild_start,
        "rebuild_end_date": requested_end,
    }


def refresh_shfe_cu_main(
    con, start_date=None, end_date=None, fetcher=None, dry_run=False, progress_callback=None
):
    if start_date is None or end_date is None:
        start_date, end_date = incremental_window(con)
    trade_dates = _requested_dates(start_date, end_date)
    return import_shfe_cu_dates(
        con,
        trade_dates,
        fetcher=fetcher,
        dry_run=dry_run,
        progress_callback=progress_callback,
    )
