import pytest

from app.db import economic_confirmation
from app.services import dol_claims_refresh
from app.services.macro_refresh_resources import ArtifactStore


def release_rows():
    return [{
        "series_id": sid,
        "reference_period": "2026-10-24",
        "release_date": "2026-10-29",
        "vintage_id": f"{sid}:2026-10-24:2026-10-29",
        "as_of_timestamp": "2026-11-03T00:00:00+00:00",
        "value_at_release": value,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://www.dol.gov/ui/data.pdf",
        "source_hash": "release-hash",
    } for sid, value in (("initial_claims_sa", 200000), ("continuing_claims_sa", 1700000))]


def test_release_refresh_survives_history_failure(monkeypatch, tmp_path):
    def broken_history(*args):
        raise ValueError("claims page has no national report form")

    monkeypatch.setattr(dol_claims_refresh.dol_ui_claims, "fetch_national_claims_history", broken_history)
    monkeypatch.setattr(dol_claims_refresh.dol_ui_claims, "fetch_claims_release", lambda *args: release_rows())
    artifacts = ArtifactStore()
    with pytest.raises(ValueError, match="national report form"):
        dol_claims_refresh.fetch_history(artifacts)
    dol_claims_refresh.fetch_release(artifacts)
    db_path = tmp_path / "market.sqlite"
    result = dol_claims_refresh.persist_release(db_path, artifacts)
    assert result["observations"] == 2
    con = economic_confirmation.connect(db_path)
    rows = economic_confirmation.load_current_series(con, ["initial_claims_sa", "continuing_claims_sa"])
    assert rows["initial_claims_sa"][0]["reference_period"] == "2026-10-24"
    assert rows["continuing_claims_sa"][0]["value_at_release"] == 1700000
    assert economic_confirmation.load_source_contracts(con, list(rows))["initial_claims_sa"]["method_version"] == "claims_trend_v1"
    con.close()
    assert dol_claims_refresh.persist_release(db_path, artifacts)["observations"] == 0


def test_scheduled_release_persists_after_history_task_fails(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services.macro_refresh_executor import execute_tasks
    from app.services.macro_refresh_registry import build_refresh_tasks
    from app.services.macro_refresh_runtime import build_runtime_providers

    def broken_history(*args):
        raise ValueError("claims page has no national report form")

    monkeypatch.setattr(dol_claims_refresh.dol_ui_claims, "fetch_national_claims_history", broken_history)
    monkeypatch.setattr(dol_claims_refresh.dol_ui_claims, "fetch_claims_release", lambda *args: release_rows())
    artifacts = ArtifactStore()
    providers = build_runtime_providers(artifacts)
    db_path = tmp_path / "market.sqlite"
    providers["dol_release_import"] = lambda argv: dol_claims_refresh.persist_release(db_path, artifacts) and 0
    providers = {k: v for k, v in providers.items() if k.startswith("dol_")}
    tasks = build_refresh_tasks(SimpleNamespace(), providers, openai_config={}, artifact_store=artifacts)
    result = execute_tasks(tasks)
    statuses = {row["name"]: row["status"] for row in result}
    assert statuses == {"dol_fetch": "failed", "dol_import": "blocked", "dol_release_fetch": "ok", "dol_release_import": "ok"}
    con = economic_confirmation.connect(db_path)
    rows = economic_confirmation.load_current_series(con, ["initial_claims_sa"])
    assert rows["initial_claims_sa"][0]["reference_period"] == "2026-10-24"
    con.close()
