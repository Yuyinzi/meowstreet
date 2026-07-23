import json
import re

from app.db import growth_cycle
from app.db import ism_surveys
from app.db import us_rates_liquidity
from app.tools import ism_services
from scripts import fetch_ism_services_reports


SERVICES_COMPONENTS = sorted(
    [
        "ism_services_pmi",
        "ism_services_business_activity",
        "ism_services_new_orders",
        "ism_services_employment",
        "ism_services_supplier_deliveries",
        "ism_services_inventories",
        "ism_services_inventory_sentiment",
        "ism_services_prices",
        "ism_services_order_backlog",
        "ism_services_new_export_orders",
        "ism_services_imports",
    ]
)


COMPONENT_LABELS = {
    "ism_services_pmi": "Services PMI",
    "ism_services_business_activity": "Business Activity",
    "ism_services_new_orders": "New Orders",
    "ism_services_employment": "Employment",
    "ism_services_supplier_deliveries": "Supplier Deliveries",
    "ism_services_inventories": "Inventories",
    "ism_services_inventory_sentiment": "Inventory Sentiment",
    "ism_services_prices": "Prices",
    "ism_services_order_backlog": "Backlog of Orders",
    "ism_services_new_export_orders": "New Export Orders",
    "ism_services_imports": "Imports",
}


class FakeAiClient:
    def __init__(self):
        self.model = "test-model"

    async def complete_json_async(self, prompt):
        section = re.search(r"Section: (\w+)", prompt)
        name = section.group(1) if section else "unknown"
        return _response_for_section(name)


def _fixture_html(components, industries_growth, industries_contraction, comments):
    rows = []
    for sid, label in components:
        rows.append(f"<p>{label} Index at {50.0 + len(rows) * 0.5:.1f} percent.</p>")
    glance_table = ""
    for i, (sid, label) in enumerate(components):
        val = 50.0 + i * 0.5
        glance_table += f"{label} {val:.1f} {val - 1:.1f} +1.0 Growing Faster {i + 1}\n"
    growth_list = "; ".join(industries_growth) if industries_growth else "None"
    contraction_list = (
        "; ".join(industries_contraction) if industries_contraction else "None"
    )
    comment_section = ""
    for ind, text in comments:
        comment_section += f'<p>"{text}" [{ind}]</p>\n'
    filler = (
        "The 11 services PMI component indexes averaged 53.5 percent in June, "
        "which is 1.2 percentage points above the 52.3 percent average recorded in May. "
        "The services sector has now reported expansion in 46 of the last 48 months. "
        "The average PMI for the first half of 2026 is 53.1 percent. "
    )
    return f"""<article>
<h1>June 2026 ISM Services PMI Report</h1>
<p>Services PMI Index at {50.0:.1f} percent. The services sector continued its expansion.</p>
<p>{filler}</p>
{"".join(rows)}
<h3>SERVICES AT A GLANCE</h3>
<p>{glance_table}</p>
<h3>INDUSTRY PERFORMANCE</h3>
<p>The {len(industries_growth)} services industries reporting growth in June are: {growth_list}.</p>
<p>The {len(industries_contraction)} services industries reporting contraction in June are: {contraction_list}.</p>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
{comment_section}
<h3>COMMODITIES REPORTED</h3>
<p>Commodities Up in Price: Construction Labor; Fuel.</p>
</article>"""


DEFAULT_COMPONENTS = [(sid, COMPONENT_LABELS[sid]) for sid in SERVICES_COMPONENTS]
REPORT_HTML = _fixture_html(
    DEFAULT_COMPONENTS,
    ["Construction", "Retail Trade"],
    ["Educational Services"],
    [("Construction", "Pipeline remains healthy.")],
)
EXPECTED_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/june/"
EXPECTED_JULY_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/july/"
EXPECTED_MONTH = "2026-06-01"


def _response_for_section(section_name):
    if section_name == "report":
        return {
            "report": {
                "report_id": "ism_services_2026_06",
                "report_month": "2026-06-01",
                "title": "June 2026 ISM Services PMI Report",
                "source_name": "ismworld",
                "source_url": EXPECTED_URL,
            }
        }
    if section_name == "at_a_glance_rows":
        return {
            "at_a_glance_rows": [
                {
                    "series_id": sid,
                    "label": COMPONENT_LABELS[sid],
                    "current_value": 50.0 + i * 0.5,
                    "previous_value": 49.0 + i * 0.5,
                    "point_change": 1.0,
                    "direction": "Growing",
                    "rate_of_change": "Faster",
                    "trend_months": i + 1,
                }
                for i, sid in enumerate(SERVICES_COMPONENTS)
            ]
        }
    if section_name == "industry_signals":
        return {
            "industry_signals": [
                {
                    "signal_type": "overall_growth",
                    "direction": "growth",
                    "industry": "Construction",
                    "rank": 1,
                    "source_excerpt": "The 2 services industries reporting growth in June are",
                },
                {
                    "signal_type": "overall_growth",
                    "direction": "growth",
                    "industry": "Retail Trade",
                    "rank": 2,
                    "source_excerpt": "The 2 services industries reporting growth in June are",
                },
                {
                    "signal_type": "overall_contraction",
                    "direction": "contraction",
                    "industry": "Educational Services",
                    "rank": 1,
                    "source_excerpt": "The 1 services industries reporting contraction in June are",
                },
            ]
        }
    if section_name == "comments_commodities":
        return {
            "respondent_comments": [
                {
                    "industry": "Construction",
                    "comment_text": "Pipeline remains healthy.",
                }
            ],
            "commodities": [
                {
                    "commodity": "Construction Labor",
                    "signal_type": "up_in_price",
                    "months": 2,
                },
                {"commodity": "Fuel", "signal_type": "up_in_price", "months": None},
            ],
        }
    if section_name == "narrative_facts":
        return {
            "narrative_facts": {
                "consecutive_expansion_months": None,
                "services_economy_gdp_share_percent": None,
                "broad_based_expansion_mentioned": False,
                "inflationary_pressure_mentioned": False,
            }
        }
    return {}


def _fake_client_factory(config):
    return FakeAiClient()


def _reduced_components():
    return DEFAULT_COMPONENTS


def _no_backlog_components():
    return DEFAULT_COMPONENTS


REDUCED_REPORT_HTML = _fixture_html(
    _reduced_components(),
    ["Construction", "Retail Trade"],
    ["Educational Services"],
    [("Construction", "Pipeline remains healthy.")],
)
NO_BACKLOG_REPORT_HTML = _fixture_html(
    _no_backlog_components(),
    ["Construction", "Retail Trade"],
    ["Educational Services"],
    [("Construction", "Pipeline remains healthy.")],
)


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
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    out = captured.out
    assert (
        "ism_services_2026_06: source=ismworld metrics=11 rankings=3 comments=1" in out
    )
    assert "[1/1] services 2026-06 fetching source=ismworld" in captured.err
    assert "fetched chars=" in captured.err
    assert "prepared report_id=ism_services_2026_06 chars=" in captured.err
    assert "section report started prompt_chars=" in captured.err
    assert "promotion started report_id=ism_services_2026_06" in captured.err
    assert "promotion ok report_id=ism_services_2026_06" in captured.err

    con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(con, EXPECTED_URL)
        assert snapshot["parse_status"] == "ok"
        assert snapshot["report_id"] == "ism_services_2026_06"

        points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
        assert points[-1] == {
            "date": "2026-06-01",
            "value": 54.0,
            "source": "ISM AI extraction",
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
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "mismatch" in stderr.lower()

    con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(con, EXPECTED_JULY_URL)
        assert snapshot is not None
        assert snapshot["parse_status"] == "failed"
        assert "mismatch" in snapshot["parse_error"]

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


def test_main_returns_1_on_promotion_failure(tmp_path, monkeypatch, capsys):
    import datetime as dt_module

    db_path = tmp_path / "market_data.sqlite"
    fake_july = dt_module.datetime(2026, 7, 21, 12, 0, 0)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return fake_july

    monkeypatch.setattr(fetch_ism_services_reports, "datetime", FakeDatetime)

    import app.services.ism_services_ai_ingestion as svc_ingestion

    def _fail_promotion(con, extraction, source):
        raise RuntimeError("simulated promotion failure")

    monkeypatch.setattr(svc_ingestion, "promote_services_extraction", _fail_promotion)

    exit_code = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
        ai_client_factory=_fake_client_factory,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "promotion failure" in stderr

    check_con = us_rates_liquidity.connect(db_path)
    try:
        snapshot = growth_cycle.load_ism_report_source_snapshot(check_con, EXPECTED_URL)
        assert snapshot is not None
        assert snapshot["parse_status"] == "failed"
        assert "promotion failure" in snapshot["parse_error"]

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
        ai_client_factory=_fake_client_factory,
    )
    assert ec == 0
    first_out = capsys.readouterr()
    assert "rankings=3 comments=1" in first_out.out

    capsys.readouterr()

    import app.services.ism_services_ai_ingestion as svc_ingestion

    def _fail_promotion(con, extraction, source):
        raise RuntimeError("simulated promotion failure")

    monkeypatch.setattr(svc_ingestion, "promote_services_extraction", _fail_promotion)

    ec2 = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
        ai_client_factory=_fake_client_factory,
    )
    assert ec2 == 1
    second_err = capsys.readouterr().err
    assert "promotion failure" in second_err

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
        assert len(rankings) >= 1

        report_comments = growth_cycle.load_ism_report_comments(
            con, "ism_services_2026_06"
        )
        assert len(report_comments) >= 1
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
        ai_client_factory=_fake_client_factory,
    )
    assert ec == 0
    assert "rankings=3 comments=1" in capsys.readouterr().out

    capsys.readouterr()

    def _reduced_factory(config):
        client = FakeAiClient()
        return client

    ec2 = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REDUCED_REPORT_HTML,
        ai_client_factory=_fake_client_factory,
    )
    assert ec2 == 0
    assert "rankings=3 comments=1" in capsys.readouterr().out

    con = us_rates_liquidity.connect(db_path)
    try:
        rankings = ism_surveys.load_industry_rankings(con, "services")
        assert len(rankings) >= 1

        report_comments = growth_cycle.load_ism_report_comments(
            con, "ism_services_2026_06"
        )
        assert len(report_comments) >= 1

        points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
        assert len(points) > 0
    finally:
        con.close()


def test_retry_reruns_extraction(tmp_path, monkeypatch, capsys):
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
        ai_client_factory=_fake_client_factory,
    )
    assert ec == 0
    assert "metrics=11" in capsys.readouterr().out

    capsys.readouterr()

    ec2 = fetch_ism_services_reports.main(
        ["--db-path", str(db_path), "--months", "1"],
        fetch=lambda url: REPORT_HTML,
        ai_client_factory=_fake_client_factory,
    )
    assert ec2 == 0
    assert "metrics=11" in capsys.readouterr().out

    con = us_rates_liquidity.connect(db_path)
    try:
        points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
        june_points = [p for p in points if p["date"] == "2026-06-01"]
        assert len(june_points) == 1

        rankings = ism_surveys.load_industry_rankings(con, "services")
        assert len(rankings) >= 1

        report_comments = growth_cycle.load_ism_report_comments(
            con, "ism_services_2026_06"
        )
        assert len(report_comments) >= 1
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
