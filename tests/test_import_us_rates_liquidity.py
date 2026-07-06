import datetime

from openpyxl import Workbook

from app.db import us_rates_liquidity
from scripts import import_us_rates_liquidity


def make_rates_workbook(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append([None, "Fed Funds", "1mo", "2yr", "10yr", "10yr TIPS", "30yr"])
    ws.append([None, None, None, None, None, None, None])
    ws.append([None, None, None, None, None, None, None])
    ws.append([datetime.datetime(2021, 1, 3), 0.09, 0.06, 0.12, 0.93, -1.03, 1.66])
    ws.append([datetime.datetime(2020, 12, 27), 0.09, 0.09, 0.13, 0.94, -1.03, 1.66])
    wb.save(path)


def test_parse_data_sheet_groups_points_by_series(tmp_path):
    workbook_path = tmp_path / "Benchmark_Yields_US.xlsm"
    make_rates_workbook(workbook_path)

    parsed = import_us_rates_liquidity.parse_data_sheet(workbook_path)

    assert parsed["treasury_10y"]["series"]["title"] == "10-Year Treasury"
    assert parsed["treasury_10y"]["points"] == [
        {
            "date": "2020-12-27",
            "value": 0.94,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "date": "2021-01-03",
            "value": 0.93,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]
    assert parsed["tips_10y"]["points"][-1]["value"] == -1.03


def test_parse_data_sheet_ignores_unknown_header(tmp_path):
    workbook_path = tmp_path / "Benchmark_Yields_US.xlsm"
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append([None, "Unknown Series", "10yr"])
    ws.append([None, None, None])
    ws.append([None, None, None])
    ws.append([datetime.datetime(2021, 1, 3), 9.99, 0.93])
    wb.save(workbook_path)

    parsed = import_us_rates_liquidity.parse_data_sheet(workbook_path)

    assert sorted(parsed) == ["treasury_10y"]


def test_import_workbook_saves_all_parsed_series(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    workbook_path = tmp_path / "Benchmark_Yields_US.xlsm"
    make_rates_workbook(workbook_path)

    inserted = import_us_rates_liquidity.import_workbook(con, workbook_path)

    assert inserted["fed_funds"] == 2
    assert inserted["treasury_10y"] == 2
    assert inserted["tips_10y"] == 2
    assert us_rates_liquidity.load_rate_points(con, "treasury_10y")[-1]["value"] == 0.93
