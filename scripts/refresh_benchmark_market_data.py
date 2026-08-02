import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import benchmark_market_data
from app.db import market_data as market_data_db
from app.tools import benchmark_market_data as benchmark_market_data_tool


def _benchmark_ids_from_args(args):
    if args.all:
        return [
            config["benchmark_id"]
            for config in benchmark_market_data_tool.BENCHMARK_YAHOO_SYMBOLS
        ]
    if args.benchmark_id:
        return args.benchmark_id
    raise ValueError("use --benchmark-id or --all")


def main(argv=None, refresh_benchmarks=benchmark_market_data_tool.refresh_benchmarks):
    parser = argparse.ArgumentParser(description="Refresh benchmark market data")
    parser.add_argument("--benchmark-id", action="append")
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--benchmark-db-path",
        type=Path,
        default=benchmark_market_data.DEFAULT_DB_PATH,
    )
    parser.add_argument(
        "--market-db-path",
        type=Path,
        default=market_data_db.DEFAULT_DB_PATH,
    )
    parser.add_argument("--today-date")
    args = parser.parse_args(argv)
    try:
        benchmark_ids = _benchmark_ids_from_args(args)
        results = refresh_benchmarks(
            benchmark_ids,
            benchmark_db_path=args.benchmark_db_path,
            market_db_path=args.market_db_path,
            today_date=args.today_date,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for result in results:
        print(
            f"{result['benchmark_id']} {result['symbol']}: "
            f"{result['rows_upserted']} rows through {result['latest_date']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
