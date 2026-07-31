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
from scripts import import_fomc_calendar
from scripts import import_gdp_market_relationships
from scripts import import_ism_manufacturing
from scripts import import_ism_services
from scripts import import_m2_money_supply
from scripts import import_nfib_sbet
from scripts import import_nfib_sbet_regional
from scripts import import_tracked_commodities
from scripts import import_cyclical_commodities
from scripts import import_lumber
from scripts import import_oil
from scripts import import_shfe_copper
from scripts import import_us_building_permits
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
    fred_fetch_exit = consumer_main(["--fetch-fred-csv", str(cache_dir)])
    if fred_fetch_exit:
        return fred_fetch_exit
    return consumer_main(
        ["--fred-csv-import", str(cache_dir), "--db-path", str(db_path)]
    )


def _planned_tasks(
    args,
    benchmark_main,
    rates_main,
    consumer_main,
    m2_main,
    building_permits_main,
    ism_main,
    ism_services_main,
    ism_reports_main,
    gdp_main,
    fomc_main=import_fomc_calendar.main,
    fomc_document_main=fetch_fomc_documents.main,
    fomc_policy_tone_main=generate_fomc_policy_tone.main,
    fomc_minutes_main=generate_fomc_minutes_structure.main,
    nfib_main=import_nfib_sbet.main,
    nfib_regional_main=import_nfib_sbet_regional.main,
    main=None,
    oil_main=None,
    tracked_commodities_main=None,
    lumber_main=import_lumber.main,
    shfe_copper_main=None,
):
    tasks = []
    if not args.skip_yahoo:
        tasks.append(("benchmark_yahoo", benchmark_main, ["--all"]))
    if not args.skip_rates:
        tasks.append(("rates_fred", rates_main, ["--skip-credit-workbook"]))
    if not args.skip_consumer_sentiment:
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
    if not args.skip_m2:
        tasks.append(("m2_fred_fetch", m2_main, ["--fetch-fred-csv"]))
        tasks.append(("m2_fred_merge", m2_main, ["--fred-csv-merge"]))
    if not args.skip_building_permits:
        tasks.append(("building_permits_census", building_permits_main, []))
    if not args.skip_ism:
        tasks.append(("ism_manufacturing", ism_main, []))
        tasks.append(
            (
                "ism_manufacturing_official",
                ism_reports_main,
                ["--survey", "manufacturing", "--latest-only"],
            )
        )
        tasks.append(("ism_services", ism_services_main, []))
        tasks.append(
            (
                "ism_services_official",
                ism_reports_main,
                ["--survey", "services", "--latest-only"],
            )
        )
    if not args.skip_gdp:
        tasks.append(("gdp_fred_fetch", gdp_main, ["--fetch-fred-csv"]))
        tasks.append(("gdp_fred_merge", gdp_main, ["--us-csv-merge"]))
    if not args.skip_fomc:
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
    if not args.skip_nfib_sbo:
        tasks.append(("nfib_sbo_official", nfib_main, []))
    if not args.skip_nfib_sbo_regional:
        tasks.append(("nfib_sbo_regional_official", nfib_regional_main, []))
    if main is not None and not args.skip_cyclical_commodities:
        tasks.append(("cyclical_commodities_official", main, []))
    if oil_main is not None and not args.skip_oil:
        tasks.append(("oil_official", oil_main, []))
    if not args.skip_lumber:
        tasks.append(("lumber_yahoo", lumber_main, []))
    if shfe_copper_main is not None and not args.skip_shfe_copper:
        tasks.append(("shfe_copper", shfe_copper_main, ["--incremental"]))
    return tasks


def _print_result(result):
    if result["status"] == "ok":
        print(f"{result['name']}: ok")
    else:
        print(f"{result['name']}: failed - {result['error']}", file=sys.stderr)


def main(
    argv=None,
    benchmark_main=refresh_benchmark_market_data.main,
    rates_main=refresh_us_rates_liquidity.main,
    consumer_main=import_consumer_sentiment.main,
    m2_main=import_m2_money_supply.main,
    building_permits_main=import_us_building_permits.main,
    ism_main=import_ism_manufacturing.main,
    ism_services_main=import_ism_services.main,
    ism_reports_main=fetch_ism_reports.main,
    gdp_main=import_gdp_market_relationships.main,
    fomc_main=import_fomc_calendar.main,
    fomc_document_main=fetch_fomc_documents.main,
    fomc_policy_tone_main=generate_fomc_policy_tone.main,
    fomc_minutes_main=generate_fomc_minutes_structure.main,
    nfib_main=import_nfib_sbet.main,
    nfib_regional_main=import_nfib_sbet_regional.main,
    main=None,
    oil_main=None,
    tracked_commodities_main=None,
    lumber_main=import_lumber.main,
    shfe_copper_main=None,
):
    if main is None:
        main = import_cyclical_commodities.main
    if oil_main is None:
        oil_main = import_oil.main
    if tracked_commodities_main is None:
        tracked_commodities_main = import_tracked_commodities.main
    if shfe_copper_main is None:
        shfe_copper_main = import_shfe_copper.main
    parser = argparse.ArgumentParser(description="Refresh macro dashboard market data")
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--skip-rates", action="store_true")
    parser.add_argument("--skip-consumer-sentiment", action="store_true")
    parser.add_argument("--skip-m2", action="store_true")
    parser.add_argument("--skip-building-permits", action="store_true")
    parser.add_argument("--skip-ism", action="store_true")
    parser.add_argument("--skip-gdp", action="store_true")
    parser.add_argument("--skip-fomc", action="store_true")
    parser.add_argument("--skip-nfib-sbo", action="store_true")
    parser.add_argument("--skip-nfib-sbo-regional", action="store_true")
    parser.add_argument("--skip-cyclical-commodities", action="store_true")
    parser.add_argument("--skip-oil", action="store_true")
    parser.add_argument("--skip-method-commodities", action="store_true")
    parser.add_argument("--skip-lumber", action="store_true")
    parser.add_argument("--skip-shfe-copper", action="store_true")
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
        ism_main,
        ism_services_main,
        ism_reports_main,
        gdp_main,
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


if __name__ == "__main__":
    raise SystemExit(main())
