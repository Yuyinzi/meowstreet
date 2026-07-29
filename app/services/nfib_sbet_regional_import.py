from datetime import datetime, timezone

from app.data_sources import nfib_sbet_api
from app.db import macro_indicators


SOURCE_URL = f"{nfib_sbet_api.API_BASE}/{nfib_sbet_api.API_PROCEDURE}"
ALL_REGION_IDS = set(nfib_sbet_api.REGIONS.keys())
ALL_SERIES_IDS = nfib_sbet_api.ALL_SERIES_IDS
NATIONAL_REGION_ID = "national"


def merge_nfib_regional_observations_batch(con, observations):
    return macro_indicators.merge_nfib_regional_observations_batch(con, observations)


def load_nfib_regional_observations(con, region_id, indicator_id):
    return macro_indicators.load_nfib_regional_observations(
        con, region_id, indicator_id
    )


def load_all_nfib_regional_observations(con):
    return macro_indicators.load_all_nfib_regional_observations(con)


def _api_obs_to_db_obs(api_obs, region_id, api_payload):
    db_obs_list = []
    api_obs_key = api_obs
    region_info = (
        nfib_sbet_api.REGIONS.get(region_id)
        if region_id != NATIONAL_REGION_ID
        else None
    )

    for series_id, indicator_code in nfib_sbet_api.SERIES_TO_INDICATOR.items():
        if indicator_code == "OPT_INDEX":
            value = api_obs_key.get("optimism")
        else:
            value = api_obs_key.get(indicator_code)

        db_obs = {
            "region_id": region_id,
            "indicator_id": series_id,
            "date": api_obs_key["date"],
            "value": value,
            "availability": "available" if value is not None else "suppressed",
            "title": nfib_sbet_api.OFFICIAL_INDICATORS.get(indicator_code, {}).get(
                "title", ""
            ),
            "units": nfib_sbet_api.OFFICIAL_INDICATORS.get(indicator_code, {}).get(
                "units", ""
            ),
            "frequency": "quarterly_3_month_aggregate",
            "procedure_name": nfib_sbet_api.API_PROCEDURE,
            "source_url": SOURCE_URL,
            "retrieval_time": api_payload.get("retrieval_time", ""),
            "request_params": api_payload.get("request_body"),
            "response_hash": api_payload.get("response_hash"),
        }
        if region_info:
            db_obs["api_label"] = region_info["display_label"]
            db_obs["display_label"] = region_info["display_label"]
            db_obs["states"] = region_info["states"]
        else:
            db_obs["api_label"] = "National"
            db_obs["display_label"] = "National"
            db_obs["states"] = ""
        db_obs_list.append(db_obs)
    return db_obs_list


def import_official_regional_sbet(con, start_year, end_year, fetcher=None):
    if fetcher is None:
        fetcher = nfib_sbet_api.fetch_regional_data
        national_fetcher = nfib_sbet_api.fetch_national_data
    else:
        national_fetcher = None

    all_observations = []

    for region_id in sorted(ALL_REGION_IDS):
        api_payload = fetcher(region_id, start_year, end_year)
        for api_obs in api_payload.get("observations", []):
            all_observations.extend(_api_obs_to_db_obs(api_obs, region_id, api_payload))

    if national_fetcher is not None:
        try:
            nat_payload = national_fetcher(start_year, end_year)
            for api_obs in nat_payload.get("observations", []):
                all_observations.extend(
                    _api_obs_to_db_obs(api_obs, NATIONAL_REGION_ID, nat_payload)
                )
        except ValueError:
            raise

    return merge_nfib_regional_observations_batch(con, all_observations)
