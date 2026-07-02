import sqlite3

import pytest

from app.db import benchmark_market_data
from app.tools import benchmark_market_data as benchmark_market_data_tool


def cached_yahoo_rows():
    return [
        {
            "date": "2021-10-12",
            "open": 4368.31,
            "high": 4374.89,
            "low": 4342.09,
            "close": 4350.65,
            "adjusted_close": 4350.65,
            "volume": 100,
        },
        {
            "date": "2021-10-13",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "adjusted_close": 4363.8,
            "volume": 100,
        },
    ]


def test_benchmark_registry_maps_sp500_to_yahoo_symbol():
    config = benchmark_market_data_tool.benchmark_config("us_sp500")

    assert config == {
        "benchmark_id": "us_sp500",
        "symbol": "^GSPC",
        "interval": "1d",
    }


def test_benchmark_config_rejects_unknown_id():
    with pytest.raises(ValueError, match="benchmark refresh is unknown: unknown"):
        benchmark_market_data_tool.benchmark_config("unknown")


def test_yahoo_rows_to_benchmark_rows_uses_close_then_adjusted_close():
    rows = benchmark_market_data_tool.yahoo_rows_to_benchmark_rows(cached_yahoo_rows())

    assert rows == [
        {
            "date": "2021-10-12",
            "open": 4368.31,
            "high": 4374.89,
            "low": 4342.09,
            "close": 4350.65,
        },
        {
            "date": "2021-10-13",
            "open": None,
            "high": None,
            "low": None,
            "close": 4363.8,
        },
    ]


def test_yahoo_rows_to_benchmark_rows_rejects_rows_without_close_values():
    with pytest.raises(
        ValueError, match="benchmark row close is missing for 2021-10-12"
    ):
        benchmark_market_data_tool.yahoo_rows_to_benchmark_rows(
            [
                {
                    "date": "2021-10-12",
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "adjusted_close": None,
                    "volume": None,
                }
            ]
        )


def test_yahoo_benchmark_fetcher_refreshes_sp500_from_market_data_cache(tmp_path):
    benchmark_db_path = tmp_path / "benchmark_market_data.sqlite"
    market_db_path = tmp_path / "market_data.sqlite"
    calls = []

    con = benchmark_market_data.connect(benchmark_db_path)
    try:
        benchmark_market_data.upsert_benchmark_prices(
            con,
            "us_sp500",
            [
                {
                    "date": "2021-10-11",
                    "open": 4300.0,
                    "high": 4545.85,
                    "low": 4300.0,
                    "close": 4361.19,
                }
            ],
            source="seed",
        )
    finally:
        con.close()

    def fake_fetch_market_data(
        symbol,
        period="max",
        interval="1d",
        fetch_json=None,
        db_path=None,
        today_date=None,
        refresh_days=1,
        overlap_days=5,
    ):
        calls.append(
            {
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "db_path": db_path,
                "today_date": today_date,
                "refresh_days": refresh_days,
                "overlap_days": overlap_days,
            }
        )
        return {"symbol": symbol}

    def fake_load_price_rows(con, symbol, interval, start_date=None):
        assert symbol == "^GSPC"
        assert interval == "1d"
        assert start_date == "2021-10-06"
        return cached_yahoo_rows()

    fetcher = benchmark_market_data_tool.YahooBenchmarkFetcher(
        benchmark_db_path=benchmark_db_path,
        market_db_path=market_db_path,
        fetch_market_data=fake_fetch_market_data,
        load_market_rows=fake_load_price_rows,
        today_date="2021-10-14",
    )

    result = fetcher.refresh("us_sp500")

    assert result == {
        "benchmark_id": "us_sp500",
        "symbol": "^GSPC",
        "rows_upserted": 2,
        "latest_date": "2021-10-13",
        "source": "yahoo_finance:^GSPC",
    }
    assert calls == [
        {
            "symbol": "^GSPC",
            "period": "max",
            "interval": "1d",
            "db_path": market_db_path,
            "today_date": "2021-10-14",
            "refresh_days": 1,
            "overlap_days": 5,
        }
    ]

    con = benchmark_market_data.connect(benchmark_db_path)
    try:
        assert benchmark_market_data.load_price_rows(con, "us_sp500") == [
            {
                "date": "2021-10-11",
                "open": 4300.0,
                "high": 4545.85,
                "low": 4300.0,
                "close": 4361.19,
            },
            {
                "date": "2021-10-12",
                "open": 4368.31,
                "high": 4374.89,
                "low": 4342.09,
                "close": 4350.65,
            },
            {
                "date": "2021-10-13",
                "open": None,
                "high": None,
                "low": None,
                "close": 4363.8,
            },
        ]
    finally:
        con.close()


def test_yahoo_benchmark_fetcher_upserts_without_replacing_existing_history(tmp_path):
    benchmark_db_path = tmp_path / "benchmark_market_data.sqlite"
    con = benchmark_market_data.connect(benchmark_db_path)
    try:
        benchmark_market_data.replace_benchmark_prices(
            con,
            "us_sp500",
            [
                {
                    "date": "2021-10-11",
                    "open": 4300.0,
                    "high": 4545.85,
                    "low": 4300.0,
                    "close": 4361.19,
                }
            ],
            source="Bull_Bear_Markets.xlsx",
        )
    finally:
        con.close()

    fetcher = benchmark_market_data_tool.YahooBenchmarkFetcher(
        benchmark_db_path=benchmark_db_path,
        market_db_path=tmp_path / "market_data.sqlite",
        fetch_market_data=lambda *args, **kwargs: {"symbol": "^GSPC"},
        load_market_rows=lambda con, symbol, interval, start_date=None: (
            cached_yahoo_rows()
        ),
        today_date="2021-10-14",
    )

    fetcher.refresh("us_sp500")

    con = benchmark_market_data.connect(benchmark_db_path)
    try:
        dates = [
            row["date"]
            for row in benchmark_market_data.load_price_rows(con, "us_sp500")
        ]
    finally:
        con.close()

    assert dates == ["2021-10-11", "2021-10-12", "2021-10-13"]
