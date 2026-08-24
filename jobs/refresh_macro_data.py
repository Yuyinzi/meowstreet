import argparse
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import fetch_fomc_documents
from scripts import fetch_ism_reports
from scripts import generate_fomc_minutes_structure
from scripts import generate_fomc_policy_tone
from scripts import import_consumer_sentiment
from scripts import import_economic_confirmation
from scripts import import_fomc_calendar
from scripts import import_gdp_market_relationships
from scripts import import_m2_money_supply
from scripts import import_nfib_sbet
from scripts import import_nfib_sbet_regional
from scripts import import_tracked_commodities
from scripts import import_cyclical_commodities
from scripts import import_dce_iron_ore_sina
from scripts import import_lumber
from scripts import import_oil
from scripts import import_shfe_copper
from scripts import import_us_building_permits
from scripts import import_us_macro_indicators
from scripts import refresh_benchmark_market_data
from scripts import refresh_us_rates_liquidity

from app import llm


def _timestamp():
    return datetime.now().replace(microsecond=0).isoformat()


def _task(name, func, argv, skip_reason=None):
    return {
        "name": name,
        "func": func,
        "argv": list(argv),
        "skip_reason": skip_reason,
    }


def _openai_enrichment_skip_reason(config):
    if config.get("api_key"):
        return None
    return "OPENAI_API_KEY is not configured"


def _run_task(task):
    if task["skip_reason"]:
        return {
            "name": task["name"],
            "status": "skipped",
            "exit_code": 0,
            "error": task["skip_reason"],
            "stdout": "",
            "stderr": "",
        }
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = task["func"](task["argv"])
    except Exception as exc:
        exit_code = 1
        error = str(exc)
    else:
        error = "" if not exit_code else f"exit code {exit_code}"
    return {
        "name": task["name"],
        "status": "ok" if not exit_code else "failed",
        "exit_code": int(exit_code or 0),
        "error": error,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def _result_counts(results):
    return {
        "ok": sum(result["status"] == "ok" for result in results),
        "skipped": sum(result["status"] == "skipped" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
    }


def _fomc_calendar_path(args):
    configured_path = (
        args.fomc_calendar_path or import_fomc_calendar.DEFAULT_CALENDAR_PATH
    )
    path = Path(configured_path)
    return path if path.exists() else None


def _consumer_cache_dir():
    return ROOT / "data" / "local_system" / "consumer_cache"


def _combined_consumer_refresh(consumer_main, cache_dir, db_path):
    fetch_exit = consumer_main(["--fetch-michigan-csv", str(cache_dir)])
    if fetch_exit:
        return fetch_exit
    table_1 = cache_dir / "table_1.csv"
    table_5 = cache_dir / "table_5.csv"
    import_exit = consumer_main(
        ["--michigan-csv-import", str(table_1), str(table_5), "--db-path", str(db_path)]
    )
    if import_exit:
        return import_exit
    front_page_exit = consumer_main(
        ["--fetch-front-page-import", "--db-path", str(db_path)]
    )
    if front_page_exit:
        return front_page_exit
    fred_fetch_exit = consumer_main(["--fetch-fred-csv", str(cache_dir)])
    if fred_fetch_exit:
        return fred_fetch_exit
    return consumer_main(
        ["--fred-csv-import", str(cache_dir), "--db-path", str(db_path)]
    )


def _planned_tasks(
    args,
    benchmark_main=None,
    rates_main=None,
    consumer_main=None,
    m2_main=None,
    building_permits_main=None,
    ism_reports_main=None,
    gdp_main=None,
    macro_indicators_main=None,
    fomc_main=None,
    fomc_document_main=None,
    fomc_policy_tone_main=None,
    fomc_minutes_main=None,
    nfib_main=None,
    nfib_regional_main=None,
    main=None,
    oil_main=None,
    tracked_commodities_main=None,
    lumber_main=None,
    shfe_copper_main=None,
    dce_iron_ore_sina_main=None,
    economic_confirmation_main=None,
    openai_config=None,
):
    tasks = []
    if benchmark_main is not None and not args.skip_yahoo:
        tasks.append(_task(
            "benchmark_yahoo",
            benchmark_main,
            [
                "--benchmark-id",
                "us_sp500",
                "--benchmark-id",
                "us_nasdaq_100",
                "--benchmark-id",
                "us_nasdaq_composite",
                "--benchmark-id",
                "us_djia",
            ],
        ))
    if rates_main is not None and not args.skip_rates:
        tasks.append(_task("rates_fred", rates_main, []))
    if consumer_main is not None and not args.skip_consumer_sentiment:
        cache_dir = _consumer_cache_dir()
        consumer_db_path = ROOT / "data" / "local_system" / "market_data.sqlite"
        tasks.append(_task(
            "consumer_sentiment",
            lambda argv: _combined_consumer_refresh(
                consumer_main, cache_dir, consumer_db_path
            ),
            [],
        ))
    if m2_main is not None and not args.skip_m2:
        tasks.append(_task("m2_fred_fetch", m2_main, ["--fetch-fred-csv"]))
        tasks.append(_task("m2_fred_merge", m2_main, ["--fred-csv-merge"]))
    if macro_indicators_main is not None and not args.skip_macro_indicators:
        tasks.append(_task("macro_indicators_fred_fetch", macro_indicators_main, ["--fetch-fred-csv"]))
        tasks.append(_task("macro_indicators_fred_merge", macro_indicators_main, ["--fred-csv-merge"]))
    if building_permits_main is not None and not args.skip_building_permits:
        tasks.append(_task("building_permits_census", building_permits_main, []))
    if ism_reports_main is not None and not args.skip_ism:
        enrichment_skip_reason = _openai_enrichment_skip_reason(openai_config or {})
        tasks.extend(
            [
                _task(
                    "ism_manufacturing_official",
                    ism_reports_main,
                    [
                        "--survey",
                        "manufacturing",
                        "--latest-only",
                        "--core-only",
                    ],
                ),
                _task(
                    "ism_manufacturing_ai_enrichment",
                    ism_reports_main,
                    [
                        "--survey",
                        "manufacturing",
                        "--latest-only",
                        "--enrichment-only",
                    ],
                    enrichment_skip_reason,
                ),
                _task(
                    "ism_services_official",
                    ism_reports_main,
                    ["--survey", "services", "--latest-only", "--core-only"],
                ),
                _task(
                    "ism_services_ai_enrichment",
                    ism_reports_main,
                    [
                        "--survey",
                        "services",
                        "--latest-only",
                        "--enrichment-only",
                    ],
                    enrichment_skip_reason,
                ),
            ]
        )
    if gdp_main is not None and not args.skip_gdp:
        tasks.append(_task("gdp_fred_fetch", gdp_main, ["--fetch-fred-csv"]))
        tasks.append(_task("gdp_fred_merge", gdp_main, ["--us-csv-merge"]))
    if fomc_main is not None and not args.skip_fomc:
        calendar_path = _fomc_calendar_path(args)
        if calendar_path:
            tasks.extend(
                [
                    _task(
                        "fomc_calendar",
                        fomc_main,
                        ["--calendar-path", str(calendar_path)],
                    ),
                    _task("fomc_documents", fomc_document_main, ["--document-type", "all"]),
                    _task(
                        "fomc_policy_tone",
                        fomc_policy_tone_main,
                        ["--all"]
                        + (["--verbose"] if getattr(args, "verbose", False) else []),
                    ),
                    _task(
                        "fomc_minutes_structure",
                        fomc_minutes_main,
                        ["--all"]
                        + (["--verbose"] if getattr(args, "verbose", False) else []),
                    ),
                ]
            )
    if nfib_main is not None and not args.skip_nfib_sbo:
        tasks.append(_task("nfib_sbo_official", nfib_main, []))
    if nfib_regional_main is not None and not args.skip_nfib_sbo_regional:
        tasks.append(_task("nfib_sbo_regional_official", nfib_regional_main, []))
    if main is not None and not args.skip_cyclical_commodities:
        tasks.append(_task("cyclical_commodities_official", main, []))
    if oil_main is not None and not args.skip_oil:
        tasks.append(_task("oil_official", oil_main, []))
    if lumber_main is not None and not args.skip_lumber:
        tasks.append(_task("lumber_yahoo", lumber_main, []))
    if shfe_copper_main is not None and not getattr(args, "skip_shfe_copper", False):
        tasks.append(_task("shfe_copper", shfe_copper_main, ["--incremental"]))
    if dce_iron_ore_sina_main is not None and not args.skip_dce_iron_ore_sina:
        tasks.append(_task("dce_iron_ore_sina", dce_iron_ore_sina_main, []))
    if economic_confirmation_main is not None and not args.skip_economic_confirmation:
        tasks.append(_task("economic_confirmation_official", economic_confirmation_main, []))
    return tasks


def _write_report_text(text, *, file, progress):
    if not text:
        return
    if getattr(progress, "disable", False):
        print(text, end="", file=file)
        return
    for line in text.splitlines():
        progress.write(line, file=file)


def _write_report_line(message, *, file, progress):
    if getattr(progress, "disable", False):
        print(message, file=file)
    else:
        progress.write(message, file=file)


def _report_result(result, *, verbose, progress):
    replay_output = verbose or result["status"] == "failed"
    if replay_output:
        _write_report_text(result["stdout"], file=sys.stdout, progress=progress)
        _write_report_text(result["stderr"], file=sys.stderr, progress=progress)
    if result["status"] == "ok":
        message = f"{result['name']}: ok"
        file = sys.stdout
    elif result["status"] == "skipped":
        message = f"{result['name']}: skipped - {result['error']}"
        file = sys.stdout
    else:
        message = f"{result['name']}: failed - {result['error']}"
        file = sys.stderr
    _write_report_line(message, file=file, progress=progress)


def run(
    argv=None,
    benchmark_main=None,
    rates_main=None,
    consumer_main=None,
    m2_main=None,
    building_permits_main=None,
    ism_reports_main=None,
    gdp_main=None,
    macro_indicators_main=None,
    fomc_main=None,
    fomc_document_main=None,
    fomc_policy_tone_main=None,
    fomc_minutes_main=None,
    nfib_main=None,
    nfib_regional_main=None,
    main=None,
    oil_main=None,
    tracked_commodities_main=None,
    lumber_main=None,
    shfe_copper_main=None,
    dce_iron_ore_sina_main=None,
    economic_confirmation_main=None,
    progress_factory=tqdm,
    openai_config=None,
):
    parser = argparse.ArgumentParser(description="Refresh macro dashboard market data")
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--skip-rates", action="store_true")
    parser.add_argument("--skip-consumer-sentiment", action="store_true")
    parser.add_argument("--skip-m2", action="store_true")
    parser.add_argument("--skip-macro-indicators", action="store_true")
    parser.add_argument("--skip-building-permits", action="store_true")
    parser.add_argument("--skip-ism", action="store_true")
    parser.add_argument("--skip-gdp", action="store_true")
    parser.add_argument("--skip-fomc", action="store_true")
    parser.add_argument("--skip-nfib-sbo", action="store_true")
    parser.add_argument("--skip-nfib-sbo-regional", action="store_true")
    parser.add_argument("--skip-tracked-commodities", action="store_true")
    parser.add_argument("--skip-cyclical-commodities", action="store_true")
    parser.add_argument("--skip-oil", action="store_true")
    parser.add_argument("--skip-lumber", action="store_true")
    parser.add_argument("--skip-shfe-copper", action="store_true")
    parser.add_argument("--skip-dce-iron-ore-sina", action="store_true")
    parser.add_argument("--skip-economic-confirmation", action="store_true")
    parser.add_argument("--fomc-calendar-path", type=Path)
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="stop running remaining refresh tasks after the first failure",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if openai_config is None:
        openai_config = llm.load_openai_config(args, root=ROOT)
    print(f"macro data refresh started: {_timestamp()}")
    tasks = _planned_tasks(
        args,
        benchmark_main,
        rates_main,
        consumer_main,
        m2_main,
        building_permits_main,
        ism_reports_main,
        gdp_main,
        macro_indicators_main,
        fomc_main,
        fomc_document_main,
        fomc_policy_tone_main,
        fomc_minutes_main,
        nfib_main,
        nfib_regional_main,
        main,
        oil_main,
        tracked_commodities_main,
        lumber_main,
        shfe_copper_main,
        dce_iron_ore_sina_main,
        economic_confirmation_main,
        openai_config,
    )
    results = []
    with progress_factory(
        total=len(tasks),
        disable=not sys.stderr.isatty(),
        file=sys.stderr,
    ) as progress:
        for task in tasks:
            progress.set_description_str(task["name"])
            result = _run_task(task)
            _report_result(result, verbose=args.verbose, progress=progress)
            result["stdout"] = ""
            result["stderr"] = ""
            results.append(result)
            progress.set_postfix(_result_counts(results), refresh=False)
            progress.update(1)
            if result["status"] == "failed" and args.stop_on_error:
                break
    counts = _result_counts(results)
    print(
        "macro data refresh completed: "
        f"ok={counts['ok']} skipped={counts['skipped']} failed={counts['failed']}"
    )
    return 1 if counts["failed"] else 0


def main(argv=None):
    return run(
        argv,
        benchmark_main=refresh_benchmark_market_data.main,
        rates_main=refresh_us_rates_liquidity.main,
        consumer_main=import_consumer_sentiment.main,
        m2_main=import_m2_money_supply.main,
        building_permits_main=import_us_building_permits.main,
        ism_reports_main=fetch_ism_reports.main,
        gdp_main=import_gdp_market_relationships.main,
        macro_indicators_main=import_us_macro_indicators.main,
        fomc_main=import_fomc_calendar.main,
        fomc_document_main=fetch_fomc_documents.main,
        fomc_policy_tone_main=generate_fomc_policy_tone.main,
        fomc_minutes_main=generate_fomc_minutes_structure.main,
        nfib_main=import_nfib_sbet.main,
        nfib_regional_main=import_nfib_sbet_regional.main,
        main=import_cyclical_commodities.main,
        oil_main=import_oil.main,
        tracked_commodities_main=import_tracked_commodities.main,
        lumber_main=import_lumber.main,
        shfe_copper_main=import_shfe_copper.main,
        dce_iron_ore_sina_main=import_dce_iron_ore_sina.main,
        economic_confirmation_main=import_economic_confirmation.main,
    )


if __name__ == "__main__":
    raise SystemExit(main())
