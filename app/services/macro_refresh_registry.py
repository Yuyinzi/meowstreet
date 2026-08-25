from app.services.macro_refresh_plan import make_task


_FRED_MACRO_SPECS = (
    ("rates", "rates", "rates_fred", "--fred-csv-merge"),
    ("m2", "m2", "m2_fred", "--fred-csv-merge"),
    ("macro_indicators", "macro_indicators", "macro_indicators_fred", "--fred-csv-merge"),
    ("gdp", "gdp", "gdp_fred", "--us-csv-merge"),
    ("cyclical_fred_fetch", "cyclical_fred_import", "cyclical_fred", "--import-usd"),
)


def build_refresh_tasks(args, providers, *, openai_config=None, artifact_store):
    tasks = []
    plan_index = 0

    for fetch_key, import_key, task_prefix, import_flag in _FRED_MACRO_SPECS:
        provider = providers.get(fetch_key)
        skip_key = "cyclical_commodities" if fetch_key == "cyclical_fred_fetch" else fetch_key
        if provider is None or getattr(args, f"skip_{skip_key}", False):
            continue
        tasks.append(
            make_task(
                f"{task_prefix}_fetch",
                "fred_macro",
                "fetch",
                provider,
                ["--fetch-fred-csv"],
                resources=["fred"],
                plan_index=plan_index,
            )
        )
        plan_index += 1

    for fetch_key, import_key, task_prefix, import_flag in _FRED_MACRO_SPECS:
        provider = providers.get(import_key)
        skip_key = "cyclical_commodities" if fetch_key == "cyclical_fred_fetch" else fetch_key
        if provider is None or getattr(args, f"skip_{skip_key}", False):
            continue
        fetch_name = f"{task_prefix}_fetch"
        tasks.append(
            make_task(
                f"{task_prefix}_import",
                "fred_macro",
                "persist",
                provider,
                [import_flag],
                dependencies=[fetch_name],
                resources=["sqlite_writer"],
                plan_index=plan_index,
            )
        )
        plan_index += 1

    credit_provider = providers.get("credit")
    if credit_provider is not None:
        tasks.extend(
            [
                make_task(
                    "credit_fred_fetch",
                    "credit",
                    "fetch",
                    credit_provider,
                    ["--fetch-fred-csv"],
                    resources=["fred"],
                    plan_index=plan_index,
                ),
                make_task(
                    "credit_fred_import",
                    "credit",
                    "persist",
                    credit_provider,
                    ["--fred-csv-merge"],
                    dependencies=["credit_fred_fetch"],
                    resources=["sqlite_writer"],
                    plan_index=plan_index + 1,
                ),
            ]
        )

    def add_pair(lane, fetch_name, import_name, fetch_provider, import_provider, *, skip=False):
        nonlocal plan_index
        if fetch_provider is None or import_provider is None or skip:
            return
        tasks.extend(
            [
                make_task(
                    fetch_name,
                    lane,
                    "fetch",
                    fetch_provider,
                    plan_index=plan_index,
                ),
                make_task(
                    import_name,
                    lane,
                    "persist",
                    import_provider,
                    dependencies=[fetch_name],
                    resources=["sqlite_writer"],
                    plan_index=plan_index + 1,
                ),
            ]
        )
        plan_index += 2

    add_pair(
        "yahoo",
        "yahoo.benchmarks_fetch",
        "yahoo.benchmarks_import",
        providers.get("benchmarks_fetch") or providers.get("yahoo_benchmarks_fetch"),
        providers.get("benchmarks_import") or providers.get("yahoo_benchmarks_import"),
        skip=getattr(args, "skip_yahoo", False),
    )
    add_pair(
        "yahoo",
        "yahoo.lumber_fetch",
        "yahoo.lumber_import",
        providers.get("lumber_fetch") or providers.get("yahoo_lumber_fetch"),
        providers.get("lumber_import") or providers.get("yahoo_lumber_import"),
        skip=getattr(args, "skip_lumber", False),
    )

    api_key = (openai_config or {}).get("api_key")
    enrichment_skip_reason = None if api_key else "OPENAI_API_KEY is not configured"

    def add_ism(survey_type):
        nonlocal plan_index
        prefix = f"ism.{survey_type}"
        fetch_provider = providers.get(f"ism_{survey_type}_fetch")
        import_provider = providers.get(f"ism_{survey_type}_import")
        enrichment_provider = providers.get(f"ism_{survey_type}_enrichment")
        enrichment_import_provider = providers.get(
            f"ism_{survey_type}_enrichment_import"
        )
        if any(
            provider is None
            for provider in (
                fetch_provider,
                import_provider,
                enrichment_provider,
                enrichment_import_provider,
            )
        ):
            return
        fetch_name = f"{prefix}_fetch"
        import_name = f"{prefix}_import"
        enrichment_name = f"{prefix}_enrichment"
        enrichment_import_name = f"{prefix}_enrichment_import"
        tasks.extend(
            [
                make_task(
                    fetch_name,
                    f"ism_{survey_type}",
                    "fetch",
                    fetch_provider,
                    plan_index=plan_index,
                ),
                make_task(
                    import_name,
                    f"ism_{survey_type}",
                    "persist",
                    import_provider,
                    dependencies=[fetch_name],
                    resources=["sqlite_writer"],
                    plan_index=plan_index + 1,
                ),
                make_task(
                    enrichment_name,
                    f"ism_{survey_type}",
                    "enrich",
                    enrichment_provider,
                    dependencies=[import_name],
                    skip_reason=enrichment_skip_reason,
                    plan_index=plan_index + 2,
                ),
                make_task(
                    enrichment_import_name,
                    f"ism_{survey_type}",
                    "persist",
                    enrichment_import_provider,
                    dependencies=[enrichment_name],
                    accepted_dependency_statuses=["ok", "skipped"],
                    resources=["sqlite_writer"],
                    skip_reason=enrichment_skip_reason,
                    plan_index=plan_index + 3,
                ),
            ]
        )
        plan_index += 4

    if not getattr(args, "skip_ism", False):
        add_ism("manufacturing")
        add_ism("services")

    def provider(*keys):
        for key in keys:
            value = providers.get(key)
            if value is not None:
                return value
        return None

    def add_official_pair(
        lane,
        fetch_name,
        import_name,
        fetch_provider,
        import_provider,
        *,
        fetch_resources=(),
        skip=False,
        dependencies=(),
    ):
        nonlocal plan_index
        if fetch_provider is None or import_provider is None or skip:
            return
        tasks.extend(
            [
                make_task(
                    fetch_name,
                    lane,
                    "fetch",
                    fetch_provider,
                    resources=fetch_resources,
                    dependencies=dependencies,
                    plan_index=plan_index,
                ),
                make_task(
                    import_name,
                    lane,
                    "persist",
                    import_provider,
                    dependencies=[fetch_name],
                    resources=["sqlite_writer"],
                    plan_index=plan_index + 1,
                ),
            ]
        )
        plan_index += 2

    if not getattr(args, "skip_consumer_sentiment", False):
        add_official_pair(
            "consumer",
            "consumer.michigan_fetch",
            "consumer.michigan_import",
            provider("consumer_michigan_fetch", "michigan_consumer_fetch"),
            provider("consumer_michigan_import", "michigan_consumer_import"),
        )
        add_official_pair(
            "consumer",
            "consumer.fred_fetch",
            "consumer.fred_import",
            provider("consumer_fred_fetch", "consumer_capacity_fred_fetch"),
            provider("consumer_fred_import", "consumer_capacity_fred_import"),
            fetch_resources=["fred"],
        )

    if not getattr(args, "skip_building_permits", False):
        add_official_pair(
            "census",
            "census.building_permits_fetch",
            "census.building_permits_import",
            provider("building_permits_fetch", "census_building_permits_fetch"),
            provider("building_permits_import", "census_building_permits_import"),
        )

    if not getattr(args, "skip_nfib_sbo", False):
        add_official_pair(
            "nfib",
            "nfib.national_fetch",
            "nfib.national_import",
            provider("nfib_fetch", "nfib_national_fetch"),
            provider("nfib_import", "nfib_national_import"),
        )
    if not getattr(args, "skip_nfib_sbo_regional", False):
        add_official_pair(
            "nfib",
            "nfib.regional_fetch",
            "nfib.regional_import",
            provider("nfib_regional_fetch"),
            provider("nfib_regional_import"),
        )

    if not getattr(args, "skip_fomc", False):
        calendar_provider = provider(
            "fomc_calendar_import", "fomc_calendar", "fomc_main"
        )
        documents_fetch_provider = provider(
            "fomc_documents_fetch", "fomc_document_fetch"
        )
        documents_import_provider = provider(
            "fomc_documents_import", "fomc_document_import"
        )
        tone_extract_provider = provider(
            "fomc_policy_tone_extract", "fomc_policy_tone_enrich"
        )
        tone_import_provider = provider(
            "fomc_policy_tone_import", "fomc_policy_tone_enrichment_import"
        )
        minutes_extract_provider = provider(
            "fomc_minutes_extract", "fomc_minutes_enrich"
        )
        minutes_import_provider = provider(
            "fomc_minutes_import", "fomc_minutes_enrichment_import"
        )
        fomc_providers = (
            calendar_provider,
            documents_fetch_provider,
            documents_import_provider,
            tone_extract_provider,
            tone_import_provider,
            minutes_extract_provider,
            minutes_import_provider,
        )
        if all(provider_value is not None for provider_value in fomc_providers):
            tasks.extend(
                [
                    make_task(
                        "fomc.calendar_import",
                        "fomc",
                        "persist",
                        calendar_provider,
                        resources=["sqlite_writer"],
                        plan_index=plan_index,
                    ),
                    make_task(
                        "fomc.documents_fetch",
                        "fomc",
                        "fetch",
                        documents_fetch_provider,
                        dependencies=["fomc.calendar_import"],
                        plan_index=plan_index + 1,
                    ),
                    make_task(
                        "fomc.documents_import",
                        "fomc",
                        "persist",
                        documents_import_provider,
                        dependencies=["fomc.documents_fetch"],
                        resources=["sqlite_writer"],
                        plan_index=plan_index + 2,
                    ),
                ]
            )
            enrichment_skip_reason = None if (openai_config or {}).get("api_key") else "OPENAI_API_KEY is not configured"
            tasks.extend(
                [
                    make_task(
                        "fomc.policy_tone_extract",
                        "fomc",
                        "enrich",
                        tone_extract_provider,
                        dependencies=["fomc.documents_import"],
                        skip_reason=enrichment_skip_reason,
                        plan_index=plan_index + 3,
                    ),
                    make_task(
                        "fomc.policy_tone_import",
                        "fomc",
                        "persist",
                        tone_import_provider,
                        dependencies=["fomc.policy_tone_extract"],
                        accepted_dependency_statuses=["ok", "skipped"],
                        resources=["sqlite_writer"],
                        skip_reason=enrichment_skip_reason,
                        plan_index=plan_index + 4,
                    ),
                    make_task(
                        "fomc.minutes_extract",
                        "fomc",
                        "enrich",
                        minutes_extract_provider,
                        dependencies=["fomc.documents_import"],
                        accepted_dependency_statuses=["ok", "skipped"],
                        skip_reason=enrichment_skip_reason,
                        plan_index=plan_index + 5,
                    ),
                    make_task(
                        "fomc.minutes_import",
                        "fomc",
                        "persist",
                        minutes_import_provider,
                        dependencies=["fomc.minutes_extract"],
                        accepted_dependency_statuses=["ok", "skipped"],
                        resources=["sqlite_writer"],
                        skip_reason=enrichment_skip_reason,
                        plan_index=plan_index + 6,
                    ),
                ]
            )
            plan_index += 7

    def add_commodity_pair(
        lane,
        fetch_name,
        import_name,
        fetch_provider,
        import_provider,
        *,
        skip=False,
        fetch_resources=(),
    ):
        nonlocal plan_index
        if fetch_provider is None or import_provider is None or skip:
            return
        tasks.extend(
            [
                make_task(
                    fetch_name,
                    lane,
                    "fetch",
                    fetch_provider,
                    resources=fetch_resources,
                    plan_index=plan_index,
                ),
                make_task(
                    import_name,
                    lane,
                    "persist",
                    import_provider,
                    dependencies=[fetch_name],
                    resources=["sqlite_writer"],
                    plan_index=plan_index + 1,
                ),
            ]
        )
        plan_index += 2

    add_commodity_pair(
        "tracked_commodities",
        "tracked_commodities_fetch",
        "tracked_commodities_import",
        provider("tracked_commodities_fetch", "tracked_fetch"),
        provider("tracked_commodities_import", "tracked_import"),
        skip=getattr(args, "skip_tracked_commodities", False),
    )
    add_commodity_pair(
        "cftc",
        "cyclical_cot_fetch",
        "cyclical_cot_import",
        provider("cyclical_cot_fetch", "cftc_fetch"),
        provider("cyclical_cot_import", "cftc_import"),
        skip=getattr(args, "skip_cyclical_commodities", False),
    )
    add_commodity_pair(
        "eia",
        "oil_fetch",
        "oil_import",
        provider("oil_fetch", "eia_fetch"),
        provider("oil_import", "eia_import"),
        skip=getattr(args, "skip_oil", False),
    )
    add_commodity_pair(
        "shfe",
        "shfe_copper_fetch",
        "shfe_copper_import",
        provider("shfe_copper_fetch", "shfe_fetch"),
        provider("shfe_copper_import", "shfe_import"),
        skip=getattr(args, "skip_shfe_copper", False),
    )
    add_commodity_pair(
        "dce_sina",
        "dce_iron_ore_sina_fetch",
        "dce_iron_ore_sina_import",
        provider("dce_iron_ore_sina_fetch", "dce_fetch"),
        provider("dce_iron_ore_sina_import", "dce_import"),
        skip=getattr(args, "skip_dce_iron_ore_sina", False),
    )
    add_commodity_pair(
        "dol",
        "dol_fetch",
        "dol_import",
        provider("dol_fetch", "economic_confirmation_dol_fetch"),
        provider("dol_import", "economic_confirmation_dol_import"),
        skip=getattr(args, "skip_economic_confirmation", False),
    )
    add_commodity_pair(
        "bls",
        "bls_fetch",
        "bls_import",
        provider("bls_fetch", "economic_confirmation_bls_fetch"),
        provider("bls_import", "economic_confirmation_bls_import"),
        skip=getattr(args, "skip_economic_confirmation", False),
    )
    add_commodity_pair(
        "federal_reserve",
        "federal_reserve_fetch",
        "federal_reserve_import",
        provider("federal_reserve_fetch", "g17_fetch", "economic_confirmation_g17_fetch"),
        provider("federal_reserve_import", "g17_import", "economic_confirmation_g17_import"),
        skip=getattr(args, "skip_economic_confirmation", False),
    )

    return tasks
