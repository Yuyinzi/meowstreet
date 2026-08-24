from app.services.macro_refresh_plan import make_task


_FRED_MACRO_SPECS = (
    ("rates", "rates_fred", "--fred-csv-merge"),
    ("m2", "m2_fred", "--fred-csv-merge"),
    ("macro_indicators", "macro_indicators_fred", "--fred-csv-merge"),
    ("gdp", "gdp_fred", "--us-csv-merge"),
)


def build_refresh_tasks(args, providers, *, openai_config=None, artifact_store):
    del openai_config, artifact_store
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

    return tasks
