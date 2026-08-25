from datetime import date as date_type
from datetime import timedelta

from app.data_sources.dce_iron_ore_sina import fetch_dce_iron_ore_sina
from app.db import macro_indicators

DCE_IRON_ORE_SINA_SERIES_ID = "iron_ore_dce"
DCE_IRON_ORE_SINA_START_DATE = "2013-10-18"

_OVERLAP_DAYS = 14


def _overlap_start(stored_rows):
    latest = max(row["date"] for row in stored_rows)
    return (date_type.fromisoformat(latest) - timedelta(days=_OVERLAP_DAYS)).isoformat()


def _default_fetcher(start_date, end_date):
    payload = fetch_dce_iron_ore_sina()
    observations = [
        row for row in payload["observations"] if start_date <= row["date"] < end_date
    ]
    return {"series": payload["series"], "observations": observations}


def refresh_dce_iron_ore_sina(con, today_date=None, fetcher=None, initial=False):
    effective_today = today_date or date_type.today().isoformat()
    stored_rows = macro_indicators.load_macro_indicator_observations(
        con, DCE_IRON_ORE_SINA_SERIES_ID
    )
    if initial or not stored_rows:
        start_date = DCE_IRON_ORE_SINA_START_DATE
    else:
        start_date = _overlap_start(stored_rows)
    end_date = (
        date_type.fromisoformat(effective_today) + timedelta(days=1)
    ).isoformat()
    fetch = fetcher or _default_fetcher
    try:
        payload = fetch(start_date, end_date)
        observations = payload["observations"]
        if not observations:
            raise ValueError("sina I0 returned no valid observations")
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


def persist_dce_payload(con, payload):
    try:
        macro_indicators.merge_macro_indicator_observations(
            con, payload["series"], payload["observations"], commit=False
        )
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return {
        "series": payload["series"]["series_id"],
        "observations": len(payload["observations"]),
    }
