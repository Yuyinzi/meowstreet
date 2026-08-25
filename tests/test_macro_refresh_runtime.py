from types import SimpleNamespace

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
