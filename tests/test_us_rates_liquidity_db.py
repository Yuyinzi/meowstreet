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
