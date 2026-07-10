import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import import_gdp_market_relationships
from scripts import import_m2_money_supply
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


def _planned_tasks(args, benchmark_main, rates_main, m2_main, gdp_main):
    tasks = []
    if not args.skip_yahoo:
        tasks.append(("benchmark_yahoo", benchmark_main, ["--all"]))
    if not args.skip_rates:
        tasks.append(("rates_fred", rates_main, ["--skip-credit-workbook"]))
    if not args.skip_m2:
        tasks.append(("m2_fred_fetch", m2_main, ["--fetch-fred-csv"]))
        tasks.append(("m2_fred_merge", m2_main, ["--fred-csv-merge"]))
    if not args.skip_gdp:
        tasks.append(("gdp_fred_fetch", gdp_main, ["--fetch-fred-csv"]))
        tasks.append(("gdp_fred_merge", gdp_main, ["--us-csv-merge"]))
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
    m2_main=import_m2_money_supply.main,
    gdp_main=import_gdp_market_relationships.main,
):
    parser = argparse.ArgumentParser(description="Refresh macro dashboard market data")
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--skip-rates", action="store_true")
    parser.add_argument("--skip-m2", action="store_true")
    parser.add_argument("--skip-gdp", action="store_true")
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
        m2_main,
        gdp_main,
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
