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
    assert "sp500_pe" not in payload["derived"]
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


def test_build_cpi_real_rate_detail_payload_compares_with_vix_only():
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
        },
    )

    assert payload["detail_id"] == "cpi_based_real_rate"
    assert len(payload["charts"]) == 2
    assert payload["charts"][0]["title"] == "10Y Treasury Minus CPI YoY"
    assert payload["charts"][0]["series"][-1]["value"] == -0.47
    assert payload["charts"][1]["title"] == "CPI Real Rate vs VIX"
    assert payload["charts"][1]["labels"] == {
        "real_rate": "CPI Real Rate",
        "vix": "VIX",
    }


def _credit_macro_points():
    return [
        {
            "series_id": "aaa_corporate_yield",
            "date": "2021-01-03",
            "value": 4.60,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "bbb_corporate_yield",
            "date": "2021-01-03",
            "value": 5.20,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "ccc_corporate_yield",
            "date": "2021-01-03",
            "value": 7.80,
            "source": "Corporate_Bond_Indices.xlsm",
        },
    ]


def test_build_dashboard_payload_computes_credit_spreads():
    payload = us_rates_liquidity.build_dashboard_payload(
        series_rows(),
        latest_points(),
        _credit_macro_points(),
    )

    assert payload["derived"]["aaa_credit_spread"] == 3.67
    assert payload["derived"]["bbb_credit_spread"] == 4.27
    assert payload["derived"]["ccc_credit_spread"] == 6.87
    assert payload["derived"]["bbb_aaa_quality_spread"] == 0.60
    assert payload["derived"]["ccc_bbb_quality_spread"] == 2.60
    assert payload["derived"]["ccc_aaa_quality_spread"] == 3.20


def test_build_dashboard_payload_credit_status_supportive():
    points = [
        {
            "series_id": "treasury_10y",
            "date": "2021-01-03",
            "value": 4.00,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]
    macro = [
        {
            "series_id": "aaa_corporate_yield",
            "date": "2021-01-03",
            "value": 4.60,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "bbb_corporate_yield",
            "date": "2021-01-03",
            "value": 5.20,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "ccc_corporate_yield",
            "date": "2021-01-03",
            "value": 7.00,
            "source": "Corporate_Bond_Indices.xlsm",
        },
    ]
    payload = us_rates_liquidity.build_dashboard_payload(series_rows(), points, macro)

    assert payload["derived"]["credit_conditions_status"] == "supportive"


def test_build_dashboard_payload_credit_status_caution():
    points = [
        {
            "series_id": "treasury_10y",
            "date": "2021-01-03",
            "value": 4.00,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]
    macro = [
        {
            "series_id": "aaa_corporate_yield",
            "date": "2021-01-03",
            "value": 4.60,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "bbb_corporate_yield",
            "date": "2021-01-03",
            "value": 5.20,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "ccc_corporate_yield",
            "date": "2021-01-03",
            "value": 9.80,
            "source": "Corporate_Bond_Indices.xlsm",
        },
    ]
    payload = us_rates_liquidity.build_dashboard_payload(series_rows(), points, macro)

    assert payload["derived"]["credit_conditions_status"] == "selective"


def test_build_dashboard_payload_credit_status_risk_off():
    points = [
        {
            "series_id": "treasury_10y",
            "date": "2021-01-03",
            "value": 4.00,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]
    macro = [
        {
            "series_id": "aaa_corporate_yield",
            "date": "2021-01-03",
            "value": 4.60,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "bbb_corporate_yield",
            "date": "2021-01-03",
            "value": 7.00,
            "source": "Corporate_Bond_Indices.xlsm",
        },
        {
            "series_id": "ccc_corporate_yield",
            "date": "2021-01-03",
            "value": 13.00,
            "source": "Corporate_Bond_Indices.xlsm",
        },
    ]
    payload = us_rates_liquidity.build_dashboard_payload(series_rows(), points, macro)

    assert payload["derived"]["credit_conditions_status"] == "risk_off"


def test_build_dashboard_payload_credit_status_missing_when_no_corporate_data():
    payload = us_rates_liquidity.build_dashboard_payload(
        series_rows(),
        latest_points(),
        [],
    )

    assert payload["derived"]["credit_conditions_status"] == "missing"


def test_build_dashboard_payload_credit_cards_in_headline():
    payload = us_rates_liquidity.build_dashboard_payload(
        series_rows(),
        latest_points(),
        _credit_macro_points(),
    )

    credit_ids = [card["id"] for card in payload["headline"]]
    assert "bbb_credit_spread" in credit_ids
    assert "ccc_credit_spread" in credit_ids
    assert "ccc_bbb_quality_spread" in credit_ids
    assert "credit_conditions" in credit_ids
    assert "aaa_credit_spread" not in credit_ids
    assert "bbb_aaa_quality_spread" not in credit_ids
    assert "ccc_aaa_quality_spread" not in credit_ids

    bbb_card = next(c for c in payload["headline"] if c["id"] == "bbb_credit_spread")
    assert bbb_card["value"] == 4.27
    assert bbb_card["unit"] == "%"

    ccc_card = next(c for c in payload["headline"] if c["id"] == "ccc_credit_spread")
    assert ccc_card["value"] == 6.87
    assert ccc_card["unit"] == "%"

    status_card = next(c for c in payload["headline"] if c["id"] == "credit_conditions")
    assert status_card["value"] == "stress"


def _credit_time_series():
    return {
        "aaa_corporate_yield": [
            {
                "date": "2020-12-27",
                "value": 1.56,
                "source": "Corporate_Bond_Indices.xlsm",
            },
            {
                "date": "2021-01-03",
                "value": 1.58,
                "source": "Corporate_Bond_Indices.xlsm",
            },
        ],
        "bbb_corporate_yield": [
            {
                "date": "2020-12-27",
                "value": 2.30,
                "source": "Corporate_Bond_Indices.xlsm",
            },
            {
                "date": "2021-01-03",
                "value": 2.32,
                "source": "Corporate_Bond_Indices.xlsm",
            },
        ],
        "ccc_corporate_yield": [
            {
                "date": "2020-12-27",
                "value": 8.10,
                "source": "Corporate_Bond_Indices.xlsm",
            },
            {
                "date": "2021-01-03",
                "value": 8.15,
                "source": "Corporate_Bond_Indices.xlsm",
            },
        ],
        "treasury_10y": [
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
        ],
    }


def test_build_corporate_yields_detail_payload_returns_three_series():
    payload = us_rates_liquidity.build_detail_payload(
        "corporate_yields",
        series_rows(),
        _credit_time_series(),
    )

    assert payload["detail_id"] == "corporate_yields"
    assert payload["title"] == "Corporate Yields"
    assert len(payload["charts"]) == 1
    assert payload["charts"][0]["kind"] == "time_series"
    assert payload["charts"][0]["title"] == "Corporate Yields (Historical)"
    assert len(payload["charts"][0]["series"]) == 2
    assert payload["charts"][0]["labels"]["aaa"] == "AAA"
    assert payload["charts"][0]["labels"]["bbb"] == "BBB"
    assert payload["charts"][0]["labels"]["ccc"] == "CCC"
    assert payload["charts"][0]["series"][0]["aaa"] == 1.56
    assert payload["charts"][0]["series"][0]["bbb"] == 2.30
    assert payload["charts"][0]["series"][0]["ccc"] == 8.10


def test_build_treasury_credit_spreads_detail_payload_computes_spreads():
    payload = us_rates_liquidity.build_detail_payload(
        "treasury_credit_spreads",
        series_rows(),
        _credit_time_series(),
    )

    assert payload["detail_id"] == "treasury_credit_spreads"
    assert payload["title"] == "Treasury Credit Spreads"
    assert len(payload["charts"]) == 1
    assert payload["charts"][0]["kind"] == "time_series"
    assert payload["charts"][0]["title"] == "Treasury Credit Spreads (Historical)"
    assert payload["charts"][0]["labels"]["aaa_spread"] == "AAA - 10Y"
    assert payload["charts"][0]["labels"]["bbb_spread"] == "BBB - 10Y"
    assert payload["charts"][0]["labels"]["ccc_spread"] == "CCC - 10Y"
    last = payload["charts"][0]["series"][-1]
    assert last["aaa_spread"] == 0.65
    assert last["bbb_spread"] == 1.39
    assert last["ccc_spread"] == 7.22


def test_build_quality_spreads_detail_payload_computes_quality_spreads():
    payload = us_rates_liquidity.build_detail_payload(
        "quality_spreads",
        series_rows(),
        _credit_time_series(),
    )

    assert payload["detail_id"] == "quality_spreads"
    assert payload["title"] == "Quality Spreads"
    assert len(payload["charts"]) == 1
    assert payload["charts"][0]["kind"] == "time_series"
    assert payload["charts"][0]["title"] == "Quality Spreads (Historical)"
    assert payload["charts"][0]["labels"]["bbb_aaa"] == "BBB - AAA"
    assert payload["charts"][0]["labels"]["ccc_bbb"] == "CCC - BBB"
    assert payload["charts"][0]["labels"]["ccc_aaa"] == "CCC - AAA"
    last = payload["charts"][0]["series"][-1]
    assert last["bbb_aaa"] == 0.74
    assert last["ccc_bbb"] == 5.83
    assert last["ccc_aaa"] == 6.57


def test_detail_series_ids_returns_corporate_credit_ids():
    assert us_rates_liquidity.detail_series_ids("corporate_yields") == [
        "aaa_corporate_yield",
        "bbb_corporate_yield",
        "ccc_corporate_yield",
    ]
    assert "treasury_10y" in us_rates_liquidity.detail_series_ids(
        "treasury_credit_spreads"
    )
    assert "aaa_corporate_yield" in us_rates_liquidity.detail_series_ids(
        "treasury_credit_spreads"
    )


def test_bbb_credit_spread_detail_returns_single_line_series():
    payload = us_rates_liquidity.build_detail_payload(
        "bbb_credit_spread",
        [],
        {
            "treasury_10y": [{"date": "2021-01-03", "value": 0.93}],
            "bbb_corporate_yield": [{"date": "2021-01-07", "value": 2.16}],
        },
    )

    chart = payload["charts"][0]
    assert payload["detail_id"] == "bbb_credit_spread"
    assert chart["kind"] == "time_series"
    assert chart["title"] == "BBB Credit Spread"
    assert chart["keys"] == ["bbb_credit_spread"]
    assert chart["labels"] == {"bbb_credit_spread": "BBB - 10Y"}
    assert chart["series"] == [{"date": "2021-01-07", "bbb_credit_spread": 1.23}]


def test_ccc_credit_spread_detail_returns_single_line_series():
    payload = us_rates_liquidity.build_detail_payload(
        "ccc_credit_spread",
        [],
        {
            "treasury_10y": [{"date": "2021-01-03", "value": 0.93}],
            "ccc_corporate_yield": [{"date": "2021-01-07", "value": 8.34}],
        },
    )

    chart = payload["charts"][0]
    assert payload["detail_id"] == "ccc_credit_spread"
    assert chart["kind"] == "time_series"
    assert chart["title"] == "CCC Credit Spread"
    assert chart["keys"] == ["ccc_credit_spread"]
    assert chart["labels"] == {"ccc_credit_spread": "CCC - 10Y"}
    assert chart["series"] == [{"date": "2021-01-07", "ccc_credit_spread": 7.41}]


def test_ccc_bbb_quality_spread_detail_returns_single_line_series():
    payload = us_rates_liquidity.build_detail_payload(
        "ccc_bbb_quality_spread",
        [],
        {
            "bbb_corporate_yield": [{"date": "2021-01-07", "value": 2.16}],
            "ccc_corporate_yield": [{"date": "2021-01-07", "value": 8.34}],
        },
    )

    chart = payload["charts"][0]
    assert payload["detail_id"] == "ccc_bbb_quality_spread"
    assert chart["kind"] == "time_series"
    assert chart["title"] == "CCC vs BBB Quality Spread"
    assert chart["keys"] == ["ccc_bbb_quality_spread"]
    assert chart["labels"] == {"ccc_bbb_quality_spread": "CCC - BBB"}
    assert chart["series"] == [{"date": "2021-01-07", "ccc_bbb_quality_spread": 6.18}]


def test_credit_risk_regime_detail_returns_diagnostics_as_compat_alias():
    payload = us_rates_liquidity.build_detail_payload(
        "credit_risk_regime",
        [],
        {
            "treasury_10y": [{"date": "2021-01-03", "value": 0.93}],
            "bbb_corporate_yield": [{"date": "2021-01-07", "value": 2.16}],
            "ccc_corporate_yield": [{"date": "2021-01-07", "value": 8.34}],
        },
    )

    chart = payload["charts"][0]
    assert chart["kind"] == "credit_diagnostics"
    assert set(chart["metrics"]) == {
        "bbb_credit_spread",
        "ccc_credit_spread",
        "ccc_bbb_quality_spread",
    }


def test_credit_level_zone_classifies_bbb_spread():
    assert us_rates_liquidity._bbb_credit_zone(1.49) == "very_low"
    assert us_rates_liquidity._bbb_credit_zone(1.50) == "normal"
    assert us_rates_liquidity._bbb_credit_zone(2.50) == "tightening"
    assert us_rates_liquidity._bbb_credit_zone(4.00) == "stressed"
    assert us_rates_liquidity._bbb_credit_zone(6.00) == "crisis"


def test_credit_level_zone_classifies_quality_spread():
    assert us_rates_liquidity._ccc_bbb_quality_zone(2.99) == "low_dispersion"
    assert us_rates_liquidity._ccc_bbb_quality_zone(3.00) == "normal"
    assert us_rates_liquidity._ccc_bbb_quality_zone(5.00) == "weak_credit_pressure"
    assert us_rates_liquidity._ccc_bbb_quality_zone(8.00) == "serious_deterioration"
    assert us_rates_liquidity._ccc_bbb_quality_zone(12.00) == "crisis"


def test_credit_level_zone_classifies_ccc_spread():
    assert us_rates_liquidity._ccc_credit_zone(4.99) == "calm"
    assert us_rates_liquidity._ccc_credit_zone(5.00) == "elevated"
    assert us_rates_liquidity._ccc_credit_zone(8.00) == "stressed"
    assert us_rates_liquidity._ccc_credit_zone(12.00) == "crisis"


def test_credit_percentile_and_label():
    values = [1, 2, 3, 4]

    assert us_rates_liquidity._percentile_rank(values, 3) == 75
    assert us_rates_liquidity._percentile_label(24) == "low"
    assert us_rates_liquidity._percentile_label(25) == "normal"
    assert us_rates_liquidity._percentile_label(75) == "elevated"
    assert us_rates_liquidity._percentile_label(90) == "extreme"


def test_credit_trend_summary_computes_changes_and_acceleration():
    series = [
        {"date": "2021-01-01", "value": 1.0},
        {"date": "2021-01-08", "value": 1.1},
        {"date": "2021-01-15", "value": 1.2},
        {"date": "2021-01-22", "value": 1.3},
        {"date": "2021-01-29", "value": 1.9},
    ]

    summary = us_rates_liquidity._trend_summary(series)

    assert summary["change_1m"] == 0.90
    assert summary["change_3m"] is None
    assert summary["trend_1m"] == "rising"
    assert summary["trend_3m"] == "missing"
    assert summary["acceleration"] == "none"


def test_credit_trend_summary_uses_calendar_lookback_for_daily_series():
    series = [
        {"date": f"2021-01-{day:02d}", "value": value}
        for day, value in [
            (1, 1.00),
            (2, 1.00),
            (3, 1.00),
            (4, 1.00),
            (5, 1.00),
            (6, 1.00),
            (7, 1.00),
            (8, 1.20),
            (9, 1.20),
            (10, 1.20),
            (11, 1.20),
            (12, 1.20),
            (13, 1.20),
            (14, 1.20),
            (15, 1.20),
            (16, 1.20),
            (17, 1.20),
            (18, 1.20),
            (19, 1.20),
            (20, 1.20),
            (21, 1.20),
            (22, 1.20),
            (23, 1.20),
            (24, 1.20),
            (25, 1.20),
            (26, 1.20),
            (27, 1.20),
            (28, 1.20),
            (29, 1.20),
            (30, 1.80),
            (31, 1.80),
        ]
    ]

    summary = us_rates_liquidity._trend_summary(series)

    assert summary["change_1m"] == 0.80
    assert summary["trend_1m"] == "rising"


def test_credit_trend_summary_detects_accelerating_up():
    series = [
        {"date": "2020-10-14", "value": 1.00},
        {"date": "2020-11-14", "value": 1.20},
        {"date": "2020-12-14", "value": 1.45},
        {"date": "2021-01-07", "value": 1.60},
        {"date": "2021-01-14", "value": 2.20},
    ]

    summary = us_rates_liquidity._trend_summary(series)

    assert summary["change_1m"] == 0.75
    assert summary["change_3m"] == 1.20
    assert summary["trend_1m"] == "rising"
    assert summary["trend_3m"] == "rising"
    assert summary["acceleration"] == "accelerating_up"


def test_credit_metric_diagnostic_combines_level_percentile_and_trend():
    series = [
        {"date": "2021-01-01", "bbb_credit_spread": 1.0},
        {"date": "2021-01-08", "bbb_credit_spread": 1.1},
        {"date": "2021-01-15", "bbb_credit_spread": 1.2},
        {"date": "2021-01-22", "bbb_credit_spread": 1.3},
        {"date": "2021-01-29", "bbb_credit_spread": 1.6},
    ]

    diagnostic = us_rates_liquidity._credit_metric_diagnostic(
        series,
        "bbb_credit_spread",
        us_rates_liquidity._bbb_credit_zone,
    )

    assert diagnostic == {
        "value": 1.6,
        "zone": "normal",
        "percentile": 100,
        "percentile_label": "extreme",
        "change_1m": 0.60,
        "change_3m": None,
        "trend_1m": "rising",
        "trend_3m": "missing",
        "acceleration": "none",
    }


def test_credit_diagnostics_status_identifies_weak_credit_warning():
    diagnostics = {
        "bbb_credit_spread": {
            "zone": "very_low",
            "trend_1m": "stable",
            "trend_3m": "stable",
            "acceleration": "none",
        },
        "ccc_bbb_quality_spread": {
            "zone": "weak_credit_pressure",
            "trend_1m": "rising",
            "trend_3m": "rising",
            "acceleration": "none",
        },
    }

    assert (
        us_rates_liquidity._credit_conditions_status_from_diagnostics(diagnostics)
        == "weak_credit_warning"
    )


def test_credit_diagnostics_status_identifies_healthy():
    diagnostics = {
        "bbb_credit_spread": {
            "zone": "very_low",
            "trend_1m": "stable",
            "trend_3m": "stable",
            "acceleration": "none",
        },
        "ccc_bbb_quality_spread": {
            "zone": "normal",
            "trend_1m": "stable",
            "trend_3m": "stable",
            "acceleration": "none",
        },
    }

    assert (
        us_rates_liquidity._credit_conditions_status_from_diagnostics(diagnostics)
        == "healthy"
    )


def test_credit_diagnostics_status_identifies_risk_rising():
    diagnostics = {
        "bbb_credit_spread": {
            "zone": "tightening",
            "trend_1m": "rising",
            "trend_3m": "rising",
            "acceleration": "none",
        },
        "ccc_bbb_quality_spread": {
            "zone": "weak_credit_pressure",
            "trend_1m": "rising",
            "trend_3m": "rising",
            "acceleration": "none",
        },
    }

    assert (
        us_rates_liquidity._credit_conditions_status_from_diagnostics(diagnostics)
        == "risk_rising"
    )


def test_credit_diagnostics_status_identifies_crisis_stress():
    diagnostics = {
        "bbb_credit_spread": {
            "zone": "crisis",
            "trend_1m": "rising",
            "trend_3m": "rising",
            "acceleration": "accelerating_up",
        },
        "ccc_bbb_quality_spread": {
            "zone": "serious_deterioration",
            "trend_1m": "rising",
            "trend_3m": "rising",
            "acceleration": "none",
        },
    }

    assert (
        us_rates_liquidity._credit_conditions_status_from_diagnostics(diagnostics)
        == "crisis_stress"
    )


def test_credit_diagnostics_status_returns_mixed_for_unclear():
    diagnostics = {
        "bbb_credit_spread": {
            "zone": "tightening",
            "trend_1m": "falling",
            "trend_3m": "stable",
            "acceleration": "none",
        },
        "ccc_bbb_quality_spread": {
            "zone": "normal",
            "trend_1m": "stable",
            "trend_3m": "stable",
            "acceleration": "none",
        },
    }

    assert (
        us_rates_liquidity._credit_conditions_status_from_diagnostics(diagnostics)
        == "mixed"
    )


def test_credit_diagnostics_status_returns_missing_when_data_absent():
    diagnostics = {
        "bbb_credit_spread": {
            "zone": "missing",
            "trend_1m": "missing",
            "trend_3m": "missing",
            "acceleration": "none",
        },
        "ccc_bbb_quality_spread": {
            "zone": "missing",
            "trend_1m": "missing",
            "trend_3m": "missing",
            "acceleration": "none",
        },
    }

    assert (
        us_rates_liquidity._credit_conditions_status_from_diagnostics(diagnostics)
        == "missing"
    )


def test_credit_conditions_diagnostics_detail_returns_metrics_and_series():
    payload = us_rates_liquidity.build_detail_payload(
        "credit_conditions_diagnostics",
        [],
        {
            "treasury_10y": [
                {"date": "2021-01-01", "value": 1.0},
                {"date": "2021-01-08", "value": 1.0},
                {"date": "2021-01-15", "value": 1.0},
                {"date": "2021-01-22", "value": 1.0},
                {"date": "2021-01-29", "value": 1.0},
            ],
            "bbb_corporate_yield": [
                {"date": "2021-01-01", "value": 2.0},
                {"date": "2021-01-08", "value": 2.1},
                {"date": "2021-01-15", "value": 2.2},
                {"date": "2021-01-22", "value": 2.3},
                {"date": "2021-01-29", "value": 2.6},
            ],
            "ccc_corporate_yield": [
                {"date": "2021-01-01", "value": 6.0},
                {"date": "2021-01-08", "value": 6.4},
                {"date": "2021-01-15", "value": 6.8},
                {"date": "2021-01-22", "value": 7.2},
                {"date": "2021-01-29", "value": 8.6},
            ],
        },
    )

    chart = payload["charts"][0]
    assert payload["detail_id"] == "credit_conditions_diagnostics"
    assert chart["kind"] == "credit_diagnostics"
    assert chart["status"] in {
        "healthy",
        "weak_credit_warning",
        "risk_rising",
        "crisis_stress",
        "mixed",
    }
    assert set(chart["metrics"]) == {
        "bbb_credit_spread",
        "ccc_credit_spread",
        "ccc_bbb_quality_spread",
    }
    assert chart["series"][-1] == {
        "date": "2021-01-29",
        "bbb_credit_spread": 1.6,
        "ccc_credit_spread": 7.6,
        "ccc_bbb_quality_spread": 6.0,
    }


def test_build_dashboard_payload_reports_credit_data_gap():
    credit_series_points = {
        "aaa_corporate_yield": [
            {
                "date": "2021-01-07",
                "value": 2.00,
                "source": "Corporate_Bond_Indices.xlsm",
            },
            {"date": "2023-10-01", "value": 6.00, "source": "BAMLC0A4CBBBEY.csv"},
        ],
        "bbb_corporate_yield": [
            {
                "date": "2021-01-07",
                "value": 2.00,
                "source": "Corporate_Bond_Indices.xlsm",
            },
            {"date": "2023-10-01", "value": 6.00, "source": "BAMLC0A4CBBBEY.csv"},
        ],
        "ccc_corporate_yield": [
            {
                "date": "2021-01-07",
                "value": 2.00,
                "source": "Corporate_Bond_Indices.xlsm",
            },
            {"date": "2023-10-01", "value": 6.00, "source": "BAMLC0A4CBBBEY.csv"},
        ],
    }
    payload = us_rates_liquidity.build_dashboard_payload(
        series_rows(),
        latest_points(),
        credit_macro_series_points=credit_series_points,
    )

    assert payload["credit_coverage"] == {
        "series_ids": [
            "aaa_corporate_yield",
            "bbb_corporate_yield",
            "ccc_corporate_yield",
        ],
        "start_date": "2021-01-07",
        "latest_date": "2023-10-01",
        "gap_start": "2021-01-08",
        "gap_end": "2023-09-30",
        "has_gap": True,
        "source_note": "P05 workbook history is merged with latest FRED ICE/BofA observations. Missing dates are shown as a data gap and are not interpolated.",
    }


def test_credit_interpretation_snapshot_is_stable_and_hashable():
    derived = {
        "credit_as_of": "2026-07-06",
        "bbb_credit_spread": 0.98,
        "ccc_credit_spread": 9.42,
        "ccc_bbb_quality_spread": 8.44,
        "credit_conditions_status": "risk_rising",
        "credit_diagnostics": {
            "bbb_credit_spread": {
                "value": 0.98,
                "zone": "very_low",
                "percentile": 21,
                "trend_1m": "stable",
                "trend_3m": "falling",
                "acceleration": "none",
            },
            "ccc_credit_spread": {
                "value": 9.42,
                "zone": "serious_deterioration",
                "percentile": 43,
                "trend_1m": "rising",
                "trend_3m": "rising",
                "acceleration": "none",
            },
            "ccc_bbb_quality_spread": {
                "value": 8.44,
                "zone": "serious_deterioration",
                "percentile": 41,
                "trend_1m": "rising",
                "trend_3m": "rising",
                "acceleration": "none",
            },
        },
    }
    coverage = {
        "has_gap": True,
        "gap_start": "2021-01-08",
        "gap_end": "2023-07-09",
    }

    snapshot = us_rates_liquidity.credit_interpretation_snapshot(derived, coverage)
    same_snapshot = us_rates_liquidity.credit_interpretation_snapshot(
        dict(reversed(list(derived.items()))),
        coverage,
    )

    assert snapshot["scope"] == "us_credit_conditions"
    assert snapshot["as_of"] == "2026-07-06"
    assert snapshot["status"] == "risk_rising"
    assert snapshot["metrics"]["bbb_credit_spread"]["value"] == 0.98
    assert snapshot["coverage"]["gap_start"] == "2021-01-08"
    assert snapshot["hash"] == same_snapshot["hash"]
