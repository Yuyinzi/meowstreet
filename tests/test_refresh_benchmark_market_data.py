import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import refresh_benchmark_market_data


def test_main_refreshes_one_benchmark(capsys):
    calls = []

    def fake_refresh_benchmarks(
        benchmark_ids, benchmark_db_path, market_db_path, today_date
    ):
        calls.append(
            {
                "benchmark_ids": benchmark_ids,
                "benchmark_db_path": benchmark_db_path,
                "market_db_path": market_db_path,
                "today_date": today_date,
            }
        )
        return [
            {
                "benchmark_id": "us_sp500",
                "symbol": "^GSPC",
                "rows_upserted": 2,
                "latest_date": "2021-10-13",
                "source": "yahoo_finance:^GSPC",
            }
        ]

    exit_code = refresh_benchmark_market_data.main(
        [
            "--benchmark-id",
            "us_sp500",
            "--benchmark-db-path",
            "benchmark.sqlite",
            "--market-db-path",
            "market.sqlite",
            "--today-date",
            "2021-10-14",
        ],
        refresh_benchmarks=fake_refresh_benchmarks,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [
        {
            "benchmark_ids": ["us_sp500"],
            "benchmark_db_path": Path("benchmark.sqlite"),
            "market_db_path": Path("market.sqlite"),
            "today_date": "2021-10-14",
        }
    ]
    assert captured.out == "us_sp500 ^GSPC: 2 rows through 2021-10-13\n"
    assert captured.err == ""


def test_main_refreshes_all_configured_benchmarks(capsys):
    def fake_refresh_benchmarks(
        benchmark_ids, benchmark_db_path, market_db_path, today_date
    ):
        assert benchmark_ids == [
            "us_sp500",
            "us_nasdaq_100",
            "us_nasdaq_composite",
            "us_djia",
            "europe_stoxx_50",
            "europe_stoxx_600",
            "uk_ftse_100",
            "uk_ftse_250",
            "uk_ftse_350",
            "germany_dax_40",
            "hong_kong_hsi",
            "hong_kong_hscei",
            "japan_nikkei_225",
            "australia_asx_200",
        ]
        return [
            {
                "benchmark_id": "us_sp500",
                "symbol": "^GSPC",
                "rows_upserted": 1,
                "latest_date": "2021-10-13",
                "source": "yahoo_finance:^GSPC",
            }
        ]

    exit_code = refresh_benchmark_market_data.main(
        ["--all"],
        refresh_benchmarks=fake_refresh_benchmarks,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "us_sp500 ^GSPC: 1 rows through 2021-10-13\n"
    assert captured.err == ""


def test_main_requires_benchmark_id_or_all(capsys):
    exit_code = refresh_benchmark_market_data.main([])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "use --benchmark-id or --all\n"


def test_main_reports_value_errors(capsys):
    def fake_refresh_benchmarks(
        benchmark_ids, benchmark_db_path, market_db_path, today_date
    ):
        raise ValueError(
            "market data fetch failed for ^GSPC: HTTP 429 Too Many Requests"
        )

    exit_code = refresh_benchmark_market_data.main(
        ["--benchmark-id", "us_sp500"],
        refresh_benchmarks=fake_refresh_benchmarks,
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert (
        captured.err
        == "market data fetch failed for ^GSPC: HTTP 429 Too Many Requests\n"
    )
