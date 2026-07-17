from app.db import growth_cycle, us_rates_liquidity


def test_replace_ism_report_source_snapshot_saves_raw_html(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    saved = growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/jan-2026.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T00:00:00Z",
            "raw_html": "<html>report</html>",
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": "ism_manufacturing_2026_01",
            "report_month": "2026-01-01",
        },
    )

    row = growth_cycle.load_ism_report_source_snapshot(
        con,
        "https://example.com/jan-2026.html",
    )

    assert saved == {"source_snapshots": 1}
    assert row["report_id"] == "ism_manufacturing_2026_01"
    assert row["raw_html"] == "<html>report</html>"


def test_replace_ism_ai_section_extraction_saves_checkpoint(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    saved = growth_cycle.replace_ism_ai_section_extraction(
        con,
        {
            "report_id": "ism_manufacturing_2026_01",
            "source_url": "https://example.com/jan-2026.html",
            "report_month": "2026-01-01",
            "source_hash": "abc123",
            "section_name": "at_a_glance_rows",
            "status": "ok",
            "payload_json": {"at_a_glance_rows": []},
            "error": None,
            "attempt_count": 1,
            "model": "test-model",
            "prompt_version": "ism-rich-v1",
            "updated_at": "2026-07-15T00:00:00Z",
        },
    )

    rows = growth_cycle.load_ism_ai_section_extractions(
        con,
        "ism_manufacturing_2026_01",
        "https://example.com/jan-2026.html",
        "ism-rich-v1",
    )

    assert saved == {"ai_section_extractions": 1}
    assert rows[0]["section_name"] == "at_a_glance_rows"
    assert rows[0]["status"] == "ok"
    assert rows[0]["payload_json"] == {"at_a_glance_rows": []}


def test_replace_ism_ai_summary_run_saves_reviewable_summary(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    saved = growth_cycle.replace_ism_ai_summary_run(
        con,
        {
            "report_id": "ism_manufacturing_2026_01",
            "report_month": "2026-01-01",
            "source_hash": "abc123",
            "facts_hash": "facts456",
            "status": "ok",
            "quality_status": "accepted",
            "summary_text": "Manufacturing PMI improved.",
            "summary_json": {
                "summary_text": "Manufacturing PMI improved.",
                "summary_text_zh": "制造业PMI改善。",
            },
            "guidance": "",
            "error": None,
            "attempt_count": 1,
            "model": "test-model",
            "prompt_version": "ism-summary-from-validated-v1",
            "updated_at": "2026-07-15T00:00:00Z",
        },
    )

    row = growth_cycle.load_latest_ism_ai_summary_run(
        con,
        "ism_manufacturing_2026_01",
    )

    assert saved == {"ai_summary_runs": 1}
    assert row["quality_status"] == "accepted"
    assert row["summary_json"]["summary_text_zh"] == "制造业PMI改善。"


def test_fresh_db_with_m2_only_does_not_crash_on_growth_cycle_ism_reads(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "m2_money_stock",
            "title": "M2 Money Stock",
            "units": "billions",
            "source": "test",
        },
        [{"date": "2026-01-01", "value": 100.0, "source": "test"}],
    )
    con.close()

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    rows = us_rates_liquidity.load_macro_indicator_points(con, "m2_money_stock")
    assert len(rows) == 1
    at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
    assert at_a_glance == []
    rankings = growth_cycle.load_latest_ism_industry_rankings(con)
    assert rankings == []
    con.close()

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    rows = us_rates_liquidity.load_macro_indicator_points(con, "m2_money_stock")
    assert len(rows) == 1
    at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
    assert at_a_glance == []
    rankings = growth_cycle.load_latest_ism_industry_rankings(con)
    assert rankings == []
    con.close()


def test_replace_ism_report_industry_signal_coverage_saves_rows(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    saved = growth_cycle.replace_ism_report_industry_signal_coverage(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "list_present": True,
                "declared_count": 14,
                "extracted_count": 14,
                "validation_status": "complete",
                "evidence_text": "The 14 manufacturing industries reporting growth.",
            },
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "list_present": True,
                "declared_count": 11,
                "extracted_count": 11,
                "validation_status": "complete",
                "evidence_text": "The 11 industries reporting growth in new orders.",
            },
        ],
        "https://example.com/report.html",
        "abc123",
    )

    assert saved == {"industry_signal_coverage": 2}

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )

    assert len(rows) == 2
    assert rows[0]["signal_type"] == "new_orders"
    assert rows[0]["validation_status"] == "complete"
    assert rows[0]["list_present"] is True
    assert rows[1]["signal_type"] == "overall_growth"
    assert rows[1]["declared_count"] == 14


def test_load_ism_report_industry_signal_coverage_returns_empty_for_missing(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )

    assert rows == []


def test_replace_ism_report_industry_signal_coverage_replaces_existing(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    growth_cycle.replace_ism_report_industry_signal_coverage(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "list_present": True,
                "declared_count": 14,
                "extracted_count": 14,
                "validation_status": "complete",
                "evidence_text": "old evidence",
            },
        ],
        "https://example.com/report.html",
        "abc123",
    )

    growth_cycle.replace_ism_report_industry_signal_coverage(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "list_present": True,
                "declared_count": 15,
                "extracted_count": 15,
                "validation_status": "complete",
                "evidence_text": "updated evidence",
            },
        ],
        "https://example.com/report.html",
        "def456",
    )

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )

    assert len(rows) == 1
    assert rows[0]["declared_count"] == 15
    assert rows[0]["evidence_text"] == "updated evidence"


def test_ism_report_signal_coverage_is_isolated_by_report_id(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    growth_cycle.replace_ism_report_industry_signal_coverage(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "list_present": True,
                "declared_count": 14,
                "extracted_count": 14,
                "validation_status": "complete",
                "evidence_text": "The 14 industries reporting growth.",
            },
        ],
        "https://example.com/june.html",
        "abc123",
    )

    rows_a = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )
    rows_b = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_05"
    )

    assert len(rows_a) == 1
    assert len(rows_b) == 0


def test_load_ism_at_a_glance_rows_by_report_id(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    series_ids = [
        "ism_manufacturing_pmi",
        "ism_manufacturing_new_orders",
        "ism_manufacturing_production",
    ]
    rows = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": sid,
            "label": f"Label {sid}",
            "current_value": 50.0 + i,
            "previous_value": 49.0 + i,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
            "source_url": "https://example.com/report.html",
            "source_hash": "abc123",
        }
        for i, sid in enumerate(series_ids)
    ]

    growth_cycle.replace_ism_at_a_glance_rows(con, rows)

    result = growth_cycle.load_ism_at_a_glance_rows(con, "ism_manufacturing_2026_06")

    assert len(result) == 3
    assert result[0]["series_id"] == "ism_manufacturing_new_orders"


def test_load_ism_at_a_glance_rows_returns_empty_for_missing_report(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    result = growth_cycle.load_ism_at_a_glance_rows(con, "ism_manufacturing_2026_06")

    assert result == []


def test_replace_ism_ai_extraction_deletes_stale_coverage(tmp_path):
    from tests.test_ism_ai_extraction import valid_extraction

    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    payload = valid_extraction()

    growth_cycle.replace_ism_report_industry_signal_coverage(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "list_present": True,
                "declared_count": 14,
                "extracted_count": 14,
                "validation_status": "complete",
                "evidence_text": "stale evidence",
            },
        ],
        "https://example.com/stale.html",
        "stalehash",
    )

    saved = growth_cycle.replace_ism_ai_extraction(
        con,
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "source_url": "https://example.com/report.html",
            "source_hash": "abc123",
            "extractor": "llm",
            "model": "test",
            "prompt_version": "ism-rich-v1",
            "validation_status": "ok",
            "validation_error": None,
            "extraction_json": payload,
        },
    )

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )

    assert "old evidence" not in [r["evidence_text"] for r in rows]
    assert saved["ai_extractions"] == 1
    assert saved["industry_signal_coverage"] == 2
    coverage_by_key = {(r["signal_type"], r["direction"]): r for r in rows}
    assert ("overall_growth", "growth") in coverage_by_key
    assert ("new_orders", "growth") in coverage_by_key
