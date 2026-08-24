from app.db import benchmark_market_data
from app.db import market_data
from app.tools import benchmark_market_data as benchmark_tool


def prepare_benchmarks(
    benchmark_ids,
    *,
    fetch_market_data,
    load_market_rows,
    today_date=None,
    latest_dates=None,
    refresh_days=1,
    overlap_days=5,
):
    latest_dates = latest_dates or {}
    prepared = []
    for benchmark_id in benchmark_ids:
        config = benchmark_tool.benchmark_config(benchmark_id)
        latest_date = latest_dates.get(config["benchmark_id"])
        start_date = market_data.fetch_start_date(
            latest_date,
            today_date or market_data._today_iso(),
            overlap_days=overlap_days,
        )
        fetch_market_data(
            config["symbol"],
            period="max",
            interval=config["interval"],
            today_date=today_date,
            refresh_days=refresh_days,
            overlap_days=overlap_days,
        )
        rows = load_market_rows(
            config["symbol"], config["interval"], start_date=start_date
        )
        benchmark_rows = benchmark_tool.yahoo_rows_to_benchmark_rows(rows)
        prepared.append(
            {
                "benchmark_id": config["benchmark_id"],
                "symbol": config["symbol"],
                "rows": benchmark_rows,
                "latest_date": benchmark_rows[-1]["date"] if benchmark_rows else latest_date,
                "source": f"yahoo_finance:{config['symbol']}",
            }
        )
    return prepared


def persist_benchmarks(payloads, *, benchmark_db_path, market_db_path):
    del market_db_path
    con = benchmark_market_data.connect(benchmark_db_path)
    try:
        results = []
        for payload in payloads:
            rows_upserted = benchmark_market_data.upsert_benchmark_prices(
                con,
                payload["benchmark_id"],
                payload["rows"],
                source=payload["source"],
            )
            results.append(
                {
                    "benchmark_id": payload["benchmark_id"],
                    "symbol": payload["symbol"],
                    "rows_upserted": rows_upserted,
                    "latest_date": payload["latest_date"],
                    "source": payload["source"],
                }
            )
        return results
    finally:
        con.close()
