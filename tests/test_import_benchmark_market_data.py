import datetime
from pathlib import Path

from openpyxl import Workbook

from app.db import benchmark_market_data
from scripts import import_benchmark_market_data


def _make_workbook(path, sheets_config):
    """Create a test workbook at path with sheets defined in sheets_config.

    sheets_config: list of (sheet_name, rows) where each row is a list of cell values.
    S&P 500 sheet uses 5-column format; others use 2-column format.
    """
    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheets_config:
        ws = wb.create_sheet(title=sheet_name)
        for row in rows:
            ws.append(row)
    wb.save(path)


def test_parse_workbook_sheet_extracts_sp500_rows(tmp_path):
    workbook_path = tmp_path / "test.xlsx"
    _make_workbook(workbook_path, [
        ("S&P 500", [
            (datetime.date(2019, 12, 31), 99.0, 100.0, 98.5, 99.5),
            (datetime.date(2020, 1, 2), 100.0, 101.0, 99.0, 100.5),
            (datetime.date(2020, 1, 3), 100.5, 102.0, 100.0, 101.5),
        ]),
    ])

    rows = import_benchmark_market_data.parse_workbook_sheet(workbook_path, "S&P 500")

    assert len(rows) == 2
    assert rows[0]["date"] == "2020-01-03"
    assert rows[0]["close"] == 101.5
    assert rows[-1]["date"] == "2020-01-02"
    assert rows[-1]["close"] == 100.5


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
    workbook_path = tmp_path / "test.xlsx"
    _make_workbook(workbook_path, [
        ("S&P 500", [
            (datetime.date(2019, 12, 31), 99.0, 100.0, 98.5, 99.5),
            (datetime.date(2020, 1, 2), 100.0, 101.0, 99.0, 100.5),
            (datetime.date(2020, 1, 3), 100.5, 102.0, 100.0, 101.5),
        ]),
        ("Nasdaq 100", [
            (datetime.date(2019, 12, 31), 199.0),
            (datetime.date(2020, 1, 2), 200.0),
            (datetime.date(2020, 1, 3), 201.0),
        ]),
    ])

    inserted, errors = import_benchmark_market_data.import_workbook(con, workbook_path)

    assert inserted["us_sp500"] == 2
    assert inserted["us_nasdaq_100"] == 2
    assert benchmark_market_data.latest_price_date(con, "us_sp500") == "2020-01-03"
    assert "us_nasdaq_composite" in errors


def test_import_script_owns_workbook_sheet_mapping():
    config = import_benchmark_market_data.WORKBOOK_BENCHMARK_SHEETS[0]

    assert config == {"benchmark_id": "us_sp500", "sheet": "S&P 500"}
