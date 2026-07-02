from app.db import benchmark_market_data


def price_rows():
    return [
        {
            "date": "2020-03-20",
            "open": 2431.94,
            "high": 2453.01,
            "low": 2295.56,
            "close": 2304.92,
        },
        {
            "date": "2020-03-23",
            "open": 2290.71,
            "high": 2300.73,
            "low": 2191.86,
            "close": 2237.40,
        },
    ]


def test_save_and_load_benchmark_prices(tmp_path):
    con = benchmark_market_data.connect(tmp_path / "benchmark_market_data.sqlite")

    saved = benchmark_market_data.save_benchmark_prices(
        con,
        " us_sp500 ",
        price_rows(),
        source="Bull_Bear_Markets.xlsx",
    )

    assert saved == 2
    assert benchmark_market_data.latest_price_date(con, "US_SP500") == "2020-03-23"
    assert benchmark_market_data.load_price_rows(con, "us_sp500") == price_rows()


def test_save_benchmark_prices_replaces_existing_rows(tmp_path):
    con = benchmark_market_data.connect(tmp_path / "benchmark_market_data.sqlite")
    benchmark_market_data.save_benchmark_prices(
        con,
        "us_sp500",
        price_rows(),
        source="Bull_Bear_Markets.xlsx",
    )

    replacement = [
        {
            "date": "2020-03-23",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
        }
    ]

    saved = benchmark_market_data.save_benchmark_prices(
        con,
        "us_sp500",
        replacement,
        source="manual",
    )

    assert saved == 1
    assert benchmark_market_data.load_price_rows(con, "us_sp500") == replacement


def test_normalize_benchmark_id_rejects_blank():
    try:
        benchmark_market_data.normalize_benchmark_id(" ")
    except ValueError as exc:
        assert str(exc) == "benchmark id is required"
    else:
        raise AssertionError("expected ValueError")
