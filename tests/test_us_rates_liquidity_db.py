import pytest

from app.db import growth_cycle
from app.db import us_rates_liquidity


def series():
    return {
        "series_id": "treasury_10y",
        "title": "10-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 120,
        "units": "percent",
        "source_workbook": "Benchmark_Yields_US.xlsm",
        "source_sheet": "Data",
    }


def points():
    return [
        {
            "date": "2020-12-27",
            "value": 0.94,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        {
            "date": "2021-01-03",
            "value": 0.93,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
    ]


def test_replace_rate_series_points_loads_sorted_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)

    saved = us_rates_liquidity.replace_rate_series_points(con, series(), points())
    loaded_series = us_rates_liquidity.load_rate_series(con)
    loaded_points = us_rates_liquidity.load_rate_points(con, "treasury_10y")

    assert saved == {"series": 1, "points": 2}
    assert loaded_series[0]["series_id"] == "treasury_10y"
    assert loaded_series[0]["maturity_months"] == 120
    assert [row["date"] for row in loaded_points] == ["2020-12-27", "2021-01-03"]
    assert loaded_points[-1]["value"] == 0.93


def test_replace_rate_series_points_deletes_old_points(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    us_rates_liquidity.replace_rate_series_points(con, series(), points())

    saved = us_rates_liquidity.replace_rate_series_points(
        con,
        series(),
        [
            {
                "date": "2021-01-10",
                "value": 1.04,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            }
        ],
    )
    loaded_points = us_rates_liquidity.load_rate_points(con, "treasury_10y")

    assert saved == {"series": 1, "points": 1}
    assert loaded_points == [
        {
            "date": "2021-01-10",
            "value": 1.04,
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        }
    ]


def test_normalize_series_id_rejects_empty_id():
    try:
        us_rates_liquidity.normalize_series_id("")
    except ValueError as exc:
        assert str(exc) == "rate series id is required"
    else:
        raise AssertionError("expected ValueError")


def test_load_rate_points_for_series_returns_grouped_sorted_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    us_rates_liquidity.replace_rate_series_points(con, series(), points())
    us_rates_liquidity.replace_rate_series_points(
        con,
        {
            "series_id": "treasury_2y",
            "title": "2-Year Treasury",
            "instrument_type": "nominal_treasury",
            "maturity_months": 24,
            "units": "percent",
            "source_workbook": "Benchmark_Yields_US.xlsm",
            "source_sheet": "Data",
        },
        [
            {
                "date": "2020-12-27",
                "value": 0.13,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
            {
                "date": "2021-01-03",
                "value": 0.12,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
        ],
    )

    grouped = us_rates_liquidity.load_rate_points_for_series(
        con,
        ["treasury_10y", "treasury_2y"],
    )

    assert list(grouped) == ["treasury_10y", "treasury_2y"]
    assert grouped["treasury_10y"][-1]["value"] == 0.93
    assert grouped["treasury_2y"][-1]["value"] == 0.12


def test_merge_macro_indicator_points_preserves_existing_points(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    series = {
        "series_id": "bbb_corporate_yield",
        "title": "BBB Corporate Yield",
        "units": "percent",
        "source": "Corporate_Bond_Indices.xlsm",
    }
    workbook_points = [
        {"date": "2021-01-06", "value": 2.20, "source": "Corporate_Bond_Indices.xlsm"},
        {"date": "2021-01-07", "value": 2.16, "source": "Corporate_Bond_Indices.xlsm"},
    ]
    fred_points = [
        {"date": "2023-10-01", "value": 6.10, "source": "BAMLC0A4CBBBEY.csv"},
        {"date": "2023-10-02", "value": 6.08, "source": "BAMLC0A4CBBBEY.csv"},
    ]

    us_rates_liquidity.replace_macro_indicator_points(con, series, workbook_points)
    saved = us_rates_liquidity.merge_macro_indicator_points(
        con,
        {**series, "source": "P05 workbook + FRED"},
        fred_points,
    )
    loaded = us_rates_liquidity.load_macro_indicator_points(con, "bbb_corporate_yield")
    loaded_series = [
        row
        for row in us_rates_liquidity.load_macro_indicator_series(con)
        if row["series_id"] == "bbb_corporate_yield"
    ][0]

    assert saved == {"series": 1, "points": 2}
    assert [row["date"] for row in loaded] == [
        "2021-01-06",
        "2021-01-07",
        "2023-10-01",
        "2023-10-02",
    ]
    assert loaded[-1]["value"] == 6.08
    assert loaded_series["source"] == "P05 workbook + FRED"


def test_merge_macro_indicator_points_replaces_matching_dates(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    series = {
        "series_id": "ccc_corporate_yield",
        "title": "CCC Corporate Yield",
        "units": "percent",
        "source": "Corporate_Bond_Indices.xlsm",
    }
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        series,
        [{"date": "2023-10-02", "value": 12.00, "source": "old.csv"}],
    )

    saved = us_rates_liquidity.merge_macro_indicator_points(
        con,
        {**series, "source": "P05 workbook + FRED"},
        [{"date": "2023-10-02", "value": 11.75, "source": "BAMLH0A3HYCEY.csv"}],
    )
    loaded = us_rates_liquidity.load_macro_indicator_points(con, "ccc_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert loaded == [
        {"date": "2023-10-02", "value": 11.75, "source": "BAMLH0A3HYCEY.csv"}
    ]


def test_replace_credit_ai_interpretation_loads_latest_by_scope(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    row = {
        "scope": "us_credit_conditions",
        "as_of": "2026-07-06",
        "snapshot_hash": "abc123",
        "prompt_version": "credit-cat-v1",
        "model": "gpt-4.1-mini",
        "tone": "trader_cat",
        "status": "risk_rising",
        "text_en": "Risk is rising. The cat keeps one paw on the exit.",
        "text_zh": "信用风险上升。交易猫把一只爪子放在出口旁。",
        "metrics_json": '{"status":"risk_rising"}',
        "generated_at": "2026-07-08T10:30:00Z",
    }

    saved = us_rates_liquidity.replace_ai_interpretation(con, row)
    loaded = us_rates_liquidity.load_ai_interpretation(
        con,
        "us_credit_conditions",
        "abc123",
    )

    assert saved == {"interpretations": 1}
    assert loaded == row


def test_load_ai_interpretation_returns_none_for_missing_snapshot(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)

    loaded = us_rates_liquidity.load_ai_interpretation(
        con,
        "us_credit_conditions",
        "missing",
    )

    assert loaded is None


def test_replace_macro_events_and_load_by_type(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        saved = us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_06_16",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-06-16",
                    "end_date": "2026-06-17",
                    "display_month": "2026-06-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                }
            ],
        )

        rows = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
    finally:
        con.close()

    assert saved == {"events": 1}
    assert rows == [
        {
            "event_id": "fomc_2026_06_16",
            "event_type": "fomc_meeting",
            "start_date": "2026-06-16",
            "end_date": "2026-06-17",
            "display_month": "2026-06-01",
            "title": "FOMC Meeting",
            "source": "Federal Reserve",
            "policy_tone": "unknown",
            "has_sep": 0,
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        }
    ]


def test_load_next_macro_event_uses_start_date(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_06_16",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-06-16",
                    "end_date": "2026-06-17",
                    "display_month": "2026-06-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                },
                {
                    "event_id": "fomc_2026_07_28",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-07-28",
                    "end_date": "2026-07-29",
                    "display_month": "2026-07-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                },
            ],
        )

        row = us_rates_liquidity.load_next_macro_event(
            con,
            "fomc_meeting",
            "2026-07-09",
        )
    finally:
        con.close()

    assert row["event_id"] == "fomc_2026_07_28"


def test_replace_macro_event_document_and_load_by_event(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        saved = us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "document_type": "statement",
                "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
                "text": "Recent indicators suggest that economic activity has continued to expand.",
                "source_hash": "abc123",
                "fetched_at": "2026-07-30T00:00:00Z",
            },
        )
        rows = us_rates_liquidity.load_macro_event_documents(
            con,
            "fomc_2026_07_28",
        )
    finally:
        con.close()

    assert saved == {"documents": 1}
    assert rows == [
        {
            "event_id": "fomc_2026_07_28",
            "document_type": "statement",
            "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
            "text": "Recent indicators suggest that economic activity has continued to expand.",
            "source_hash": "abc123",
            "fetched_at": "2026-07-30T00:00:00Z",
        }
    ]


def test_replace_macro_event_document_upserts_by_event_and_type(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "document_type": "statement",
                "url": "https://example.test/old",
                "text": "old text",
                "source_hash": "oldhash",
                "fetched_at": "2026-07-28T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "document_type": "statement",
                "url": "https://example.test/new",
                "text": "new text",
                "source_hash": "newhash",
                "fetched_at": "2026-07-30T00:00:00Z",
            },
        )
        rows = us_rates_liquidity.load_macro_event_documents(
            con,
            "fomc_2026_07_28",
        )
    finally:
        con.close()

    assert len(rows) == 1
    assert rows[0]["text"] == "new text"
    assert rows[0]["source_hash"] == "newhash"


def test_load_macro_event_document_returns_none_when_missing(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        row = us_rates_liquidity.load_macro_event_document(
            con,
            "fomc_2026_07_28",
            "statement",
        )
    finally:
        con.close()

    assert row is None


def test_replace_macro_event_tone_extraction_loads_latest(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        saved = us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": "fomc_2026_06_16",
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "medium",
                "extraction_status": "approved",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": '[{"dimension":"inflation"}]',
                "comparison_json": '{"inflation":{"change":"more_hawkish"}}',
                "reviewer_feedback_json": "[]",
                "final_reviewer_feedback_json": '["approved"]',
                "reason": "Inflation language became firmer.",
                "generated_at": "2026-07-30T00:00:00Z",
            },
        )
        row = us_rates_liquidity.load_latest_macro_event_tone_extraction(
            con,
            "fomc_2026_07_28",
            "statement",
        )
    finally:
        con.close()

    assert saved == {"tone_extractions": 1}
    assert row["policy_action"] == "hold"
    assert row["guidance_bias"] == "neutral"
    assert row["language_tone"] == "hawkish"
    assert row["overall_bias"] == "mild_hawkish"
    assert row["statement_tone"] == "hawkish"
    assert row["marker_tone"] == "hawkish"
    assert row["tone_change"] == "more_hawkish"
    assert row["final_reviewer_feedback_json"] == '["approved"]'


def test_connect_migrates_macro_event_tone_final_feedback_column(tmp_path):
    db_path = tmp_path / "market.sqlite"
    con = us_rates_liquidity.connect(db_path)
    try:
        con.execute(
            "alter table macro_event_tone_extractions drop column final_reviewer_feedback_json"
        )
        con.commit()
    finally:
        con.close()

    con = us_rates_liquidity.connect(db_path)
    try:
        columns = [
            row["name"]
            for row in con.execute("pragma table_info(macro_event_tone_extractions)")
        ]
    finally:
        con.close()

    assert "final_reviewer_feedback_json" in columns


def test_connect_migrates_macro_event_tone_bias_columns(tmp_path):
    db_path = tmp_path / "market.sqlite"
    con = us_rates_liquidity.connect(db_path)
    try:
        for column_name in [
            "policy_action",
            "guidance_bias",
            "language_tone",
            "overall_bias",
        ]:
            con.execute(
                f"alter table macro_event_tone_extractions drop column {column_name}"
            )
        con.commit()
    finally:
        con.close()

    con = us_rates_liquidity.connect(db_path)
    try:
        columns = [
            row["name"]
            for row in con.execute("pragma table_info(macro_event_tone_extractions)")
        ]
    finally:
        con.close()

    assert "policy_action" in columns
    assert "guidance_bias" in columns
    assert "language_tone" in columns
    assert "overall_bias" in columns


def test_load_macro_events_with_latest_tone_merges_tone_fields(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_07_28",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-07-28",
                    "end_date": "2026-07-29",
                    "display_month": "2026-07-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "document_type": "statement",
                "url": "https://example.test/statement",
                "text": "Federal Reserve issues FOMC statement\nRecent indicators suggest economic activity expanded.",
                "source_hash": "abc123",
                "fetched_at": "2026-07-30T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": None,
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "high",
                "extraction_status": "approved",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": "[]",
                "comparison_json": "{}",
                "reviewer_feedback_json": "[]",
                "reason": "test",
                "generated_at": "2026-07-30T00:00:00Z",
            },
        )
        events = us_rates_liquidity.load_macro_events_with_latest_tone(
            con,
            "fomc_meeting",
        )
    finally:
        con.close()

    assert len(events) == 1
    assert events[0]["policy_action"] == "hold"
    assert events[0]["guidance_bias"] == "neutral"
    assert events[0]["language_tone"] == "hawkish"
    assert events[0]["overall_bias"] == "mild_hawkish"
    assert events[0]["statement_tone"] == "hawkish"
    assert events[0]["marker_tone"] == "hawkish"
    assert events[0]["tone_change"] == "more_hawkish"
    assert events[0]["tone_confidence"] == "high"
    assert events[0]["tone_reason"] == "test"


def test_load_macro_event_tone_extraction_finds_exact_hash(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": None,
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "high",
                "extraction_status": "approved",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": "[]",
                "comparison_json": "{}",
                "reviewer_feedback_json": "[]",
                "reason": "test",
                "generated_at": "2026-07-30T00:00:00Z",
            },
        )
        found = us_rates_liquidity.load_macro_event_tone_extraction(
            con,
            "fomc_2026_07_28",
            "statement",
            "abc123",
        )
        not_found = us_rates_liquidity.load_macro_event_tone_extraction(
            con,
            "fomc_2026_07_28",
            "statement",
            "nonexistent",
        )
    finally:
        con.close()

    assert found is not None
    assert found["statement_tone"] == "hawkish"
    assert not_found is None


def test_load_macro_events_with_latest_tone_ignores_stale_hash(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_07_28",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-07-28",
                    "end_date": "2026-07-29",
                    "display_month": "2026-07-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "document_type": "statement",
                "url": "https://example.test/statement",
                "text": "Old statement text",
                "source_hash": "abc123",
                "fetched_at": "2026-07-29T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": None,
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "high",
                "extraction_status": "approved",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": "[]",
                "comparison_json": "{}",
                "reviewer_feedback_json": "[]",
                "reason": "test",
                "generated_at": "2026-07-30T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_07_28",
                "document_type": "statement",
                "url": "https://example.test/statement",
                "text": "Cleaner statement text that re-fetched",
                "source_hash": "def456",
                "fetched_at": "2026-07-31T00:00:00Z",
            },
        )
        events = us_rates_liquidity.load_macro_events_with_latest_tone(
            con,
            "fomc_meeting",
        )
    finally:
        con.close()

    assert len(events) == 1
    assert "statement_tone" not in events[0]
    assert "marker_tone" not in events[0]
    assert "tone_change" not in events[0]


def test_load_macro_events_with_latest_tone_defaults_when_no_tone(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_07_28",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-07-28",
                    "end_date": "2026-07-29",
                    "display_month": "2026-07-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        events = us_rates_liquidity.load_macro_events_with_latest_tone(
            con,
            "fomc_meeting",
        )
    finally:
        con.close()

    assert len(events) == 1
    assert "statement_tone" not in events[0]
    assert "marker_tone" not in events[0]


def test_load_latest_approved_macro_event_tone_returns_latest_past_event(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_06_16",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-06-16",
                    "end_date": "2026-06-17",
                    "display_month": "2026-06-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
                {
                    "event_id": "fomc_2026_07_28",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-07-28",
                    "end_date": "2026-07-29",
                    "display_month": "2026-07-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        for event_id, source_hash in [
            ("fomc_2026_06_16", "abc123"),
            ("fomc_2026_07_28", "def456"),
        ]:
            us_rates_liquidity.replace_macro_event_document(
                con,
                {
                    "event_id": event_id,
                    "document_type": "statement",
                    "url": "https://example.test/statement",
                    "text": f"Statement for {event_id}",
                    "source_hash": source_hash,
                    "fetched_at": f"{event_id[:17]}T00:00:00Z",
                },
            )
            us_rates_liquidity.replace_macro_event_tone_extraction(
                con,
                {
                    "event_id": event_id,
                    "source_document_type": "statement",
                    "source_hash": source_hash,
                    "previous_event_id": None,
                    "policy_action": "hold",
                    "guidance_bias": "neutral",
                    "language_tone": "hawkish",
                    "overall_bias": "mild_hawkish",
                    "statement_tone": "hawkish",
                    "minutes_tone": "unknown",
                    "marker_tone": "hawkish",
                    "tone_score": 1,
                    "tone_change": "more_hawkish",
                    "confidence": "high",
                    "extraction_status": "approved",
                    "review_rounds": 1,
                    "extractor_model": "gpt-4.1-mini",
                    "reviewer_model": "gpt-4.1",
                    "facts_json": "[]",
                    "comparison_json": "{}",
                    "reviewer_feedback_json": "[]",
                    "reason": "test",
                    "generated_at": "2026-07-30T00:00:00Z",
                },
            )
        result = us_rates_liquidity.load_latest_approved_macro_event_tone(
            con,
            "fomc_meeting",
            "2026-07-30",
        )
    finally:
        con.close()

    assert result is not None
    assert result["event_id"] == "fomc_2026_07_28"
    assert result["marker_tone"] == "hawkish"


def test_load_latest_approved_macro_event_tone_ignores_future_events(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_09_15",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-09-15",
                    "end_date": "2026-09-16",
                    "display_month": "2026-09-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_09_15",
                "document_type": "statement",
                "url": "https://example.test/statement",
                "text": "Future statement",
                "source_hash": "abc123",
                "fetched_at": "2026-09-17T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_09_15",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": None,
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "high",
                "extraction_status": "approved",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": "[]",
                "comparison_json": "{}",
                "reviewer_feedback_json": "[]",
                "reason": "test",
                "generated_at": "2026-09-18T00:00:00Z",
            },
        )
        result = us_rates_liquidity.load_latest_approved_macro_event_tone(
            con,
            "fomc_meeting",
            "2026-07-30",
        )
    finally:
        con.close()

    assert result is None


def test_load_latest_approved_macro_event_tone_ignores_stale_hash(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_06_16",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-06-16",
                    "end_date": "2026-06-17",
                    "display_month": "2026-06-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_06_16",
                "document_type": "statement",
                "url": "https://example.test/statement",
                "text": "Current statement text",
                "source_hash": "def456",
                "fetched_at": "2026-06-18T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_06_16",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": None,
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "high",
                "extraction_status": "approved",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": "[]",
                "comparison_json": "{}",
                "reviewer_feedback_json": "[]",
                "reason": "test",
                "generated_at": "2026-06-19T00:00:00Z",
            },
        )
        result = us_rates_liquidity.load_latest_approved_macro_event_tone(
            con,
            "fomc_meeting",
            "2026-07-01",
        )
    finally:
        con.close()

    assert result is None


def test_load_latest_approved_macro_event_tone_ignores_unapproved(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [
                {
                    "event_id": "fomc_2026_06_16",
                    "event_type": "fomc_meeting",
                    "start_date": "2026-06-16",
                    "end_date": "2026-06-17",
                    "display_month": "2026-06-01",
                    "title": "FOMC Meeting",
                    "source": "Federal Reserve",
                    "policy_tone": "unknown",
                    "has_sep": 0,
                    "url": "https://example.test",
                },
            ],
        )
        us_rates_liquidity.replace_macro_event_document(
            con,
            {
                "event_id": "fomc_2026_06_16",
                "document_type": "statement",
                "url": "https://example.test/statement",
                "text": "Statement text",
                "source_hash": "abc123",
                "fetched_at": "2026-06-18T00:00:00Z",
            },
        )
        us_rates_liquidity.replace_macro_event_tone_extraction(
            con,
            {
                "event_id": "fomc_2026_06_16",
                "source_document_type": "statement",
                "source_hash": "abc123",
                "previous_event_id": None,
                "policy_action": "hold",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "hawkish",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "high",
                "extraction_status": "pending",
                "review_rounds": 1,
                "extractor_model": "gpt-4.1-mini",
                "reviewer_model": "gpt-4.1",
                "facts_json": "[]",
                "comparison_json": "{}",
                "reviewer_feedback_json": "[]",
                "reason": "test",
                "generated_at": "2026-06-19T00:00:00Z",
            },
        )
        result = us_rates_liquidity.load_latest_approved_macro_event_tone(
            con,
            "fomc_meeting",
            "2026-07-01",
        )
    finally:
        con.close()

    assert result is None


def test_load_latest_combined_fomc_policy_read_merges_statement_and_minutes(tmp_path):
    db_path = tmp_path / "macro.sqlite"
    con = us_rates_liquidity.connect(db_path)
    us_rates_liquidity.replace_macro_events(
        con,
        "fomc_meeting",
        [
            {
                "event_id": "fomc_2026_06_16",
                "event_type": "fomc_meeting",
                "start_date": "2026-06-16",
                "end_date": "2026-06-17",
                "display_month": "2026-06-01",
                "title": "FOMC Meeting",
                "source": "Federal Reserve",
                "policy_tone": "unknown",
                "has_sep": 0,
                "url": "https://example.test/statement",
            }
        ],
    )
    us_rates_liquidity.replace_macro_event_document(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "document_type": "statement",
            "url": "https://example.test/statement",
            "text": "statement",
            "source_hash": "statement_hash",
            "fetched_at": "2026-06-17T00:00:00Z",
        },
    )
    us_rates_liquidity.replace_macro_event_document(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "document_type": "minutes",
            "url": "https://example.test/minutes",
            "text": "minutes",
            "source_hash": "minutes_hash",
            "fetched_at": "2026-07-08T00:00:00Z",
        },
    )
    us_rates_liquidity.replace_macro_event_tone_extraction(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "source_document_type": "statement",
            "source_hash": "statement_hash",
            "previous_event_id": None,
            "policy_action": "hold",
            "guidance_bias": "neutral",
            "language_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "statement_tone": "hawkish",
            "minutes_tone": "unknown",
            "marker_tone": "hawkish",
            "tone_score": 1,
            "tone_change": "more_hawkish",
            "confidence": "medium",
            "extraction_status": "approved",
            "review_rounds": 1,
            "extractor_model": "extractor",
            "reviewer_model": "reviewer",
            "facts_json": "[]",
            "comparison_json": "{}",
            "reviewer_feedback_json": "[]",
            "final_reviewer_feedback_json": "[]",
            "reason": "statement reason",
            "generated_at": "2026-06-17T00:00:00Z",
        },
    )
    us_rates_liquidity.replace_macro_event_tone_extraction(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "source_document_type": "minutes",
            "source_hash": "minutes_hash",
            "previous_event_id": None,
            "policy_action": "hold",
            "guidance_bias": "neutral",
            "language_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "statement_tone": "hawkish",
            "minutes_tone": "hawkish",
            "marker_tone": "hawkish",
            "tone_score": 1,
            "tone_change": "more_hawkish",
            "confidence": "medium",
            "extraction_status": "approved",
            "review_rounds": 1,
            "extractor_model": "extractor",
            "reviewer_model": "reviewer",
            "facts_json": '{"risk_focus":"inflation","risk_bias":"hawkish","divergence_level":"medium","uncertainty_level":"medium","policy_conviction":"moderate","minutes_confirmation":"confirmed_but_divided","participant_distribution":[],"facts":[]}',
            "comparison_json": "{}",
            "reviewer_feedback_json": "[]",
            "final_reviewer_feedback_json": "[]",
            "reason": "minutes reason",
            "generated_at": "2026-07-08T00:00:00Z",
        },
    )

    row = us_rates_liquidity.load_latest_combined_fomc_policy_read(
        con,
        "2026-07-11",
    )

    assert row["event_id"] == "fomc_2026_06_16"
    assert row["statement_marker_tone"] == "hawkish"
    assert row["minutes_confirmation"] == "confirmed_but_divided"
    assert row["risk_focus"] == "inflation"
    assert row["policy_conviction"] == "moderate"


def test_load_latest_approved_macro_event_tone_returns_none_when_no_tone(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        result = us_rates_liquidity.load_latest_approved_macro_event_tone(
            con,
            "fomc_meeting",
            "2026-07-01",
        )
    finally:
        con.close()

    assert result is None


def test_load_macro_events_with_latest_tone_merges_minutes_structure_fields(tmp_path):
    db_path = tmp_path / "macro.sqlite"
    con = us_rates_liquidity.connect(db_path)
    us_rates_liquidity.replace_macro_events(
        con,
        "fomc_meeting",
        [
            {
                "event_id": "fomc_2026_06_16",
                "event_type": "fomc_meeting",
                "start_date": "2026-06-16",
                "end_date": "2026-06-17",
                "display_month": "2026-06-01",
                "title": "FOMC Meeting",
                "source": "Federal Reserve",
                "policy_tone": "unknown",
                "has_sep": 0,
                "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            }
        ],
    )
    us_rates_liquidity.replace_macro_event_document(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "document_type": "statement",
            "url": "https://example.test/statement",
            "text": "statement",
            "source_hash": "statement_hash",
            "fetched_at": "2026-06-17T00:00:00Z",
        },
    )
    us_rates_liquidity.replace_macro_event_document(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "document_type": "minutes",
            "url": "https://example.test/minutes",
            "text": "minutes",
            "source_hash": "minutes_hash",
            "fetched_at": "2026-07-08T00:00:00Z",
        },
    )
    us_rates_liquidity.replace_macro_event_tone_extraction(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "source_document_type": "statement",
            "source_hash": "statement_hash",
            "previous_event_id": None,
            "policy_action": "hold",
            "guidance_bias": "neutral",
            "language_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "statement_tone": "hawkish",
            "minutes_tone": "unknown",
            "marker_tone": "hawkish",
            "tone_score": 1,
            "tone_change": "more_hawkish",
            "confidence": "medium",
            "extraction_status": "approved",
            "review_rounds": 1,
            "extractor_model": "extractor",
            "reviewer_model": "reviewer",
            "facts_json": "[]",
            "comparison_json": "{}",
            "reviewer_feedback_json": "[]",
            "final_reviewer_feedback_json": "[]",
            "reason": "statement reason",
            "generated_at": "2026-06-17T00:00:00Z",
        },
    )
    us_rates_liquidity.replace_macro_event_tone_extraction(
        con,
        {
            "event_id": "fomc_2026_06_16",
            "source_document_type": "minutes",
            "source_hash": "minutes_hash",
            "previous_event_id": None,
            "policy_action": "hold",
            "guidance_bias": "neutral",
            "language_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "statement_tone": "hawkish",
            "minutes_tone": "hawkish",
            "marker_tone": "hawkish",
            "tone_score": 1,
            "tone_change": "more_hawkish",
            "confidence": "high",
            "extraction_status": "approved",
            "review_rounds": 1,
            "extractor_model": "extractor",
            "reviewer_model": "reviewer",
            "facts_json": '{"risk_focus":"inflation","risk_bias":"hawkish","divergence_level":"high","uncertainty_level":"high","policy_conviction":"divided","minutes_confirmation":"confirmed_but_divided","participant_distribution":[],"facts":[]}',
            "comparison_json": "{}",
            "reviewer_feedback_json": "[]",
            "final_reviewer_feedback_json": "[]",
            "reason": "minutes reason",
            "generated_at": "2026-07-13T04:31:29Z",
        },
    )

    events = us_rates_liquidity.load_macro_events_with_latest_tone(
        con,
        "fomc_meeting",
    )

    assert events[0]["marker_tone"] == "hawkish"
    assert events[0]["minutes_status"] == "available"
    assert events[0]["minutes_tone"] == "hawkish"
    assert events[0]["minutes_confirmation"] == "confirmed_but_divided"
    assert events[0]["risk_focus"] == "inflation"
    assert events[0]["policy_conviction"] == "divided"
    assert events[0]["minutes_generated_at"] == "2026-07-13T04:31:29Z"


def test_replace_ism_industry_rankings_saves_and_loads_latest_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    rankings = [
        {
            "date": "2026-05-01",
            "industry": "Machinery",
            "direction": "growth",
            "rank": 8,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
        {
            "date": "2026-06-01",
            "industry": "Computer & Electronic Products",
            "direction": "growth",
            "rank": 16,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
        {
            "date": "2026-06-01",
            "industry": "Furniture & Related Products",
            "direction": "contraction",
            "rank": -1,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
    ]

    saved = growth_cycle.replace_ism_industry_rankings(con, rankings)

    assert saved == 3
    assert growth_cycle.load_latest_ism_industry_rankings(con) == [
        {
            "date": "2026-06-01",
            "industry": "Computer & Electronic Products",
            "direction": "growth",
            "rank": 16,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
        {
            "date": "2026-06-01",
            "industry": "Furniture & Related Products",
            "direction": "contraction",
            "rank": -1,
            "source": "ISM_Manufacturing_Index.xlsx",
        },
    ]


def test_load_latest_ism_industry_rankings_returns_empty_without_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)

    assert growth_cycle.load_latest_ism_industry_rankings(con) == []


def test_replace_ism_report_snapshot_saves_metadata_and_comments(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    report = {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/report/june/",
        "source_hash": "abc123",
        "fetched_at": "2026-07-14T10:00:00Z",
        "parse_status": "ok",
        "next_report_period": "2026-07-01",
        "next_release_at": "2026-08-03T10:00:00-04:00",
        "next_release_label": "Monday, August 3, 2026 at 10:00 a.m. ET",
    }
    comments = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "industry": "Chemical Products",
            "comment_index": 1,
            "comment_text": "Input costs remain elevated.",
            "source_url": "https://www.ismworld.org/report/june/",
            "source_hash": "abc123",
        },
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "industry": "Machinery",
            "comment_index": 2,
            "comment_text": "Conditions are optimistic.",
            "source_url": "https://www.ismworld.org/report/june/",
            "source_hash": "abc123",
        },
    ]

    saved = growth_cycle.replace_ism_report_snapshot(con, report, comments)

    assert saved == {"reports": 1, "comments": 2}
    assert growth_cycle.load_latest_ism_report_snapshot(con) == report
    assert (
        growth_cycle.load_ism_report_comments(con, "ism_manufacturing_2026_06")
        == comments
    )


def test_replace_ism_report_snapshot_replaces_comments_for_same_report(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    report = {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/report/june/",
        "source_hash": "abc123",
        "fetched_at": "2026-07-14T10:00:00Z",
        "parse_status": "ok",
        "next_report_period": None,
        "next_release_at": None,
        "next_release_label": "",
    }

    growth_cycle.replace_ism_report_snapshot(
        con,
        report,
        [
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "industry": "Chemical Products",
                "comment_index": 1,
                "comment_text": "Old comment.",
                "source_url": "https://www.ismworld.org/report/june/",
                "source_hash": "abc123",
            }
        ],
    )
    saved = growth_cycle.replace_ism_report_snapshot(
        con,
        report,
        [
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "industry": "Machinery",
                "comment_index": 1,
                "comment_text": "New comment.",
                "source_url": "https://www.ismworld.org/report/june/",
                "source_hash": "abc123",
            }
        ],
    )

    assert saved == {"reports": 1, "comments": 1}
    assert (
        growth_cycle.load_ism_report_comments(con, "ism_manufacturing_2026_06")[0][
            "comment_text"
        ]
        == "New comment."
    )


def test_replace_ism_at_a_glance_rows_saves_and_loads_latest(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    rows = [
        {
            "report_id": "ism_manufacturing_2026_05",
            "report_month": "2026-05-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 54.0,
            "previous_value": 53.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 5,
            "source_url": "https://www.ismworld.org/report/may/",
            "source_hash": "mayhash",
        },
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 53.3,
            "previous_value": 54.0,
            "point_change": -0.7,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 6,
            "source_url": "https://www.ismworld.org/report/june/",
            "source_hash": "junehash",
        },
    ]

    saved = growth_cycle.replace_ism_at_a_glance_rows(con, rows)

    assert saved == {"at_a_glance_rows": 2}
    assert growth_cycle.load_latest_ism_at_a_glance_rows(con) == [rows[1]]


def test_replace_ism_ai_extraction_saves_payload_and_signals(tmp_path):
    from tests.test_ism_ai_extraction import valid_extraction

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    payload = valid_extraction()

    saved = growth_cycle.replace_ism_ai_extraction(
        con,
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "source_url": "https://example.com/report.html",
            "source_hash": "abc123",
            "extractor": "llm",
            "model": "gpt-5-mini",
            "prompt_version": "ism-rich-v1",
            "validation_status": "ok",
            "validation_error": None,
            "extraction_json": payload,
        },
    )

    assert saved == {"ai_extractions": 1, "industry_signals": 2}
    assert (
        len(
            growth_cycle.load_ism_report_industry_signals(
                con,
                "ism_manufacturing_2026_06",
            )
        )
        == 2
    )


def test_replace_ism_ai_extraction_rejects_malformed_payload(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)

    with pytest.raises(ValueError, match="Field required"):
        growth_cycle.replace_ism_ai_extraction(
            con,
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/report.html",
                "source_hash": "abc123",
                "extractor": "llm",
                "model": "gpt-5-mini",
                "prompt_version": "ism-rich-v1",
                "validation_status": "ok",
                "validation_error": None,
                "extraction_json": {
                    "report": {
                        "report_id": "ism_manufacturing_2026_06",
                        "report_month": "2026-06-01",
                        "title": "June 2026 ISM Manufacturing PMI Report",
                        "source_name": "prnewswire",
                        "source_url": "https://example.com/report.html",
                    },
                },
            },
        )


def test_replace_ism_ai_extraction_rejects_malformed_failed_payload(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)

    with pytest.raises(ValueError, match="Field required"):
        growth_cycle.replace_ism_ai_extraction(
            con,
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/report.html",
                "source_hash": "abc123",
                "extractor": "llm",
                "model": "gpt-5-mini",
                "prompt_version": "ism-rich-v1",
                "validation_status": "failed",
                "validation_error": "llm returned incomplete json",
                "extraction_json": {
                    "report": {
                        "report_id": "ism_manufacturing_2026_06",
                        "report_month": "2026-06-01",
                        "title": "June 2026 ISM Manufacturing PMI Report",
                        "source_name": "prnewswire",
                        "source_url": "https://example.com/report.html",
                    },
                },
            },
        )


def test_replace_ism_report_source_snapshot_saves_raw_html(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    snapshot = {
        "source_url": "https://www.prnewswire.com/news-releases/example.html",
        "source_name": "prnewswire",
        "source_hash": "abc123",
        "fetched_at": "2026-07-15T10:00:00Z",
        "raw_html": "<html><body>release</body></html>",
        "parse_status": "failed",
        "parse_error": "ism report overall industry rankings are missing",
        "report_id": None,
        "report_month": None,
    }

    saved = growth_cycle.replace_ism_report_source_snapshot(con, snapshot)

    assert saved == {"source_snapshots": 1}
    assert (
        growth_cycle.load_ism_report_source_snapshot(
            con,
            "https://www.prnewswire.com/news-releases/example.html",
        )
        == snapshot
    )


def test_load_existing_ism_report_months(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_snapshot(
        con,
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "title": "June report",
            "source_url": "https://example.com/june.html",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T00:00:00Z",
            "next_release_at": None,
        },
        [],
    )

    assert growth_cycle.load_existing_ism_report_months(con) == {"2026-06-01"}


def test_replace_ism_ai_report_outputs_saves_summary_and_commodities(tmp_path):
    from tests.test_ism_ai_extraction import valid_extraction

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    payload = valid_extraction()
    saved = growth_cycle.replace_ism_ai_report_outputs(
        con,
        payload,
        {
            "source_url": "https://example.com/report.html",
            "source_hash": "abc123",
            "model": "gpt-5-mini",
            "prompt_version": "ism-rich-v1",
        },
    )

    assert saved["ai_summary"] == 1
    assert saved["commodities"] == 1
    summary = growth_cycle.load_ism_report_ai_summary(
        con,
        "ism_manufacturing_2026_06",
    )
    assert "Headline PMI rose" in summary["summary_text"]
