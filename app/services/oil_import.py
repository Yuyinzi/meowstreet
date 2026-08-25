from datetime import timedelta, date as date_type

from app.data_sources import oil
from app.db import macro_indicators


_PRICE_SERIES_IDS = ["oil_wti_spot", "oil_brent_spot"]


def refresh_official_oil(
    con, api_key, fetcher=oil.fetch_oil_observations, full_price_history=False
):
    if full_price_history:
        payload = fetcher(api_key, full_price_history=True)
    else:
        latest_dates = []
        for sid in _PRICE_SERIES_IDS:
            points = macro_indicators.load_macro_indicator_points(con, sid)
            if points:
                latest_dates.append(max(p["date"] for p in points))
        if len(latest_dates) == 2:
            price_start = (
                date_type.fromisoformat(min(latest_dates)) - timedelta(days=14)
            ).isoformat()
        else:
            price_start = None
        payload = fetcher(api_key, price_start_date=price_start)
    try:
        result = {"series": 0, "observations": 0}
        for item in payload.values():
            macro_indicators.merge_macro_indicator_observations(
                con, item["series"], item["observations"], commit=False
            )
            result["series"] += 1
            result["observations"] += len(item["observations"])
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise


def persist_oil_payload(con, payload):
    try:
        result = {"series": 0, "observations": 0}
        for item in payload.values():
            macro_indicators.merge_macro_indicator_observations(
                con, item["series"], item["observations"], commit=False
            )
            result["series"] += 1
            result["observations"] += len(item["observations"])
        con.commit()
        return result
    except BaseException:
        con.rollback()
        raise
