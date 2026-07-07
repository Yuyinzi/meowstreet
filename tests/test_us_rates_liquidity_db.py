from app.db import us_rates_liquidity


def series():
    return {
        "series_id": "treasury_10y",
        "title": "10-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 120,
        "units": "percent",
        "source_workbook": "Benchmark_Yields_US.xlsm",
        "source_sheet": "Data",
    }


def points():
    return [
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


def test_replace_rate_series_points_loads_sorted_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    saved = us_rates_liquidity.replace_rate_series_points(con, series(), points())
    loaded_series = us_rates_liquidity.load_rate_series(con)
    loaded_points = us_rates_liquidity.load_rate_points(con, "treasury_10y")

    assert saved == {"series": 1, "points": 2}
    assert loaded_series[0]["series_id"] == "treasury_10y"
    assert loaded_series[0]["maturity_months"] == 120
    assert [row["date"] for row in loaded_points] == ["2020-12-27", "2021-01-03"]
    assert loaded_points[-1]["value"] == 0.93


def test_replace_rate_series_points_deletes_old_points(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    us_rates_liquidity.replace_rate_series_points(con, series(), points())

    saved = us_rates_liquidity.replace_rate_series_points(
        con,
        series(),
        [
            {
                "date": "2021-01-10",
                "value": 1.04,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            }
        ],
    )
    loaded_points = us_rates_liquidity.load_rate_points(con, "treasury_10y")

    assert saved == {"series": 1, "points": 1}
    assert loaded_points == [
        {
            "date": "2021-01-10",
            "value": 1.04,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        }
    ]


def test_normalize_series_id_rejects_empty_id():
    try:
        us_rates_liquidity.normalize_series_id("")
    except ValueError as exc:
        assert str(exc) == "rate series id is required"
    else:
        raise AssertionError("expected ValueError")


def test_load_rate_points_for_series_returns_grouped_sorted_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    us_rates_liquidity.replace_rate_series_points(con, series(), points())
    us_rates_liquidity.replace_rate_series_points(
        con,
        {
            "series_id": "treasury_2y",
            "title": "2-Year Treasury",
            "instrument_type": "nominal_treasury",
            "maturity_months": 24,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        [
            {
                "date": "2020-12-27",
                "value": 0.13,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
            {
                "date": "2021-01-03",
                "value": 0.12,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
        ],
    )

    grouped = us_rates_liquidity.load_rate_points_for_series(
        con,
        ["treasury_10y", "treasury_2y"],
    )

    assert list(grouped) == ["treasury_10y", "treasury_2y"]
    assert grouped["treasury_10y"][-1]["value"] == 0.93
    assert grouped["treasury_2y"][-1]["value"] == 0.12


def test_merge_macro_indicator_points_preserves_existing_points(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    series = {
        "series_id": "bbb_corporate_yield",
        "title": "BBB Corporate Yield",
        "units": "percent",
        "source": "Corporate_Bond_Indices.xlsm",
    }
    workbook_points = [
        {"date": "2021-01-06", "value": 2.20, "source": "Corporate_Bond_Indices.xlsm"},
        {"date": "2021-01-07", "value": 2.16, "source": "Corporate_Bond_Indices.xlsm"},
    ]
    fred_points = [
        {"date": "2023-10-01", "value": 6.10, "source": "BAMLC0A4CBBBEY.csv"},
        {"date": "2023-10-02", "value": 6.08, "source": "BAMLC0A4CBBBEY.csv"},
    ]

    us_rates_liquidity.replace_macro_indicator_points(con, series, workbook_points)
    saved = us_rates_liquidity.merge_macro_indicator_points(
        con,
        {**series, "source": "P05 workbook + FRED"},
        fred_points,
    )
    loaded = us_rates_liquidity.load_macro_indicator_points(con, "bbb_corporate_yield")
    loaded_series = [
        row
        for row in us_rates_liquidity.load_macro_indicator_series(con)
        if row["series_id"] == "bbb_corporate_yield"
    ][0]

    assert saved == {"series": 1, "points": 2}
    assert [row["date"] for row in loaded] == [
        "2021-01-06",
        "2021-01-07",
        "2023-10-01",
        "2023-10-02",
    ]
    assert loaded[-1]["value"] == 6.08
    assert loaded_series["source"] == "P05 workbook + FRED"


def test_merge_macro_indicator_points_replaces_matching_dates(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    series = {
        "series_id": "ccc_corporate_yield",
        "title": "CCC Corporate Yield",
        "units": "percent",
        "source": "Corporate_Bond_Indices.xlsm",
    }
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        series,
        [{"date": "2023-10-02", "value": 12.00, "source": "old.csv"}],
    )

    saved = us_rates_liquidity.merge_macro_indicator_points(
        con,
        {**series, "source": "P05 workbook + FRED"},
        [{"date": "2023-10-02", "value": 11.75, "source": "BAMLH0A3HYCEY.csv"}],
    )
    loaded = us_rates_liquidity.load_macro_indicator_points(con, "ccc_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert loaded == [
        {"date": "2023-10-02", "value": 11.75, "source": "BAMLH0A3HYCEY.csv"}
    ]
