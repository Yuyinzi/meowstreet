from app.db import growth_cycle
from app.db import ism_surveys
from app.db import us_rates_liquidity
from scripts import fetch_ism_services_reports


REPORT_HTML = """
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

EXPECTED_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/june/"


def test_main_imports_latest_month(tmp_path, monkeypatch, capsys):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    exit_code = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert (
        "ism_services_2026_06: source=ismworld metrics=4 rankings=3 comments=1" in out
    )

    con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(con, EXPECTED_URL)
        assert snapshot["parse_status"] == "parsed"
        assert snapshot["report_id"] == "ism_services_2026_06"

        points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
        assert points[-1] == {
            "date": "2026-06-01",
            "value": 54.0,
            "source": "ISM official report",
        }

        report = ism_surveys.load_latest_report_snapshot(con, "services")
        assert report["report_id"] == "ism_services_2026_06"
    finally:
        con.close()


def test_requested_months_produces_correct_range(monkeypatch):
    import datetime as dt_module

    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    assert fetch_ism_services_reports.requested_months(1) == ["2026-06-01"]
    assert fetch_ism_services_reports.requested_months(3) == [
        "2026-04-01",
        "2026-05-01",
        "2026-06-01",
    ]


def test_requested_months_handles_year_boundary(monkeypatch):
    import datetime as dt_module

    fake_jan = dt_module.datetime(2026, 1, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_jan

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    months = fetch_ism_services_reports.requested_months(3)
    assert months == ["2025-10-01", "2025-11-01", "2025-12-01"]
