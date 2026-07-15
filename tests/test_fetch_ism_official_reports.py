import pytest
from subprocess import CalledProcessError

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

NO_REPORT_HTML = """
<html>
<head><title>January</title></head>
<body>
<h1>January</h1>
<p>Purchase Historical PMI® Data</p>
</body>
</html>
"""


def test_main_handles_sso_error_gracefully(tmp_path, monkeypatch, capsys):
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"

    def failing_fetch(url):
        raise ValueError("ism official report requires ISM membership login")

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", failing_fetch)

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--month", "june"],
        ai_client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ism_official_report/june: failed" in err
    assert "ISM membership login" in err


def test_fetch_text_uses_plain_curl_transport(monkeypatch):
    calls = []

    class Result:
        stdout = HTML

    def fake_run(args, capture_output, text, check, timeout):
        calls.append(
            {
                "args": args,
                "capture_output": capture_output,
                "text": text,
                "check": check,
                "timeout": timeout,
            }
        )
        return Result()

    monkeypatch.setattr(fetch_ism_official_reports.subprocess, "run", fake_run)

    result = fetch_ism_official_reports.fetch_text("https://example.com/report")

    assert result == HTML
    assert calls == [
        {
            "args": ["curl", "-sS", "https://example.com/report"],
            "capture_output": True,
            "text": True,
            "check": True,
            "timeout": 30,
        }
    ]


def test_import_report_fetches_and_stores_official_ism_data(tmp_path):
    from tests.test_ism_ai_extraction import valid_extraction

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    result = fetch_ism_official_reports.import_report(
        con,
        "june",
        fetch=lambda url: HTML,
        now=lambda: "2026-07-14T10:00:00Z",
        ai_client=FakeClient(),
        model="test-model",
    )

    assert result == {
        "report_id": "ism_manufacturing_2026_06",
        "metrics": 11,
        "rankings": 0,
        "comments": 1,
        "at_a_glance_rows": 11,
        "source_name": "ismworld",
        "ai_extractions": 1,
        "industry_signals": 2,
        "ai_summary": 1,
        "commodities": 1,
    }
    assert us_rates_liquidity.load_macro_indicator_points(con, "ism_manufacturing_pmi")[
        -1
    ] == {
        "date": "2026-06-01",
        "value": 50.0,
        "source": "ISM AI extraction",
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
    rows = us_rates_liquidity.load_latest_ism_at_a_glance_rows(con)
    assert len(rows) == 11
    assert rows[0]["point_change"] == 1.0
    assert rows[0]["direction"] == "Growing"
    assert rows[0]["rate_of_change"] == "Faster"


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
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", lambda url: HTML)
    monkeypatch.setattr(
        fetch_ism_official_reports,
        "fetched_at_now",
        lambda: "2026-07-14T10:00:00Z",
    )

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--month", "june"],
        ai_client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert (
        "ism_manufacturing_2026_06: source=ismworld metrics=11 rankings=0 comments=1 "
        "at_a_glance_rows=11" in out
    )


def test_main_current_year_skips_month_landing_pages(tmp_path, monkeypatch, capsys):
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    class FakeArgs:
        current_year = True
        month = None

    responses = {
        "january": NO_REPORT_HTML,
        "february": NO_REPORT_HTML,
        "march": NO_REPORT_HTML,
        "april": HTML,
    }

    def fake_fetch(url):
        for month, html in responses.items():
            if f"/{month}/" in url:
                return html
        raise ValueError(f"unexpected url: {url}")

    monkeypatch.setattr(
        fetch_ism_official_reports,
        "requested_months",
        lambda args: ["january", "february", "march", "april"],
    )
    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", fake_fetch)
    monkeypatch.setattr(
        fetch_ism_official_reports,
        "fetched_at_now",
        lambda: "2026-07-14T10:00:00Z",
    )

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--current-year"],
        ai_client_factory=lambda config: FakeClient(),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ism_official_report/january: skipped - no report page available" in (
        captured.err
    )
    assert "ism_official_report/february: skipped - no report page available" in (
        captured.err
    )
    assert "ism_official_report/march: skipped - no report page available" in (
        captured.err
    )
    assert (
        "ism_manufacturing_2026_06: source=ismworld metrics=11 rankings=0 comments=1 "
        "at_a_glance_rows=11" in captured.out
    )


def test_import_report_saves_failed_raw_snapshot(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    url = "https://www.prnewswire.com/news-releases/bad-report.html"

    class FakeClient:
        def complete_json(self, prompt):
            raise ValueError("simulated AI extraction failure")

    with pytest.raises(ValueError, match="simulated AI extraction failure"):
        fetch_ism_official_reports.import_report_url(
            con,
            url,
            source_name="prnewswire",
            fetch=lambda value: (
                "<html><article>June 2026 ISM Manufacturing PMI Report</article></html>"
            ),
            now=lambda: "2026-07-15T10:00:00Z",
            ai_client=FakeClient(),
        )

    snapshot = us_rates_liquidity.load_ism_report_source_snapshot(con, url)
    assert snapshot["source_name"] == "prnewswire"
    assert snapshot["parse_status"] == "prepared"
    assert snapshot["raw_html"].startswith("<html>")


def test_import_report_url_saves_successful_raw_snapshot(tmp_path):
    from tests.test_ism_ai_extraction import valid_extraction

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    url = "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html"

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    result = fetch_ism_official_reports.import_report_url(
        con,
        url,
        source_name="prnewswire",
        fetch=lambda value: HTML,
        now=lambda: "2026-07-15T10:00:00Z",
        ai_client=FakeClient(),
        model="test-model",
    )

    snapshot = us_rates_liquidity.load_ism_report_source_snapshot(con, url)
    assert result["report_id"] == "ism_manufacturing_2026_06"
    assert snapshot["parse_status"] == "prepared"
    assert snapshot["report_id"] == "ism_manufacturing_2026_06"


def test_main_imports_single_url(tmp_path, monkeypatch, capsys):
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"
    url = "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html"

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", lambda value: HTML)
    monkeypatch.setattr(
        fetch_ism_official_reports,
        "fetched_at_now",
        lambda: "2026-07-15T10:00:00Z",
    )

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--url", url],
        ai_client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 0
    assert "source=prnewswire" in capsys.readouterr().out


def test_main_discovers_prnewswire_pages_and_imports_urls(
    tmp_path, monkeypatch, capsys
):
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"
    article_url = "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html"
    listing_html = (
        f'<a href="{article_url}">'
        "Jul 01, 2026 Manufacturing PMI® at 53.3%; June 2026 ISM® Manufacturing PMI® Report"
        "</a>"
    )

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    def fake_fetch(url):
        if "institute-for-supply-management" in url:
            return listing_html
        return HTML

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", fake_fetch)
    monkeypatch.setattr(
        fetch_ism_official_reports,
        "fetched_at_now",
        lambda: "2026-07-15T10:00:00Z",
    )

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--prnewswire-pages", "1"],
        ai_client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 0
    assert "source=prnewswire" in capsys.readouterr().out


def test_ai_payload_to_metric_points_uses_at_a_glance_current_values():
    from tests.test_ism_ai_extraction import valid_extraction

    points = fetch_ism_official_reports.ai_metric_points(valid_extraction())

    assert points["ism_manufacturing_pmi"] == [
        {
            "date": "2026-06-01",
            "value": 50.0,
            "source": "ISM AI extraction",
        }
    ]


def test_import_report_url_uses_ai_extraction_by_default(tmp_path):
    from tests.test_ism_ai_extraction import valid_extraction

    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    result = fetch_ism_official_reports.import_report_url(
        con,
        "https://example.com/report.html",
        source_name="prnewswire",
        fetch=lambda url: (
            "<html><article>Manufacturing PMI at 50.0%; June 2026 ISM Manufacturing PMI Report text</article></html>"
        ),
        now=lambda: "2026-07-15T00:00:00Z",
        ai_client=FakeClient(),
        model="fake-model",
    )

    assert result["report_id"] == "ism_manufacturing_2026_06"
    assert result["source_name"] == "prnewswire"
    assert result["ai_summary"] == 1
    assert result["industry_signals"] == 2


def test_backfill_targets_use_prnewswire_for_history_and_official_for_latest():
    archive_reports = [
        {
            "url": "https://www.prnewswire.com/jan-2026.html",
            "title": "January 2026 ISM Manufacturing PMI Report",
            "report_month": "2026-01-01",
            "report_id": "ism_manufacturing_2026_01",
        },
        {
            "url": "https://www.prnewswire.com/jun-2026.html",
            "title": "June 2026 ISM Manufacturing PMI Report",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
        },
    ]

    targets = fetch_ism_official_reports.backfill_targets(
        archive_reports,
        since_year=2026,
        latest_report_month="2026-06-01",
        existing_months={"2026-01-01"},
        missing_only=True,
    )

    assert targets == [
        {
            "source_name": "ismworld",
            "url": fetch_ism_official_reports.report_url("june"),
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
        }
    ]


def test_normalize_report_month_rejects_bad_format():
    with pytest.raises(ValueError, match="ism report month must be YYYY-MM"):
        fetch_ism_official_reports.normalize_report_month("bad-date")


def test_normalize_report_month_adds_day():
    assert fetch_ism_official_reports.normalize_report_month("2026-06") == "2026-06-01"


def test_normalize_report_month_preserves_full_date():
    assert (
        fetch_ism_official_reports.normalize_report_month("2026-06-01") == "2026-06-01"
    )


def test_main_imports_one_report_month_with_ai(tmp_path, capsys):
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    exit_code = fetch_ism_official_reports.main(
        [
            "--db-path",
            str(db_path),
            "--report-month",
            "2026-06",
            "--force",
        ],
        fetch=lambda url: (
            "<html><article>Manufacturing PMI at 50.0%; "
            "June 2026 ISM Manufacturing PMI Report text</article></html>"
        ),
        ai_client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 0
    assert "ism_manufacturing_2026_06" in capsys.readouterr().out


def test_main_continues_when_prnewswire_article_fetch_fails(
    tmp_path, monkeypatch, capsys
):
    from tests.test_ism_ai_extraction import valid_extraction

    db_path = tmp_path / "market_data.sqlite"
    bad_url = "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-52-6-january-2026-ism-manufacturing-pmi-report-302675443.html"
    good_url = "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html"
    listing_html = (
        f'<a href="{bad_url}">'
        "Jan 2026 Manufacturing PMI® at 52.6%; January 2026 ISM® Manufacturing PMI® Report"
        "</a>"
        f'<a href="{good_url}">'
        "Jul 01, 2026 Manufacturing PMI® at 53.3%; June 2026 ISM® Manufacturing PMI® Report"
        "</a>"
    )

    class FakeClient:
        def complete_json(self, prompt):
            return valid_extraction()

    def fake_fetch(url):
        if "institute-for-supply-management" in url:
            return listing_html
        if url == bad_url:
            raise CalledProcessError(35, ["curl", "-sS", url])
        return HTML

    monkeypatch.setattr(fetch_ism_official_reports, "fetch_text", fake_fetch)
    monkeypatch.setattr(
        fetch_ism_official_reports,
        "fetched_at_now",
        lambda: "2026-07-15T10:00:00Z",
    )

    exit_code = fetch_ism_official_reports.main(
        ["--db-path", str(db_path), "--prnewswire-pages", "1"],
        ai_client_factory=lambda config: FakeClient(),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"ism_official_report/{bad_url}: failed -" in captured.err
    assert (
        "ism_manufacturing_2026_06: source=prnewswire metrics=11 rankings=0 "
        "comments=1 at_a_glance_rows=11" in captured.out
    )
