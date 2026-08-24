from app.services.macro_refresh_plan import make_task


_FRED_MACRO_SPECS = (
    ("rates", "rates_fred", "--fred-csv-merge"),
    ("m2", "m2_fred", "--fred-csv-merge"),
    ("macro_indicators", "macro_indicators_fred", "--fred-csv-merge"),
    ("gdp", "gdp_fred", "--us-csv-merge"),
)


def build_refresh_tasks(args, providers, *, openai_config=None, artifact_store):
    tasks = []
    plan_index = 0

    for provider_key, task_prefix, import_flag in _FRED_MACRO_SPECS:
        provider = providers.get(provider_key)
        if provider is None or getattr(args, f"skip_{provider_key}", False):
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

    for provider_key, task_prefix, import_flag in _FRED_MACRO_SPECS:
        provider = providers.get(provider_key)
        if provider is None or getattr(args, f"skip_{provider_key}", False):
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

    return tasks
