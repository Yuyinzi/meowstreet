from app.db import us_rates_liquidity
from scripts import import_us_macro_indicators


def test_replace_macro_indicator_points_saves_and_loads_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    saved = us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "cpi_yoy",
            "title": "CPI YoY",
            "units": "percent",
            "source": "US_P4_Macro_Indicators.csv",
        },
        [
            {
                "date": "2020-12-31",
                "value": 1.36,
                "source": "US_P4_Macro_Indicators.csv",
            },
            {
                "date": "2021-01-03",
                "value": 1.40,
                "source": "US_P4_Macro_Indicators.csv",
            },
        ],
    )

    assert saved == {"series": 1, "points": 2}
    assert (
        us_rates_liquidity.load_macro_indicator_series(con)[0]["series_id"] == "cpi_yoy"
    )
    assert (
        us_rates_liquidity.load_latest_macro_indicator_points(con)[0]["value"] == 1.40
    )
    assert us_rates_liquidity.load_macro_indicator_points_for_series(
        con, ["cpi_yoy"]
    ) == {
        "cpi_yoy": [
            {
                "date": "2020-12-31",
                "value": 1.36,
                "source": "US_P4_Macro_Indicators.csv",
            },
            {
                "date": "2021-01-03",
                "value": 1.40,
                "source": "US_P4_Macro_Indicators.csv",
            },
        ]
    }


def test_parse_macro_indicator_csv_groups_points_by_series(tmp_path):
    csv_path = tmp_path / "US_P4_Macro_Indicators.csv"
    csv_path.write_text(
        "date,cpi_yoy,vix,sp500_pe\n"
        "2020-12-31,1.36,22.75,30.10\n"
        "2021-01-03,1.40,22.90,30.20\n",
    )

    parsed = import_us_macro_indicators.parse_csv(csv_path)

    assert sorted(parsed) == ["cpi_yoy", "vix"]
    assert parsed["cpi_yoy"]["series"]["title"] == "CPI YoY"
    assert parsed["cpi_yoy"]["points"][-1]["value"] == 1.40
    assert parsed["vix"]["points"][-1]["value"] == 22.90


def test_import_macro_indicator_csv_saves_all_parsed_series(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    csv_path = tmp_path / "US_P4_Macro_Indicators.csv"
    csv_path.write_text(
        "date,cpi_yoy,vix,sp500_pe\n"
        "2020-12-31,1.36,22.75,30.10\n"
        "2021-01-03,1.40,22.90,30.20\n"
    )

    inserted = import_us_macro_indicators.import_csv(con, csv_path)

    assert inserted == {"cpi_yoy": 2, "vix": 2}
    assert (
        us_rates_liquidity.load_macro_indicator_points(con, "cpi_yoy")[-1]["value"]
        == 1.40
    )
    assert us_rates_liquidity.load_macro_indicator_points(con, "sp500_pe") == []


def test_import_fred_macro_csvs_saves_cpi_yoy_and_vix(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    (fred_dir / "CPIAUCSL.csv").write_text(
        "observation_date,CPIAUCSL\n2019-12-01,258.203\n2020-12-01,262.035\n",
        encoding="utf-8",
    )
    (fred_dir / "VIXCLS.csv").write_text(
        "observation_date,VIXCLS\n2020-12-24,21.53\n2020-12-31,22.75\n",
        encoding="utf-8",
    )

    inserted = import_us_macro_indicators.import_fred_macro_csvs(
        con,
        fred_dir,
        start_date="2020-12-20",
        end_date="2021-01-03",
    )

    assert inserted == {"cpi_yoy": 3, "vix": 2}
    assert us_rates_liquidity.load_macro_indicator_points(con, "cpi_yoy")[-1] == {
        "date": "2021-01-03",
        "value": 1.48,
        "source": "FRED weekly Sunday resample",
    }
    assert us_rates_liquidity.load_macro_indicator_points(con, "vix")[-1] == {
        "date": "2021-01-03",
        "value": 22.75,
        "source": "FRED weekly Sunday resample",
    }


def test_fetch_fred_macro_csvs_uses_shared_fred_client(tmp_path, monkeypatch):
    fetched = []

    class FakeFredClient:
        def __init__(self, cache_dir):
            assert cache_dir == tmp_path

        def fetch_csv(self, series_id):
            fetched.append(series_id)
            return tmp_path / f"{series_id}.csv"

        def fetch_csvs(self, series_ids):
            return {sid: self.fetch_csv(sid) for sid in series_ids}

    monkeypatch.setattr(import_us_macro_indicators, "FredClient", FakeFredClient)

    result = import_us_macro_indicators.fetch_fred_csvs(
        fred_dir=tmp_path,
        fred_series_ids=["CPIAUCSL", "VIXCLS"],
    )

    assert fetched == ["CPIAUCSL", "VIXCLS"]
    assert result == {
        "CPIAUCSL": tmp_path / "CPIAUCSL.csv",
        "VIXCLS": tmp_path / "VIXCLS.csv",
    }
