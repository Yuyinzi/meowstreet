from app.data_sources import dol_ui_claims
from app.db import economic_confirmation
from app.http_client import HttpClient


HISTORY_URL = "https://oui.doleta.gov/unemploy/claims.asp"
RELEASE_URL = "https://www.dol.gov/ui/data.pdf"
HISTORY_ARTIFACT = "economic_confirmation.dol_history"
RELEASE_ARTIFACT = "economic_confirmation.dol_release"
CLAIMS_SOURCE_CONTRACTS = {
    series_id: {
        "metric_id": metric_id,
        "source": "DOL",
        "seasonal_adjustment": "seasonally_adjusted",
        "raw_frequency": "weekly",
        "aggregation": "four_week_moving_average",
        "method_version": "claims_trend_v1",
    }
    for series_id, metric_id in (
        ("initial_claims_sa", "initial_claims_trend"),
        ("continuing_claims_sa", "continuing_claims_trend"),
    )
}


def _stage(artifacts, key, rows):
    if hasattr(artifacts, "put"):
        artifacts.put(key, rows)
    else:
        artifacts[key] = rows
    return {"artifact_key": key, "observations": len(rows)}


def fetch_history(artifacts, *, client=None, url=HISTORY_URL):
    rows = dol_ui_claims.fetch_national_claims_history(client or HttpClient(), url)
    return _stage(artifacts, HISTORY_ARTIFACT, rows)


def fetch_release(artifacts, *, client=None, url=RELEASE_URL):
    rows = dol_ui_claims.fetch_claims_release(client or HttpClient(), url)
    return _stage(artifacts, RELEASE_ARTIFACT, rows)


def _persist(db_path, artifacts, key, writer):
    rows = artifacts.get(key)
    if rows is None:
        raise ValueError(f"macro refresh artifact is missing: {key}")
    con = economic_confirmation.connect(db_path)
    try:
        count = writer(con, rows)
        for series_id, contract in CLAIMS_SOURCE_CONTRACTS.items():
            economic_confirmation.record_source_contract(con, series_id, contract)
    finally:
        con.close()
    return {"status": "ok", "artifact_key": key, "observations": count}


def persist_history(db_path, artifacts):
    return _persist(db_path, artifacts, HISTORY_ARTIFACT, economic_confirmation.replace_national_claims_history_batch)


def persist_release(db_path, artifacts):
    return _persist(db_path, artifacts, RELEASE_ARTIFACT, economic_confirmation.record_vintage_batch)
