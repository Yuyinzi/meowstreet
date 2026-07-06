from app.tools import us_rates_liquidity


def series_rows():
    return [
        {
            "series_id": "fed_funds",
            "title": "Fed Funds",
            "instrument_type": "policy_rate",
            "maturity_months": None,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "series_id": "treasury_2y",
            "title": "2-Year Treasury",
            "instrument_type": "nominal_treasury",
            "maturity_months": 24,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "series_id": "treasury_10y",
            "title": "10-Year Treasury",
            "instrument_type": "nominal_treasury",
            "maturity_months": 120,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "series_id": "tips_10y",
            "title": "10-Year TIPS",
            "instrument_type": "tips",
            "maturity_months": 120,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]


def latest_points():
    return [
        {
            "series_id": "fed_funds",
            "date": "2021-01-03",
            "value": 0.09,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "series_id": "treasury_2y",
            "date": "2021-01-03",
            "value": 0.12,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "series_id": "treasury_10y",
            "date": "2021-01-03",
            "value": 0.93,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "series_id": "tips_10y",
            "date": "2021-01-03",
            "value": -1.03,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]


def test_build_dashboard_payload_computes_key_method_indicators():
    payload = us_rates_liquidity.build_dashboard_payload(
        series_rows(),
        latest_points(),
        [
            {
                "series_id": "cpi_yoy",
                "date": "2021-01-03",
                "value": 1.40,
                "source": "US_P4_Macro_Indicators.csv",
            },
            {
                "series_id": "vix",
                "date": "2021-01-03",
                "value": 22.90,
                "source": "US_P4_Macro_Indicators.csv",
            },
            {
                "series_id": "sp500_pe",
                "date": "2021-01-03",
                "value": 30.20,
                "source": "US_P4_Macro_Indicators.csv",
            },
        ],
    )

    assert payload["as_of"] == "2021-01-03"
    assert payload["source"] == "Benchmark_Yields_US.xlsm"
    assert payload["derived"]["tens_twos_spread"] == 0.81
    assert payload["derived"]["ten_year_real_rate"] == -1.03
    assert payload["derived"]["ten_year_breakeven_inflation"] == 1.96
    assert payload["derived"]["curve_status"] == "steep"
    assert payload["headline"][0]["label"] == "10-Year Treasury"
    assert "date" not in payload["headline"][0]
    assert "context" not in payload["headline"][0]
    assert payload["derived"]["cpi_based_real_rate"] == -0.47
    assert payload["derived"]["vix"] == 22.90
    assert payload["derived"]["sp500_pe"] == 30.20
    cpi_headline = next(
        item for item in payload["headline"] if item["id"] == "cpi_based_real_rate"
    )
    assert cpi_headline["label"] == "CPI Real Rate"
    assert cpi_headline["value"] == -0.47


def test_build_dashboard_payload_handles_empty_db():
    payload = us_rates_liquidity.build_dashboard_payload([], [])

    assert payload["as_of"] is None
    assert payload["headline"] == []
    assert payload["curve"] == []
    assert payload["derived"]["curve_status"] == "missing"
    assert (
        payload["derived"]["method_interpretation"]
        == "No US rates data found. Run scripts/import_us_rates_liquidity.py."
    )


def rate_points_10y():
    return [
        {
            "date": "2000-01-02",
            "value": 6.58,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
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


def rate_points_2y():
    return [
        {
            "date": "2000-01-02",
            "value": 6.24,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
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
    ]


def test_build_rate_detail_payload_returns_two_workbook_style_charts():
    payload = us_rates_liquidity.build_detail_payload(
        "treasury_10y",
        series_rows(),
        {"treasury_10y": rate_points_10y()},
    )

    assert payload["detail_id"] == "treasury_10y"
    assert payload["title"] == "10-Year Treasury"
    assert len(payload["charts"]) == 2
    assert payload["charts"][0]["title"] == "10 Year Treasury Yield (Historical)"
    assert payload["charts"][1]["title"] == "10 Year Treasury Yield (Last 20 Years)"
    assert payload["charts"][0]["kind"] == "time_series"
    assert payload["charts"][0]["series"][0]["value"] == 6.58
    assert payload["charts"][1]["series"][-1]["value"] == 0.93


def test_build_spread_detail_payload_computes_two_chart_series():
    payload = us_rates_liquidity.build_detail_payload(
        "tens_twos_spread",
        series_rows(),
        {
            "treasury_10y": rate_points_10y(),
            "treasury_2y": rate_points_2y(),
        },
    )

    assert payload["detail_id"] == "tens_twos_spread"
    assert payload["title"] == "10Y - 2Y Spread"
    assert payload["charts"][0]["title"] == "10Y - 2Y Treasury Spread (Historical)"
    assert payload["charts"][0]["series"][-1]["value"] == 0.81
    assert payload["charts"][1]["title"] == "10Y - 2Y Treasury Spread (Last 20 Years)"


def test_build_yield_curve_detail_payload_returns_nominal_and_real_curve_charts():
    payload = us_rates_liquidity.build_detail_payload(
        "yield_curve_shape",
        series_rows(),
        {
            "treasury_2y": rate_points_2y(),
            "treasury_10y": rate_points_10y(),
            "tips_10y": [
                {
                    "date": "2020-12-27",
                    "value": -1.03,
                    "source_workbook": "Benchmark_Yields_US.xlsm",
                    "source_sheet": "Data",
                },
                {
                    "date": "2021-01-03",
                    "value": -1.03,
                    "source_workbook": "Benchmark_Yields_US.xlsm",
                    "source_sheet": "Data",
                },
            ],
        },
        {
            "nominal_current_date": "2021-01-03",
            "nominal_comparison_date": "2020-12-27",
            "real_current_date": "2021-01-03",
            "real_comparison_date": "2020-12-27",
        },
    )

    assert payload["detail_id"] == "yield_curve_shape"
    assert len(payload["charts"]) == 2
    assert payload["charts"][0]["kind"] == "curve_comparison"
    assert payload["charts"][0]["title"] == "US Yield Curve - Comparative Analysis"
    assert (
        payload["charts"][1]["title"]
        == "US Real Yield Curve (TIPS) - Comparative Analysis"
    )


def test_build_yield_curve_detail_payload_matches_workbook_nominal_maturities():
    payload = us_rates_liquidity.build_detail_payload(
        "yield_curve_shape",
        series_rows(),
        {
            "treasury_2y": rate_points_2y(),
            "treasury_10y": rate_points_10y(),
            "treasury_20y": [
                {
                    "date": "2021-01-03",
                    "value": 1.46,
                    "source_workbook": "Benchmark_Yields_US.xlsm",
                    "source_sheet": "Data",
                }
            ],
            "treasury_30y": [
                {
                    "date": "2021-01-03",
                    "value": 1.66,
                    "source_workbook": "Benchmark_Yields_US.xlsm",
                    "source_sheet": "Data",
                }
            ],
            "tips_10y": [
                {
                    "date": "2021-01-03",
                    "value": -1.03,
                    "source_workbook": "Benchmark_Yields_US.xlsm",
                    "source_sheet": "Data",
                }
            ],
        },
    )

    labels = [point["label"] for point in payload["charts"][0]["series"]]

    assert labels[-1] == "20Y"
    assert "30Y" not in labels


def test_build_cpi_real_rate_detail_payload_compares_with_vix_and_pe():
    payload = us_rates_liquidity.build_detail_payload(
        "cpi_based_real_rate",
        series_rows(),
        {
            "treasury_10y": rate_points_10y(),
            "cpi_yoy": [
                {
                    "date": "2020-12-27",
                    "value": 1.30,
                    "source": "US_P4_Macro_Indicators.csv",
                },
                {
                    "date": "2021-01-03",
                    "value": 1.40,
                    "source": "US_P4_Macro_Indicators.csv",
                },
            ],
            "vix": [
                {
                    "date": "2020-12-27",
                    "value": 22.00,
                    "source": "US_P4_Macro_Indicators.csv",
                },
                {
                    "date": "2021-01-03",
                    "value": 22.90,
                    "source": "US_P4_Macro_Indicators.csv",
                },
            ],
            "sp500_pe": [
                {
                    "date": "2020-12-27",
                    "value": 30.00,
                    "source": "US_P4_Macro_Indicators.csv",
                },
                {
                    "date": "2021-01-03",
                    "value": 30.20,
                    "source": "US_P4_Macro_Indicators.csv",
                },
            ],
        },
    )

    assert payload["detail_id"] == "cpi_based_real_rate"
    assert payload["charts"][0]["title"] == "10Y Treasury Minus CPI YoY"
    assert payload["charts"][0]["series"][-1]["value"] == -0.47
    assert payload["charts"][1]["title"] == "CPI Real Rate vs VIX"
    assert payload["charts"][1]["labels"] == {
        "real_rate": "CPI Real Rate",
        "vix": "VIX",
    }
    assert payload["charts"][2]["title"] == "CPI Real Rate vs S&P 500 PE"
