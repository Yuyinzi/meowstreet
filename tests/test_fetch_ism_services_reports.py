from app.db import growth_cycle
from app.db import ism_surveys
from app.db import us_rates_liquidity
from app.tools import ism_services
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
EXPECTED_JULY_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/july/"

REDUCED_REPORT_HTML = """
<article>
<h1>June 2026 ISM Services PMI Report</h1>
<p>Services PMI registered 54 percent.</p>
<p>Business Activity Index at 55.4 percent.</p>
<p>New Orders Index registered 55.1 percent.</p>
<p>The 1 services industries reporting growth in June are: Construction.</p>
</article>
"""

NO_BACKLOG_REPORT_HTML = """
<article>
<h1>June 2026 ISM Services PMI Report</h1>
<p>Services PMI registered 54 percent.</p>
<p>Business Activity Index at 55.4 percent.</p>
<p>New Orders Index registered 55.1 percent.</p>
<p>The 2 services industries reporting growth in June are: Construction; and Retail Trade.</p>
<p>The one industry reporting contraction in June is: Educational Services.</p>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<p>"Pipeline remains healthy." [Construction]</p>
</article>
"""


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
        assert snapshot["parse_status"] == "ok"
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


def test_main_returns_1_on_report_month_mismatch(tmp_path, monkeypatch, capsys):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_august = dt_module.datetime(2026, 8, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_august

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    exit_code = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "report month mismatch" in stderr

    con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(con, EXPECTED_JULY_URL)
        assert snapshot is not None
        assert snapshot["parse_status"] == "failed"
        assert "report month mismatch" in snapshot["parse_error"]

        for sid in [
            "ism_services_pmi",
            "ism_services_business_activity",
            "ism_services_new_orders",
            "ism_services_order_backlog",
        ]:
            points = us_rates_liquidity.load_macro_indicator_points(con, sid)
            assert len(points) == 0, f"{sid} has points despite mismatch"

        report = ism_surveys.load_latest_report_snapshot(con, "services")
        assert report is None

        rankings = ism_surveys.load_industry_rankings(con, "services")
        assert len(rankings) == 0

        comments = ism_surveys.load_industry_comments(con, "services")
        assert len(comments) == 0
    finally:
        con.close()


def test_main_returns_1_on_rankings_write_failure(tmp_path, monkeypatch, capsys):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    def _fail_rankings(con, survey_type, rows, commit=True):
        raise RuntimeError("simulated rankings write failure")

    monkeypatch.setattr(ism_surveys, "merge_industry_rankings", _fail_rankings)

    exit_code = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "rankings write failure" in stderr

    check_con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(check_con, EXPECTED_URL)
        assert snapshot is not None
        assert snapshot["parse_status"] == "failed"
        assert "rankings write failure" in snapshot["parse_error"]

        for sid in [
            "ism_services_pmi",
            "ism_services_business_activity",
            "ism_services_new_orders",
            "ism_services_order_backlog",
        ]:
            points = us_rates_liquidity.load_macro_indicator_points(check_con, sid)
            assert len(points) == 0, f"{sid} persisted despite atomic write failure"

        report = ism_surveys.load_latest_report_snapshot(check_con, "services")
        assert report is None

        rankings = ism_surveys.load_industry_rankings(check_con, "services")
        assert len(rankings) == 0

        comments = ism_surveys.load_industry_comments(check_con, "services")
        assert len(comments) == 0
    finally:
        check_con.close()


def test_success_then_failure_preserves_provenance(tmp_path, monkeypatch, capsys):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    ec = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )
    assert ec == 0
    first_out = capsys.readouterr()
    assert "rankings=3 comments=1" in first_out.out

    capsys.readouterr()

    def _fail_rankings(con, survey_type, rows, commit=True):
        raise RuntimeError("simulated rankings write failure")

    monkeypatch.setattr(ism_surveys, "merge_industry_rankings", _fail_rankings)

    ec2 = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )
    assert ec2 == 1
    second_err = capsys.readouterr().err
    assert "rankings write failure" in second_err

    con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(con, EXPECTED_URL)
        assert snapshot["parse_status"] == "failed"
        assert snapshot["report_id"] == "ism_services_2026_06"
        assert snapshot["report_month"] == "2026-06-01"

        points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
        assert len(points) > 0
        assert points[-1]["value"] == 54.0

        report = ism_surveys.load_latest_report_snapshot(con, "services")
        assert report["report_id"] == "ism_services_2026_06"

        rankings = ism_surveys.load_industry_rankings(con, "services")
        assert len(rankings) == 3

        comments = ism_surveys.load_industry_comments(con, "services")
        assert len(comments) == 1
    finally:
        con.close()


def test_full_then_reduced_retry_replaces_rankings_and_comments(
    tmp_path, monkeypatch, capsys
):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    ec = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )
    assert ec == 0
    assert "rankings=3 comments=1" in capsys.readouterr().out

    capsys.readouterr()

    ec2 = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REDUCED_REPORT_HTML,
    )
    assert ec2 == 0
    assert "rankings=1 comments=0" in capsys.readouterr().out

    con = us_rates_liquidity.connect(db_path)
    try:
        rankings = ism_surveys.load_industry_rankings(con, "services")
        assert len(rankings) == 1
        assert rankings[0]["industry"] == "Construction"

        comments = ism_surveys.load_industry_comments(con, "services")
        assert len(comments) == 0

        points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
        assert len(points) > 0
    finally:
        con.close()


def test_retry_without_backlog_clears_old_backlog(tmp_path, monkeypatch, capsys):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    ec = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
    )
    assert ec == 0
    assert "metrics=4" in capsys.readouterr().out

    capsys.readouterr()

    ec2 = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: NO_BACKLOG_REPORT_HTML,
    )
    assert ec2 == 0
    assert "metrics=3" in capsys.readouterr().out

    con = us_rates_liquidity.connect(db_path)
    try:
        backlog_points = us_rates_liquidity.load_macro_indicator_points(
            con, "ism_services_order_backlog"
        )
        backlog_june = [p for p in backlog_points if p["date"] == "2026-06-01"]
        assert len(backlog_june) == 0

        for sid in [
            "ism_services_pmi",
            "ism_services_business_activity",
            "ism_services_new_orders",
        ]:
            points = us_rates_liquidity.load_macro_indicator_points(con, sid)
            june_points = [p for p in points if p["date"] == "2026-06-01"]
            assert len(june_points) == 1, f"{sid} missing June point after retry"

        rankings = ism_surveys.load_industry_rankings(con, "services")
        assert len(rankings) == 3

        comments = ism_surveys.load_industry_comments(con, "services")
        assert len(comments) == 1

        points_by_id = us_rates_liquidity.load_macro_indicator_points_for_series(
            con, list(ism_services.SERIES_TO_KEY)
        )
        signal = ism_services.build_signal(points_by_id)
        assert signal["backlog_confirmation"] == "unavailable"
    finally:
        con.close()


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
