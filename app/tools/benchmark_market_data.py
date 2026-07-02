from app.db import benchmark_market_data
from app.db import market_data as market_data_db
from app.tools import market_data


BENCHMARK_YAHOO_SYMBOLS = [
    {
        "benchmark_id": "us_sp500",
        "symbol": "^GSPC",
        "interval": "1d",
    },
]

BENCHMARK_YAHOO_SYMBOLS_BY_ID = {
    config["benchmark_id"]: config for config in BENCHMARK_YAHOO_SYMBOLS
}


def benchmark_config(benchmark_id):
    normalized_id = benchmark_market_data.normalize_benchmark_id(benchmark_id)
    config = BENCHMARK_YAHOO_SYMBOLS_BY_ID.get(normalized_id)
    if not config:
        raise ValueError(f"benchmark refresh is unknown: {normalized_id}")
    return dict(config)


def yahoo_rows_to_benchmark_rows(rows):
    benchmark_rows = []
    for row in rows:
        close = row.get("close")
        if close is None:
            close = row.get("adjusted_close")
        if close is None:
            raise ValueError(f"benchmark row close is missing for {row.get('date')}")
        benchmark_rows.append(
            {
                "date": row["date"],
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": close,
            }
        )
    return benchmark_rows


class YahooBenchmarkFetcher:
    def __init__(
        self,
        benchmark_db_path=benchmark_market_data.DEFAULT_DB_PATH,
        market_db_path=market_data_db.DEFAULT_DB_PATH,
        fetch_market_data=market_data.fetch_market_data,
        load_market_rows=market_data_db.load_price_rows,
        today_date=None,
        refresh_days=1,
        overlap_days=5,
    ):
        self.benchmark_db_path = benchmark_db_path
        self.market_db_path = market_db_path
        self.fetch_market_data = fetch_market_data
        self.load_market_rows = load_market_rows
        self.today_date = today_date
        self.refresh_days = refresh_days
        self.overlap_days = overlap_days

    def refresh(self, benchmark_id):
        config = benchmark_config(benchmark_id)
        benchmark_con = benchmark_market_data.connect(self.benchmark_db_path)
        market_con = market_data_db.connect(self.market_db_path)
        try:
            latest_date = benchmark_market_data.latest_price_date(
                benchmark_con,
                config["benchmark_id"],
            )
            start_date = market_data_db.fetch_start_date(
                latest_date,
                self.today_date or market_data._today_iso(),
                overlap_days=self.overlap_days,
            )
            self.fetch_market_data(
                config["symbol"],
                period="max",
                interval=config["interval"],
                db_path=self.market_db_path,
                today_date=self.today_date,
                refresh_days=self.refresh_days,
                overlap_days=self.overlap_days,
            )
            yahoo_rows = self.load_market_rows(
                market_con,
                config["symbol"],
                config["interval"],
                start_date=start_date,
            )
            benchmark_rows = yahoo_rows_to_benchmark_rows(yahoo_rows)
            source = f"yahoo_finance:{config['symbol']}"
            rows_upserted = benchmark_market_data.upsert_benchmark_prices(
                benchmark_con,
                config["benchmark_id"],
                benchmark_rows,
                source=source,
            )
        finally:
            market_con.close()
            benchmark_con.close()
        return {
            "benchmark_id": config["benchmark_id"],
            "symbol": config["symbol"],
            "rows_upserted": rows_upserted,
            "latest_date": benchmark_rows[-1]["date"]
            if benchmark_rows
            else latest_date,
            "source": source,
        }


def refresh_benchmarks(
    benchmark_ids,
    benchmark_db_path=benchmark_market_data.DEFAULT_DB_PATH,
    market_db_path=market_data_db.DEFAULT_DB_PATH,
    today_date=None,
):
    fetcher = YahooBenchmarkFetcher(
        benchmark_db_path=benchmark_db_path,
        market_db_path=market_db_path,
        today_date=today_date,
    )
    return [fetcher.refresh(benchmark_id) for benchmark_id in benchmark_ids]
