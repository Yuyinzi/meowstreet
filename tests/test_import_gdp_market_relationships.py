import datetime

from openpyxl import Workbook

from app.db import gdp_market_relationships
from scripts import import_gdp_market_relationships


def make_workbook(path):
    wb = Workbook()
    wb.remove(wb.active)

    corr = wb.create_sheet("S&P500_USGDP Correlation")
    corr.append(
        [
            "Date",
            "S&P500",
            "US Real GDP",
            "S&P500 YoY",
            "GDP YoY",
            "Rolling 10yr-Correlation: NO LAG",
            "S&P500 YoY",
            "GDP YoY",
            "Rolling 10yr-Correlation: 3-MO LAG",
            "S&P500 YoY",
            "GDP YoY",
            "Rolling 10yr-Correlation: 6-MO LAG",
        ]
    )
    corr.append(
        [
            None,
            None,
            None,
            "No Lag",
            None,
            None,
            None,
            "S&P 500 3-Month Lag",
            None,
            None,
            "S&P 500 6-Month Lag",
            None,
        ]
    )
    corr.append(
        [
            datetime.datetime(2020, 6, 30),
            3100.29,
            17302.511,
            0.0538,
            -0.0903,
            0.1729,
            -0.0881,
            -0.0903,
            0.2602,
            0.2887,
            -0.0903,
            -0.0944,
        ]
    )

    quad = wb.create_sheet("S&P500_US_Quadnomial")
    quad.append(
        [
            "Date",
            "S&P500 6-MO LAG",
            None,
            "US Real GDP",
            "S&P",
            "GDP",
            "Total",
            "0,0",
            "1,1",
            "0,1",
            "1,0",
        ]
    )
    quad.append(
        [
            datetime.datetime(2020, 9, 30),
            2584.59,
            "2020 Q3",
            18596.521,
            0,
            1,
            1,
            None,
            None,
            1,
            None,
        ]
    )

    wb.save(path)


def test_parse_configured_relationship_extracts_lags_and_quad_rows(tmp_path):
    workbook_path = tmp_path / "GDP_Correlations.xlsx"
    make_workbook(workbook_path)

    relationship, lag_rows, quad_rows = (
        import_gdp_market_relationships.parse_relationship(
            workbook_path,
            import_gdp_market_relationships.GDP_RELATIONSHIP_SHEETS[0],
        )
    )

    assert relationship["relationship_id"] == "us_sp500_gdp"
    assert relationship["primary_lag_months"] == 6
    assert [row["lag_months"] for row in lag_rows] == [0, 3, 6]
    assert lag_rows[-1]["rolling_correlation"] == -0.0944
    assert quad_rows[0]["quad_case"] == "0,1"


def test_import_workbook_saves_relationship_data(tmp_path):
    db_path = tmp_path / "gdp.sqlite"
    workbook_path = tmp_path / "GDP_Correlations.xlsx"
    make_workbook(workbook_path)
    con = gdp_market_relationships.connect(db_path)

    inserted, errors = import_gdp_market_relationships.import_workbook(
        con,
        workbook_path,
        configs=[import_gdp_market_relationships.GDP_RELATIONSHIP_SHEETS[0]],
    )

    assert inserted["us_sp500_gdp"] == {"lag_rows": 3, "quad_rows": 1}
    assert errors == {}
    assert (
        gdp_market_relationships.load_relationships(con)[0]["relationship_id"]
        == "us_sp500_gdp"
    )
