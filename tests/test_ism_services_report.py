from pathlib import Path

import pytest

from app.tools import ism_services_report

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


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


def test_parse_report_extracts_only_operational_metrics_and_evidence():
    result = ism_services_report.parse_report(
        REPORT_HTML,
        "https://example.test/services/june/",
        "2026-07-06T10:00:00-04:00",
    )

    assert result["report"]["report_id"] == "ism_services_2026_06"
    assert result["metrics"] == {
        "ism_services_pmi": 54.0,
        "ism_services_business_activity": 55.4,
        "ism_services_new_orders": 55.1,
        "ism_services_order_backlog": 54.9,
    }
    assert [row["industry"] for row in result["rankings"]] == [
        "Construction",
        "Retail Trade",
        "Educational Services",
    ]
    assert result["comments"][0]["industry"] == "Construction"


def test_parse_report_extracts_all_fields():
    result = ism_services_report.parse_report(
        REPORT_HTML,
        "https://example.test/services/june/",
        "2026-07-06T10:00:00-04:00",
    )

    assert result["report"] == {
        "report_id": "ism_services_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Services PMI Report",
        "source_url": "https://example.test/services/june/",
        "source_hash": result["report"]["source_hash"],
        "source_name": "ismworld",
        "fetched_at": "2026-07-06T10:00:00-04:00",
        "parse_status": "ok",
        "next_report_period": None,
        "next_release_at": None,
        "next_release_label": "",
    }
    assert result["rankings"][0] == {
        "date": "2026-06-01",
        "industry": "Construction",
        "direction": "growth",
        "rank": 1,
        "source": "ISM official report",
    }
    assert result["rankings"][1] == {
        "date": "2026-06-01",
        "industry": "Retail Trade",
        "direction": "growth",
        "rank": 2,
        "source": "ISM official report",
    }
    assert result["rankings"][2] == {
        "date": "2026-06-01",
        "industry": "Educational Services",
        "direction": "contraction",
        "rank": -1,
        "source": "ISM official report",
    }
    assert result["comments"] == [
        {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "industry": "Construction",
            "comment_index": 1,
            "comment_text": "Pipeline remains healthy.",
            "source_url": "https://example.test/services/june/",
            "source_hash": result["report"]["source_hash"],
            "source": "ISM official report",
        }
    ]


def test_parse_report_rejects_hospital_document():
    html = """
    <html><body>
    <h1>June 2026 ISM Hospital PMI Report</h1>
    <p>Hospital PMI at 52.0 percent.</p>
    </body></html>
    """
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_services_report.parse_report(
            html,
            "https://example.com/hospital.html",
            "2026-07-15T10:00:00Z",
        )


def test_parse_report_rejects_generic_ism_release():
    html = """
    <html><body>
    <h1>ISM 2026 Annual Conference Announcement</h1>
    <p>The Institute for Supply Management will hold its annual conference.</p>
    </body></html>
    """
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_services_report.parse_report(
            html,
            "https://example.com/generic.html",
            "2026-07-15T10:00:00Z",
        )


def test_parse_report_accepts_all_caps_marker():
    html = """
    <html><body>
    <h1>SERVICES PMI AT 54%</h1>
    <p>June 2026 ISM Services PMI Report</p>
    <p>The 2 services industries reporting growth in June are: Construction; and Retail Trade.</p>
    <p>The one industry reporting contraction in June is: Educational Services.</p>
    <p>Services PMI registered 54 percent.</p>
    <p>Business Activity Index at 55.4 percent.</p>
    <p>New Orders Index registered 55.1 percent.</p>
    <p>The next ISM Services PMI Report featuring July 2026 data will be released at 10:00 a.m. ET on Monday, August 3, 2026.</p>
    </body></html>
    """
    parsed = ism_services_report.parse_report(
        html,
        "https://example.com/allcaps.html",
        "2026-07-15T10:00:00Z",
    )
    assert parsed["report"]["report_id"] == "ism_services_2026_06"


def test_prepare_report_for_ai_ismworld_fixture():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html, "https://www.ismworld.org/services/june/", "2026-07-03T14:00:00Z"
    )
    assert prepared["report_id"] == "ism_services_2026_06"
    assert prepared["report_month"] == "2026-06-01"
    assert "Services PMI" in prepared["source_text"]
    assert "Manufacturing PMI" not in prepared["source_text"]


def test_prepare_report_for_ai_prnewswire_fixture():
    html = (FIXTURE_DIR / "ism_services_prnewswire_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://www.prnewswire.com/services/june/",
        "2026-07-03T14:00:00Z",
        source_name="prnewswire",
    )
    assert prepared["report_id"] == "ism_services_2026_06"
    assert prepared["report_month"] == "2026-06-01"
    assert "Services PMI" in prepared["source_text"]


def test_prepare_report_for_ai_rejects_manufacturing():
    html = "<html><body><h1>June 2026 Manufacturing PMI Report</h1><p>Manufacturing PMI at 53%</p></body></html>"
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_services_report.prepare_report_for_ai(
            html, "https://example.test/mfg/", "2026-07-03T14:00:00Z"
        )


def test_prepare_report_for_ai_rejects_hospital():
    html = "<html><body><h1>June 2026 ISM Hospital PMI Report</h1><p>Hospital PMI at 52%</p></body></html>"
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_services_report.prepare_report_for_ai(
            html, "https://example.test/hospital/", "2026-07-03T14:00:00Z"
        )


def test_prepare_report_for_ai_rejects_generic_ism():
    html = "<html><body><h1>ISM Annual Conference</h1><p>Some generic content.</p></body></html>"
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_services_report.prepare_report_for_ai(
            html, "https://example.test/generic/", "2026-07-03T14:00:00Z"
        )


def test_prepare_report_for_ai_rejects_marker_free():
    html = "<html><body><h1>Random Page</h1><p>No ISM content here.</p></body></html>"
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_services_report.prepare_report_for_ai(
            html, "https://example.test/random/", "2026-07-03T14:00:00Z"
        )


def test_prepare_report_for_ai_prnewswire_strips_non_content():
    html = """
    <html><head><script>tracking code</script></head>
    <body>
    <nav>navigation links</nav>
    <article>
    <h1>June 2026 ISM Services PMI Report</h1>
    <p>Services PMI at 54.0%</p>
    </article>
    </body></html>
    """
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://www.prnewswire.com/services/june/",
        "2026-07-03T14:00:00Z",
        source_name="prnewswire",
    )
    assert "tracking code" not in prepared["source_text"]
    assert "navigation links" not in prepared["source_text"]
    assert "Services PMI" in prepared["source_text"]


def test_at_a_glance_region_contains_component_table():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html, "https://example.test/services/", "2026-07-03T14:00:00Z"
    )
    region = ism_services_report._extract_at_a_glance_region(prepared["source_text"])
    assert "Services PMI" in region
    assert "Business Activity" in region
    assert "New Orders" in region
    assert "Employment" in region
    assert "Supplier Deliveries" in region
    assert "Inventories" in region
    assert "Inventory Sentiment" in region
    assert "Prices" in region
    assert "Backlog of Orders" in region
    assert "New Export Orders" in region
    assert "Imports" in region


def test_industry_signals_region_contains_industry_lists():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html, "https://example.test/services/", "2026-07-03T14:00:00Z"
    )
    region = ism_services_report._extract_industry_signals_region(
        prepared["source_text"]
    )
    assert "reporting growth" in region
    assert "reporting contraction" in region
    assert "Construction" in region
    assert "Educational Services" in region


def test_comments_commodities_region_contains_both():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html, "https://example.test/services/", "2026-07-03T14:00:00Z"
    )
    region = ism_services_report._extract_comments_commodities_region(
        prepared["source_text"]
    )
    assert "WHAT RESPONDENTS ARE SAYING" in region or "visitor spending" in region
    assert "Commodities Up" in region or "Commodities Down" in region


def test_narrative_region_contains_headline_metrics():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html, "https://example.test/services/", "2026-07-03T14:00:00Z"
    )
    region = ism_services_report._extract_narrative_region(prepared["source_text"])
    assert "Services PMI at" in region
    assert "Business Activity" in region
    assert "Prices Index" in region
    assert "Tempe, Arizona" not in region


def test_live_ismworld_article_excludes_boilerplate_and_slices_real_sections():
    html = (FIXTURE_DIR / "ism_services_live_page.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://www.ismworld.org/reports/services/june/",
        "2026-07-03T14:00:00Z",
    )

    source_text = prepared["source_text"]
    assert "Create an Account Navigation Marker" not in source_text
    assert "Footer Privacy Marker" not in source_text
    assert "must not appear" not in source_text

    at_a_glance = ism_services_report._extract_at_a_glance_region(source_text)
    industries = ism_services_report._extract_industry_signals_region(source_text)
    comments_commodities = ism_services_report._extract_comments_commodities_region(
        source_text
    )
    narrative = ism_services_report._extract_narrative_region(source_text)

    assert "Services PMI" in at_a_glance
    assert "Pipeline remains healthy" not in at_a_glance
    assert "Construction" in industries
    assert "Pipeline remains healthy" in comments_commodities
    assert "Construction Labor" in comments_commodities
    assert "24th consecutive month" in narrative
    assert "INDUSTRY PERFORMANCE" not in narrative


def test_component_industry_lists_included_in_industry_signals_region():
    html = (FIXTURE_DIR / "ism_services_live_page.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://www.ismworld.org/reports/services/june/",
        "2026-07-03T14:00:00Z",
    )
    region = ism_services_report._extract_industry_signals_region(
        prepared["source_text"]
    )
    assert "reporting growth in June" in region
    assert "reporting a contraction in June" in region
    assert "reporting growth in business activity" in region
    assert "Construction" in region


def test_component_industry_lists_excludes_methodology_text_and_tables():
    html = (FIXTURE_DIR / "ism_services_live_page.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://www.ismworld.org/reports/services/june/",
        "2026-07-03T14:00:00Z",
    )
    region = ism_services_report._extract_industry_signals_region(
        prepared["source_text"]
    )
    assert "Services PMI index details" not in region
    assert "methodology" not in region


def test_component_industry_lists_excludes_methodology_after_repeated_heading():
    source_text = """INDUSTRY PERFORMANCE
The industries reporting growth are: Construction.
WHAT RESPONDENTS ARE SAYING
JUNE 2026 SERVICES INDEX SUMMARIES
Inventory Sentiment
The industries reporting inventories were too high are: Retail Trade.
Inventory Sentiment
The survey divides responses into the following industry categories: Mining.
"""

    region = ism_services_report._extract_industry_signals_region(source_text)

    assert "inventories were too high" in region
    assert "divides responses" not in region


def test_component_industry_lists_retains_all_component_types_in_fixture():
    html = (FIXTURE_DIR / "ism_services_live_page.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://www.ismworld.org/reports/services/june/",
        "2026-07-03T14:00:00Z",
    )
    region = ism_services_report._extract_industry_signals_region(
        prepared["source_text"]
    )
    assert "Business Activity" in region
    assert "New Orders" in region
    assert "Employment" in region


def test_component_lists_unaffected_when_no_index_summaries_section():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = ism_services_report.prepare_report_for_ai(
        html,
        "https://example.test/services/",
        "2026-07-03T14:00:00Z",
    )
    region = ism_services_report._extract_industry_signals_region(
        prepared["source_text"]
    )
    assert "reporting growth in June" in region
    assert "reporting contraction" in region


def test_missing_at_a_glance_raises_value_error():
    text = "Services PMI at 54% no at a glance section here"
    with pytest.raises(ValueError, match="at a glance"):
        ism_services_report._extract_at_a_glance_region(text)


def test_missing_narrative_returns_available_text():
    text = "Services PMI at 54% no narrative content with Tempe marker"
    region = ism_services_report._extract_narrative_region(text)
    assert "Services PMI" in region


def test_comments_commodities_region_stops_at_split_index_summary_heading():
    source_text = """WHAT RESPONDENTS ARE SAYING
"Demand remains stable." [Construction]
COMMODITIES REPORTED UP/DOWN IN PRICE, AND IN SHORT SUPPLY
Copper
JANUARY
2026 SERVICES INDEX SUMMARIES
Services PMI
Methodology text that must be excluded.
"""

    region = ism_services_report._extract_comments_commodities_region(source_text)

    assert "Copper" in region
    assert "SERVICES INDEX SUMMARIES" not in region
    assert "Methodology text" not in region


@pytest.mark.parametrize(
    "heading",
    [
        "JANUARY 2026 SERVICES INDEX SUMMARIES",
        "JANUARY\n2026 SERVICES INDEX SUMMARIES",
        "JANUARY\r\n2026 SERVICES INDEX SUMMARIES",
    ],
)
def test_component_industry_lists_accept_index_summary_heading_layouts(heading):
    source_text = f"""INDUSTRY PERFORMANCE
The industry reporting growth is Construction.
WHAT RESPONDENTS ARE SAYING
{heading}
Business Activity
The industry reporting an increase in business activity is: Construction.
"""

    region = ism_services_report._extract_industry_signals_region(source_text)

    assert "Business Activity" in region
    assert "increase in business activity" in region
