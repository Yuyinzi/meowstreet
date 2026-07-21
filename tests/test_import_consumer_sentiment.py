from pathlib import Path

import pytest

from app.data_sources.michigan_consumer_sentiment import (
    AGGREGATE_TABLE_ID,
    COMPONENTS_TABLE_ID,
    parse_aggregate_csv,
    parse_components_csv,
)
from app.db import consumer_sentiment, macro_indicators


TABLE_1_CSV = (
    "Table 1: The Index of Consumer Sentiment\n"
    "Month,Year,Index,\n"
    "1,1978,80.0,\n"
    "2,1978,78.5,\n"
    "6,2026,70.2,\n"
)


TABLE_5_CSV = (
    "Table 5: Components of the Index of Consumer Sentiment\n"
    "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index,\n"
    "1,1978,105,114,106,80,142,85.0,95.1,\n"
    "2,1978,106,109,108,89,139,84.2,94.8,\n"
    "6,2026,100,102,95,75,140,68.5,71.0,\n"
)


FRED_HDT_CSV = "observation_date,HDTGPDUSQ163N\n2020-01-01,80.0\n2021-01-01,82.5\n"
FRED_TDSP_CSV = "observation_date,TDSP\n2020-01-01,9.8\n2021-01-01,9.7\n"
FRED_PSAVERT_CSV = "observation_date,PSAVERT\n2020-01-01,7.5\n2021-01-01,8.0\n"
FRED_HHMSDODNS_CSV = (
    "observation_date,HHMSDODNS\n2020-01-01,12000000.0\n2021-01-01,12500000.0\n"
)


@pytest.fixture
def table_1_path(tmp_path):
    path = tmp_path / "table_1.csv"
    path.write_text(TABLE_1_CSV, encoding="utf-8")
    return path


@pytest.fixture
def table_5_path(tmp_path):
    path = tmp_path / "table_5.csv"
    path.write_text(TABLE_5_CSV, encoding="utf-8")
    return path


@pytest.fixture
def fred_capacity_dir(tmp_path):
    for filename, content in [
        ("HDTGPDUSQ163N.csv", FRED_HDT_CSV),
        ("TDSP.csv", FRED_TDSP_CSV),
        ("PSAVERT.csv", FRED_PSAVERT_CSV),
        ("HHMSDODNS.csv", FRED_HHMSDODNS_CSV),
    ]:
        (tmp_path / filename).write_text(content, encoding="utf-8")
    return tmp_path


def test_import_michigan_csvs_stores_all_three_series(
    table_1_path, table_5_path, tmp_path
):
    from scripts.import_consumer_sentiment import import_michigan_csvs

    db_path = tmp_path / "market.sqlite"
    result = import_michigan_csvs(table_1_path, table_5_path, db_path)

    assert len(result) == 3
    con = consumer_sentiment.connect(db_path)
    try:
        series = macro_indicators.load_macro_indicator_series(con)
        series_ids = {s["series_id"] for s in series}
        assert series_ids == {
            "umcsi_aggregate",
            "umcsi_expectations",
            "umcsi_current_conditions",
        }
        aggregate_points = macro_indicators.load_macro_indicator_points(
            con, "umcsi_aggregate"
        )
        assert len(aggregate_points) == 3
        expectations_points = macro_indicators.load_macro_indicator_points(
            con, "umcsi_expectations"
        )
        assert len(expectations_points) == 3
        current_points = macro_indicators.load_macro_indicator_points(
            con, "umcsi_current_conditions"
        )
        assert len(current_points) == 3
    finally:
        con.close()


def test_import_michigan_csvs_metadata_has_required_fields(
    table_1_path, table_5_path, tmp_path
):
    from scripts.import_consumer_sentiment import import_michigan_csvs

    db_path = tmp_path / "market.sqlite"
    import_michigan_csvs(table_1_path, table_5_path, db_path)
    con = consumer_sentiment.connect(db_path)
    try:
        series = macro_indicators.load_macro_indicator_series(con)
        for s in series:
            assert "series_id" in s
            assert "title" in s
            assert "units" in s
            assert "source" in s
            assert "Michigan" in s["source"] or "UMCSI" in s["title"]
    finally:
        con.close()


def test_import_michigan_csvs_idempotent(table_1_path, table_5_path, tmp_path):
    from scripts.import_consumer_sentiment import import_michigan_csvs

    db_path = tmp_path / "market.sqlite"
    import_michigan_csvs(table_1_path, table_5_path, db_path)
    import_michigan_csvs(table_1_path, table_5_path, db_path)

    con = consumer_sentiment.connect(db_path)
    try:
        aggregate_points = macro_indicators.load_macro_indicator_points(
            con, "umcsi_aggregate"
        )
        assert len(aggregate_points) == 3
        assert aggregate_points[0]["value"] == 80.0
    finally:
        con.close()


def test_import_michigan_csvs_preserves_unrelated_series(
    table_1_path, table_5_path, tmp_path
):
    from scripts.import_consumer_sentiment import import_michigan_csvs

    db_path = tmp_path / "market.sqlite"
    con = consumer_sentiment.connect(db_path)
    macro_indicators.replace_macro_indicator_points(
        con,
        {
            "series_id": "treasury_10y",
            "title": "10Y",
            "units": "percent",
            "source": "test",
        },
        [{"date": "2026-06-01", "value": 4.5, "source": "test"}],
    )
    con.close()

    import_michigan_csvs(table_1_path, table_5_path, db_path)

    con = consumer_sentiment.connect(db_path)
    try:
        treasury = macro_indicators.load_macro_indicator_points(con, "treasury_10y")
        assert len(treasury) == 1
    finally:
        con.close()


def test_import_fred_csvs_stores_all_four(table_1_path, fred_capacity_dir, tmp_path):
    from scripts.import_consumer_sentiment import import_fred_csvs

    db_path = tmp_path / "market.sqlite"
    result = import_fred_csvs(fred_capacity_dir, db_path)

    assert len(result) == 4
    con = consumer_sentiment.connect(db_path)
    try:
        series = macro_indicators.load_macro_indicator_series(con)
        series_ids = {s["series_id"] for s in series}
        assert "household_debt_to_gdp" in series_ids
        assert "household_debt_service_ratio" in series_ids
        assert "personal_saving_rate" in series_ids
        assert "one_to_four_family_mortgage_liabilities" in series_ids
    finally:
        con.close()


def test_import_fred_missing_values_handled(fred_capacity_dir, tmp_path):
    from scripts.import_consumer_sentiment import import_fred_csvs

    csv_path = fred_capacity_dir / "HDTGPDUSQ163N.csv"
    csv_path.write_text(
        "observation_date,HDTGPDUSQ163N\n2020-01-01,80.0\n2020-04-01,.\n2020-07-01,82.0\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "market.sqlite"
    import_fred_csvs(fred_capacity_dir, db_path)

    con = consumer_sentiment.connect(db_path)
    try:
        points = macro_indicators.load_macro_indicator_points(
            con, "household_debt_to_gdp"
        )
        assert len(points) == 2
    finally:
        con.close()


def test_no_workbook_or_fred_umcsent():
    from scripts import import_consumer_sentiment as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "openpyxl" not in source
    assert "UMCSI.xlsx" not in source
    assert "UMCSENT" not in source
    assert "bootstrap" not in source
