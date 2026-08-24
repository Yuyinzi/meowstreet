from pathlib import Path

from app.services import macro_refresh_official


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
