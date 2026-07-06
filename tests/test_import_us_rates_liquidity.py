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


def test_build_fred_rate_payload_uses_shared_weekly_resample(tmp_path):
    csv_path = tmp_path / "DGS10.csv"
    csv_path.write_text(
        "observation_date,DGS10\n2020-12-24,0.94\n2020-12-31,0.93\n",
        encoding="utf-8",
    )

    payload = import_us_rates_liquidity.build_fred_rate_payload(csv_path, "DGS10")

    assert payload["series"] == {
        "series_id": "treasury_10y",
        "title": "10-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 120,
        "units": "percent",
        "source_workbook": "DGS10.csv",
        "source_sheet": "FRED weekly Sunday resample",
    }
    assert payload["points"] == [
        {
            "date": "2020-12-27",
            "value": 0.94,
            "source_workbook": "DGS10.csv",
            "source_sheet": "FRED weekly Sunday resample",
        }
    ]


def test_import_fred_csvs_replaces_rate_series(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    (fred_dir / "DGS10.csv").write_text(
        "observation_date,DGS10\n2020-12-24,0.94\n2020-12-31,0.93\n",
        encoding="utf-8",
    )

    inserted = import_us_rates_liquidity.import_fred_csvs(
        con,
        fred_dir,
        fred_series_ids=["DGS10"],
    )

    assert inserted == {"treasury_10y": 1}
    assert us_rates_liquidity.load_rate_points(con, "treasury_10y") == [
        {
            "date": "2020-12-27",
            "value": 0.94,
            "source_workbook": "DGS10.csv",
            "source_sheet": "FRED weekly Sunday resample",
        }
    ]


def test_fetch_fred_csvs_uses_shared_fred_client(tmp_path, monkeypatch):
    fetched = []

    class FakeFredClient:
        def __init__(self, cache_dir):
            assert cache_dir == tmp_path

        def fetch_csv(self, series_id):
            fetched.append(series_id)
            return tmp_path / f"{series_id}.csv"

        def fetch_csvs(self, series_ids):
            return {sid: self.fetch_csv(sid) for sid in series_ids}

    monkeypatch.setattr(import_us_rates_liquidity, "FredClient", FakeFredClient)

    result = import_us_rates_liquidity.fetch_fred_csvs(
        fred_dir=tmp_path,
        fred_series_ids=["DGS10", "DFII10"],
    )

    assert fetched == ["DGS10", "DFII10"]
    assert result == {
        "DGS10": tmp_path / "DGS10.csv",
        "DFII10": tmp_path / "DFII10.csv",
    }


def test_local_dgs10_fred_csv_matches_workbook_weekly_resample():
    workbook_path = import_us_rates_liquidity.DEFAULT_WORKBOOK_PATH
    csv_path = workbook_path.parent / "DGS10.csv"
    if not workbook_path.exists() or not csv_path.exists():
        return

    workbook = import_us_rates_liquidity.parse_data_sheet(workbook_path)
    workbook_points = workbook["treasury_10y"]["points"]
    fred_payload = import_us_rates_liquidity.build_fred_rate_payload(csv_path, "DGS10")
    fred_points = {point["date"]: point["value"] for point in fred_payload["points"]}

    compared = [point for point in workbook_points if point["date"] in fred_points]

    assert len(compared) == len(workbook_points)
    assert all(point["value"] == fred_points[point["date"]] for point in compared)
