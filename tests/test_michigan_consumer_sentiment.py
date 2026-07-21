import csv
import io
from pathlib import Path

import pytest

from app.data_sources.michigan_consumer_sentiment import (
    MICHIGAN_ARCHIVE_URL,
    AGGREGATE_TABLE_ID,
    COMPONENTS_TABLE_ID,
    MichiganConsumerSentimentClient,
    parse_aggregate_csv,
    parse_components_csv,
)


TABLE_1_CSV = (
    "Month,Year,Index,Title,University of Michigan Consumer Sentiment Index\n"
    "1,1978,80.0,,,,,\n"
    "2,1978,78.5,,,,,\n"
    "3,1978,80.3,,,,,\n"
    "4,1978,78.1,,,,,\n"
    "5,1978,75.2,,,,,\n"
    "6,1978,78.2,,,,,\n"
)


TABLE_5_CSV = (
    "Month,Year,Current Index,Expected Index\n"
    "1,1978,85.0,95.1,,,,,\n"
    "2,1978,84.2,94.8,,,,,\n"
    "3,1978,83.9,95.5,,,,,\n"
)


TABLE_5_NO_TRAILING = (
    "Month,Year,Current Index,Expected Index\n1,1978,85.0,95.1\n2,1978,84.2,94.8\n"
)


def _write_csv(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_aggregate_csv_returns_ascending_rows(tmp_path):
    path = _write_csv(tmp_path, "table_1.csv", TABLE_1_CSV)
    rows = parse_aggregate_csv(path)
    assert len(rows) == 6
    assert rows[0] == {"date": "1978-01-01", "value": 80.0}
    assert rows[-1] == {"date": "1978-06-01", "value": 78.2}
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


def test_parse_aggregate_csv_handles_decimal_values(tmp_path):
    content = "Month,Year,Index,Title\n1,2024,71.4,,,,,\n2,2024,76.9,,,,,\n"
    path = _write_csv(tmp_path, "table_1.csv", content)
    rows = parse_aggregate_csv(path)
    assert rows[0]["value"] == 71.4
    assert rows[1]["value"] == 76.9


def test_parse_components_csv_extracts_both_series(tmp_path):
    path = _write_csv(tmp_path, "table_5.csv", TABLE_5_CSV)
    rows = parse_components_csv(path)
    assert len(rows) == 3
    assert rows[0] == {
        "date": "1978-01-01",
        "current_conditions": 85.0,
        "expectations": 95.1,
    }
    assert rows[1] == {
        "date": "1978-02-01",
        "current_conditions": 84.2,
        "expectations": 94.8,
    }


def test_parse_components_csv_no_trailing_blank(tmp_path):
    path = _write_csv(tmp_path, "table_5.csv", TABLE_5_NO_TRAILING)
    rows = parse_components_csv(path)
    assert len(rows) == 2
    assert rows[-1] == {
        "date": "1978-02-01",
        "current_conditions": 84.2,
        "expectations": 94.8,
    }


def test_parse_aggregate_csv_rejects_missing_month_column(tmp_path):
    content = "Year,Index,Title\n1978,80.0\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="missing required header"):
        parse_aggregate_csv(path)


def test_parse_components_csv_rejects_missing_expected_index_column(tmp_path):
    content = "Month,Year,Current Index\n1,1978,85.0\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="missing required header"):
        parse_components_csv(path)


def test_parse_aggregate_csv_rejects_blank_month(tmp_path):
    content = "Month,Year,Index\n,1978,80.0\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Month"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_blank_year(tmp_path):
    content = "Month,Year,Index\n1,,80.0\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Year"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_invalid_month(tmp_path):
    content = "Month,Year,Index\n13,1978,80.0\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="invalid month"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_duplicate_date(tmp_path):
    content = "Month,Year,Index\n1,1978,80.0\n1,1978,81.0\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="duplicate date"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_blank_value(tmp_path):
    content = "Month,Year,Index\n1,1978,\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Index"):
        parse_aggregate_csv(path)


def test_parse_aggregate_csv_rejects_nonnumeric_value(tmp_path):
    content = "Month,Year,Index\n1,1978,N/A\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="non-numeric Index"):
        parse_aggregate_csv(path)


def test_parse_components_csv_rejects_blank_current(tmp_path):
    content = "Month,Year,Current Index,Expected Index\n1,1978,,95.1\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="blank Current Index"):
        parse_components_csv(path)


def test_parse_components_csv_rejects_nonnumeric_expectations(tmp_path):
    content = "Month,Year,Current Index,Expected Index\n1,1978,85.0,N/A\n"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="non-numeric Expected Index"):
        parse_components_csv(path)


def test_michigan_client_fetch_csvs_returns_paths(tmp_path):
    client = MichiganConsumerSentimentClient()

    def fake_urlopen(url, data=None, timeout=None):
        class FakeResponse:
            def read(self):
                return b""

        return FakeResponse()

    import unittest.mock

    with unittest.mock.patch(
        "app.data_sources.michigan_consumer_sentiment.urlopen",
        side_effect=lambda url, data=None, timeout=None: fake_urlopen(
            url, data, timeout
        ),
    ):
        result = client.fetch_csvs(tmp_path)

    assert AGGREGATE_TABLE_ID in result
    assert COMPONENTS_TABLE_ID in result
    assert result[AGGREGATE_TABLE_ID].exists()
    assert result[COMPONENTS_TABLE_ID].exists()
    assert result[AGGREGATE_TABLE_ID].name == "table_1.csv"
    assert result[COMPONENTS_TABLE_ID].name == "table_5.csv"


def test_michigan_client_parse_aggregate_round_trip(tmp_path):
    csv_path = _write_csv(tmp_path, "table_1.csv", TABLE_1_CSV)
    rows = parse_aggregate_csv(csv_path)
    assert len(rows) == 6
    assert all("date" in r and "value" in r for r in rows)


def test_michigan_client_parse_components_round_trip(tmp_path):
    csv_path = _write_csv(tmp_path, "table_5.csv", TABLE_5_CSV)
    rows = parse_components_csv(csv_path)
    assert len(rows) == 3
    assert all(
        "date" in r and "current_conditions" in r and "expectations" in r for r in rows
    )


def test_parse_components_csv_handles_trailing_blank_column(tmp_path):
    content = (
        "Month,Year,Current Index,Expected Index\n"
        "1,1978,85.0,95.1,,,,,\n"
        "2,1978,84.2,94.8,,,,,\n"
    )
    path = _write_csv(tmp_path, "table_5.csv", content)
    rows = parse_components_csv(path)
    assert len(rows) == 2
    assert rows[0]["current_conditions"] == 85.0
    assert rows[0]["expectations"] == 95.1
