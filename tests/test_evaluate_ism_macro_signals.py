import sys

import pytest

from app.db import growth_cycle
from scripts import evaluate_ism_macro_signals


_SERIES_IDS = {
    "pmi": "ism_manufacturing_pmi",
    "new_orders": "ism_manufacturing_new_orders",
    "production": "ism_manufacturing_production",
    "inventories": "ism_manufacturing_inventories",
    "prices": "ism_manufacturing_prices",
    "supplier_deliveries": "ism_manufacturing_supplier_deliveries",
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
    for series_id, label in [
        (_SERIES_IDS["pmi"], "PMI"),
        (_SERIES_IDS["new_orders"], "New Orders"),
        (_SERIES_IDS["production"], "Production"),
        (_SERIES_IDS["inventories"], "Inventories"),
        (_SERIES_IDS["prices"], "Prices"),
        (_SERIES_IDS["supplier_deliveries"], "Supplier Deliveries"),
    ]:
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
                month,
                series_id,
                label,
                53.0,
                52.0,
                1.0,
                "rising",
                "moderate",
                2,
                f"https://example.com/ism/{month}.html",
                f"hash_{month}",
            ),
        )
    return report_id


def test_evaluate_prints_distributions(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    for m in ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]:
        _seed_month(con, m)
    con.commit()
    con.close()

    evaluate_ism_macro_signals.evaluate(str(db_path))
    captured = capsys.readouterr()

    assert "ISM Macro Signal Evaluation" in captured.out
    assert "Version: ism_macro_signal_v1" in captured.out
    assert "eligible months" in captured.out
    assert "Signal Availability:" in captured.out
    assert "Cycle State Distribution:" in captured.out
    assert "Growth Impulse Distribution:" in captured.out
    assert "Month-to-Month Transitions" in captured.out
    assert "Missing required metrics:" in captured.out


def test_evaluate_insufficient_history_three_report_minimum(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    _seed_month(con, "2026-01-01")
    _seed_month(con, "2026-02-01")
    con.commit()
    con.close()

    evaluate_ism_macro_signals.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Insufficient history" in captured.out


def test_evaluate_empty_db(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    con.commit()
    con.close()

    evaluate_ism_macro_signals.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Insufficient history" in captured.out


def test_evaluate_insufficient_usable_signals(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    for m in ["2026-01-01", "2026-02-01", "2026-03-01"]:
        _seed_month(con, m)
    con.commit()
    con.close()

    evaluate_ism_macro_signals.evaluate(str(db_path))
    captured = capsys.readouterr()
    assert "Insufficient history" in captured.out


def test_evaluate_does_not_mutate_db(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    for m in ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]:
        _seed_month(con, m)
    con.commit()

    snapshots_before = con.execute(
        "select count(*) from ism_report_snapshots"
    ).fetchone()[0]
    rows_before = con.execute("select count(*) from ism_at_a_glance_rows").fetchone()[0]
    con.close()

    evaluate_ism_macro_signals.evaluate(str(db_path))

    con2 = growth_cycle.connect(db_path)
    snapshots_after = con2.execute(
        "select count(*) from ism_report_snapshots"
    ).fetchone()[0]
    rows_after = con2.execute("select count(*) from ism_at_a_glance_rows").fetchone()[0]
    con2.close()

    assert snapshots_before == snapshots_after
    assert rows_before == rows_after


def test_evaluate_with_since_filter(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    for m in [
        "2024-06-01",
        "2025-01-01",
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
    ]:
        _seed_month(con, m)
    con.commit()
    con.close()

    evaluate_ism_macro_signals.evaluate(str(db_path), since="2026-01")
    captured = capsys.readouterr()
    assert "eligible months" in captured.out


def test_evaluate_cli_accepts_db_path(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    for m in ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]:
        _seed_month(con, m)
    con.commit()
    con.close()

    sys.argv = [
        "evaluate_ism_macro_signals.py",
        f"--db-path={db_path}",
    ]
    evaluate_ism_macro_signals.main()
    captured = capsys.readouterr()
    assert "eligible months" in captured.out


def test_evaluate_cli_accepts_since_filter(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = growth_cycle.connect(db_path)
    for m in ["2024-06-01", "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]:
        _seed_month(con, m)
    con.commit()
    con.close()

    sys.argv = [
        "evaluate_ism_macro_signals.py",
        f"--db-path={db_path}",
        "--since=2026-01",
    ]
    evaluate_ism_macro_signals.main()
    captured = capsys.readouterr()
    assert "eligible months" in captured.out
