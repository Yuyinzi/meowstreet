from datetime import datetime

import pytest
from openpyxl import Workbook

from app.db import us_rates_liquidity
from scripts import import_m2_money_supply


def write_m2_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Nominal M2 - Monthly"
    sheet.append([
        "Date",
        "Nominal M2 Money Stock, Billions of Dollars, Monthly, Seasonally Adjusted",
    ])
    sheet.append([datetime(2026, 1, 1), 100])
    sheet.append([datetime(2026, 2, 1), 101.5])
    sheet.append([datetime(2026, 3, 1), None])
    sheet.append([datetime(2026, 4, 1), 104])
    workbook.save(path)


def test_parse_workbook_reads_nominal_m2_sheet(tmp_path):
    workbook_path = tmp_path / "m2.xlsx"
    write_m2_workbook(workbook_path)

    result = import_m2_money_supply.parse_workbook(workbook_path)

    assert result == {
        "series": {
            "series_id": "m2_money_stock",
            "title": "M2 Money Stock",
            "units": "billions_usd",
            "source": "m2.xlsx",
        },
        "points": [
            {"date": "2026-01-01", "value": 100.0, "source": "m2.xlsx"},
            {"date": "2026-02-01", "value": 101.5, "source": "m2.xlsx"},
            {"date": "2026-04-01", "value": 104.0, "source": "m2.xlsx"},
        ],
    }


def test_import_workbook_saves_m2_money_stock_to_macro_indicator_tables(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    workbook_path = tmp_path / "m2.xlsx"
    write_m2_workbook(workbook_path)
    con = us_rates_liquidity.connect(db_path)

    inserted = import_m2_money_supply.import_workbook(con, workbook_path)

    assert inserted == {"m2_money_stock": 3}
    assert us_rates_liquidity.load_macro_indicator_series(con) == [
        {
            "series_id": "m2_money_stock",
            "title": "M2 Money Stock",
            "units": "billions_usd",
            "source": "m2.xlsx",
        }
    ]
    assert us_rates_liquidity.load_macro_indicator_points(con, "m2_money_stock") == [
        {"date": "2026-01-01", "value": 100.0, "source": "m2.xlsx"},
        {"date": "2026-02-01", "value": 101.5, "source": "m2.xlsx"},
        {"date": "2026-04-01", "value": 104.0, "source": "m2.xlsx"},
    ]


def test_parse_workbook_rejects_missing_workbook(tmp_path):
    with pytest.raises(ValueError, match="m2 money supply workbook is missing"):
        import_m2_money_supply.parse_workbook(tmp_path / "missing.xlsx")
