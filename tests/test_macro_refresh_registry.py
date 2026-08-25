from pathlib import Path
from types import SimpleNamespace

from app.services.macro_refresh_registry import build_refresh_tasks
from app.services.macro_refresh_resources import ArtifactStore


def fred_registry_args(**overrides):
    values = {
        "skip_yahoo": True,
        "skip_rates": False,
        "skip_consumer_sentiment": True,
        "skip_m2": False,
        "skip_macro_indicators": False,
        "skip_building_permits": True,
        "skip_ism": True,
        "skip_gdp": False,
        "skip_fomc": True,
        "skip_nfib_sbo": True,
        "skip_nfib_sbo_regional": True,
        "skip_tracked_commodities": True,
        "skip_cyclical_commodities": True,
        "skip_oil": True,
        "skip_lumber": True,
        "skip_shfe_copper": True,
        "skip_dce_iron_ore_sina": True,
        "skip_economic_confirmation": True,
        "fomc_calendar_path": None,
        "verbose": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def fred_provider_stubs():
    return {
        "rates": lambda argv: 0,
        "credit": lambda argv: 0,
        "m2": lambda argv: 0,
        "macro_indicators": lambda argv: 0,
        "gdp": lambda argv: 0,
    }


def test_fred_and_credit_are_separate_lanes_with_shared_resources():
    tasks = build_refresh_tasks(
        fred_registry_args(),
        fred_provider_stubs(),
        openai_config={"api_key": None},
        artifact_store=ArtifactStore(),
    )
    selected = {
        task["name"]: (
            task["lane"],
            task["stage"],
            task["dependencies"],
            task["resources"],
        )
        for task in tasks
    }

    assert selected["rates_fred_fetch"] == ("fred_macro", "fetch", [], ["fred"])
    assert selected["rates_fred_import"] == (
        "fred_macro",
        "persist",
        ["rates_fred_fetch"],
        ["sqlite_writer"],
    )
    assert selected["credit_fred_fetch"] == ("credit", "fetch", [], ["fred"])
    assert selected["credit_fred_import"] == (
        "credit",
        "persist",
        ["credit_fred_fetch"],
        ["sqlite_writer"],
    )

    macro_fetches = [
        task["name"]
        for task in tasks
        if task["lane"] == "fred_macro" and task["stage"] == "fetch"
    ]
    macro_imports = [
        task["name"]
        for task in tasks
        if task["lane"] == "fred_macro" and task["stage"] == "persist"
    ]
    assert macro_fetches == [
        "rates_fred_fetch",
        "m2_fred_fetch",
        "macro_indicators_fred_fetch",
        "gdp_fred_fetch",
    ]
    assert macro_imports == [
        "rates_fred_import",
        "m2_fred_import",
        "macro_indicators_fred_import",
        "gdp_fred_import",
    ]
    assert all(
        task["dependencies"] == [task["name"].replace("_import", "_fetch")]
        for task in tasks
        if task["stage"] == "persist"
    )


def test_fred_skip_flags_remove_only_their_fetch_import_pairs():
    all_tasks = build_refresh_tasks(
        fred_registry_args(),
        fred_provider_stubs(),
        openai_config={"api_key": None},
        artifact_store=ArtifactStore(),
    )
    skipped_tasks = build_refresh_tasks(
        fred_registry_args(
            skip_rates=True,
            skip_m2=True,
            skip_macro_indicators=True,
            skip_gdp=True,
        ),
        fred_provider_stubs(),
        openai_config={"api_key": None},
        artifact_store=ArtifactStore(),
    )

    assert {task["name"] for task in skipped_tasks} == {
        "credit_fred_fetch",
        "credit_fred_import",
    }
    assert len(all_tasks) == 10


def test_credit_stage_provider_pair_is_registered_as_its_own_lane():
    tasks = build_refresh_tasks(
        fred_registry_args(
            skip_rates=True,
            skip_m2=True,
            skip_macro_indicators=True,
            skip_gdp=True,
        ),
        {
            "credit_fetch": lambda argv: 0,
            "credit_import": lambda argv: 0,
        },
        openai_config={"api_key": None},
        artifact_store=ArtifactStore(),
    )

    assert [task["name"] for task in tasks] == [
        "credit_fred_fetch",
        "credit_fred_import",
    ]
    assert tasks[1]["dependencies"] == ["credit_fred_fetch"]


def test_yahoo_and_ism_stage_resources_and_missing_key_skips_enrichment():
    providers = fred_provider_stubs()
    providers.update(
        {
            "benchmarks_fetch": lambda argv: 0,
            "benchmarks_import": lambda argv: 0,
            "lumber_fetch": lambda argv: 0,
            "lumber_import": lambda argv: 0,
        }
    )
    for survey in ("manufacturing", "services"):
        providers.update(
            {
                f"ism_{survey}_fetch": lambda argv: 0,
                f"ism_{survey}_import": lambda argv: 0,
                f"ism_{survey}_enrichment": lambda argv: 0,
                f"ism_{survey}_enrichment_import": lambda argv: 0,
            }
        )

    tasks = build_refresh_tasks(
        fred_registry_args(skip_yahoo=False, skip_lumber=False, skip_ism=False),
        providers,
        openai_config={"api_key": None},
        artifact_store=ArtifactStore(),
    )
    selected = {task["name"]: task for task in tasks}

    assert selected["yahoo.benchmarks_fetch"]["resources"] == []
    assert selected["yahoo.benchmarks_import"]["resources"] == ["sqlite_writer"]
    assert selected["ism.manufacturing_enrichment"]["skip_reason"] == (
        "OPENAI_API_KEY is not configured"
    )
    assert selected["ism.manufacturing_enrichment_import"]["accepted_dependency_statuses"] == [
        "ok",
        "skipped",
    ]
    assert selected["ism.manufacturing_enrichment"]["resources"] == []
    assert selected["ism.manufacturing_enrichment_import"]["resources"] == [
        "sqlite_writer"
    ]


def test_ism_enrichment_runs_when_openai_key_exists():
    providers = {
        f"ism_{survey}_{stage}": (lambda argv: 0)
        for survey in ("manufacturing", "services")
        for stage in ("fetch", "import", "enrichment", "enrichment_import")
    }
    tasks = build_refresh_tasks(
        fred_registry_args(skip_yahoo=True, skip_lumber=True, skip_ism=False),
        providers,
        openai_config={"api_key": "configured"},
        artifact_store=ArtifactStore(),
    )

    assert all(
        task["skip_reason"] is None
        for task in tasks
        if task["stage"] == "enrich"
    )


def test_official_registry_stages_consumer_census_nfib_and_fomc():
    providers = {
        "consumer_michigan_fetch": lambda argv: 0,
        "consumer_michigan_import": lambda argv: 0,
        "consumer_fred_fetch": lambda argv: 0,
        "consumer_fred_import": lambda argv: 0,
        "building_permits_fetch": lambda argv: 0,
        "building_permits_import": lambda argv: 0,
        "nfib_fetch": lambda argv: 0,
        "nfib_import": lambda argv: 0,
        "nfib_regional_fetch": lambda argv: 0,
        "nfib_regional_import": lambda argv: 0,
        "fomc_calendar_import": lambda argv: 0,
        "fomc_documents_fetch": lambda argv: 0,
        "fomc_documents_import": lambda argv: 0,
        "fomc_policy_tone_extract": lambda argv: 0,
        "fomc_policy_tone_import": lambda argv: 0,
        "fomc_minutes_extract": lambda argv: 0,
        "fomc_minutes_import": lambda argv: 0,
    }
    tasks = build_refresh_tasks(
        fred_registry_args(
            skip_consumer_sentiment=False,
            skip_building_permits=False,
            skip_fomc=False,
            skip_nfib_sbo=False,
            skip_nfib_sbo_regional=False,
            fomc_calendar_path=Path("calendar.json"),
        ),
        providers,
        openai_config={"api_key": "configured"},
        artifact_store={},
    )

    selected = {task["name"]: task for task in tasks}
    assert selected["consumer.michigan_fetch"]["resources"] == []
    assert selected["consumer.fred_fetch"]["resources"] == ["fred"]
    assert selected["consumer.fred_import"]["resources"] == ["sqlite_writer"]
    assert selected["census.building_permits_import"]["resources"] == [
        "sqlite_writer"
    ]
    assert selected["nfib.national_import"]["resources"] == ["sqlite_writer"]
    assert selected["nfib.regional_import"]["resources"] == ["sqlite_writer"]
    assert selected["fomc.documents_fetch"]["dependencies"] == [
        "fomc.calendar_import"
    ]
    assert selected["fomc.policy_tone_extract"]["dependencies"] == [
        "fomc.documents_import"
    ]
    assert selected["fomc.policy_tone_extract"]["resources"] == []
    assert selected["fomc.policy_tone_import"]["resources"] == ["sqlite_writer"]
