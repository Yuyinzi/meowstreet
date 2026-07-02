from pathlib import Path

from app.db import benchmark_market_data
from scripts import import_benchmark_market_data


def test_parse_workbook_sheet_extracts_sp500_rows():
    workbook_path = Path("data/source_material/Video 02/Bull_Bear_Markets.xlsx")

    rows = import_benchmark_market_data.parse_workbook_sheet(workbook_path, "S&P 500")

    assert rows[0]["date"] == "1928-01-03"
    assert rows[-1]["date"] == "2021-10-11"
    assert rows[-1]["close"] == 4361.19


def test_normalize_import_rows_supports_future_source_adapters():
    raw_rows = [
        {
            "date": "2020-01-02",
            "open": "100.5",
            "high": "101.5",
            "low": "",
            "close": "99.5",
        }
    ]

    rows = import_benchmark_market_data.normalize_price_rows(raw_rows)

    assert rows == [
        {
            "date": "2020-01-02",
            "open": 100.5,
            "high": 101.5,
            "low": None,
            "close": 99.5,
        }
    ]


def test_import_workbook_saves_configured_benchmarks(tmp_path):
    con = benchmark_market_data.connect(tmp_path / "benchmark_market_data.sqlite")

    inserted = import_benchmark_market_data.import_workbook(
        con,
        Path("data/source_material/Video 02/Bull_Bear_Markets.xlsx"),
    )

    assert inserted["us_sp500"] > 20000
    assert inserted["us_nasdaq_100"] > 8000
    assert benchmark_market_data.latest_price_date(con, "us_sp500") == "2021-10-11"
