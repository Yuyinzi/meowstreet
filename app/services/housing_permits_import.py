from pathlib import Path

from app.data_sources import census_nrc
from app.db import macro_indicators


def fetch_official_workbook(cache_path):
    destination = census_nrc.fetch_permits_workbook(cache_path)
    return destination


def import_cached_official_workbook(con, cache_path, release_date=None):
    payload = census_nrc.parse_permits_workbook(cache_path, release_date=release_date)
    observations = payload["observations"]
    if not observations:
        return 0
    macro_indicators.merge_macro_indicator_observations(
        con, payload["series"], observations
    )
    return len(observations)


def refresh_official_history(con, cache_path, release_date=None):
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fetch_official_workbook(cache_path)
    return import_cached_official_workbook(con, cache_path, release_date=release_date)
