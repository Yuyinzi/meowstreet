import csv
import io
from pathlib import Path

import httpx
import pytest

from app.data_sources.michigan_consumer_sentiment import (
    MICHIGAN_ARCHIVE_URL,
    MICHIGAN_FRONT_PAGE_URL,
    AGGREGATE_TABLE_ID,
    COMPONENTS_TABLE_ID,
    MichiganConsumerSentimentClient,
    fetch_front_page_results,
    parse_aggregate_csv,
    parse_components_csv,
)
from app.http_client import HttpClient


FRONT_PAGE_HTML = """
<html><body>
<h1>Preliminary Results for August 2026</h1>
<table id="front_table">
  <tr><td class=""></td><td class="em">Aug</td><td>Jul</td><td>Aug</td><td>M-M</td><td>Y-Y</td></tr>
  <tr><td></td><td class="em">2026</td><td>2026</td><td>2025</td><td>Change</td><td>Change</td></tr>
  <tr><td>Index of Consumer Sentiment</td><td class="em">51.0</td><td>55.2</td><td>58.2</td><td>-7.6%</td><td>-12.4%</td></tr>
  <tr><td>Current Economic Conditions</td><td class="em">51.8</td><td>54.8</td><td>61.7</td><td>-5.5%</td><td>-16.0%</td></tr>
  <tr><td>Index of Consumer Expectations</td><td class="em">50.6</td><td>55.4</td><td>55.9</td><td>-8.7%</td><td>-9.5%</td></tr>
</table>
</body></html>
"""

FRONT_PAGE_FINAL_HTML = """
<html><body>
<h1>Final Results for July 2026</h1>
<table id="front_table">
  <tr><td class=""></td><td class="em">Jul</td><td>Jun</td><td>Jul</td><td>M-M</td><td>Y-Y</td></tr>
  <tr><td></td><td class="em">2026</td><td>2026</td><td>2025</td><td>Change</td><td>Change</td></tr>
  <tr><td>Index of Consumer Sentiment</td><td class="em">55.2</td><td>49.5</td><td>61.0</td><td>11.5%</td><td>-9.5%</td></tr>
  <tr><td>Current Economic Conditions</td><td class="em">54.8</td><td>53.0</td><td>62.0</td><td>3.4%</td><td>-11.6%</td></tr>
  <tr><td>Index of Consumer Expectations</td><td class="em">55.4</td><td>47.1</td><td>60.5</td><td>17.6%</td><td>-8.4%</td></tr>
</table>
</body></html>
"""


def _front_page_client(html_text):
    def handler(request):
        assert request.method == "GET"
        assert request.url == MICHIGAN_FRONT_PAGE_URL
        return httpx.Response(200, content=html_text.encode("utf-8"))

    return HttpClient(transport=httpx.MockTransport(handler))


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
    TABLE_1_RESPONSE = "Month,Year,Index,Title\n1,1978,80.0\n"
    TABLE_5_RESPONSE = "Month,Year,Current Index,Expected Index\n1,1978,85.0,95.1\n"

    def handler(request):
        assert request.method == "POST"
        assert request.url == MICHIGAN_ARCHIVE_URL
        body = request.content
        if b"table=1" in body:
            return httpx.Response(200, content=TABLE_1_RESPONSE.encode("utf-8"))
        return httpx.Response(200, content=TABLE_5_RESPONSE.encode("utf-8"))

    client = MichiganConsumerSentimentClient(
        http_client=HttpClient(transport=httpx.MockTransport(handler))
    )

    result_table_1 = client.fetch_csv(tmp_path, AGGREGATE_TABLE_ID)
    assert result_table_1.exists()
    assert result_table_1.name == "table_1.csv"

    result_table_5 = client.fetch_csv(tmp_path, COMPONENTS_TABLE_ID)
    assert result_table_5.exists()
    assert result_table_5.name == "table_5.csv"


def test_michigan_client_rejects_empty_response(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"")

    client = MichiganConsumerSentimentClient(
        http_client=HttpClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(ValueError, match="empty response body"):
        client.fetch_csv(tmp_path, AGGREGATE_TABLE_ID)


def test_fetch_csv_rejects_plain_text_response(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"upstream temporarily unavailable")

    client = MichiganConsumerSentimentClient(
        http_client=HttpClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(ValueError, match="missing required columns"):
        client.fetch_csv(tmp_path, AGGREGATE_TABLE_ID)


def test_fetch_csv_rejects_wrong_columns_for_table(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"Date,Price\n1,100\n")

    client = MichiganConsumerSentimentClient(
        http_client=HttpClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(ValueError, match="missing required columns"):
        client.fetch_csv(tmp_path, COMPONENTS_TABLE_ID)


def test_fetch_csv_rejects_html_response(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"<html>upstream error</html>")

    client = MichiganConsumerSentimentClient(
        http_client=HttpClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(ValueError, match="non-csv"):
        client.fetch_csv(tmp_path, 1)


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


def test_parse_aggregate_csv_rejects_html_content(tmp_path):
    content = "<html><body>upstream error</body></html>"
    path = _write_csv(tmp_path, "bad.csv", content)
    with pytest.raises(ValueError, match="non-csv content"):
        parse_aggregate_csv(path)


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


def test_parse_aggregate_csv_handles_official_title_line(tmp_path):
    content = (
        "Table 1: The Index of Consumer Sentiment\nMonth,Year,Index,\n1,1978,83.7,\n"
    )
    path = _write_csv(tmp_path, "table_1.csv", content)

    assert parse_aggregate_csv(path) == [{"date": "1978-01-01", "value": 83.7}]


def test_parse_components_csv_handles_official_title_line(tmp_path):
    content = (
        "Table 5: Components of the Index of Consumer Sentiment\n"
        "Month,Year,Personal Finance Current,Personal Finance Expected,"
        "Business Condition 12 Months,Business Condition 5 Years,"
        "Buying Conditions,Current Index,Expected Index,\n"
        "1,1978,105,114,106,80,142,96.2,75.7,\n"
    )
    path = _write_csv(tmp_path, "table_5.csv", content)

    assert parse_components_csv(path) == [
        {
            "date": "1978-01-01",
            "current_conditions": 96.2,
            "expectations": 75.7,
        }
    ]


def test_parse_aggregate_csv_rejects_title_without_header(tmp_path):
    path = _write_csv(tmp_path, "bad.csv", "Only one line\n")

    with pytest.raises(ValueError, match="only 1 lines"):
        parse_aggregate_csv(path)


def test_fetch_front_page_results_parses_preliminary_two_months():
    results = fetch_front_page_results(_front_page_client(FRONT_PAGE_HTML))

    assert results["release_kind"] == "preliminary"
    assert results["latest"] == {
        "date": "2026-08-01",
        "sentiment": 51.0,
        "current_conditions": 51.8,
        "expectations": 50.6,
    }
    assert results["previous"] == {
        "date": "2026-07-01",
        "sentiment": 55.2,
        "current_conditions": 54.8,
        "expectations": 55.4,
    }


def test_fetch_front_page_results_parses_final_release():
    results = fetch_front_page_results(_front_page_client(FRONT_PAGE_FINAL_HTML))

    assert results["release_kind"] == "final"
    assert results["latest"]["date"] == "2026-07-01"
    assert results["latest"]["sentiment"] == 55.2
    assert results["previous"]["date"] == "2026-06-01"
    assert results["previous"]["expectations"] == 47.1


def test_fetch_front_page_results_rejects_h1_table_mismatch():
    html = FRONT_PAGE_HTML.replace(
        "Preliminary Results for August 2026", "Preliminary Results for September 2026"
    )

    with pytest.raises(ValueError, match="does not match h1"):
        fetch_front_page_results(_front_page_client(html))


def test_fetch_front_page_results_rejects_unexpected_h1():
    html = FRONT_PAGE_HTML.replace(
        "Preliminary Results for August 2026", "Surveys of Consumers"
    )

    with pytest.raises(ValueError, match="unexpected format"):
        fetch_front_page_results(_front_page_client(html))


def test_fetch_front_page_results_rejects_missing_h1():
    html = FRONT_PAGE_HTML.replace(
        "<h1>Preliminary Results for August 2026</h1>", ""
    )

    with pytest.raises(ValueError, match="missing the release h1"):
        fetch_front_page_results(_front_page_client(html))


def test_fetch_front_page_results_rejects_missing_table():
    html = FRONT_PAGE_HTML.replace('id="front_table"', 'id="other_table"')

    with pytest.raises(ValueError, match="missing table#front_table"):
        fetch_front_page_results(_front_page_client(html))


def test_fetch_front_page_results_rejects_missing_index_row():
    html = FRONT_PAGE_HTML.replace(
        "  <tr><td>Index of Consumer Expectations</td><td class=\"em\">50.6</td>"
        "<td>55.4</td><td>55.9</td><td>-8.7%</td><td>-9.5%</td></tr>\n",
        "",
    )

    with pytest.raises(ValueError, match="missing rows: expectations"):
        fetch_front_page_results(_front_page_client(html))


def test_fetch_front_page_results_rejects_non_numeric_value():
    html = FRONT_PAGE_HTML.replace(
        "<td>Current Economic Conditions</td><td class=\"em\">51.8</td>",
        "<td>Current Economic Conditions</td><td class=\"em\">N/A</td>",
    )

    with pytest.raises(ValueError, match="not numeric"):
        fetch_front_page_results(_front_page_client(html))
