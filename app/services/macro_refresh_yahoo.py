from app.db import benchmark_market_data
from app.db import market_data
from app.tools import benchmark_market_data as benchmark_tool
from app.tools import market_data as market_data_tool


def prepare_benchmarks(
    benchmark_ids,
    *,
    fetch_market_data,
    load_market_rows,
    fetch_yahoo_chart_json=None,
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
            today_date or market_data_tool._today_iso(),
            overlap_days=overlap_days,
        )
        if fetch_yahoo_chart_json is None:
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
        else:
            payload = fetch_yahoo_chart_json(
                config["symbol"],
                start_date=start_date,
                end_date=market_data_tool._tomorrow_iso(
                    today_date or market_data_tool._today_iso()
                ),
                interval=config["interval"],
            )
            rows = market_data_tool.chart_payload_to_price_rows(
                payload, config["symbol"]
            )
        benchmark_rows = benchmark_tool.yahoo_rows_to_benchmark_rows(rows)
        item = {
            "benchmark_id": config["benchmark_id"],
            "symbol": config["symbol"],
            "rows": benchmark_rows,
            "latest_date": benchmark_rows[-1]["date"] if benchmark_rows else latest_date,
            "source": f"yahoo_finance:{config['symbol']}",
        }
        if fetch_yahoo_chart_json is not None:
            item["market_rows"] = rows
            item["interval"] = config["interval"]
        prepared.append(item)
    return prepared


def persist_benchmarks(payloads, *, benchmark_db_path, market_db_path):
    market_con = None
    if any("market_rows" in payload for payload in payloads):
        market_con = market_data.connect(market_db_path)
    con = benchmark_market_data.connect(benchmark_db_path)
    try:
        results = []
        for payload in payloads:
            if market_con is not None:
                market_data.save_price_rows(
                    market_con,
                    payload["symbol"],
                    payload.get("interval", "1d"),
                    payload.get("market_rows", []),
                )
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
        if market_con is not None:
            market_con.close()
