import pytest

from app.db import gdp_market_relationships
from app.tools import gdp_market_relationship_compute


def raw_rows():
    dates = [
        f"{year}-{month_day}"
        for year in range(2010, 2022)
        for month_day in ["03-31", "06-30", "09-30", "12-31"]
    ]
    return [
        {
            "date": date_iso,
            "gdp_level": 1000 + index * 10,
            "index_level": 2000 + index * 20,
        }
        for index, date_iso in enumerate(dates)
    ]


def test_compute_lag_rows_builds_all_lags_and_yoy_values():
    rows = gdp_market_relationship_compute.compute_lag_rows(
        raw_rows(),
        source="computed",
    )

    latest_rows = [row for row in rows if row["date"] == "2021-12-31"]

    assert [row["lag_months"] for row in latest_rows] == [0, 3, 6, 9, 12]
    assert latest_rows[0]["gdp_yoy"] == pytest.approx(40 / 1430)
    assert latest_rows[0]["index_yoy"] == pytest.approx(80 / 2860)
    assert latest_rows[0]["source_workbook"] == "computed"
    assert latest_rows[0]["source_sheet"] == "computed"


def test_compute_lag_rows_uses_41_quarter_rolling_correlation_window():
    rows = gdp_market_relationship_compute.compute_lag_rows(
        raw_rows(),
        source="computed",
    )

    first_corr = [
        row
        for row in rows
        if row["lag_months"] == 0 and row["rolling_correlation"] is not None
    ][0]

    assert first_corr["date"] == "2021-03-31"
    assert first_corr["rolling_correlation"] == pytest.approx(1.0)


def test_compute_lag_rows_respects_configured_correlation_window_years():
    rows = gdp_market_relationship_compute.compute_lag_rows(
        raw_rows(),
        source="computed",
        correlation_window_years=5,
    )

    first_corr = [
        row
        for row in rows
        if row["lag_months"] == 0 and row["rolling_correlation"] is not None
    ][0]

    assert first_corr["date"] == "2016-03-31"
    assert first_corr["rolling_correlation"] == pytest.approx(1.0)


def test_compute_quad_rows_uses_primary_six_month_lag():
    rows = gdp_market_relationship_compute.compute_quad_rows(
        [
            {"date": "2020-03-31", "gdp_level": 100, "index_level": 3000},
            {"date": "2020-06-30", "gdp_level": 95, "index_level": 3100},
            {"date": "2020-09-30", "gdp_level": 98, "index_level": 3050},
            {"date": "2020-12-31", "gdp_level": 105, "index_level": 3200},
            {"date": "2021-03-31", "gdp_level": 104, "index_level": 3150},
        ],
        source="computed",
    )

    assert rows[-1]["date"] == "2021-03-31"
    assert rows[-1]["period_label"] == "2021 Q1"
    assert rows[-1]["primary_lag_months"] == 6
    assert rows[-1]["index_level"] == 3050
    assert rows[-1]["gdp_level"] == 104
    assert rows[-1]["index_direction"] == 0
    assert rows[-1]["gdp_direction"] == 0
    assert rows[-1]["quad_case"] == "0,0"


def test_compute_quad_rows_matches_workbook_first_usable_row_behavior():
    rows = gdp_market_relationship_compute.compute_quad_rows(
        [
            {"date": "1950-03-31", "gdp_level": 2184.872, "index_level": 17.29},
            {"date": "1950-06-30", "gdp_level": 2251.507, "index_level": 17.69},
            {"date": "1950-09-30", "gdp_level": 2338.514, "index_level": 19.45},
        ],
        source="computed",
    )

    assert rows[0]["date"] == "1950-09-30"
    assert rows[0]["index_level"] == 17.29
    assert rows[0]["index_direction"] == 1
    assert rows[0]["gdp_direction"] == 1
    assert rows[0]["quad_case"] == "1,1"


def test_computed_rows_match_expected_derived_rows_loaded_from_db(tmp_path):
    con = gdp_market_relationships.connect(tmp_path / "gdp.sqlite")
    input_rows = [
        {"date": "2020-03-31", "gdp_level": 100, "index_level": 3000},
        {"date": "2020-06-30", "gdp_level": 95, "index_level": 3100},
        {"date": "2020-09-30", "gdp_level": 98, "index_level": 3050},
        {"date": "2020-12-31", "gdp_level": 105, "index_level": 3200},
        {"date": "2021-03-31", "gdp_level": 104, "index_level": 3150},
    ]
    gdp_market_relationships.replace_raw_source_rows(
        con,
        "us_sp500_gdp",
        [
            {
                **row,
                "gdp_source": "fixture",
                "index_source": "fixture",
            }
            for row in input_rows
        ],
    )
    gdp_market_relationships.replace_relationship_data(
        con,
        {
            "relationship_id": "us_sp500_gdp",
            "title": "S&P 500 vs US GDP",
            "region": "US",
            "economy": "US GDP",
            "index_name": "S&P 500",
            "primary_lag_months": 6,
            "correlation_window_years": 10,
            "source_workbook": "expected",
            "source_sheet": "expected",
        },
        [],
        [
            {
                "date": "2021-03-31",
                "period_label": "2021 Q1",
                "primary_lag_months": 6,
                "index_level": 3050,
                "gdp_level": 104,
                "index_direction": 0,
                "gdp_direction": 0,
                "quad_case": "0,0",
                "source_workbook": "expected",
                "source_sheet": "expected",
            }
        ],
    )

    computed_quad_rows = gdp_market_relationship_compute.compute_quad_rows(
        gdp_market_relationships.load_raw_source_rows(con, "us_sp500_gdp"),
        source="computed",
    )
    expected_quad_rows = gdp_market_relationships.load_quad_rows(
        con,
        "us_sp500_gdp",
    )

    assert computed_quad_rows[-1]["date"] == expected_quad_rows[0]["date"]
    assert (
        computed_quad_rows[-1]["period_label"] == expected_quad_rows[0]["period_label"]
    )
    assert computed_quad_rows[-1]["index_level"] == expected_quad_rows[0]["index_level"]
    assert computed_quad_rows[-1]["gdp_level"] == expected_quad_rows[0]["gdp_level"]
    assert (
        computed_quad_rows[-1]["index_direction"]
        == expected_quad_rows[0]["index_direction"]
    )
    assert computed_quad_rows[-1]["gdp_direction"] == expected_quad_rows[0]["gdp_direction"]
    assert computed_quad_rows[-1]["quad_case"] == expected_quad_rows[0]["quad_case"]


def test_computed_lag_rows_match_expected_derived_rows_loaded_from_db(tmp_path):
    con = gdp_market_relationships.connect(tmp_path / "gdp.sqlite")
    input_rows = [
        {
            "date": f"{year}-{month_day}",
            "gdp_level": 1000 + index * 10,
            "index_level": 2000 + index * 20,
            "gdp_source": "fixture",
            "index_source": "fixture",
        }
        for index, (year, month_day) in enumerate(
            [
                (year, month_day)
                for year in range(2010, 2022)
                for month_day in ["03-31", "06-30", "09-30", "12-31"]
            ]
        )
    ]
    gdp_market_relationships.replace_raw_source_rows(
        con,
        "us_sp500_gdp",
        input_rows,
    )
    gdp_market_relationships.replace_relationship_data(
        con,
        {
            "relationship_id": "us_sp500_gdp",
            "title": "S&P 500 vs US GDP",
            "region": "US",
            "economy": "US GDP",
            "index_name": "S&P 500",
            "primary_lag_months": 6,
            "correlation_window_years": 10,
            "source_workbook": "expected",
            "source_sheet": "expected",
        },
        [
            {
                "date": "2021-12-31",
                "lag_months": 0,
                "index_yoy": 80 / 2860,
                "gdp_yoy": 40 / 1430,
                "rolling_correlation": 1.0,
                "source_workbook": "expected",
                "source_sheet": "expected",
            }
        ],
        [],
    )

    computed_lag_rows = gdp_market_relationship_compute.compute_lag_rows(
        gdp_market_relationships.load_raw_source_rows(con, "us_sp500_gdp"),
        source="computed",
    )
    expected_lag_rows = gdp_market_relationships.load_lag_rows(
        con,
        "us_sp500_gdp",
    )
    computed_latest = [
        row
        for row in computed_lag_rows
        if row["date"] == "2021-12-31" and row["lag_months"] == 0
    ][0]

    assert computed_latest["index_yoy"] == pytest.approx(expected_lag_rows[0]["index_yoy"])
    assert computed_latest["gdp_yoy"] == pytest.approx(expected_lag_rows[0]["gdp_yoy"])
    assert computed_latest["rolling_correlation"] == pytest.approx(
        expected_lag_rows[0]["rolling_correlation"]
    )
