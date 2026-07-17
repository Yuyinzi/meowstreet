import pytest

from app.db import growth_cycle
from scripts import backfill_ism_industry_signal_coverage


def _seed_signals(con, report_id, report_month, groups, source_url, source_hash):
    for signal_type, direction, industries, evidence_text in groups:
        for rank, industry in enumerate(industries, start=1):
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
                    signal_type,
                    direction,
                    industry,
                    rank,
                    evidence_text,
                    source_url,
                    source_hash,
                ),
            )
    con.commit()


def test_backfill_complete_list_from_declared_count(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_signals(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            (
                "overall_growth",
                "growth",
                ["Printing & Related Support Activities", "Machinery"],
                (
                    "The two manufacturing industries reporting growth in June "
                    "are Printing & Related Support Activities and Machinery."
                ),
            ),
            (
                "new_orders",
                "growth",
                ["Primary Metals"],
                (
                    "Of the 18 manufacturing industries, one reported growth "
                    "in new orders: Primary Metals."
                ),
            ),
        ],
        "https://example.com/report.html",
        "abc123",
    )

    result = backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_06"
    )

    assert result["status"] == "ok"
    assert result["complete"] == 2

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )

    assert len(rows) == 2
    for row in rows:
        assert row["validation_status"] == "complete"


def test_backfill_partial_list_when_declared_count_mismatches(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_signals(
        con,
        "ism_manufacturing_2026_05",
        "2026-05-01",
        [
            (
                "overall_growth",
                "growth",
                ["Machinery"],
                (
                    "The 14 manufacturing industries reporting growth in May "
                    "are Machinery and others."
                ),
            ),
        ],
        "https://example.com/report.html",
        "def456",
    )

    result = backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_05"
    )

    assert result["status"] == "ok"
    assert result["complete"] == 0
    assert result["partial"] == 1

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_05"
    )

    assert len(rows) == 1
    assert rows[0]["validation_status"] == "partial"
    assert rows[0]["declared_count"] == 14
    assert rows[0]["extracted_count"] == 1


def test_backfill_partial_when_no_declared_count(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_signals(
        con,
        "ism_manufacturing_2026_04",
        "2026-04-01",
        [
            (
                "backlog",
                "higher",
                ["Machinery", "Primary Metals", "Chemical Products"],
                "Three industries reported higher backlogs in April.",
            ),
        ],
        "https://example.com/report.html",
        "ghi789",
    )

    result = backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_04"
    )

    assert result["partial"] == 1
    assert result["complete"] == 0

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_04"
    )
    assert rows[0]["validation_status"] == "partial"
    assert rows[0]["declared_count"] is None


def test_backfill_skips_report_with_no_signals(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")

    result = backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_06"
    )

    assert result["status"] == "no_signals"

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )
    assert rows == []


def test_backfill_is_idempotent(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_signals(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            (
                "overall_growth",
                "growth",
                ["Printing & Related Support Activities"],
                "The one manufacturing industry reporting growth is Printing.",
            ),
        ],
        "https://example.com/report.html",
        "abc123",
    )

    backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_06"
    )
    backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_06"
    )

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )
    assert len(rows) == 1
    assert rows[0]["validation_status"] == "complete"


def test_backfill_signals_without_declared_count_become_partial(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_signals(
        con,
        "ism_manufacturing_2026_03",
        "2026-03-01",
        [
            (
                "backlog",
                "lower",
                ["Machinery", "Primary Metals"],
                "Some industries reported lower backlogs in March.",
            ),
        ],
        "https://example.com/report.html",
        "jkl012",
    )

    result = backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_03"
    )

    assert result["partial"] == 1
    assert result["complete"] == 0


def test_backfill_multiple_directions_same_signal_type(tmp_path):
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    _seed_signals(
        con,
        "ism_manufacturing_2026_06",
        "2026-06-01",
        [
            (
                "new_orders",
                "growth",
                ["Machinery", "Primary Metals"],
                (
                    "Of the 18 manufacturing industries, two reported growth "
                    "in new orders: Machinery and Primary Metals."
                ),
            ),
            (
                "new_orders",
                "decrease",
                ["Chemical Products"],
                (
                    "Only one industry reported a decrease in new orders: "
                    "Chemical Products."
                ),
            ),
        ],
        "https://example.com/report.html",
        "abc123",
    )

    result = backfill_ism_industry_signal_coverage.backfill_single_report(
        con, "ism_manufacturing_2026_06"
    )

    assert result["complete"] == 2

    rows = growth_cycle.load_ism_report_industry_signal_coverage(
        con, "ism_manufacturing_2026_06"
    )
    assert len(rows) == 2
    for row in rows:
        assert row["validation_status"] == "complete"


def test_backfill_cli_no_signals_message(capsys, tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    growth_cycle.connect(db_path)

    import sys

    sys.argv = [
        "backfill_ism_industry_signal_coverage.py",
        f"--db-path={db_path}",
    ]
    backfill_ism_industry_signal_coverage.main()
    captured = capsys.readouterr()

    assert "no industry signal rows found" in captured.out
