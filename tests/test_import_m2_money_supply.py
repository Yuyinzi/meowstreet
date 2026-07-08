from datetime import datetime

import pytest
from openpyxl import Workbook

from app.db import us_rates_liquidity
from scripts import import_m2_money_supply


def write_m2_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Nominal M2 - Monthly"
    sheet.append(
        [
            "Date",
            "Nominal M2 Money Stock, Billions of Dollars, Monthly, Seasonally Adjusted",
        ]
    )
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


def test_build_fred_m2_payload_parses_m2sl_csv(tmp_path):
    csv_path = tmp_path / "M2SL.csv"
    csv_path.write_text(
        "observation_date,M2SL\n2026-03-01,22686.2\n2026-04-01,.\n2026-05-01,23052.3\n",
        encoding="utf-8",
    )

    payload = import_m2_money_supply.build_fred_m2_payload(csv_path)

    assert payload == {
        "series": {
            "series_id": "m2_money_stock",
            "title": "M2 Money Stock",
            "units": "billions_usd",
            "source": "P06 workbook + FRED",
        },
        "points": [
            {"date": "2026-03-01", "value": 22686.2, "source": "M2SL.csv"},
            {"date": "2026-05-01", "value": 23052.3, "source": "M2SL.csv"},
        ],
    }


def test_import_fred_csvs_merges_m2sl_with_existing_workbook_history(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    csv_path = fred_dir / "M2SL.csv"
    csv_path.write_text(
        "observation_date,M2SL\n2026-02-01,102.5\n2026-05-01,105.5\n",
        encoding="utf-8",
    )
    con = us_rates_liquidity.connect(db_path)
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "m2_money_stock",
            "title": "M2 Money Stock",
            "units": "billions_usd",
            "source": "m2.xlsx",
        },
        [
            {"date": "2026-01-01", "value": 100.0, "source": "m2.xlsx"},
            {"date": "2026-02-01", "value": 101.5, "source": "m2.xlsx"},
        ],
    )

    inserted = import_m2_money_supply.import_fred_csvs(con, fred_dir)

    assert inserted == {"m2_money_stock": 2}
    assert us_rates_liquidity.load_macro_indicator_series(con) == [
        {
            "series_id": "m2_money_stock",
            "title": "M2 Money Stock",
            "units": "billions_usd",
            "source": "P06 workbook + FRED",
        }
    ]
    assert us_rates_liquidity.load_macro_indicator_points(con, "m2_money_stock") == [
        {"date": "2026-01-01", "value": 100.0, "source": "m2.xlsx"},
        {"date": "2026-02-01", "value": 102.5, "source": "M2SL.csv"},
        {"date": "2026-05-01", "value": 105.5, "source": "M2SL.csv"},
    ]


def test_fetch_fred_csvs_fetches_m2sl(monkeypatch, tmp_path):
    calls = []

    class FakeFredClient:
        def __init__(self, cache_dir):
            calls.append(("init", cache_dir))

        def fetch_csvs(self, series_ids):
            calls.append(("fetch", series_ids))
            return {"M2SL": tmp_path / "fred" / "M2SL.csv"}

    monkeypatch.setattr(import_m2_money_supply, "FredClient", FakeFredClient)

    fetched = import_m2_money_supply.fetch_fred_csvs(tmp_path / "fred")

    assert fetched == {"M2SL": tmp_path / "fred" / "M2SL.csv"}
    assert calls == [
        ("init", tmp_path / "fred"),
        ("fetch", ["M2SL"]),
    ]


def test_main_can_fetch_fred_csv(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        import_m2_money_supply,
        "fetch_fred_csvs",
        lambda fred_dir: {"M2SL": fred_dir / "M2SL.csv"},
    )

    exit_code = import_m2_money_supply.main(
        ["--fred-dir", str(tmp_path / "fred"), "--fetch-fred-csv"]
    )

    assert exit_code == 0
    assert "M2SL:" in capsys.readouterr().out


def test_main_can_merge_fred_csv(monkeypatch, tmp_path, capsys):
    class FakeCon:
        def close(self):
            pass

    monkeypatch.setattr(
        import_m2_money_supply.us_rates_liquidity,
        "connect",
        lambda db_path: FakeCon(),
    )
    monkeypatch.setattr(
        import_m2_money_supply,
        "import_fred_csvs",
        lambda con, fred_dir: {"m2_money_stock": 2},
    )

    exit_code = import_m2_money_supply.main(
        [
            "--db-path",
            str(tmp_path / "market_data.sqlite"),
            "--fred-dir",
            str(tmp_path / "fred"),
            "--fred-csv-merge",
        ]
    )

    assert exit_code == 0
    assert "m2_money_stock: 2" in capsys.readouterr().out
