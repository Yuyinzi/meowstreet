"""Tests for the canonical ISM report ingestion CLI."""

import argparse
from unittest.mock import patch

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


class FakeAiClient:
    def __init__(self):
        self.model = "test-model"

    def complete_json(self, prompt, schema=None):
        raise ValueError("FakeAiClient cannot make real API calls")

    async def request_structured_output(self, prompt):
        raise ValueError("FakeAiClient cannot make real API calls")


def _fake_client_factory(config):
    return FakeAiClient()


def _mock_import(monkeypatch, func, result=([], 0)):
    def fake(**kwargs):
        return result

    monkeypatch.setattr(func, "__call__", lambda *a, **kw: result)


def test_latest_only_manufacturing(tmp_path, monkeypatch, capsys):
    from scripts import fetch_ism_official_reports as mfg

    db_path = tmp_path / "market_data.sqlite"
    monkeypatch.setattr(
        mfg,
        "import_targets",
        lambda *a, **kw: (
            [
                {
                    "report_id": "ism_manufacturing_2026_06",
                    "source_name": "ismworld",
                    "metrics": 11,
                    "at_a_glance_rows": 11,
                    "comments": 1,
                    "rankings": 2,
                    "survey_type": "manufacturing",
                }
            ],
            0,
        ),
    )

    exit_code = fetch_ism_reports.main(
        ["--survey", "manufacturing", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: MANUFACTURING_HTML,
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_manufacturing" in out


def test_latest_only_services(tmp_path, monkeypatch, capsys):
    from app.services import ism_services_ai_ingestion as svc

    db_path = tmp_path / "market_data.sqlite"
    monkeypatch.setattr(
        svc,
        "import_targets",
        lambda *a, **kw: (
            [
                {
                    "report_id": "ism_services_2026_06",
                    "source_name": "ismworld",
                    "metrics": 4,
                    "at_a_glance_rows": 11,
                    "comments": 1,
                    "industry_signals": 1,
                }
            ],
            0,
        ),
    )

    exit_code = fetch_ism_reports.main(
        ["--survey", "services", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: SERVICES_HTML,
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_services" in out


def test_survey_all_runs_both_surveys(tmp_path, monkeypatch, capsys):
    from scripts import fetch_ism_official_reports as mfg
    from app.services import ism_services_ai_ingestion as svc

    db_path = tmp_path / "market_data.sqlite"
    monkeypatch.setattr(
        mfg,
        "import_targets",
        lambda *a, **kw: (
            [
                {
                    "report_id": "ism_manufacturing_2026_06",
                    "source_name": "ismworld",
                    "metrics": 11,
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(
        svc,
        "import_targets",
        lambda *a, **kw: (
            [
                {
                    "report_id": "ism_services_2026_06",
                    "source_name": "ismworld",
                    "metrics": 4,
                }
            ],
            0,
        ),
    )

    exit_code = fetch_ism_reports.main(
        ["--survey", "all", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: SERVICES_HTML,
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_manufacturing_2026_06" in out
    assert "ism_services_2026_06" in out


def test_report_month_generates_target(tmp_path, monkeypatch, capsys):
    from scripts import fetch_ism_official_reports as mfg

    db_path = tmp_path / "market_data.sqlite"

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )
    monkeypatch.setattr(
        mfg,
        "import_targets",
        lambda *a, **kw: (
            [
                {
                    "report_id": "ism_manufacturing_2026_06",
                    "source_name": "ismworld",
                    "metrics": 11,
                }
            ],
            0,
        ),
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
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_manufacturing_2026_06" in out


def test_report_concurrency_passed_through(tmp_path, monkeypatch):
    from scripts import fetch_ism_official_reports as mfg

    db_path = tmp_path / "market_data.sqlite"
    seen = {}

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )

    def fake_mfg_import(db_path, targets, fetch, ai_client, model, report_concurrency):
        seen["concurrency"] = report_concurrency
        return [], 0

    monkeypatch.setattr(mfg, "import_targets", fake_mfg_import)

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
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    assert seen["concurrency"] == 2


def test_survey_all_failure_does_not_hide_other(tmp_path, monkeypatch, capsys):
    from scripts import fetch_ism_official_reports as mfg
    from app.services import ism_services_ai_ingestion as svc

    db_path = tmp_path / "market_data.sqlite"
    call_count = [0]

    def failing_mfg(db_path, targets, fetch, ai_client, model, report_concurrency):
        call_count[0] += 1
        raise ValueError("manufacturing failed")

    def ok_svc(db_path, targets, ai_client, model, **kw):
        return [
            {
                "report_id": "ism_services_2026_06",
                "source_name": "ismworld",
                "metrics": 4,
            }
        ], 0

    monkeypatch.setattr(mfg, "import_targets", failing_mfg)
    monkeypatch.setattr(svc, "import_targets", ok_svc)

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )

    exit_code = fetch_ism_reports.main(
        ["--survey", "all", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: SERVICES_HTML,
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "failed" in stderr


def test_services_report_month_via_ismworld(tmp_path, monkeypatch, capsys):
    from app.services import ism_services_ai_ingestion as svc

    db_path = tmp_path / "market_data.sqlite"

    monkeypatch.setattr(
        ingestion,
        "latest_released_report_month",
        lambda: "2026-06-01",
    )
    monkeypatch.setattr(
        svc,
        "import_targets",
        lambda *a, **kw: (
            [
                {
                    "report_id": "ism_services_2026_06",
                    "source_name": "ismworld",
                    "metrics": 4,
                }
            ],
            0,
        ),
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
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_services_2026_06" in out


def test_manufacturing_dispatches_to_existing_rich_importer(monkeypatch, tmp_path):
    from scripts import fetch_ism_official_reports

    db_path = tmp_path / "macro.db"
    captured = {}

    def fake_import(db_path_arg, targets, fetch, ai_client, model, report_concurrency):
        captured["db_path"] = db_path_arg
        captured["targets"] = targets
        captured["fetch"] = fetch
        captured["ai_client"] = ai_client
        captured["model"] = model
        captured["report_concurrency"] = report_concurrency
        return [], 0

    monkeypatch.setattr(fetch_ism_official_reports, "import_targets", fake_import)

    exit_code = fetch_ism_reports.main(
        ["--survey", "manufacturing", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: MANUFACTURING_HTML,
        ai_client_factory=lambda config: "fake_ai_client",
    )

    assert exit_code == 0
    assert captured["db_path"] == str(db_path)
    assert captured["ai_client"] == "fake_ai_client"
    assert captured["model"] == "test-model"
    assert captured["report_concurrency"] == 1
    assert len(captured["targets"]) > 0


def test_client_construction_failure_returns_nonzero(tmp_path):
    db_path = tmp_path / "macro.db"

    def failing_factory(config):
        raise ValueError("no api key")

    exit_code = fetch_ism_reports.main(
        ["--survey", "manufacturing", "--latest-only", "--db-path", str(db_path)],
        fetch=lambda url: "",
        ai_client_factory=failing_factory,
    )

    assert exit_code != 0


def test_survey_all_constructs_one_client_invokes_both(monkeypatch, tmp_path):
    from scripts import fetch_ism_official_reports

    db_path = tmp_path / "macro.db"
    factory_calls = []
    importers_called = []

    def mfg_import(db_path_arg, targets, fetch, ai_client, model, report_concurrency):
        importers_called.append("manufacturing")
        return [], 0

    def svc_import(db_path_arg, targets, ai_client, model, **kwargs):
        importers_called.append("services")
        return [], 0

    monkeypatch.setattr(fetch_ism_official_reports, "import_targets", mfg_import)

    def tracking_fetch(url):
        if "pmi/" in url:
            return MANUFACTURING_HTML
        return SERVICES_HTML

    with patch("app.services.ism_services_ai_ingestion.import_targets", svc_import):
        exit_code = fetch_ism_reports.main(
            ["--survey", "all", "--latest-only", "--db-path", str(db_path)],
            fetch=tracking_fetch,
            ai_client_factory=lambda config: (
                factory_calls.append(config) or "shared_client"
            ),
        )

    assert exit_code == 0
    assert importers_called == ["manufacturing", "services"]
    assert len(factory_calls) == 1
