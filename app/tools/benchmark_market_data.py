from app.db import benchmark_market_data
from app.db import market_data as market_data_db
from app.tools import market_data


BENCHMARK_YAHOO_SYMBOLS = [
    {
        "benchmark_id": "us_sp500",
        "symbol": "^GSPC",
        "interval": "1d",
    },
    {
        "benchmark_id": "us_nasdaq_100",
        "symbol": "^NDX",
        "interval": "1d",
    },
    {
        "benchmark_id": "us_nasdaq_composite",
        "symbol": "^IXIC",
        "interval": "1d",
    },
    {
        "benchmark_id": "us_djia",
        "symbol": "^DJI",
        "interval": "1d",
    },
    {
        "benchmark_id": "europe_stoxx_50",
        "symbol": "^STOXX50E",
        "interval": "1d",
    },
    {
        "benchmark_id": "europe_stoxx_600",
        "symbol": "^STOXX",
        "interval": "1d",
    },
    {
        "benchmark_id": "uk_ftse_100",
        "symbol": "^FTSE",
        "interval": "1d",
    },
    {
        "benchmark_id": "uk_ftse_250",
        "symbol": "^FTMC",
        "interval": "1d",
    },
    {
        "benchmark_id": "uk_ftse_350",
        "symbol": "^FTLC",
        "interval": "1d",
    },
    {
        "benchmark_id": "germany_dax_40",
        "symbol": "^GDAXI",
        "interval": "1d",
    },
    {
        "benchmark_id": "hong_kong_hsi",
        "symbol": "^HSI",
        "interval": "1d",
    },
    {
        "benchmark_id": "hong_kong_hscei",
        "symbol": "^HSCE",
        "interval": "1d",
    },
    {
        "benchmark_id": "japan_nikkei_225",
        "symbol": "^N225",
        "interval": "1d",
    },
    {
        "benchmark_id": "australia_asx_200",
        "symbol": "^AXJO",
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
            from app.services import macro_refresh_yahoo

            prepared = macro_refresh_yahoo.prepare_benchmarks(
                [benchmark_id],
                fetch_market_data=lambda symbol, **kwargs: self.fetch_market_data(
                    symbol, db_path=self.market_db_path, **kwargs
                ),
                load_market_rows=lambda symbol, interval, start_date=None: self.load_market_rows(
                    market_con, symbol, interval, start_date=start_date
                ),
                today_date=self.today_date,
                latest_dates={config["benchmark_id"]: latest_date},
                refresh_days=self.refresh_days,
                overlap_days=self.overlap_days,
            )
        finally:
            market_con.close()
            benchmark_con.close()
        return macro_refresh_yahoo.persist_benchmarks(
            prepared,
            benchmark_db_path=self.benchmark_db_path,
            market_db_path=self.market_db_path,
        )[0]


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
