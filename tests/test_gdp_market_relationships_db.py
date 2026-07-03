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
