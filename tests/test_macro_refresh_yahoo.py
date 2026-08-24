from types import SimpleNamespace

from app.db import macro_indicators
from app.services import lumber_import
from app.services import macro_refresh_yahoo


def test_prepare_benchmarks_fetches_and_normalizes_without_benchmark_connection():
    calls = []

    def fetch(symbol, **kwargs):
        calls.append(("fetch", symbol, kwargs))

    rows = [{"date": "2026-08-20", "close": None, "adjusted_close": 10.5}]

    prepared = macro_refresh_yahoo.prepare_benchmarks(
        ["us_sp500"],
        fetch_market_data=fetch,
        load_market_rows=lambda symbol, interval, start_date=None: rows,
        latest_dates={"us_sp500": "2026-08-20"},
        today_date="2026-08-24",
    )

    assert prepared == [
        {
            "benchmark_id": "us_sp500",
            "symbol": "^GSPC",
            "rows": [
                {
                    "date": "2026-08-20",
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": 10.5,
                }
            ],
            "latest_date": "2026-08-20",
            "source": "yahoo_finance:^GSPC",
        }
    ]
    assert calls[0][0:2] == ("fetch", "^GSPC")


def test_persist_benchmarks_uses_prepared_rows_without_network(tmp_path):
    benchmark_db = tmp_path / "benchmark.sqlite"
    market_db = tmp_path / "market.sqlite"
    prepared = [
        {
            "benchmark_id": "us_sp500",
            "symbol": "^GSPC",
            "rows": [{"date": "2026-08-20", "close": 10.5}],
            "latest_date": "2026-08-20",
            "source": "yahoo_finance:^GSPC",
        }
    ]

    result = macro_refresh_yahoo.persist_benchmarks(
        prepared, benchmark_db_path=benchmark_db, market_db_path=market_db
    )

    assert result[0]["rows_upserted"] == 1
    assert not market_db.exists()


def test_prepare_and_persist_lumber_separate_commit(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con,
        {
            "series_id": "lumber",
            "title": "Lumber",
            "units": "USD/1,000 board feet",
            "source": "investing.com",
            "source_class": "free_web",
            "source_url": "https://example.test/lumber",
            "source_identifier": "lumber",
        },
        [{"date": "2022-08-08", "value": 621.0, "source": "investing.com"}],
    )
    payload = {
        "series": lumber_import.LUMBER_SERIES,
        "observations": [
            {"date": "2022-08-08", "value": 621.0, "source": "yahoo_finance"}
        ],
    }

    prepared = lumber_import.prepare_lumber(
        con, today_date="2026-08-24", initial=True, fetcher=lambda *_: payload
    )

    assert con.in_transaction is False
    assert prepared["payload"] == payload
    result = lumber_import.persist_lumber(con, prepared)
    assert result["observations"] == 1
    con.close()
