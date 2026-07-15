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
