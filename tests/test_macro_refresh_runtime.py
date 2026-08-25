from types import SimpleNamespace

import pytest

from app.db import market_data
from app.services import macro_refresh_runtime
from app.services.macro_refresh_executor import execute_tasks
from app.services.macro_refresh_registry import build_refresh_tasks
from app.services.macro_refresh_resources import ArtifactStore, SQLiteWriterGate


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


def test_runtime_yahoo_fetch_stages_rows_and_defers_saves_to_writer_gated_import(
    monkeypatch,
):
    artifacts = ArtifactStore()
    requests = []
    writer_states = []

    class Connection:
        def close(self):
            return None

    class TrackingLock:
        def __init__(self):
            self.acquired = False

        def acquire(self, timeout):
            self.acquired = True
            return True

        def release(self):
            self.acquired = False

    chart = {
        "chart": {
            "result": [
                {
                    "timestamp": [1786752000],
                    "indicators": {
                        "adjclose": [{"adjclose": [10.5]}],
                        "quote": [
                            {
                                "open": [10.0],
                                "high": [11.0],
                                "low": [9.0],
                                "close": [10.5],
                                "volume": [1],
                            }
                        ],
                    },
                }
            ]
        }
    }
    lock = TrackingLock()
    monkeypatch.setattr(
        macro_refresh_runtime.benchmark_market_data,
        "connect_read_only",
        lambda *_args: Connection(),
    )
    monkeypatch.setattr(
        macro_refresh_runtime.benchmark_market_data,
        "latest_price_date",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.market_data,
        "connect_read_only",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.market_data_tool,
        "fetch_market_data",
        lambda *_args, **_kwargs: pytest.fail("fetch stage must not save market rows"),
    )
    monkeypatch.setattr(
        macro_refresh_runtime.market_data_tool,
        "fetch_yahoo_chart_json_for_dates",
        lambda symbol, **_kwargs: requests.append(symbol) or chart,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_yahoo,
        "persist_benchmarks",
        lambda *_args, **_kwargs: writer_states.append(lock.acquired) or [],
    )
    providers = {
        key: value
        for key, value in macro_refresh_runtime.build_runtime_providers(
            artifacts
        ).items()
        if key in {"benchmarks_fetch", "benchmarks_import"}
    }
    args = SimpleNamespace(
        skip_yahoo=False,
        skip_lumber=True,
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
        skip_oil=True,
        skip_shfe_copper=True,
        skip_dce_iron_ore_sina=True,
        skip_economic_confirmation=True,
    )

    results = execute_tasks(
        build_refresh_tasks(
            args,
            providers,
            openai_config={"api_key": None},
            artifact_store=artifacts,
        ),
        writer_gate=SQLiteWriterGate(lock=lock),
    )

    assert [result["status"] for result in results] == ["ok", "ok"]
    assert requests == ["^GSPC", "^NDX", "^IXIC", "^DJI"]
    assert writer_states == [True]


def test_runtime_yahoo_reuses_fresh_market_cache_and_stages_only_stale_symbol(
    monkeypatch, tmp_path
):
    artifacts = ArtifactStore()
    market_db_path = tmp_path / "market.sqlite"
    benchmark_db_path = tmp_path / "benchmark.sqlite"
    cached_dates = {
        "^GSPC": "2026-08-25",
        "^NDX": "2026-08-22",
        "^IXIC": "2026-08-25",
        "^DJI": "2026-08-25",
    }
    market_con = market_data.connect(market_db_path)
    try:
        for symbol, date_value in cached_dates.items():
            market_data.save_price_rows(
                market_con,
                symbol,
                "1d",
                [
                    {
                        "date": date_value,
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.0,
                        "close": 10.5,
                        "adjusted_close": 10.5,
                        "volume": 1,
                    }
                ],
            )
    finally:
        market_con.close()
    requests = []
    writer_states = []

    class TrackingLock:
        def __init__(self):
            self.acquired = False

        def acquire(self, timeout):
            self.acquired = True
            return True

        def release(self):
            self.acquired = False

    chart = {
        "chart": {
            "result": [
                {
                    "timestamp": [1787616000],
                    "indicators": {
                        "adjclose": [{"adjclose": [11.5]}],
                        "quote": [
                            {
                                "open": [11.0],
                                "high": [12.0],
                                "low": [10.0],
                                "close": [11.5],
                                "volume": [2],
                            }
                        ],
                    },
                }
            ]
        }
    }
    lock = TrackingLock()
    original_save = market_data.save_price_rows
    monkeypatch.setattr(
        macro_refresh_runtime.market_data,
        "DEFAULT_DB_PATH",
        market_db_path,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.benchmark_market_data,
        "DEFAULT_DB_PATH",
        benchmark_db_path,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.market_data_tool,
        "_today_iso",
        lambda: "2026-08-25",
    )
    monkeypatch.setattr(
        macro_refresh_runtime.market_data_tool,
        "fetch_yahoo_chart_json_for_dates",
        lambda symbol, **_kwargs: requests.append(symbol) or chart,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.market_data,
        "save_price_rows",
        lambda *args, **kwargs: writer_states.append(lock.acquired)
        or original_save(*args, **kwargs),
    )
    providers = {
        name: provider
        for name, provider in macro_refresh_runtime.build_runtime_providers(
            artifacts
        ).items()
        if name in {"benchmarks_fetch", "benchmarks_import"}
    }
    args = SimpleNamespace(
        skip_yahoo=False,
        skip_lumber=True,
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
        skip_oil=True,
        skip_shfe_copper=True,
        skip_dce_iron_ore_sina=True,
        skip_economic_confirmation=True,
    )

    results = execute_tasks(
        build_refresh_tasks(
            args,
            providers,
            openai_config={"api_key": None},
            artifact_store=artifacts,
        ),
        writer_gate=SQLiteWriterGate(lock=lock),
    )

    assert [result["status"] for result in results] == ["ok", "ok"]
    assert requests == ["^NDX"]
    assert writer_states == [True]
    market_con = market_data.connect(market_db_path)
    try:
        assert market_data.latest_price_date(market_con, "^NDX", "1d") == "2026-08-25"
    finally:
        market_con.close()


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
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_ism,
        "load_ism_enrichment_checkpoints",
        lambda *_args: [],
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
            {
                "client": client,
                "model": "test-model",
                "survey_type": "manufacturing",
                "checkpoints": [],
            },
        )
    ]


def test_runtime_fomc_enrichment_builds_client_and_stages_rows(monkeypatch):
    artifacts = ArtifactStore()
    client = object()
    calls = []

    monkeypatch.setattr(
        macro_refresh_runtime,
        "_pending_fomc_enrichment_events",
        lambda _key: [{"event_id": "meeting-1"}],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {
            "client": client,
            "models": {"extractor_model": "test-model", "reviewer_model": "test-model"},
        },
    )

    async def prepare_batch(_db_path, event_ids, prepared_client, extractor_model, reviewer_model):
        return [
            calls.append((event_id, prepared_client, extractor_model, reviewer_model))
            or {"status": "ok", "event_id": event_id}
            for event_id in event_ids
        ]

    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "prepare_fomc_policy_tone_batch",
        prepare_batch,
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


def test_runtime_fomc_stages_only_latest_missing_documents_and_pending_hashes(
    monkeypatch,
):
    from scripts import fetch_fomc_documents
    from scripts import generate_fomc_policy_tone

    artifacts = ArtifactStore()
    history = {"event_id": "history", "start_date": "2026-01-01"}
    approved = {"event_id": "approved", "start_date": "2026-06-01"}
    new = {"event_id": "new", "start_date": "2026-08-01"}
    future = {"event_id": "future", "start_date": "2026-12-01"}
    events = [history, approved, new, future]
    network_events = []
    model_events = []
    bundles = []
    classified_events = []

    class Connection:
        def close(self):
            return None

    monkeypatch.setattr(macro_refresh_runtime.us_rates_liquidity, "connect", Connection)
    monkeypatch.setattr(
        macro_refresh_runtime.us_rates_liquidity,
        "load_macro_events",
        lambda *_args: events,
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "_document_events_to_fetch",
        lambda _con, _document_type, _today, _backfill: [new],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "fetch_fomc_documents",
        lambda store, selected, document_type: network_events.extend(
            (document_type, event["event_id"]) for event in selected
        )
        or store.put(f"fomc.documents.{document_type}", [])
        or {"failures": []},
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "classify_events",
        lambda _con, selected, _force: classified_events.append(
            [event["event_id"] for event in selected]
        )
        or {
            "pending": [(new, {"source_hash": "new-hash"})],
            "reused": [(approved, {"source_hash": "approved-hash"})],
            "unavailable": [(history, {"reason": "no document"}), (future, {"reason": "future"})],
        },
    )
    client = object()
    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: bundles.append(kwargs["model_specs"]) or {
            "client": client,
            "models": {"extractor_model": "extractor", "reviewer_model": "reviewer"},
        },
    )
    async def prepare_batch(_db_path, event_ids, prepared_client, *_models):
        return [
            model_events.append((event_id, prepared_client))
            or {"status": "ok", "event_id": event_id}
            for event_id in event_ids
        ]

    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "prepare_fomc_policy_tone_batch",
        prepare_batch,
    )

    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "fallback-model"},
    )

    assert providers["fomc_documents_fetch"]([]) == 0
    assert providers["fomc_policy_tone_extract"]([]) == 0
    assert network_events == [
        ("statement", "new"),
        ("minutes", "new"),
    ]
    assert model_events == [("new", client)]
    assert len(bundles) == 1
    assert classified_events == [["history", "approved", "new"]]


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
    ("provider_name", "import_name", "batch_name", "persist_name", "artifact_key", "error"),
    [
        (
            "fomc_policy_tone_extract",
            "fomc_policy_tone_import",
            "prepare_fomc_policy_tone_batch",
            "persist_fomc_policy_tone",
            "fomc.policy_tone",
            "FOMC statement document is unavailable",
        ),
        (
            "fomc_minutes_extract",
            "fomc_minutes_import",
            "prepare_fomc_minutes_structure_batch",
            "persist_fomc_minutes_structure",
            "fomc.minutes",
            "approved FOMC policy tone is unavailable",
        ),
    ],
)
def test_runtime_fomc_prepare_fails_with_event_identity(
    monkeypatch,
    provider_name,
    import_name,
    batch_name,
    persist_name,
    artifact_key,
    error,
):
    artifacts = ArtifactStore()
    monkeypatch.setattr(
        macro_refresh_runtime,
        "_pending_fomc_enrichment_events",
        lambda _key: [{"event_id": "meeting-1"}],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {
            "client": object(),
            "models": {"extractor_model": "test-model", "reviewer_model": "test-model"},
        },
    )

    async def fail_batch(*_args):
        return [{"status": "failed", "event_id": "meeting-1", "error": error}]

    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        batch_name,
        fail_batch,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        persist_name,
        lambda _db_path, prepared: prepared,
    )
    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    assert providers[provider_name]([]) == 0

    assert artifacts.get(artifact_key) == [
        {"status": "failed", "event_id": "meeting-1", "error": error}
    ]
    with pytest.raises(ValueError, match=f"fomc meeting-1: {error}"):
        providers[import_name]([])


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


@pytest.mark.parametrize(
    "staged",
    [
        [
            {"status": "failed", "event_id": "failed-event", "error": "model unavailable"},
            {"status": "ok", "event_id": "success-event", "row": {}},
        ],
        [
            {"status": "ok", "event_id": "success-event", "row": {}},
            {"status": "failed", "event_id": "failed-event", "error": "model unavailable"},
        ],
    ],
)
def test_runtime_fomc_persists_every_partial_batch_before_raising(
    monkeypatch, staged
):
    artifacts = ArtifactStore()
    persisted = []
    monkeypatch.setattr(
        macro_refresh_runtime,
        "_pending_fomc_enrichment_events",
        lambda _key: [
            {"event_id": "failed-event"},
            {"event_id": "success-event"},
        ],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {
            "client": object(),
            "models": {"extractor_model": "extractor", "reviewer_model": "reviewer"},
        },
    )

    async def prepare_batch(*_args):
        return staged

    def persist(_db_path, prepared):
        persisted.append(prepared["event_id"])
        return prepared

    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "prepare_fomc_policy_tone_batch",
        prepare_batch,
    )
    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        "persist_fomc_policy_tone",
        persist,
    )
    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    assert providers["fomc_policy_tone_extract"]([]) == 0
    with pytest.raises(ValueError, match="failed-event: model unavailable"):
        providers["fomc_policy_tone_import"]([])

    assert persisted == [item["event_id"] for item in staged]
    assert artifacts.get("fomc.policy_tone.persistence") == staged


def test_runtime_fomc_selector_skips_approved_hash_and_keeps_failed_hash(
    monkeypatch,
):
    from scripts import generate_fomc_policy_tone

    events = [
        {"event_id": "approved-event", "start_date": "2026-08-01"},
        {"event_id": "failed-event", "start_date": "2026-08-02"},
    ]

    class Connection:
        def close(self):
            return None

    monkeypatch.setattr(macro_refresh_runtime.us_rates_liquidity, "connect", Connection)
    monkeypatch.setattr(
        macro_refresh_runtime.us_rates_liquidity,
        "load_macro_events",
        lambda *_args: events,
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_event_document",
        lambda _con, event_id, _document_type: {
            "source_hash": f"{event_id}-hash"
        },
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_event_tone_extraction",
        lambda _con, event_id, _document_type, source_hash: {
            "source_hash": source_hash,
            "extraction_status": "approved",
        }
        if event_id == "approved-event"
        else None,
    )

    pending = macro_refresh_runtime._pending_fomc_enrichment_events(
        "fomc.policy_tone"
    )

    assert pending == [events[1]]


@pytest.mark.parametrize(
    ("provider_name", "batch_name", "extractor_env", "reviewer_env", "expected"),
    [
        (
            "fomc_policy_tone_extract",
            "prepare_fomc_policy_tone_batch",
            "FOMC_TONE_EXTRACTOR_MODEL",
            "FOMC_TONE_REVIEWER_MODEL",
            ("tone-extractor", "tone-reviewer"),
        ),
        (
            "fomc_minutes_extract",
            "prepare_fomc_minutes_structure_batch",
            "FOMC_MINUTES_EXTRACTOR_MODEL",
            "FOMC_MINUTES_REVIEWER_MODEL",
            ("minutes-extractor", "minutes-reviewer"),
        ),
    ],
)
def test_runtime_fomc_batches_use_dedicated_role_model_environment(
    monkeypatch,
    provider_name,
    batch_name,
    extractor_env,
    reviewer_env,
    expected,
):
    artifacts = ArtifactStore()
    received_models = []
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv(extractor_env, expected[0])
    monkeypatch.setenv(reviewer_env, expected[1])
    monkeypatch.setattr(
        macro_refresh_runtime,
        "_pending_fomc_enrichment_events",
        lambda _key: [{"event_id": "meeting-1"}],
    )
    monkeypatch.setattr(
        macro_refresh_runtime.llm,
        "build_async_client",
        lambda *_args, **_kwargs: object(),
    )

    async def prepare_batch(_db_path, _event_ids, _client, extractor_model, reviewer_model):
        received_models.append((extractor_model, reviewer_model))
        return [{"status": "ok", "event_id": "meeting-1", "row": {}}]

    monkeypatch.setattr(
        macro_refresh_runtime.macro_refresh_official,
        batch_name,
        prepare_batch,
    )
    providers = macro_refresh_runtime.build_runtime_providers(
        artifacts,
        openai_config={"api_key": "configured", "model": "generic-config-model"},
    )

    assert providers[provider_name]([]) == 0
    assert received_models == [expected]


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
