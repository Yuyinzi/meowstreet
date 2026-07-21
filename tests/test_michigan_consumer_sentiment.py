from pathlib import Path

import pytest

from app.data_sources.michigan_consumer_sentiment import (
    MICHIGAN_ARCHIVE_URL,
    AGGREGATE_TABLE_ID,
    COMPONENTS_TABLE_ID,
    TABLE_1_HEADER,
    TABLE_5_HEADER,
    MichiganConsumerSentimentClient,
    parse_aggregate_csv,
    parse_components_csv,
)


TABLE_1_CSV = (
    "Table 1: The Index of Consumer Sentiment\n"
    "Month,Year,Index,\n"
    "1,1978,83.7,\n"
    "2,1978,84.3,\n"
    "3,1978,78.8,\n"
    "4,1978,81.6,\n"
)


TABLE_5_CSV = (
    "Table 5: Components of the Index of Consumer Sentiment\n"
    "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index,\n"
    "1,1978,105,114,106,80,142,96.2,75.7,\n"
    "2,1978,106,109,108,89,139,95.4,77.2,\n"
)


def _write_csv(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_aggregate_csv_returns_ascending_rows(tmp_path):
    path = _write_csv(tmp_path, "table_1.csv", TABLE_1_CSV)
    rows = parse_aggregate_csv(path)
    assert len(rows) == 4
    assert rows[0] == {"date": "1978-01-01", "value": 83.7}
    assert rows[-1] == {"date": "1978-04-01", "value": 81.6}
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


def test_parse_aggregate_csv_handles_decimal_values(tmp_path):
    content = "Title\nMonth,Year,Index,\n1,2024,71.4,\n2,2024,76.9,\n"
    path = _write_csv(tmp_path, "table_1.csv", content)
    rows = parse_aggregate_csv(path)
    assert rows[0]["value"] == 71.4
    assert rows[1]["value"] == 76.9


def test_parse_components_csv_extracts_both_series(tmp_path):
    path = _write_csv(tmp_path, "table_5.csv", TABLE_5_CSV)
    rows = parse_components_csv(path)
    assert len(rows) == 2
    assert rows[0] == {
        "date": "1978-01-01",
        "current_conditions": 96.2,
        "expectations": 75.7,
    }
    assert rows[1] == {
        "date": "1978-02-01",
        "current_conditions": 95.4,
        "expectations": 77.2,
    }


def test_parse_aggregate_csv_rejects_missing_header(tmp_path):
    content = "Some random title\nNot,The,Header\n1,1978,80.0,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="missing required header"):
        parse_aggregate_csv(path)


def test_parse_components_csv_rejects_wrong_header(tmp_path):
    content = "Title\nMonth,Year,Wrong,Columns\n1,1978,85.0,95.1,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="missing required header"):
        parse_components_csv(path)


def test_parse_aggregate_csv_rejects_blank_month(tmp_path):
    content = "Title\nMonth,Year,Index,\n,1978,80.0,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Month"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_blank_year(tmp_path):
    content = "Title\nMonth,Year,Index,\n1,,80.0,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Year"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_invalid_month(tmp_path):
    content = "Title\nMonth,Year,Index,\n13,1978,80.0,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="invalid month"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_duplicate_date(tmp_path):
    content = "Title\nMonth,Year,Index,\n1,1978,80.0,\n1,1978,81.0,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="duplicate date"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_blank_value(tmp_path):
    content = "Title\nMonth,Year,Index,\n1,1978,,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Index"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_nonnumeric_value(tmp_path):
    content = "Title\nMonth,Year,Index,\n1,1978,N/A,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="non-numeric Index"):
        parse_aggregate_csv(path)


def test_parse_components_csv_rejects_blank_current(tmp_path):
    content = (
        "Title\n"
        "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index,\n"
        "1,1978,105,114,106,80,142,,75.7,\n"
    )
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Current Index"):
        parse_components_csv(path)


def test_parse_components_csv_rejects_nonnumeric_expectations(tmp_path):
    content = (
        "Title\n"
        "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index,\n"
        "1,1978,105,114,106,80,142,96.2,N/A,\n"
    )
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="non-numeric Expected Index"):
        parse_components_csv(path)


def test_michigan_client_fetch_csvs_returns_paths(tmp_path):
    client = MichiganConsumerSentimentClient()
    import unittest.mock

    with unittest.mock.patch(
        "app.data_sources.michigan_consumer_sentiment.urlopen",
        return_value=unittest.mock.MagicMock(read=lambda: b""),
    ):
        result = client.fetch_csvs(tmp_path)
    assert AGGREGATE_TABLE_ID in result
    assert COMPONENTS_TABLE_ID in result
    assert result[AGGREGATE_TABLE_ID].exists()
    assert result[COMPONENTS_TABLE_ID].exists()


def test_parse_components_csv_with_real_header_format(tmp_path):
    content = (
        "Table 5: Components of the Index of Consumer Sentiment\n"
        "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index,\n"
        "1,1978,105,114,106,80,142,96.2,75.7,\n"
    )
    path = _write_csv(tmp_path, "table_5.csv", content)
    rows = parse_components_csv(path)
    assert rows[0]["current_conditions"] == 96.2
    assert rows[0]["expectations"] == 75.7


def test_rejects_too_few_lines(tmp_path):
    content = "Only one line\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="only 1 lines"):
        parse_aggregate_csv(path)


def test_import_script_creates_reissue_order(tmp_path):
    content = (
        "Table 5: Components of the Index of Consumer Sentiment\n"
        "Month,Year,Personal Finance Current,Personal Finance Expected,Business Condition 12 Months,Business Condition 5 Years,Buying Conditions,Current Index,Expected Index,\n"
        "1,1978,105,114,106,80,142,96.2,75.7,\n"
    )
    path = _write_csv(tmp_path, "table_5.csv", content)
    rows = parse_components_csv(path)
    assert rows[0]["current_conditions"] == 96.2
    assert rows[0]["expectations"] == 75.7
