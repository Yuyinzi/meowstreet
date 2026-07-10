from pathlib import Path

from app.db import us_rates_liquidity
from scripts import import_fomc_calendar


def test_parse_calendar_csv_builds_month_bucketed_events(tmp_path):
    csv_path = tmp_path / "fomc_calendar.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2026-06-16,2026-06-17,FOMC Meeting,1,https://example.test/fomc\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )

    events = import_fomc_calendar.parse_calendar_csv(csv_path)

    assert events[0] == {
        "event_id": "fomc_2026_06_16",
        "event_type": "fomc_meeting",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "display_month": "2026-06-01",
        "title": "FOMC Meeting",
        "source": "Federal Reserve",
        "policy_tone": "unknown",
        "has_sep": 1,
        "url": "https://example.test/fomc",
    }
    assert events[1]["display_month"] == "2026-07-01"
    assert events[1]["has_sep"] == 0


def test_parse_calendar_csv_preserves_historical_and_future_meetings(tmp_path):
    csv_path = tmp_path / "fomc_calendar.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2024-12-17,2024-12-18,FOMC Meeting,1,https://example.test/fomc\n"
        "2025-01-28,2025-01-29,FOMC Meeting,0,https://example.test/fomc\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )

    events = import_fomc_calendar.parse_calendar_csv(csv_path)

    assert [event["event_id"] for event in events] == [
        "fomc_2024_12_17",
        "fomc_2025_01_28",
        "fomc_2026_07_28",
    ]
    assert [event["display_month"] for event in events] == [
        "2024-12-01",
        "2025-01-01",
        "2026-07-01",
    ]


def test_import_calendar_replaces_fomc_events(tmp_path):
    csv_path = tmp_path / "fomc_calendar.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        saved = import_fomc_calendar.import_calendar(con, csv_path)
        rows = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
    finally:
        con.close()

    assert saved == {"fomc_meeting": 1}
    assert rows[0]["event_id"] == "fomc_2026_07_28"
