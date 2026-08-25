from types import SimpleNamespace

import pytest

from app.services import macro_refresh_runtime
from app.services.macro_refresh_registry import build_refresh_tasks
from app.services.macro_refresh_resources import ArtifactStore


def test_runtime_oil_fetch_uses_configured_eia_key(monkeypatch):
    artifacts = ArtifactStore()
    calls = []

    monkeypatch.setattr(macro_refresh_runtime.llm, "load_env", lambda: None)
    monkeypatch.setenv("EIA_KEY", "configured-eia-key")
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_commodities,
        "fetch_oil",
        lambda store, key: calls.append(key) or store.put("commodities.oil", {}),
    )

    providers = macro_refresh_runtime.build_runtime_providers(artifacts)

    assert providers["oil_fetch"]([]) == 0
    assert calls == ["configured-eia-key"]


def test_runtime_ism_enrichment_builds_client_and_stages_result(monkeypatch):
    artifacts = ArtifactStore()
    artifacts.put(
        "ism.manufacturing",
        [{"status": "ok", "snapshot": {"report_id": "mfg-1"}}],
    )
    client = object()
    calls = []

    monkeypatch.setattr(
        macro_refresh_runtime,
        "_build_ism_client",
        lambda config: client,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_ism,
        "prepare_ism_enrichment",
        lambda snapshot, **kwargs: calls.append((snapshot, kwargs)) or {"status": "ok"},
    )

    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    assert providers["ism_manufacturing_enrichment"]([]) == 0
    assert artifacts.get("ism.manufacturing.enrichment") == {"status": "ok"}
    assert calls == [
        (
            {"report_id": "mfg-1"},
            {"client": client, "model": "test-model", "survey_type": "manufacturing"},
        )
    ]


def test_runtime_fomc_enrichment_builds_client_and_stages_rows(monkeypatch):
    artifacts = ArtifactStore()
    client = object()
    calls = []

    class Connection:
        def close(self):
            return None

    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client",
        lambda config, **kwargs: client,
    )
    monkeypatch.setattr(macro_refresh_runtime.us_rates_liquidity, "connect", Connection)
    monkeypatch.setattr(
        macro_refresh_runtime.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [{"event_id": "meeting-1"}],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "prepare_fomc_policy_tone",
        lambda db_path, event_id, prepared_client, extractor_model, reviewer_model: calls.append(
            (event_id, prepared_client, extractor_model, reviewer_model)
        )
        or {"status": "ok", "event_id": event_id},
    )

    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    assert providers["fomc_policy_tone_extract"]([]) == 0
    assert artifacts.get("fomc.policy_tone") == [
        {"status": "ok", "event_id": "meeting-1"}
    ]
    assert calls == [("meeting-1", client, "test-model", "test-model")]


def test_legacy_combined_provider_runs_only_in_persist_stage():
    artifacts = ArtifactStore()
    calls = []
    providers = macro_refresh_runtime._one_shot_pair(
        lambda argv: calls.append(list(argv)) or 0,
        ["--combined"],
        [],
        "legacy.combined",
        artifacts,
        fetch_key="combined_fetch",
        import_key="combined_import",
    )

    assert providers["combined_fetch"]([]) == 0
    assert calls == []
    assert providers["combined_import"]([]) == 0
    assert calls == [["--combined"]]


def test_legacy_combined_registry_node_has_writer_gated_persist_stage():
    artifacts = ArtifactStore()
    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        values={"oil_main": lambda argv: 0},
    )
    args = SimpleNamespace(
        skip_yahoo=True,
        skip_rates=True,
        skip_consumer_sentiment=True,
        skip_m2=True,
        skip_macro_indicators=True,
        skip_building_permits=True,
        skip_ism=True,
        skip_gdp=True,
        skip_fomc=True,
        skip_nfib_sbo=True,
        skip_nfib_sbo_regional=True,
        skip_tracked_commodities=True,
        skip_cyclical_commodities=True,
        skip_oil=False,
        skip_lumber=True,
        skip_shfe_copper=True,
        skip_dce_iron_ore_sina=True,
        skip_economic_confirmation=True,
    )

    tasks = build_refresh_tasks(
        args,
        providers,
        openai_config={"api_key": None},
        artifact_store=artifacts,
    )
    selected = {task["name"]: task for task in tasks}

    assert selected["oil_fetch"]["stage"] == "fetch"
    assert selected["oil_import"]["stage"] == "persist"
    assert selected["oil_import"]["resources"] == ["sqlite_writer"]


def test_runtime_provider_registry_exposes_callable_adapters_for_every_node():
    artifacts = ArtifactStore()
    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "test-model"},
    )
    args = SimpleNamespace(
        skip_yahoo=False,
        skip_rates=False,
        skip_consumer_sentiment=False,
        skip_m2=False,
        skip_macro_indicators=False,
        skip_building_permits=False,
        skip_ism=False,
        skip_gdp=False,
        skip_fomc=False,
        skip_nfib_sbo=False,
        skip_nfib_sbo_regional=False,
        skip_tracked_commodities=False,
        skip_cyclical_commodities=False,
        skip_oil=False,
        skip_lumber=False,
        skip_shfe_copper=False,
        skip_dce_iron_ore_sina=False,
        skip_economic_confirmation=False,
    )

    tasks = build_refresh_tasks(
        args,
        providers,
        openai_config={"api_key": "configured", "model": "test-model"},
        artifact_store=artifacts,
    )

    assert tasks
    assert all(callable(task["func"]) and isinstance(task["argv"], list) for task in tasks)


def test_runtime_ism_persist_fails_for_failed_report_row(monkeypatch):
    artifacts = ArtifactStore()
    artifacts.put("ism.manufacturing", [{"status": "failed"}])
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_ism,
        "persist_ism_reports",
        lambda db_path, prepared: [
            {
                "status": "failed",
                "report_id": "mfg-2026-08",
                "report_month": "2026-08",
                "error": "report identity mismatch",
            }
        ],
    )
    providers = macro_refresh_runtime.build_runtime_providers(artifacts)

    with pytest.raises(
        ValueError,
        match="ism manufacturing mfg-2026-08 2026-08: report identity mismatch",
    ):
        providers["ism_manufacturing_import"]([])


@pytest.mark.parametrize(
    ("provider_name", "prepare_name", "artifact_key", "error"),
    [
        (
            "fomc_policy_tone_extract",
            "prepare_fomc_policy_tone",
            "fomc.policy_tone",
            "FOMC statement document is unavailable",
        ),
        (
            "fomc_minutes_extract",
            "prepare_fomc_minutes_structure",
            "fomc.minutes",
            "approved FOMC policy tone is unavailable",
        ),
    ],
)
def test_runtime_fomc_prepare_fails_with_event_identity(
    monkeypatch, provider_name, prepare_name, artifact_key, error
):
    artifacts = ArtifactStore()

    class Connection:
        def close(self):
            return None

    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client",
        lambda config, **kwargs: object(),
    )
    monkeypatch.setattr(macro_refresh_runtime.us_rates_liquidity, "connect", Connection)
    monkeypatch.setattr(
        macro_refresh_runtime.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [{"event_id": "meeting-1"}],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        prepare_name,
        lambda *args: {"status": "failed", "event_id": "meeting-1", "error": error},
    )
    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    with pytest.raises(ValueError, match=f"fomc meeting-1: {error}"):
        providers[provider_name]([])

    assert artifacts.get(artifact_key) == [
        {"status": "failed", "event_id": "meeting-1", "error": error}
    ]


def test_runtime_fomc_persist_fails_for_failed_staged_result(monkeypatch):
    artifacts = ArtifactStore()
    artifacts.put(
        "fomc.policy_tone",
        [
            {
                "status": "failed",
                "event_id": "meeting-1",
                "error": "FOMC statement document is unavailable",
            }
        ],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "persist_fomc_policy_tone",
        lambda db_path, prepared: prepared,
    )
    providers = macro_refresh_runtime.build_runtime_providers(artifacts)

    with pytest.raises(
        ValueError,
        match="fomc meeting-1: FOMC statement document is unavailable",
    ):
        providers["fomc_policy_tone_import"]([])


def test_runtime_staged_skipped_result_is_success(monkeypatch):
    artifacts = ArtifactStore()
    artifacts.put(
        "fomc.policy_tone",
        [{"status": "skipped", "event_id": "meeting-1", "error": "already current"}],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "persist_fomc_policy_tone",
        lambda db_path, prepared: prepared,
    )
    providers = macro_refresh_runtime.build_runtime_providers(artifacts)

    assert providers["fomc_policy_tone_import"]([]) == 0
