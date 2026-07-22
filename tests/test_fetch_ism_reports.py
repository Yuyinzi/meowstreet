"""Tests for the canonical ISM report ingestion CLI."""

import argparse

import pytest

from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.services import ism_report_ingestion as ingestion
from scripts import fetch_ism_reports

SERVICES_HTML = """
<article>
<h1>June 2026 ISM Services PMI Report</h1>
<p>Services PMI registered 54 percent.</p>
<p>Business Activity Index at 55.4 percent.</p>
<p>New Orders Index registered 55.1 percent.</p>
<p>Backlog of Orders Index registered 54.9 percent.</p>
<p>The 2 services industries reporting growth in June are: Construction; and Retail Trade.</p>
<p>The one industry reporting contraction in June is: Educational Services.</p>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<p>"Pipeline remains healthy." [Construction]</p>
</article>
"""

MANUFACTURING_HTML = """
<html>
<body>
<h1>Manufacturing PMI\u00ae at 53.3%</h1>
<h1>June 2026 ISM\u00ae Manufacturing PMI\u00ae Report</h1>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<ul><li>"Input costs remain elevated." [Chemical Products]</li></ul>
<h3>MANUFACTURING AT A GLANCE</h3>
<p>Manufacturing PMI\u00ae 53.3 54.0 -0.7 Growing Slower 6</p>
<p>New Orders 56.0 56.8 -0.8 Growing Slower 6</p>
<p>Production 52.2 54.3 -2.1 Growing Slower 8</p>
<p>Employment 49.7 48.6 +1.1 Contracting Slower 33</p>
<p>Supplier Deliveries 57.4 60.6 -3.2 Slowing Slower 7</p>
<p>Inventories 51.4 49.9 +1.5 Growing From Contracting 1</p>
<p>Customers' Inventories 42.3 42.7 -0.4 Too Low Faster 21</p>
<p>Prices 73.0 82.1 -9.1 Increasing Slower 21</p>
<p>Backlog of Orders 45.2 48.0 -2.8 Contracting Faster 8</p>
<p>New Export Orders 48.1 51.2 -3.1 Contracting From Growing 1</p>
<p>Imports 49.8 51.0 -1.2 Contracting From Growing 1</p>
<p>The 4 manufacturing industries reporting growth in June are: Chemical Products; Food & Beverage; Machinery; and Primary Metals.</p>
<p>The 5 manufacturing industries reporting contraction in June are: Textile Mills; Apparel; Wood Products; Paper; and Plastics & Rubber Products.</p>
<p>The next ISM Manufacturing PMI Report featuring July 2026 data will be released at 10:00 a.m. ET on Wednesday, July 1, 2026.</p>
</body>
</html>
"""


def test_positive_int_rejects_zero():
    with pytest.raises(argparse.ArgumentTypeError, match="concurrency"):
        fetch_ism_reports.positive_int("0")


def test_positive_int_rejects_negative():
    with pytest.raises(argparse.ArgumentTypeError, match="concurrency"):
        fetch_ism_reports.positive_int("-1")


def test_positive_int_accepts_one():
    assert fetch_ism_reports.positive_int("1") == 1


def test_positive_int_accepts_ten():
    assert fetch_ism_reports.positive_int("10") == 10


def test_latest_only_manufacturing(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"

    exit_code = fetch_ism_reports.main(
        ["--survey", "manufacturing", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: MANUFACTURING_HTML,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_manufacturing" in out
    assert "metrics=" in out


def test_latest_only_services(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"

    exit_code = fetch_ism_reports.main(
        ["--survey", "services", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: SERVICES_HTML,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_services" in out
    assert "metrics=" in out


def test_survey_all_runs_both_surveys(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"
    calls = []

    def tracking_fetch(url):
        calls.append(url)
        if "pmi/" in url:
            return MANUFACTURING_HTML
        return SERVICES_HTML

    exit_code = fetch_ism_reports.main(
        ["--survey", "all", "--latest-only", "--db-path", str(db_path)],
        fetch=tracking_fetch,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "survey_type=manufacturing" in out
    assert "survey_type=services" in out


def test_report_month_generates_target(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )

    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "manufacturing",
            "--report-month",
            "2026-06",
            "--db-path",
            str(db_path),
        ],
        fetch=lambda url: MANUFACTURING_HTML,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_manufacturing_2026_06" in out


def test_report_concurrency_passed_through(tmp_path, monkeypatch):
    db_path = tmp_path / "market_data.sqlite"
    seen = {}

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )

    def fake_import(
        db_path_arg, survey_type, targets, fetch=None, report_concurrency=1
    ):
        seen["concurrency"] = report_concurrency
        return [], 0

    monkeypatch.setattr(ingestion, "import_targets", fake_import)

    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "manufacturing",
            "--latest-only",
            "--db-path",
            str(db_path),
            "--report-concurrency",
            "2",
        ],
        fetch=lambda url: MANUFACTURING_HTML,
    )

    assert exit_code == 0
    assert seen["concurrency"] == 2


def test_survey_all_failure_does_not_hide_other(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"
    call_count = [0]

    def failing_manufacturing(url):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("manufacturing fetch failed")
        return SERVICES_HTML

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )

    exit_code = fetch_ism_reports.main(
        ["--survey", "all", "--latest-only", "--db-path", str(db_path)],
        fetch=failing_manufacturing,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "failed" in stderr


def test_services_report_month_via_ismworld(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )

    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "services",
            "--report-month",
            "2026-06",
            "--db-path",
            str(db_path),
        ],
        fetch=lambda url: SERVICES_HTML,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_services_2026_06" in out
