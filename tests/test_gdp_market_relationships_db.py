from app.db import gdp_market_relationships


def relationship_payload():
    return {
        "relationship_id": "us_sp500_gdp",
        "title": "S&P 500 vs US GDP",
        "region": "US",
        "economy": "US GDP",
        "index_name": "S&P 500",
        "primary_lag_months": 6,
        "correlation_window_years": 10,
        "source_workbook": "GDP_Correlations.xlsx",
        "source_sheet": "S&P500_USGDP Correlation",
    }


def lag_rows():
    return [
        {
            "relationship_id": "us_sp500_gdp",
            "date": "2020-06-30",
            "lag_months": 0,
            "index_yoy": 0.05,
            "gdp_yoy": -0.09,
            "rolling_correlation": 0.17,
            "source_workbook": "GDP_Correlations.xlsx",
            "source_sheet": "S&P500_USGDP Correlation",
        },
        {
            "relationship_id": "us_sp500_gdp",
            "date": "2020-06-30",
            "lag_months": 6,
            "index_yoy": 0.29,
            "gdp_yoy": -0.09,
            "rolling_correlation": -0.09,
            "source_workbook": "GDP_Correlations.xlsx",
            "source_sheet": "S&P500_USGDP Correlation",
        },
    ]


def quad_rows():
    return [
        {
            "relationship_id": "us_sp500_gdp",
            "date": "2020-09-30",
            "period_label": "2020 Q3",
            "primary_lag_months": 6,
            "index_level": 2584.59,
            "gdp_level": 18596.521,
            "index_direction": 0,
            "gdp_direction": 1,
            "quad_case": "0,1",
            "source_workbook": "GDP_Correlations.xlsx",
            "source_sheet": "S&P500_US_Quadnomial",
        }
    ]


def test_replace_and_load_gdp_relationship_data(tmp_path):
    con = gdp_market_relationships.connect(tmp_path / "gdp.sqlite")

    saved = gdp_market_relationships.replace_relationship_data(
        con,
        relationship_payload(),
        lag_rows(),
        quad_rows(),
    )

    assert saved == {"relationships": 1, "lag_rows": 2, "quad_rows": 1}
    assert (
        gdp_market_relationships.load_relationships(con)[0]["relationship_id"]
        == "us_sp500_gdp"
    )
    assert len(gdp_market_relationships.load_lag_rows(con, "us_sp500_gdp")) == 2
    assert (
        gdp_market_relationships.load_quad_rows(con, "us_sp500_gdp")[0]["quad_case"]
        == "0,1"
    )


def test_normalize_relationship_id_rejects_blank():
    try:
        gdp_market_relationships.normalize_relationship_id(" ")
    except ValueError as exc:
        assert str(exc) == "relationship id is required"
    else:
        raise AssertionError("expected ValueError")


def test_replace_relationship_rows_for_dates_preserves_other_dates(tmp_path):
    con = gdp_market_relationships.connect(tmp_path / "gdp.sqlite")
    gdp_market_relationships.replace_relationship_data(
        con,
        relationship_payload(),
        lag_rows()
        + [
            {
                "relationship_id": "us_sp500_gdp",
                "date": "2020-03-31",
                "lag_months": 6,
                "index_yoy": 0.11,
                "gdp_yoy": 0.02,
                "rolling_correlation": 0.33,
                "source_workbook": "GDP_Correlations.xlsx",
                "source_sheet": "S&P500_USGDP Correlation",
            }
        ],
        quad_rows()
        + [
            {
                "relationship_id": "us_sp500_gdp",
                "date": "2020-06-30",
                "period_label": "2020 Q2",
                "primary_lag_months": 6,
                "index_level": 2800,
                "gdp_level": 18000,
                "index_direction": 0,
                "gdp_direction": 0,
                "quad_case": "0,0",
                "source_workbook": "GDP_Correlations.xlsx",
                "source_sheet": "S&P500_US_Quadnomial",
            }
        ],
    )

    saved = gdp_market_relationships.replace_relationship_rows_for_dates(
        con,
        "us_sp500_gdp",
        ["2020-06-30"],
        [
            {
                "date": "2020-06-30",
                "lag_months": 6,
                "index_yoy": 0.22,
                "gdp_yoy": 0.03,
                "rolling_correlation": 0.55,
                "source_workbook": "GDPC1.csv+SP500.csv",
                "source_sheet": "computed",
            }
        ],
        [
            {
                "date": "2020-06-30",
                "period_label": "2020 Q2",
                "primary_lag_months": 6,
                "index_level": 3000,
                "gdp_level": 19000,
                "index_direction": 1,
                "gdp_direction": 1,
                "quad_case": "1,1",
                "source_workbook": "GDPC1.csv+SP500.csv",
                "source_sheet": "computed",
            }
        ],
    )

    loaded_lag = gdp_market_relationships.load_lag_rows(con, "us_sp500_gdp")
    loaded_quad = gdp_market_relationships.load_quad_rows(con, "us_sp500_gdp")

    assert saved == {"lag_rows": 1, "quad_rows": 1}
    assert any(row["date"] == "2020-03-31" for row in loaded_lag)
    assert any(
        row["date"] == "2020-06-30" and row["index_yoy"] == 0.22
        for row in loaded_lag
    )
    assert loaded_quad[0]["date"] == "2020-06-30"
    assert loaded_quad[0]["quad_case"] == "1,1"
    assert loaded_quad[-1]["date"] == "2020-09-30"
