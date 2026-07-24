from app.db import growth_cycle, macro_indicators, us_rates_liquidity


def test_replace_ism_report_source_snapshot_saves_raw_html(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    saved = growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/jan-2026.html",
            "source_name": "prnewswire",
            "survey_type": "manufacturing",
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
    assert row["survey_type"] == "manufacturing"


def test_replace_ism_report_source_snapshot_survey_type_defaults_to_manufacturing(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    saved = growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/legacy.html",
            "source_name": "ismworld",
            "source_hash": "def456",
            "fetched_at": "2026-07-15T00:00:00Z",
            "raw_html": "<html>legacy</html>",
            "parse_status": "ok",
            "parse_error": None,
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
        },
    )
    row = growth_cycle.load_ism_report_source_snapshot(con, "https://example.com/legacy.html")
    assert row["survey_type"] == "manufacturing"


def test_replace_ism_report_source_snapshot_services_survey_type(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    saved = growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/services-june.html",
            "source_name": "ismworld",
            "survey_type": "services",
            "source_hash": "ghi789",
            "fetched_at": "2026-07-15T00:00:00Z",
            "raw_html": "<html>services report</html>",
            "parse_status": "ok",
            "parse_error": None,
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
        },
    )
    row = growth_cycle.load_ism_report_source_snapshot(
        con, "https://example.com/services-june.html"
    )
    assert row["survey_type"] == "services"
    assert row["report_id"] == "ism_services_2026_06"


def test_ism_report_source_snapshot_migration_adds_survey_type(tmp_path):
    """Verify init_db() migration adds survey_type to legacy table."""
    import sqlite3

    db_path = tmp_path / "migrate.sqlite"
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.executescript(
        """
        create table if not exists ism_report_source_snapshots (
            source_url text primary key,
            source_name text not null,
            source_hash text not null,
            fetched_at text not null,
            raw_html text not null,
            parse_status text not null,
            parse_error text,
            report_id text,
            report_month text
        );
        """
    )
    con.execute(
        "insert into ism_report_source_snapshots values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "https://example.com/old-manu.html",
            "prnewswire",
            "old",
            "2026-01-01",
            "<html>manu</html>",
            "ok",
            None,
            "ism_manufacturing_2026_01",
            "2026-01-01",
        ),
    )
    con.execute(
        "insert into ism_report_source_snapshots values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "https://example.com/old-svcs.html",
            "prnewswire",
            "old2",
            "2026-06-01",
            "<html>svcs</html>",
            "ok",
            None,
            "ism_services_2026_06",
            "2026-06-01",
        ),
    )
    con.commit()

    growth_cycle.init_db(con)

    rows = {
        row["source_url"]: dict(row)
        for row in con.execute(
            "select * from ism_report_source_snapshots"
        ).fetchall()
    }
    assert rows["https://example.com/old-manu.html"]["survey_type"] == "manufacturing"
    assert rows["https://example.com/old-svcs.html"]["survey_type"] == "services"


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
    macro_indicators.replace_macro_indicator_points(
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
    rows = macro_indicators.load_macro_indicator_points(con, "m2_money_stock")
    assert len(rows) == 1
    at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
    assert at_a_glance == []
    rankings = growth_cycle.load_latest_ism_industry_rankings(con)
    assert rankings == []
    con.close()

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    rows = macro_indicators.load_macro_indicator_points(con, "m2_money_stock")
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


# ── Step 7.4: batched historical loaders ─────────────────────────────────────


def _seed_report_with_signals(con, report_id, report_month, month_num):
    growth_count = 3 + (month_num % 3)
    for rank in range(1, growth_count + 1):
        con.execute(
            """
            insert into ism_report_industry_signals(
                report_id, report_month, signal_type, direction, industry,
                rank, evidence_text, source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                report_month,
                "overall_growth",
                "growth",
                f"Industry {rank}",
                rank,
                f"{growth_count} industries reporting growth.",
                "https://example.com",
                "hash",
            ),
        )


def _seed_report_with_coverage(con, report_id, report_month):
    con.execute(
        """
        insert into ism_report_industry_signal_coverage(
            report_id, report_month, signal_type, direction, list_present,
            declared_count, extracted_count, validation_status, evidence_text,
            source_url, source_hash
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            report_month,
            "overall_growth",
            "growth",
            1,
            14,
            14,
            "complete",
            "14 industries reporting growth.",
            "https://example.com",
            "hash",
        ),
    )


def _seed_report_with_at_a_glance(con, report_id, report_month):
    con.execute(
        """
        insert into ism_at_a_glance_rows(
            report_id, report_month, series_id, label, current_value,
            previous_value, point_change, direction, rate_of_change,
            trend_months, source_url, source_hash
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            report_month,
            "ism_manufacturing_new_orders",
            "New Orders",
            50.0,
            49.0,
            1.0,
            "Growing",
            "Faster",
            1,
            "https://example.com",
            "hash",
        ),
    )


def _seed_report_snapshot(con, report_id, report_month):
    con.execute(
        """
        insert into ism_report_snapshots(
            report_id, report_month, title, source_url, source_hash, fetched_at,
            parse_status, next_report_period, next_release_at, next_release_label
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            report_month,
            f"ISM Report {report_month}",
            "https://example.com",
            "hash",
            "2026-07-15T00:00:00Z",
            "ok",
            None,
            None,
            "",
        ),
    )


def test_load_recent_ism_report_snapshots_returns_ascending_order(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    for i, month in enumerate(["2026-01-01", "2026-02-01", "2026-03-01"]):
        _seed_report_snapshot(
            con, f"ism_manufacturing_{month.replace('-', '_')}", month
        )

    result = growth_cycle.load_recent_ism_report_snapshots(con, limit=12)

    assert len(result) == 3
    assert result[0]["report_month"] == "2026-01-01"
    assert result[-1]["report_month"] == "2026-03-01"


def test_load_recent_ism_report_snapshots_respects_limit(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    for i in range(5):
        month = f"2026-{i + 1:02d}-01"
        _seed_report_snapshot(
            con, f"ism_manufacturing_{month.replace('-', '_')}", month
        )

    result = growth_cycle.load_recent_ism_report_snapshots(con, limit=3)

    assert len(result) == 3
    assert result[0]["report_month"] == "2026-03-01"  # most recent 3, ascending
    assert result[-1]["report_month"] == "2026-05-01"


def test_load_recent_ism_report_snapshots_defaults_to_six(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    for i in range(8):
        month = f"2025-{i + 1:02d}-01"
        _seed_report_snapshot(
            con, f"ism_manufacturing_{month.replace('-', '_')}", month
        )

    result = growth_cycle.load_recent_ism_report_snapshots(con)

    assert len(result) == 6
    assert result[0]["report_month"] == "2025-03-01"
    assert result[-1]["report_month"] == "2025-08-01"


def test_load_recent_ism_report_snapshots_empty_db(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    result = growth_cycle.load_recent_ism_report_snapshots(con, limit=12)

    assert result == []


def test_load_ism_report_industry_signals_for_reports_returns_all(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_report_with_signals(con, "rid_01", "2026-01-01", 1)
    _seed_report_with_signals(con, "rid_02", "2026-02-01", 2)

    result = growth_cycle.load_ism_report_industry_signals_for_reports(
        con, ["rid_01", "rid_02"]
    )

    assert len(result) >= 2
    report_ids = {r["report_id"] for r in result}
    assert report_ids == {"rid_01", "rid_02"}


def test_load_ism_report_industry_signals_for_reports_empty_input(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    result = growth_cycle.load_ism_report_industry_signals_for_reports(con, [])

    assert result == []


def test_load_ism_report_industry_signal_coverage_for_reports_returns_all(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_report_with_coverage(con, "rid_01", "2026-01-01")
    _seed_report_with_coverage(con, "rid_02", "2026-02-01")

    result = growth_cycle.load_ism_report_industry_signal_coverage_for_reports(
        con, ["rid_01", "rid_02"]
    )

    assert len(result) == 2
    report_ids = {r["report_id"] for r in result}
    assert report_ids == {"rid_01", "rid_02"}
    assert result[0]["list_present"] is True


def test_load_ism_report_industry_signal_coverage_for_reports_empty_input(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    result = growth_cycle.load_ism_report_industry_signal_coverage_for_reports(con, [])

    assert result == []


def test_load_ism_at_a_glance_rows_for_reports_returns_all(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_report_with_at_a_glance(con, "rid_01", "2026-01-01")
    _seed_report_with_at_a_glance(con, "rid_02", "2026-02-01")

    result = growth_cycle.load_ism_at_a_glance_rows_for_reports(
        con, ["rid_01", "rid_02"]
    )

    assert len(result) == 2
    report_ids = {r["report_id"] for r in result}
    assert report_ids == {"rid_01", "rid_02"}


def test_load_ism_at_a_glance_rows_for_reports_empty_input(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    result = growth_cycle.load_ism_at_a_glance_rows_for_reports(con, [])

    assert result == []


def test_batched_loaders_respect_report_isolation(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_report_with_signals(con, "rid_01", "2026-01-01", 1)

    signals = growth_cycle.load_ism_report_industry_signals_for_reports(con, ["rid_02"])
    coverage = growth_cycle.load_ism_report_industry_signal_coverage_for_reports(
        con, ["rid_02"]
    )
    at_a_glance = growth_cycle.load_ism_at_a_glance_rows_for_reports(con, ["rid_02"])

    assert signals == []
    assert coverage == []
    assert at_a_glance == []
