import asyncio
from pathlib import Path

import httpx
import pytest

from app.db import consumer_sentiment, macro_indicators
from app.http_client import HttpClient
from app.services import macro_refresh_official


MICHIGAN_TABLES = {
    1: b"Month,Year,Index,\n6,2026,60.0,\n7,2026,54.0,\n",
    5: (
        b"Month,Year,Personal Finance Current,Personal Finance Expected,"
        b"Business Condition 12 Months,Business Condition 5 Years,"
        b"Buying Conditions,Current Index,Expected Index,\n"
        b"6,2026,100,102,95,75,140,61.0,59.0,\n"
        b"7,2026,100,102,95,75,140,53.0,55.0,\n"
    ),
}
MICHIGAN_FRONT_PAGE = """
<h1>Final Results for August 2026</h1>
<table id="front_table">
<tr><td></td><td>Aug</td><td>Jul</td></tr>
<tr><td></td><td>2026</td><td>2026</td></tr>
<tr><td>Index of Consumer Sentiment</td><td>51.0</td><td>55.2</td></tr>
<tr><td>Current Economic Conditions</td><td>51.8</td><td>54.8</td></tr>
<tr><td>Index of Consumer Expectations</td><td>50.6</td><td>55.4</td></tr>
</table>
"""


def michigan_http_client(front_page_response):
    def handler(request):
        if request.method == "POST":
            assert str(request.url) == "https://data.sca.isr.umich.edu/data-archive/mine.php"
            table_id = int(request.content.decode().split("&", 1)[0].split("=")[1])
            return httpx.Response(200, content=MICHIGAN_TABLES[table_id])
        assert request.method == "GET"
        assert str(request.url) == "https://www.sca.isr.umich.edu/"
        return front_page_response

    return HttpClient(transport=httpx.MockTransport(handler), max_attempts=1)


@pytest.mark.parametrize("release_kind", ["Final", "Preliminary"])
def test_michigan_refresh_merges_latest_front_page_and_revised_previous_month(
    monkeypatch, tmp_path, release_kind
):
    artifacts = {}
    db_path = tmp_path / "market.sqlite"
    html = MICHIGAN_FRONT_PAGE.replace("Final", release_kind)

    def forbid_database(*args, **kwargs):
        raise AssertionError("fetch must not open sqlite")

    with monkeypatch.context() as fetch_patch:
        fetch_patch.setattr(macro_indicators, "connect", forbid_database)
        macro_refresh_official.fetch_consumer_michigan(
            artifacts,
            http_client=michigan_http_client(httpx.Response(200, text=html)),
        )
    assert not db_path.exists()

    def forbid_network(*args, **kwargs):
        raise AssertionError("persistence must not fetch data")

    with monkeypatch.context() as persist_patch:
        persist_patch.setattr(HttpClient, "request", forbid_network)
        result = macro_refresh_official.persist_consumer_michigan(db_path, artifacts)

    assert result["status"] == "ok"
    con = consumer_sentiment.connect(db_path)
    try:
        for series_id, expected_values in [
            ("umcsi_aggregate", [60.0, 55.2, 51.0]),
            ("umcsi_current_conditions", [61.0, 54.8, 51.8]),
            ("umcsi_expectations", [59.0, 55.4, 50.6]),
        ]:
            points = macro_indicators.load_macro_indicator_points(con, series_id)
            assert [point["date"] for point in points] == [
                "2026-06-01", "2026-07-01", "2026-08-01"
            ]
            assert [point["value"] for point in points] == expected_values
            assert points[0]["source"].startswith("University of Michigan Table ")
            assert {point["source"] for point in points[1:]} == {
                "University of Michigan Surveys of Consumers front page"
            }
    finally:
        con.close()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(503), "failed to fetch michigan front page"),
        (httpx.Response(200, text="<html>unavailable</html>"), "missing the release h1"),
    ],
)
def test_michigan_fetch_does_not_publish_stale_tables_when_front_page_fails(
    monkeypatch, response, error
):
    artifacts = {}

    def forbid_database(*args, **kwargs):
        raise AssertionError("fetch must not open sqlite")

    monkeypatch.setattr(macro_indicators, "connect", forbid_database)
    with pytest.raises(ValueError, match=error):
        macro_refresh_official.fetch_consumer_michigan(
            artifacts, http_client=michigan_http_client(response)
        )

    assert artifacts == {}


def test_michigan_persist_rejects_missing_front_page_before_changing_database(tmp_path):
    db_path = tmp_path / "market.sqlite"

    with pytest.raises(ValueError, match="michigan front page artifact is missing"):
        macro_refresh_official.persist_consumer_michigan(
            db_path, {"consumer.michigan": dict(MICHIGAN_TABLES)}
        )

    assert not db_path.exists()


def test_building_permits_fetch_stages_bytes_without_opening_sqlite(tmp_path):
    artifacts = {}
    payload = b"census workbook bytes"

    result = macro_refresh_official.fetch_building_permits(
        artifacts,
        fetcher=lambda destination: payload,
        destination=tmp_path / "permits.xlsx",
    )

    assert result["artifact_key"] == "census.building_permits"
    assert artifacts["census.building_permits"] == payload


def test_fred_consumer_fetch_stages_each_series_under_one_artifact():
    artifacts = {}
    result = macro_refresh_official.fetch_consumer_fred(
        artifacts,
        fetcher=lambda series_id: f"csv:{series_id}".encode(),
    )

    assert result["artifact_key"] == "consumer.fred"
    assert set(artifacts["consumer.fred"]) == {
        "BOGZ1FL010000336Q",
        "TDSP",
        "PSAVERT",
        "HHMSDODNS",
    }


def test_fomc_document_fetch_stages_rows_without_database_connection():
    artifacts = {}
    event = {
        "event_id": "fomc_2026_07_28",
        "start_date": "2026-07-28",
        "end_date": "2026-07-29",
        "url": "https://example.test/calendar",
    }
    row = {
        "event_id": event["event_id"],
        "document_type": "statement",
        "url": "https://example.test/statement",
        "text": "Federal Reserve issues FOMC statement",
        "source_hash": "hash",
        "fetched_at": "2026-08-24T00:00:00Z",
    }

    result = macro_refresh_official.fetch_fomc_documents(
        artifacts,
        [event],
        "statement",
        fetcher=lambda current_event, document_type: row,
    )

    assert result["artifact_key"] == "fomc.documents.statement"
    assert artifacts["fomc.documents.statement"] == [row]


def test_fomc_preparation_does_not_open_sqlite(monkeypatch):
    monkeypatch.setattr(
        "app.db.us_rates_liquidity.connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preparation must not open sqlite")
        ),
    )

    prepared = macro_refresh_official.prepare_fomc_policy_tone(
        None,
        "event-id",
        object(),
        "extractor",
        "reviewer",
    )

    assert prepared["status"] == "failed"
    assert "document" in prepared["error"]


@pytest.mark.parametrize(
    ("batch_name", "prepare_name"),
    [
        ("prepare_fomc_policy_tone_batch", "_prepare_fomc_policy_tone"),
        ("prepare_fomc_minutes_structure_batch", "_prepare_fomc_minutes_structure"),
    ],
)
def test_fomc_batch_converts_one_event_exception_and_completes_the_batch(
    monkeypatch, batch_name, prepare_name
):
    async def prepare(_db_path, event_id, *_args):
        if event_id == "failed-event":
            raise ValueError("model unavailable")
        return {"status": "ok", "event_id": event_id, "row": {}}

    monkeypatch.setattr(macro_refresh_official, prepare_name, prepare)

    outcomes = asyncio.run(
        getattr(macro_refresh_official, batch_name)(
            "market.sqlite",
            ["failed-event", "success-event"],
            object(),
            "extractor",
            "reviewer",
        )
    )

    assert outcomes == [
        {
            "status": "failed",
            "event_id": "failed-event",
            "error": "model unavailable",
        },
        {"status": "ok", "event_id": "success-event", "row": {}},
    ]
