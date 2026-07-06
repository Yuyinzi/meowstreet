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
        "2021-01-03,1.40,22.90,\n"
    )

    parsed = import_us_macro_indicators.parse_csv(csv_path)

    assert parsed["cpi_yoy"]["series"]["title"] == "CPI YoY"
    assert parsed["cpi_yoy"]["points"][-1]["value"] == 1.40
    assert parsed["vix"]["points"][-1]["value"] == 22.90
    assert parsed["sp500_pe"]["points"] == [
        {"date": "2020-12-31", "value": 30.10, "source": "US_P4_Macro_Indicators.csv"}
    ]


def test_import_macro_indicator_csv_saves_all_parsed_series(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    csv_path = tmp_path / "US_P4_Macro_Indicators.csv"
    csv_path.write_text(
        "date,cpi_yoy,vix,sp500_pe\n"
        "2020-12-31,1.36,22.75,30.10\n"
        "2021-01-03,1.40,22.90,30.20\n"
    )

    inserted = import_us_macro_indicators.import_csv(con, csv_path)

    assert inserted == {"cpi_yoy": 2, "sp500_pe": 2, "vix": 2}
    assert (
        us_rates_liquidity.load_macro_indicator_points(con, "cpi_yoy")[-1]["value"]
        == 1.40
    )
