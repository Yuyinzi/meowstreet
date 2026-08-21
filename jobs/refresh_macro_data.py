import argparse
import sys
from datetime import datetime
from pathlib import Path

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


def _timestamp():
    return datetime.now().replace(microsecond=0).isoformat()


def _run_task(name, func, argv):
    try:
        exit_code = func(argv)
    except Exception as exc:
        return {"name": name, "status": "failed", "exit_code": 1, "error": str(exc)}
    if exit_code:
        return {
            "name": name,
            "status": "failed",
            "exit_code": int(exit_code),
            "error": f"exit code {exit_code}",
        }
    return {"name": name, "status": "ok", "exit_code": 0, "error": ""}


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
):
    tasks = []
    if benchmark_main is not None and not args.skip_yahoo:
        tasks.append(
            (
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
            )
        )
    if rates_main is not None and not args.skip_rates:
        tasks.append(("rates_fred", rates_main, ["--skip-credit-workbook"]))
    if consumer_main is not None and not args.skip_consumer_sentiment:
        cache_dir = _consumer_cache_dir()
        consumer_db_path = ROOT / "data" / "local_system" / "market_data.sqlite"
        tasks.append(
            (
                "consumer_sentiment",
                lambda argv: _combined_consumer_refresh(
                    consumer_main, cache_dir, consumer_db_path
                ),
                [],
            )
        )
    if m2_main is not None and not args.skip_m2:
        tasks.append(("m2_fred_fetch", m2_main, ["--fetch-fred-csv"]))
        tasks.append(("m2_fred_merge", m2_main, ["--fred-csv-merge"]))
    if macro_indicators_main is not None and not args.skip_macro_indicators:
        tasks.append(("macro_indicators_fred_fetch", macro_indicators_main, ["--fetch-fred-csv"]))
        tasks.append(("macro_indicators_fred_merge", macro_indicators_main, ["--fred-csv-merge"]))
    if building_permits_main is not None and not args.skip_building_permits:
        tasks.append(("building_permits_census", building_permits_main, []))
    if ism_reports_main is not None and not args.skip_ism:
        tasks.append(
            (
                "ism_manufacturing_official",
                ism_reports_main,
                ["--survey", "manufacturing", "--latest-only"],
            )
        )
        tasks.append(
            (
                "ism_services_official",
                ism_reports_main,
                ["--survey", "services", "--latest-only"],
            )
        )
    if gdp_main is not None and not args.skip_gdp:
        tasks.append(("gdp_fred_fetch", gdp_main, ["--fetch-fred-csv"]))
        tasks.append(("gdp_fred_merge", gdp_main, ["--us-csv-merge"]))
    if fomc_main is not None and not args.skip_fomc:
        calendar_path = _fomc_calendar_path(args)
        if calendar_path:
            tasks.extend(
                [
                    (
                        "fomc_calendar",
                        fomc_main,
                        ["--calendar-path", str(calendar_path)],
                    ),
                    ("fomc_documents", fomc_document_main, ["--document-type", "all"]),
                    ("fomc_policy_tone", fomc_policy_tone_main, ["--all"]),
                    ("fomc_minutes_structure", fomc_minutes_main, ["--all"]),
                ]
            )
    if nfib_main is not None and not args.skip_nfib_sbo:
        tasks.append(("nfib_sbo_official", nfib_main, []))
    if nfib_regional_main is not None and not args.skip_nfib_sbo_regional:
        tasks.append(("nfib_sbo_regional_official", nfib_regional_main, []))
    if main is not None and not args.skip_cyclical_commodities:
        tasks.append(("cyclical_commodities_official", main, []))
    if oil_main is not None and not args.skip_oil:
        tasks.append(("oil_official", oil_main, []))
    if lumber_main is not None and not args.skip_lumber:
        tasks.append(("lumber_yahoo", lumber_main, []))
    if shfe_copper_main is not None and not args.skip_shfe_copper:
        tasks.append(("shfe_copper", shfe_copper_main, ["--incremental"]))
    if dce_iron_ore_sina_main is not None and not args.skip_dce_iron_ore_sina:
        tasks.append(("dce_iron_ore_sina", dce_iron_ore_sina_main, []))
    if economic_confirmation_main is not None and not args.skip_economic_confirmation:
        tasks.append(("economic_confirmation_official", economic_confirmation_main, []))
    return tasks


def _print_result(result):
    if result["status"] == "ok":
        print(f"{result['name']}: ok")
    else:
        print(f"{result['name']}: failed - {result['error']}", file=sys.stderr)


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
    args = parser.parse_args(argv)
    print(f"macro data refresh started: {_timestamp()}")
    results = []
    for name, func, task_argv in _planned_tasks(
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
    ):
        result = _run_task(name, func, task_argv)
        results.append(result)
        _print_result(result)
        if result["status"] != "ok" and args.stop_on_error:
            break
    failed = [result for result in results if result["status"] != "ok"]
    status = "failed" if failed else "ok"
    print(f"macro data refresh completed: {status}")
    return 1 if failed else 0


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
