import pytest

from app.db import growth_cycle
from scripts import evaluate_ism_industry_signal_scores


_EVIDENCE = {
    ("overall_growth", "growth", 2): "The 2 manufacturing industries reporting growth.",
    ("overall_contraction", "contraction", 1): "The 1 industry reporting contraction.",
    ("new_orders", "growth", 1): "The 1 industry reporting growth in new orders.",
    ("new_orders", "decrease", 1): "The 1 industry reporting a decrease in new orders.",
    ("production", "growth", 2): "The 2 industries reporting production growth.",
    ("production", "decrease", 1): "The 1 industry reporting a decrease in production.",
    ("backlog", "higher", 1): "The 1 industry reporting higher backlogs.",
    ("backlog", "lower", 1): "The 1 industry reporting lower backlogs.",
}


def _seed_month(con, month):
    report_id = f"ism_manufacturing_{month.replace('-', '_')}"
    con.execute(
        """
        insert into ism_report_snapshots(
            report_id, report_month, title, source_url, source_hash, fetched_at,
            parse_status, next_release_label
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            month,
            f"ISM Manufacturing Report {month}",
            f"https://example.com/ism/{month}.html",
            f"hash_{month}",
            f"{month[:4]}-{month[5:7]}-15",
            "parsed",
            "Next release TBD",
        ),
    )

    source_url = f"https://example.com/ism/{month}.html"
    source_hash = f"hash_{month}"

    _seed_signals_for_month(con, report_id, month, source_url, source_hash)
    _seed_coverage_for_month(con, report_id, month, source_url, source_hash)

    return report_id


def _seed_signals_for_month(con, report_id, month, source_url, source_hash):
    groups = [
        ("overall_growth", "growth", ["Machinery", "Primary Metals"], 2),
        ("overall_contraction", "contraction", ["Chemical Products"], 1),
        ("new_orders", "growth", ["Machinery"], 1),
        ("new_orders", "decrease", ["Chemical Products"], 1),
        ("production", "growth", ["Machinery", "Primary Metals"], 2),
        ("production", "decrease", ["Chemical Products"], 1),
        ("backlog", "higher", ["Machinery"], 1),
        ("backlog", "lower", ["Chemical Products"], 1),
    ]

    for signal_type, direction, industries, declared_count in groups:
        evidence = _EVIDENCE[(signal_type, direction, len(industries))]
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
                    month,
                    signal_type,
                    direction,
                    industry,
                    rank,
                    evidence,
                    source_url,
                    source_hash,
                ),
            )


def _seed_coverage_for_month(con, report_id, month, source_url, source_hash):
    coverages = [
        (
            "overall_growth",
            "growth",
            2,
            2,
            "complete",
            "The 2 manufacturing industries reporting growth.",
        ),
        (
            "overall_contraction",
            "contraction",
            1,
            1,
            "complete",
            "The 1 industry reporting contraction.",
        ),
        (
            "new_orders",
            "growth",
            1,
            1,
            "complete",
            "The 1 industry reporting growth in new orders.",
        ),
        (
            "new_orders",
            "decrease",
            1,
            1,
            "complete",
            "The 1 industry reporting a decrease in new orders.",
        ),
        (
            "production",
            "growth",
            2,
            2,
            "complete",
            "The 2 industries reporting production growth.",
        ),
        (
            "production",
            "decrease",
            1,
            1,
            "complete",
            "The 1 industry reporting a decrease in production.",
        ),
        (
            "backlog",
            "higher",
            1,
            1,
            "complete",
            "The 1 industry reporting higher backlogs.",
        ),
        (
            "backlog",
            "lower",
            1,
            1,
            "complete",
            "The 1 industry reporting lower backlogs.",
        ),
    ]

    for (
        signal_type,
        direction,
        declared_count,
        extracted_count,
        validation_status,
        evidence_text,
    ) in coverages:
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
                month,
                signal_type,
                direction,
                1 if extracted_count > 0 else 0,
                declared_count,
                extracted_count,
                validation_status,
                evidence_text,
                source_url,
                source_hash,
            ),
        )


def test_evaluate_reports_stats(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))


def test_evaluate_insufficient_history_exits_early(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Insufficient history" in captured.out


def test_evaluate_with_since_filter(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2025-01-01")
    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path), since="2026-01-01")
    captured = capsys.readouterr()
    assert "Eligible months: 3" in captured.out


def test_evaluate_reports_score_distribution(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Score distribution" in captured.out
    assert "strong" in captured.out or "improving" in captured.out


def test_evaluate_reports_month_to_month_persistence(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Month-to-month label persistence" in captured.out


def test_evaluate_no_eligible_reports_no_signals(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    con.execute(
        """
        insert into ism_report_snapshots(
            report_id, report_month, title, source_url, source_hash, fetched_at,
            parse_status, next_release_label
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ism_manufacturing_2026_06",
            "2026-06-01",
            "June 2026 ISM Report",
            "https://example.com/june.html",
            "abc123",
            "2026-06-15",
            "parsed",
            "Next release TBD",
        ),
    )
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Insufficient history" in captured.out


def test_evaluate_skips_reports_without_coverage(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")

    con.execute("delete from ism_report_industry_signal_coverage")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Insufficient history" in captured.out


def test_evaluate_includes_avg_coverage(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Average score coverage" in captured.out


def test_evaluate_skips_non_adjacent_persistence(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-03-01")
    _seed_month(con, "2026-04-01")
    con.commit()
    con.close()

    evaluate_ism_industry_signal_scores.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Eligible months: 3" in captured.out
    for line in captured.out.splitlines():
        if "Month-to-month label persistence" in line:
            parts = line.split()
            count, total = parts[3].split("/")
            total = int(total.split(")")[0])
            assert total == 3, (
                f"expected exactly 3 comparisons from the single Mar→Apr "
                f"adjacent transition, got {total}"
            )


def test_evaluate_cli_accepts_db_path(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    import sys

    sys.argv = [
        "evaluate_ism_industry_signal_scores.py",
        f"--db-path={db_path}",
    ]
    evaluate_ism_industry_signal_scores.main()
    captured = capsys.readouterr()
    assert "Eligible months: 3" in captured.out


def test_evaluate_cli_accepts_since_filter(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)

    _seed_month(con, "2024-06-01")
    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    _seed_month(con, "2026-03-01")
    con.commit()
    con.close()

    import sys

    sys.argv = [
        "evaluate_ism_industry_signal_scores.py",
        f"--db-path={db_path}",
        "--since=2026-01-01",
    ]
    evaluate_ism_industry_signal_scores.main()
    captured = capsys.readouterr()
    assert "Eligible months: 3" in captured.out
