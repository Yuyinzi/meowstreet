import os
from pathlib import Path
from threading import Lock

from app import llm
from app.services import macro_refresh_commodities
from app.services import macro_refresh_official
from app.services import macro_refresh_yahoo
from app.services import lumber_import
from app.services import ism_report_ingestion
from app.services import macro_refresh_ism
from app.db import benchmark_market_data
from app.db import growth_cycle
from app.db import market_data
from app.db import macro_indicators
from app.db import us_rates_liquidity
from app.tools import market_data as market_data_tool
from scripts import import_economic_confirmation
from scripts import import_fomc_calendar
from scripts import import_gdp_market_relationships
from scripts import import_m2_money_supply
from scripts import import_us_corporate_credit
from scripts import import_us_macro_indicators
from scripts import import_us_rates_liquidity


def build_runtime_providers(
    artifacts,
    *,
    overrides=None,
    values=None,
    openai_config=None,
    fomc_calendar_path=None,
    verbose=False,
):
    values = values or {}
    providers = {
        **_fred_providers(artifacts),
        **_official_providers(artifacts),
        **_commodity_providers(artifacts, _eia_api_key()),
        **_yahoo_providers(artifacts),
        **_ism_providers(artifacts, openai_config or {}),
        **_fomc_providers(artifacts, openai_config or {}, fomc_calendar_path),
    }
    providers.update(
        _injected_cli_overrides(
            artifacts,
            values,
            fomc_calendar_path=fomc_calendar_path,
            verbose=verbose,
        )
    )
    providers.update(overrides or {})
    return providers


def _eia_api_key():
    llm.load_env()
    return os.getenv("EIA_KEY")


def _fred_providers(artifacts):
    return {
        "rates_fetch": _fred_fetch(
            artifacts,
            "rates",
            import_us_rates_liquidity.fetch_fred_csvs,
        ),
        "rates_import": _fred_import(
            artifacts,
            "rates",
            import_us_rates_liquidity.import_fred_csvs,
            us_rates_liquidity.DEFAULT_DB_PATH,
        ),
        "m2_fetch": _fred_fetch(artifacts, "m2", import_m2_money_supply.fetch_fred_csvs),
        "m2_import": _fred_import(
            artifacts,
            "m2",
            import_m2_money_supply.import_fred_csvs,
            us_rates_liquidity.DEFAULT_DB_PATH,
        ),
        "macro_indicators_fetch": _fred_fetch(
            artifacts,
            "macro_indicators",
            import_us_macro_indicators.fetch_fred_csvs,
        ),
        "macro_indicators_import": _fred_import(
            artifacts,
            "macro_indicators",
            import_us_macro_indicators.import_fred_macro_csvs,
            us_rates_liquidity.DEFAULT_DB_PATH,
        ),
        "gdp_fetch": _fred_fetch(
            artifacts,
            "gdp",
            import_gdp_market_relationships.fetch_fred_csvs,
        ),
        "gdp_import": _gdp_import(artifacts),
        "credit_fetch": _fred_fetch(
            artifacts,
            "credit",
            import_us_corporate_credit.fetch_fred_csvs,
        ),
        "credit_import": _fred_import(
            artifacts,
            "credit",
            import_us_corporate_credit.import_fred_csvs,
            us_rates_liquidity.DEFAULT_DB_PATH,
        ),
    }


def _fred_fetch(artifacts, key, fetcher):
    def fetch(argv):
        fetched = fetcher()
        artifacts.put(f"fred.{key}", fetched)
        return 0

    return fetch


def _fred_import(artifacts, key, importer, db_path):
    def persist(argv):
        fetched = artifacts.get(f"fred.{key}")
        directory = _fetched_directory(fetched)
        con = us_rates_liquidity.connect(db_path)
        try:
            importer(con, directory)
        finally:
            con.close()
        return 0

    return persist


def _gdp_import(artifacts):
    def persist(argv):
        fetched = artifacts.get("fred.gdp")
        con = import_gdp_market_relationships.gdp_market_relationships.connect()
        try:
            import_gdp_market_relationships.import_us_csv_merge(
                con,
                fetched["gdp_csv"],
                fetched["sp500_csv"],
            )
        finally:
            con.close()
        return 0

    return persist


def _fetched_directory(fetched):
    paths = list(fetched.values())
    if not paths:
        raise ValueError("macro refresh fetched artifact has no files")
    return Path(paths[0]).parent


def _official_providers(artifacts):
    return {
        "consumer_michigan_fetch": _official_fetch(
            artifacts, macro_refresh_official.fetch_consumer_michigan, "consumer.michigan"
        ),
        "consumer_michigan_import": _official_import(
            artifacts,
            macro_refresh_official.persist_consumer_michigan,
            "consumer.michigan",
            us_rates_liquidity.DEFAULT_DB_PATH,
        ),
        "consumer_fred_fetch": _official_fetch(
            artifacts, macro_refresh_official.fetch_consumer_fred, "consumer.fred"
        ),
        "consumer_fred_import": _official_import(
            artifacts,
            macro_refresh_official.persist_consumer_fred,
            "consumer.fred",
            us_rates_liquidity.DEFAULT_DB_PATH,
        ),
        "building_permits_fetch": _official_fetch(
            artifacts,
            macro_refresh_official.fetch_building_permits,
            "census.building_permits",
        ),
        "building_permits_import": _official_import(
            artifacts,
            macro_refresh_official.persist_building_permits,
            "census.building_permits",
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "nfib_fetch": _official_fetch(
            artifacts, macro_refresh_official.fetch_nfib, "nfib.national"
        ),
        "nfib_import": _official_import(
            artifacts,
            macro_refresh_official.persist_nfib,
            "nfib.national",
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "nfib_regional_fetch": _official_fetch(
            artifacts, macro_refresh_official.fetch_nfib_regional, "nfib.regional"
        ),
        "nfib_regional_import": _official_import(
            artifacts,
            macro_refresh_official.persist_nfib_regional,
            "nfib.regional",
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "dol_fetch": _official_fetch(
            artifacts, import_economic_confirmation.fetch_dol, "economic.dol"
        ),
        "dol_import": _official_import(
            artifacts,
            import_economic_confirmation.persist_dol,
            "economic.dol",
            import_economic_confirmation.DEFAULT_DB_PATH,
        ),
        "bls_fetch": _official_fetch(
            artifacts, import_economic_confirmation.fetch_bls, "economic.bls"
        ),
        "bls_import": _official_import(
            artifacts,
            import_economic_confirmation.persist_bls,
            "economic.bls",
            import_economic_confirmation.DEFAULT_DB_PATH,
        ),
        "federal_reserve_fetch": _official_fetch(
            artifacts,
            import_economic_confirmation.fetch_federal_reserve,
            "economic.federal_reserve",
        ),
        "federal_reserve_import": _official_import(
            artifacts,
            import_economic_confirmation.persist_federal_reserve,
            "economic.federal_reserve",
            import_economic_confirmation.DEFAULT_DB_PATH,
        ),
    }


def _official_fetch(artifacts, fetcher, key):
    def fetch(argv):
        fetcher(artifacts)
        return 0

    return fetch


def _official_import(artifacts, importer, key, db_path):
    def persist(argv):
        artifacts.get(key)
        importer(db_path, artifacts)
        return 0

    return persist


def _commodity_providers(artifacts, eia_api_key):
    return {
        "cyclical_fred_fetch": lambda argv: _run_fetch(
            artifacts, "commodities.cyclical_fred", macro_refresh_commodities.fetch_cyclical_fred
        ),
        "cyclical_fred_import": lambda argv: _run_import(
            artifacts,
            "commodities.cyclical_fred",
            macro_refresh_commodities.persist_cyclical_fred,
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "tracked_commodities_fetch": lambda argv: _run_fetch(
            artifacts, "commodities.tracked", macro_refresh_commodities.fetch_tracked_commodities
        ),
        "tracked_commodities_import": lambda argv: _run_import(
            artifacts,
            "commodities.tracked",
            macro_refresh_commodities.persist_tracked_commodities,
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "cyclical_cot_fetch": lambda argv: _run_fetch(
            artifacts,
            "commodities.cftc",
            lambda target: macro_refresh_commodities.fetch_cyclical_cot(target, [2026]),
        ),
        "cyclical_cot_import": lambda argv: _run_import(
            artifacts,
            "commodities.cftc",
            macro_refresh_commodities.persist_cyclical_cot,
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "oil_fetch": lambda argv: _run_fetch(
            artifacts,
            "commodities.oil",
            lambda target: macro_refresh_commodities.fetch_oil(target, eia_api_key),
        ),
        "oil_import": lambda argv: _run_import(
            artifacts,
            "commodities.oil",
            macro_refresh_commodities.persist_oil,
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "dce_iron_ore_sina_fetch": lambda argv: _run_fetch(
            artifacts,
            "commodities.dce_sina",
            lambda target: macro_refresh_commodities.fetch_dce_iron_ore_sina(
                target, db_path=macro_indicators.DEFAULT_DB_PATH
            ),
        ),
        "dce_iron_ore_sina_import": lambda argv: _run_import(
            artifacts,
            "commodities.dce_sina",
            macro_refresh_commodities.persist_dce_iron_ore_sina,
            macro_indicators.DEFAULT_DB_PATH,
        ),
        "shfe_copper_fetch": lambda argv: _fetch_shfe(artifacts),
        "shfe_copper_import": lambda argv: _run_import(
            artifacts,
            "commodities.shfe",
            macro_refresh_commodities.persist_shfe_copper,
            macro_indicators.DEFAULT_DB_PATH,
        ),
    }


def _run_fetch(artifacts, key, fetcher):
    fetcher(artifacts)
    artifacts.get(key)
    return 0


def _run_import(artifacts, key, importer, db_path):
    artifacts.get(key)
    importer(db_path, artifacts)
    return 0


def _fetch_shfe(artifacts):
    from app.services import shfe_copper_import

    con = macro_indicators.connect()
    try:
        start_date, end_date = shfe_copper_import.incremental_window(con)
    finally:
        con.close()
    dates = shfe_copper_import._requested_dates(start_date, end_date)
    macro_refresh_commodities.fetch_shfe_copper(artifacts, dates)
    artifacts.get("commodities.shfe")
    return 0


def _yahoo_providers(artifacts):
    def fetch_benchmarks(argv):
        ids = [
            "us_sp500",
            "us_nasdaq_100",
            "us_nasdaq_composite",
            "us_djia",
        ]
        benchmark_con = benchmark_market_data.connect()
        market_con = market_data.connect()
        try:
            latest = {
                benchmark_id: benchmark_market_data.latest_price_date(
                    benchmark_con, benchmark_id
                )
                for benchmark_id in ids
            }
            prepared = macro_refresh_yahoo.prepare_benchmarks(
                ids,
                fetch_market_data=lambda symbol, **kwargs: market_data_tool.fetch_market_data(
                    symbol, db_path=market_data.DEFAULT_DB_PATH, **kwargs
                ),
                load_market_rows=lambda symbol, interval, start_date=None: market_data.load_price_rows(
                    market_con, symbol, interval, start_date=start_date
                ),
                latest_dates=latest,
            )
        finally:
            market_con.close()
            benchmark_con.close()
        artifacts.put("yahoo.benchmarks", prepared)
        return 0

    def import_benchmarks(argv):
        prepared = artifacts.get("yahoo.benchmarks")
        macro_refresh_yahoo.persist_benchmarks(
            prepared,
            benchmark_db_path=benchmark_market_data.DEFAULT_DB_PATH,
            market_db_path=market_data.DEFAULT_DB_PATH,
        )
        return 0

    def fetch_lumber(argv):
        con = macro_indicators.connect()
        try:
            prepared = lumber_import.prepare_lumber(con)
        finally:
            con.close()
        artifacts.put("yahoo.lumber", prepared)
        return 0

    def import_lumber(argv):
        prepared = artifacts.get("yahoo.lumber")
        con = macro_indicators.connect()
        try:
            lumber_import.persist_lumber(con, prepared)
        finally:
            con.close()
        return 0

    return {
        "benchmarks_fetch": fetch_benchmarks,
        "benchmarks_import": import_benchmarks,
        "lumber_fetch": fetch_lumber,
        "lumber_import": import_lumber,
    }


def _ism_providers(artifacts, openai_config):
    providers = {}
    for survey_type in ("manufacturing", "services"):
        key = f"ism.{survey_type}"

        def fetch(argv, survey_type=survey_type, key=key):
            con = us_rates_liquidity.connect()
            try:
                existing = growth_cycle.load_existing_ism_report_months(
                    con, survey_type
                )
            finally:
                con.close()
            targets = ism_report_ingestion.build_targets(
                survey_type,
                latest_only=True,
                existing_months=existing,
                fetch=lambda url: "",
            )
            prepared = macro_refresh_ism.prepare_ism_reports(
                targets,
                fetcher=lambda url: __import__(
                    "scripts.fetch_ism_official_reports", fromlist=["fetch_text"]
                ).fetch_text(url),
            )
            artifacts.put(key, prepared)
            return 0

        def persist(argv, survey_type=survey_type, key=key):
            prepared = artifacts.get(key)
            macro_refresh_ism.persist_ism_reports(
                us_rates_liquidity.DEFAULT_DB_PATH, prepared
            )
            return 0

        def enrich(argv, survey_type=survey_type, key=key):
            prepared = artifacts.get(key)
            snapshot = next(
                (item["snapshot"] for item in prepared if item.get("status") == "ok"),
                None,
            )
            if not openai_config.get("api_key"):
                return 0
            if snapshot is None:
                artifacts.put(f"{key}.enrichment", None)
                return 0
            artifacts.put(
                f"{key}.enrichment",
                macro_refresh_ism.prepare_ism_enrichment(
                    snapshot,
                    client=_build_ism_client(openai_config),
                    model=openai_config.get("model"),
                    survey_type=survey_type,
                ),
            )
            return 0

        def enrich_import(argv, key=key):
            staged = artifacts.get(f"{key}.enrichment")
            if staged is None:
                return 0
            macro_refresh_ism.persist_ism_enrichment(
                us_rates_liquidity.DEFAULT_DB_PATH, staged
            )
            return 0

        providers.update(
            {
                f"ism_{survey_type}_fetch": fetch,
                f"ism_{survey_type}_import": persist,
                f"ism_{survey_type}_enrichment": enrich,
                f"ism_{survey_type}_enrichment_import": enrich_import,
            }
        )
    return providers


def _build_ism_client(config):
    from scripts import extract_ism_report_ai

    return extract_ism_report_ai.build_client(config)


def _fomc_providers(artifacts, openai_config, calendar_path):
    def calendar_import(argv):
        return int(import_fomc_calendar.main(
            [
                "--calendar-path",
                str(calendar_path or import_fomc_calendar.DEFAULT_CALENDAR_PATH),
            ]
        ) or 0)

    def documents_fetch(argv):
        con = us_rates_liquidity.connect()
        try:
            events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
        finally:
            con.close()
        for document_type in ("statement", "minutes"):
            macro_refresh_official.fetch_fomc_documents(
                artifacts, events, document_type
            )
        return 0

    def documents_import(argv):
        for document_type in ("statement", "minutes"):
            artifacts.get(f"fomc.documents.{document_type}")
            macro_refresh_official.persist_fomc_documents(
                us_rates_liquidity.DEFAULT_DB_PATH, artifacts, document_type
            )
        return 0

    def prepare_policy_tone(argv):
        return _prepare_fomc_enrichment(
            artifacts,
            "fomc.policy_tone",
            openai_config,
            macro_refresh_official.prepare_fomc_policy_tone,
        )

    def persist_policy_tone(argv):
        return _persist_fomc_enrichment(
            artifacts,
            "fomc.policy_tone",
            macro_refresh_official.persist_fomc_policy_tone,
        )

    def prepare_minutes(argv):
        return _prepare_fomc_enrichment(
            artifacts,
            "fomc.minutes",
            openai_config,
            macro_refresh_official.prepare_fomc_minutes_structure,
        )

    def persist_minutes(argv):
        return _persist_fomc_enrichment(
            artifacts,
            "fomc.minutes",
            macro_refresh_official.persist_fomc_minutes_structure,
        )

    return {
        "fomc_calendar_import": calendar_import,
        "fomc_documents_fetch": documents_fetch,
        "fomc_documents_import": documents_import,
        "fomc_policy_tone_extract": prepare_policy_tone,
        "fomc_policy_tone_import": persist_policy_tone,
        "fomc_minutes_extract": prepare_minutes,
        "fomc_minutes_import": persist_minutes,
    }


def _prepare_fomc_enrichment(artifacts, key, config, prepare):
    if not config.get("api_key"):
        artifacts.put(key, [])
        return 0
    client = llm.build_async_client(
        config,
        max_retries=0,
        timeout=120,
        error_context="FOMC refresh enrichment",
    )
    con = us_rates_liquidity.connect()
    try:
        events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
    finally:
        con.close()
    model = config.get("model")
    artifacts.put(
        key,
        [
            prepare(
                us_rates_liquidity.DEFAULT_DB_PATH,
                event["event_id"],
                client,
                model,
                model,
            )
            for event in events
        ],
    )
    return 0


def _persist_fomc_enrichment(artifacts, key, persist):
    for prepared in artifacts.get(key):
        persist(us_rates_liquidity.DEFAULT_DB_PATH, prepared)
    return 0


def _injected_cli_overrides(
    artifacts,
    values,
    *,
    fomc_calendar_path=None,
    verbose=False,
):
    providers = {}
    for key, name, fetch_args, import_args in (
        ("rates", "rates_main", ["--fetch-fred-csv"], ["--fred-csv-merge"]),
        ("m2", "m2_main", ["--fetch-fred-csv"], ["--fred-csv-merge"]),
        (
            "macro_indicators",
            "macro_indicators_main",
            ["--fetch-fred-csv"],
            ["--fred-csv-merge"],
        ),
        ("gdp", "gdp_main", ["--fetch-fred-csv"], ["--us-csv-merge"]),
        ("credit", "credit_main", ["--fetch-fred-csv"], ["--fred-csv-merge"]),
    ):
        if values.get(name) is not None:
            providers.update(
                _script_pair(
                    values[name],
                    fetch_args,
                    import_args,
                    f"fred.{key}",
                    artifacts,
                    fetch_key=f"{key}_fetch",
                    import_key=f"{key}_import",
                )
            )
    if values.get("benchmark_main") is not None:
        benchmark_args = [
            "--benchmark-id",
            "us_sp500",
            "--benchmark-id",
            "us_nasdaq_100",
            "--benchmark-id",
            "us_nasdaq_composite",
            "--benchmark-id",
            "us_djia",
        ]
        providers.update(
            _one_shot_pair(
                values["benchmark_main"],
                benchmark_args,
                [],
                "yahoo.benchmarks",
                artifacts,
                fetch_key="benchmarks_fetch",
                import_key="benchmarks_import",
            )
        )
    if values.get("consumer_main") is not None:
        providers.update(
            _script_pair(
                values["consumer_main"],
                ["--fetch-michigan-csv", "data/local_system/consumer_cache"],
                [
                    "--michigan-csv-import",
                    "data/local_system/consumer_cache/table_1.csv",
                    "data/local_system/consumer_cache/table_5.csv",
                ],
                "consumer.michigan",
                artifacts,
                fetch_key="consumer_michigan_fetch",
                import_key="consumer_michigan_import",
            )
        )
        providers.update(
            _script_pair(
                values["consumer_main"],
                ["--fetch-fred-csv", "data/local_system/consumer_cache"],
                ["--fred-csv-import", "data/local_system/consumer_cache"],
                "consumer.fred",
                artifacts,
                fetch_key="consumer_fred_fetch",
                import_key="consumer_fred_import",
            )
        )
    if values.get("building_permits_main") is not None:
        providers.update(
            _script_pair(
                values["building_permits_main"],
                ["--fetch-census-workbook"],
                ["--import-census-workbook"],
                "census.building_permits",
                artifacts,
                fetch_key="building_permits_fetch",
                import_key="building_permits_import",
            )
        )
    if values.get("ism_reports_main") is not None:
        for survey in ("manufacturing", "services"):
            prefix = f"ism_{survey}"
            providers.update(
                _one_shot_pair(
                    values["ism_reports_main"],
                    ["--survey", survey, "--latest-only", "--core-only"],
                    [],
                    f"ism.{survey}.core",
                    artifacts,
                    fetch_key=f"{prefix}_fetch",
                    import_key=f"{prefix}_import",
                )
            )
            providers.update(
                _one_shot_pair(
                    values["ism_reports_main"],
                    ["--survey", survey, "--latest-only", "--enrichment-only"],
                    [],
                    f"ism.{survey}.enrichment",
                    artifacts,
                    fetch_key=f"{prefix}_enrichment",
                    import_key=f"{prefix}_enrichment_import",
                )
            )
    cache_path = "data/local_system/nfib_cache/nfib-sbet-current.pdf"
    for value_key, fetch_args, import_args, fetch_key, import_key in (
        (
            "nfib_main",
            ["--fetch-pdf"],
            ["--import-pdf", cache_path],
            "nfib_fetch",
            "nfib_import",
        ),
        (
            "nfib_regional_main",
            [],
            [],
            "nfib_regional_fetch",
            "nfib_regional_import",
        ),
        ("oil_main", [], [], "oil_fetch", "oil_import"),
        (
            "tracked_commodities_main",
            [],
            [],
            "tracked_commodities_fetch",
            "tracked_commodities_import",
        ),
        ("dce_iron_ore_sina_main", [], [], "dce_iron_ore_sina_fetch", "dce_iron_ore_sina_import"),
        ("shfe_copper_main", ["--incremental"], [], "shfe_copper_fetch", "shfe_copper_import"),
    ):
        if values.get(value_key) is not None:
            pair_builder = _script_pair if value_key == "nfib_main" else _one_shot_pair
            providers.update(
                pair_builder(
                    values[value_key],
                    fetch_args,
                    import_args,
                    f"legacy.{value_key}",
                    artifacts,
                    fetch_key=fetch_key,
                    import_key=import_key,
                )
            )
    if values.get("lumber_main") is not None:
        providers.update(
            _one_shot_pair(
                values["lumber_main"],
                [],
                [],
                "yahoo.lumber",
                artifacts,
                fetch_key="lumber_fetch",
                import_key="lumber_import",
            )
        )
    if values.get("economic_confirmation_main") is not None:
        artifact_key = "legacy.economic_confirmation"
        combined = _one_shot_provider(
            values["economic_confirmation_main"], artifacts, artifact_key
        )
        for fetch_key, import_key in (
            ("dol_fetch", "dol_import"),
            ("bls_fetch", "bls_import"),
            ("federal_reserve_fetch", "federal_reserve_import"),
        ):
            providers[fetch_key] = _artifact_stage(artifacts, artifact_key)
            providers[import_key] = _persist_one_shot(
                combined, artifacts, artifact_key
            )
    if values.get("main") is not None:
        providers.update(
            _script_pair(
                values["main"],
                ["--fetch-cot"],
                ["--import-cot"],
                "commodities.cftc",
                artifacts,
                fetch_key="cyclical_cot_fetch",
                import_key="cyclical_cot_import",
            )
        )
        providers.update(
            _script_pair(
                values["main"],
                ["--fetch-usd"],
                ["--import-usd"],
                "commodities.cyclical_fred",
                artifacts,
                fetch_key="cyclical_fred_fetch",
                import_key="cyclical_fred_import",
            )
        )
    if values.get("fomc_main") is not None:
        providers["fomc_calendar_import"] = _script_stage(
            values["fomc_main"],
            [
                "--calendar-path",
                str(fomc_calendar_path or import_fomc_calendar.DEFAULT_CALENDAR_PATH),
            ],
            "fomc.calendar",
            artifacts,
            is_fetch=True,
        )
    for value_key, fetch_args, fetch_key, import_key in (
        (
            "fomc_document_main",
            ["--document-type", "all"],
            "fomc_documents_fetch",
            "fomc_documents_import",
        ),
        (
            "fomc_policy_tone_main",
                    ["--all"] + (["--verbose"] if verbose else []),
            "fomc_policy_tone_extract",
            "fomc_policy_tone_import",
        ),
        (
            "fomc_minutes_main",
            ["--all"],
            "fomc_minutes_extract",
            "fomc_minutes_import",
        ),
    ):
        if values.get(value_key) is not None:
            providers.update(
                _one_shot_pair(
                    values[value_key],
                    fetch_args,
                    [],
                    f"legacy.{value_key}",
                    artifacts,
                    fetch_key=fetch_key,
                    import_key=import_key,
                )
            )
    return providers


def _one_shot_provider(provider, artifacts, artifact_key, arguments=()):
    lock = Lock()
    state = {"called": False, "result": 0}

    def run(argv):
        with lock:
            if not state["called"]:
                state["result"] = int(provider(list(arguments)) or 0)
                if state["result"] == 0:
                    artifacts.put(artifact_key, {"result": state["result"]})
                state["called"] = True
            return state["result"]

    return run


def _artifact_only(artifacts, artifact_key):
    def persist(argv):
        artifacts.get(artifact_key)
        return 0

    return persist


def _artifact_stage(artifacts, artifact_key):
    def fetch(argv):
        artifacts.put(artifact_key, {"status": "pending"})
        return 0

    return fetch


def _persist_one_shot(provider, artifacts, artifact_key):
    def persist(argv):
        artifacts.get(artifact_key)
        return provider(argv)

    return persist


def _one_shot_pair(
    provider,
    fetch_args,
    import_args,
    artifact_key,
    artifacts,
    fetch_key,
    import_key,
):
    combined = _one_shot_provider(provider, artifacts, artifact_key, fetch_args)
    return {
        fetch_key: _artifact_stage(artifacts, artifact_key),
        import_key: _persist_one_shot(combined, artifacts, artifact_key),
    }


def _script_pair(
    provider,
    fetch_args,
    import_args,
    artifact_key,
    artifacts,
    fetch_key,
    import_key,
):
    return {
        fetch_key: _script_stage(
            provider,
            fetch_args,
            artifact_key,
            artifacts,
            is_fetch=True,
        ),
        import_key: _script_stage(
            provider,
            import_args,
            artifact_key,
            artifacts,
            is_fetch=False,
        ),
    }


def _script_stage(provider, argv, artifact_key, artifacts, *, is_fetch):
    def run(_argv):
        if is_fetch:
            result = provider(list(argv))
            artifacts.put(artifact_key, {"result": result})
            return int(result or 0)
        artifacts.get(artifact_key)
        return int(provider(list(argv)) or 0)

    return run
