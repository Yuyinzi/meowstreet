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

    assert sorted(parsed) == [
        "core_pce_price_index",
        "cpi_yoy",
        "fed_mbs_holdings",
        "fed_total_assets",
        "fed_treasury_holdings",
        "vix",
    ]
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

    assert inserted == {
        "core_pce_price_index": 0,
        "cpi_yoy": 2,
        "fed_mbs_holdings": 0,
        "fed_total_assets": 0,
        "fed_treasury_holdings": 0,
        "vix": 2,
    }
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
    (fred_dir / "PCEPILFE.csv").write_text(
        "observation_date,PCEPILFE\n2020-12-01,130.0\n",
        encoding="utf-8",
    )
    (fred_dir / "WALCL.csv").write_text(
        "observation_date,WALCL\n2020-12-30,6500000.0\n",
        encoding="utf-8",
    )
    (fred_dir / "TREAST.csv").write_text(
        "observation_date,TREAST\n2020-12-30,4200000.0\n",
        encoding="utf-8",
    )
    (fred_dir / "WSHOMCB.csv").write_text(
        "observation_date,WSHOMCB\n2020-12-30,2100000.0\n",
        encoding="utf-8",
    )

    inserted = import_us_macro_indicators.import_fred_macro_csvs(
        con,
        fred_dir,
        start_date="2020-12-20",
        end_date="2021-01-03",
    )

    assert inserted == {
        "cpi_yoy": 3,
        "vix": 2,
        "core_pce_price_index": 1,
        "fed_total_assets": 1,
        "fed_treasury_holdings": 1,
        "fed_mbs_holdings": 1,
    }
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


def test_import_fred_macro_csvs_saves_core_pce_price_index(tmp_path):
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    (fred_dir / "CPIAUCSL.csv").write_text(
        "observation_date,CPIAUCSL\n2025-01-01,320\n2026-01-01,330\n",
        encoding="utf-8",
    )
    (fred_dir / "VIXCLS.csv").write_text(
        "observation_date,VIXCLS\n2026-01-05,14.5\n",
        encoding="utf-8",
    )
    (fred_dir / "PCEPILFE.csv").write_text(
        "observation_date,PCEPILFE\n"
        "2025-01-01,130.0\n"
        "2025-02-01,130.5\n"
        "2026-01-01,134.0\n",
        encoding="utf-8",
    )
    (fred_dir / "WALCL.csv").write_text(
        "observation_date,WALCL\n2026-01-07,6700000.0\n",
        encoding="utf-8",
    )
    (fred_dir / "TREAST.csv").write_text(
        "observation_date,TREAST\n2026-01-07,4200000.0\n",
        encoding="utf-8",
    )
    (fred_dir / "WSHOMCB.csv").write_text(
        "observation_date,WSHOMCB\n2026-01-07,2200000.0\n",
        encoding="utf-8",
    )
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    inserted = import_us_macro_indicators.import_fred_macro_csvs(
        con,
        fred_dir,
        start_date="2026-01-04",
        end_date="2026-01-11",
    )

    assert inserted["core_pce_price_index"] == 3
    assert inserted["fed_total_assets"] == 1
    assert inserted["fed_treasury_holdings"] == 1
    assert inserted["fed_mbs_holdings"] == 1
    assert us_rates_liquidity.load_macro_indicator_points(
        con,
        "core_pce_price_index",
    ) == [
        {"date": "2025-01-01", "value": 130.0, "source": "FRED monthly"},
        {"date": "2025-02-01", "value": 130.5, "source": "FRED monthly"},
        {"date": "2026-01-01", "value": 134.0, "source": "FRED monthly"},
    ]


def test_fetch_fred_macro_csvs_includes_core_pce(monkeypatch, tmp_path):
    calls = []

    class FakeFredClient:
        def __init__(self, cache_dir):
            calls.append(("init", cache_dir))

        def fetch_csvs(self, series_ids):
            calls.append(("fetch", series_ids))
            return {
                series_id: tmp_path / f"{series_id}.csv" for series_id in series_ids
            }

    monkeypatch.setattr(import_us_macro_indicators, "FredClient", FakeFredClient)

    result = import_us_macro_indicators.fetch_fred_csvs(tmp_path / "fred")

    assert result == {
        "CPIAUCSL": tmp_path / "CPIAUCSL.csv",
        "PCEPILFE": tmp_path / "PCEPILFE.csv",
        "VIXCLS": tmp_path / "VIXCLS.csv",
        "WALCL": tmp_path / "WALCL.csv",
        "TREAST": tmp_path / "TREAST.csv",
        "WSHOMCB": tmp_path / "WSHOMCB.csv",
    }
    assert calls == [
        ("init", tmp_path / "fred"),
        ("fetch", ["CPIAUCSL", "PCEPILFE", "TREAST", "VIXCLS", "WALCL", "WSHOMCB"]),
    ]


def test_import_fred_macro_csvs_saves_fed_balance_sheet_series(tmp_path):
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    (fred_dir / "CPIAUCSL.csv").write_text(
        "observation_date,CPIAUCSL\n2025-01-01,300.0\n2026-01-01,306.0\n"
    )
    (fred_dir / "PCEPILFE.csv").write_text(
        "observation_date,PCEPILFE\n2025-01-01,130.0\n2026-01-01,134.0\n"
    )
    (fred_dir / "VIXCLS.csv").write_text("observation_date,VIXCLS\n2026-01-02,15.0\n")
    (fred_dir / "WALCL.csv").write_text(
        "observation_date,WALCL\n2026-01-07,6700000.0\n2026-01-14,6710000.0\n"
    )
    (fred_dir / "TREAST.csv").write_text(
        "observation_date,TREAST\n2026-01-07,4200000.0\n2026-01-14,4210000.0\n"
    )
    (fred_dir / "WSHOMCB.csv").write_text(
        "observation_date,WSHOMCB\n2026-01-07,2200000.0\n2026-01-14,2195000.0\n"
    )
    con = import_us_macro_indicators.us_rates_liquidity.connect(
        tmp_path / "market_data.sqlite"
    )

    inserted = import_us_macro_indicators.import_fred_macro_csvs(con, fred_dir)

    assert inserted["fed_total_assets"] == 2
    assert inserted["fed_treasury_holdings"] == 2
    assert inserted["fed_mbs_holdings"] == 2
    assert import_us_macro_indicators.us_rates_liquidity.load_macro_indicator_points(
        con,
        "fed_total_assets",
    )[-1] == {
        "date": "2026-01-14",
        "value": 6710000.0,
        "source": "FRED weekly",
    }
