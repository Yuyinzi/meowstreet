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
<h1>Manufacturing PMI® at 53.3%</h1>
<h1>June 2026 ISM® Manufacturing PMI® Report</h1>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<ul><li>"Input costs remain elevated." [Chemical Products]</li></ul>
<h3>MANUFACTURING AT A GLANCE</h3>
<p>Manufacturing PMI® 53.3 54.0 -0.7 Growing Slower 6</p>
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


def test_core_only_never_constructs_ai_client(tmp_path):
    db_path = tmp_path / "market.sqlite"
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "manufacturing",
            "--url",
            "https://www.prnewswire.com/test-manufacturing.html",
            "--db-path",
            str(db_path),
            "--core-only",
        ],
        fetch=lambda url: MANUFACTURING_HTML,
        ai_client_factory=lambda config: (_ for _ in ()).throw(
            AssertionError("AI client must not be constructed")
        ),
    )
    assert exit_code == 0


def test_core_only_services_persists_four_metrics(tmp_path):
    db_path = tmp_path / "market.sqlite"
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "services",
            "--url",
            "https://www.prnewswire.com/test-services.html",
            "--db-path",
            str(db_path),
            "--core-only",
        ],
        fetch=lambda url: SERVICES_HTML,
        ai_client_factory=lambda config: (_ for _ in ()).throw(
            AssertionError("AI client must not be constructed")
        ),
    )
    con = us_rates_liquidity.connect(db_path)
    count = con.execute(
        "select count(*) as count from macro_indicator_points where date = '2026-06-01'"
    ).fetchone()["count"]
    con.close()
    assert exit_code == 0
    assert count == 4


def test_default_without_key_imports_core_and_skips_enrichment(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(fetch_ism_reports.llm, "load_env", lambda root: None)
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "manufacturing",
            "--url",
            "https://www.prnewswire.com/test-manufacturing.html",
            "--db-path",
            str(tmp_path / "market.sqlite"),
        ],
        fetch=lambda url: MANUFACTURING_HTML,
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ism_manufacturing_2026_06" in captured.out
    assert "ai_enrichment: skipped - OPENAI_API_KEY is not configured" in captured.out


def test_core_and_enrichment_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        fetch_ism_reports.main(
            ["--survey", "services", "--core-only", "--enrichment-only"]
        )


def test_later_key_runs_enrichment_from_saved_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "market.sqlite"
    fetch_ism_reports.main(
        [
            "--survey",
            "services",
            "--url",
            "https://www.prnewswire.com/test-services.html",
            "--db-path",
            str(db_path),
            "--core-only",
        ],
        fetch=lambda url: SERVICES_HTML,
    )
    calls = []
    monkeypatch.setattr(
        fetch_ism_reports,
        "_enrich_services_snapshot",
        lambda db_path, snapshot, client, model: calls.append(snapshot["source_url"])
        or {"report_id": snapshot["report_id"]},
    )
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "services",
            "--url",
            "https://www.prnewswire.com/test-services.html",
            "--db-path",
            str(db_path),
            "--enrichment-only",
        ],
        fetch=lambda url: (_ for _ in ()).throw(AssertionError("must not fetch")),
        ai_client_factory=lambda config: "client",
    )
    assert exit_code == 0
    assert calls == ["https://www.prnewswire.com/test-services.html"]


def test_enrichment_only_exact_month_does_not_use_stale_snapshot(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "market.sqlite"
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/old.html",
            "source_name": "prnewswire",
            "survey_type": "services",
            "source_hash": "abc",
            "fetched_at": "2026-06-15T00:00:00Z",
            "raw_html": SERVICES_HTML,
            "parse_status": "ok",
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
        },
    )
    con.close()
    factory_calls = []
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "services",
            "--report-month",
            "2026-07",
            "--db-path",
            str(db_path),
            "--enrichment-only",
        ],
        ai_client_factory=lambda config: factory_calls.append(config) or "client",
    )
    assert exit_code == 0
    assert factory_calls == []
    assert "services ai_enrichment: skipped - no eligible core snapshot" in capsys.readouterr().out


def test_enrichment_only_without_snapshot_does_not_construct_client(tmp_path):
    factory_calls = []
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "manufacturing",
            "--url",
            "https://example.com/missing.html",
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--enrichment-only",
        ],
        fetch=lambda url: (_ for _ in ()).throw(AssertionError("must not fetch")),
        ai_client_factory=lambda config: factory_calls.append(config) or "client",
    )
    assert exit_code == 0
    assert factory_calls == []


def test_configured_enrichment_failure_returns_nonzero_after_core_commit(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "market.sqlite"
    monkeypatch.setattr(
        fetch_ism_reports,
        "_enrich_manufacturing_snapshot",
        lambda *args: (_ for _ in ()).throw(ValueError("provider unavailable")),
    )
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "manufacturing",
            "--url",
            "https://www.prnewswire.com/test-manufacturing.html",
            "--db-path",
            str(db_path),
        ],
        fetch=lambda url: MANUFACTURING_HTML,
        ai_client_factory=lambda config: "client",
    )
    con = us_rates_liquidity.connect(db_path)
    rows = con.execute(
        "select count(*) as count from macro_indicator_points where date = '2026-06-01'"
    ).fetchone()["count"]
    con.close()
    assert exit_code == 1
    assert rows == 11


def test_core_dispatch_uses_shared_deterministic_importer(tmp_path, monkeypatch):
    seen = {}

    def fake_import(db_path, survey_type, targets, fetch=None, report_concurrency=1):
        seen.update(
            db_path=db_path,
            survey_type=survey_type,
            targets=targets,
            fetch=fetch,
            report_concurrency=report_concurrency,
        )
        return ([{"report_id": "ism_services_2026_06", "metrics": 4}], 0)

    monkeypatch.setattr(ingestion, "import_targets", fake_import)
    exit_code = fetch_ism_reports.main(
        [
            "--survey",
            "services",
            "--url",
            "https://www.prnewswire.com/test-services.html",
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--core-only",
            "--report-concurrency",
            "2",
        ],
        fetch=lambda url: SERVICES_HTML,
    )
    assert exit_code == 0
    assert seen["survey_type"] == "services"
    assert seen["report_concurrency"] == 2
    assert seen["fetch"] is not None
