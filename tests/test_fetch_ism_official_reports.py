import pytest

from app.db import us_rates_liquidity
from scripts import fetch_ism_official_reports


SSO_HTML = """<html><head><title>Object moved</title></head><body>
<h2>Object moved to <a href="https://ecommerce.ismworld.org/SSO/Login.aspx">here</a>.</h2>
</body></html>"""

HTML = """
<html>
<body>
<h1>Manufacturing PMI® at 53.3%</h1>
<h1>June 2026 ISM® Manufacturing PMI® Report</h1>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<ul><li>“Input costs remain elevated.” [Chemical Products]</li></ul>
<h3>MANUFACTURING AT A GLANCE</h3>
<p>Manufacturing PMI® 53.3 54.0 -0.7 Growing Slower 6</p>
<p>New Orders 56.0 56.8 -0.8 Growing Slower 6</p>
<p>Production 52.2 54.3 -2.1 Growing Slower 8</p>
<p>Employment 49.7 48.6 +1.1 Contracting Slower 33</p>
<p>Supplier Deliveries 57.4 60.6 -3.2 Slowing Slower 7</p>
<p>Inventories 51.4 49.9 +1.5 Growing From Contracting 1</p>
<p>Customers' Inventories 42.3 42.7 -0.4 Too Low Faster 21</p>
<p>Prices 73.0 82.1 -9.1 Increasing Slower 21</p>
<p>Backlog of Orders 50.5 52.2 -1.7 Growing Slower 6</p>
<p>New Export Orders 48.5 50.6 -2.1 Contracting From Growing 1</p>
<p>Imports 52.9 53.0 -0.1 Growing Slower 5</p>
<p>The 14 manufacturing industries reporting growth in June — listed in order — are: Printing & Related Support Activities; Electrical Equipment, Appliances & Components.</p>
<p>The three industries in contraction are: Paper Products; Furniture & Related Products.</p>
<p>The next ISM® Manufacturing PMI® Report featuring July 2026 data will be released at 10:00 a.m. ET on Monday, August 3, 2026.</p>
</body>
</html>
"""


def test_main_handles_sso_error_gracefully(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"

    def failing_fetch(url):
        raise ValueError("ism official report requires ISM membership login")

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", failing_fetch)

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--month", "june"]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ism_official_report/june: failed" in err
    assert "ISM membership login" in err


def test_import_report_fetches_and_stores_official_ism_data(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    result = fetch_ism_official_reports.import_report(
        con,
        "june",
        fetch=lambda url: HTML,
        now=lambda: "2026-07-14T10:00:00Z",
    )

    assert result == {
        "report_id": "ism_manufacturing_2026_06",
        "metrics": 11,
        "rankings": 4,
        "comments": 1,
    }
    assert us_rates_liquidity.load_macro_indicator_points(con, "ism_manufacturing_pmi")[
        -1
    ] == {
        "date": "2026-06-01",
        "value": 53.3,
        "source": "ISM official report",
    }
    assert us_rates_liquidity.load_latest_ism_report_snapshot(con)["report_id"] == (
        "ism_manufacturing_2026_06"
    )
    assert (
        us_rates_liquidity.load_ism_report_comments(con, "ism_manufacturing_2026_06")[
            0
        ]["industry"]
        == "Chemical Products"
    )


def test_requested_months_defaults_to_previous_month(monkeypatch):
    import datetime as dt_module

    fake_july = dt_module.datetime(2026, 7, 14, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

        @classmethod
        def strftime(cls, fmt):
            return fake_july.strftime(fmt)

    monkeypatch.setattr(fetch_ism_official_reports, "datetime", FakeDatetime)

    class FakeArgs:
        current_year = False
        month = None

    result = fetch_ism_official_reports.requested_months(FakeArgs())
    assert result == ["june"]


def test_requested_months_current_year_excludes_current_month(monkeypatch):
    import datetime as dt_module

    fake_july = dt_module.datetime(2026, 7, 14, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_official_reports, "datetime", FakeDatetime)

    class FakeArgs:
        current_year = True
        month = None

    result = fetch_ism_official_reports.requested_months(FakeArgs())
    assert result == ["january", "february", "march", "april", "may", "june"]


def test_main_imports_requested_months(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "market_data.sqlite"

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", lambda url: HTML)
    monkeypatch.setattr(
        fetch_ism_official_reports,
        "fetched_at_now",
        lambda: "2026-07-14T10:00:00Z",
    )

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--month", "june"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ism_manufacturing_2026_06: metrics=11 rankings=4 comments=1" in out
