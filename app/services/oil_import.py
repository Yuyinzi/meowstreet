from app.data_sources import oil
from app.db import macro_indicators


def refresh_official_oil(con, api_key, fetcher=oil.fetch_oil_observations):
    payload = fetcher(api_key)
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
