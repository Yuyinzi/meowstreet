import pytest

from app.tools import ism_official_report


REPORT_HTML = """
<html>
<body>
<h1>Manufacturing PMI® at 53.3%</h1>
<h1>June 2026 ISM® Manufacturing PMI® Report</h1>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<ul>
<li>“Input costs remain elevated across key categories.” [Chemical Products]</li>
<li>“Conditions are optimistic but not yet booming.” [Machinery]</li>
</ul>
<h3>MANUFACTURING AT A GLANCE</h3>
<p>June 2026</p>
<p>Index Series Index Jun Series Index May Percentage Point Change Direction Rate of Change Trend* (Months)</p>
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
<p>The 14 manufacturing industries reporting growth in June — listed in order — are: Printing & Related Support Activities; Electrical Equipment, Appliances & Components; Textile Mills; Primary Metals; Apparel, Leather & Allied Products; Fabricated Metal Products; Computer & Electronic Products; Machinery; Plastics & Rubber Products; Transportation Equipment; Nonmetallic Mineral Products; Chemical Products; Miscellaneous Manufacturing; and Food, Beverage & Tobacco Products.</p>
<p>The three industries in contraction are: Paper Products; Furniture & Related Products; and Wood Products.</p>
<p>The next ISM® Manufacturing PMI® Report featuring July 2026 data will be released at 10:00 a.m. ET on Monday, August 3, 2026.</p>
</body>
</html>
"""


LIVE_STYLE_HTML = """
<html>
<body>
<h1>Manufacturing PMI<sup>®</sup> at 53.3%</h1>
<h1>June 2026 ISM<sup>®</sup> Manufacturing PMI<sup>®</sup> Report</h1>
<h3>WHAT RESPONDENTS ARE SAYING</h3>
<ul>
<li>“Input costs remain elevated across key categories.” [Chemical Products]</li>
<li>“Conditions are optimistic but not yet booming.” [Machinery]</li>
</ul>
<h3>MANUFACTURING AT A GLANCE</h3>
<p>June 2026</p>
<p>Index Series Index Jun Series Index May Percentage Point Change Direction Rate of Change Trend* (Months)</p>
<p>Manufacturing PMI<sup>®</sup> 53.3 54.0 -0.7 Growing Slower 6</p>
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
<p>The 14 manufacturing industries reporting growth in June — listed in order — are: Printing & Related Support Activities; Electrical Equipment, Appliances & Components; Textile Mills; Primary Metals; Apparel, Leather & Allied Products; Fabricated Metal Products; Computer & Electronic Products; Machinery; Plastics & Rubber Products; Transportation Equipment; Nonmetallic Mineral Products; Chemical Products; Miscellaneous Manufacturing; and Food, Beverage & Tobacco Products.</p>
<p>The three industries in contraction are: Paper Products; Furniture & Related Products; and Wood Products.</p>
<p>The next ISM<sup>®</sup> Manufacturing PMI<sup>®</sup> Report featuring July 2026 data will be released at 10:00 a.m. ET on Monday, August 3, 2026.</p>
</body>
</html>
"""


def test_parse_report_with_sup_reg_in_markup_extracts_all_fields():
    parsed = ism_official_report.parse_report(
        LIVE_STYLE_HTML,
        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        fetched_at="2026-07-14T10:00:00Z",
    )

    assert parsed["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert parsed["metrics"]["ism_manufacturing_pmi"] == 53.3
    assert parsed["metrics"]["ism_manufacturing_new_orders"] == 56.0
    assert parsed["metrics"]["ism_manufacturing_imports"] == 52.9
    assert parsed["rankings"][0]["industry"] == "Printing & Related Support Activities"
    assert parsed["rankings"][0]["direction"] == "growth"
    assert parsed["rankings"][-1]["industry"] == "Wood Products"
    assert parsed["rankings"][-1]["direction"] == "contraction"
    assert len(parsed["comments"]) == 2
    assert parsed["report"]["next_report_period"] == "2026-07-01"
    assert len(parsed["at_a_glance_rows"]) == 11
    assert parsed["at_a_glance_rows"][0] == {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "series_id": "ism_manufacturing_pmi",
        "label": "Manufacturing PMI",
        "current_value": 53.3,
        "previous_value": 54.0,
        "point_change": -0.7,
        "direction": "Growing",
        "rate_of_change": "Slower",
        "trend_months": 6,
        "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        "source_hash": parsed["report"]["source_hash"],
    }


def test_report_month_from_title_accepts_historical_prnewswire_title():
    assert ism_official_report.report_month_from_title(
        "Manufacturing PMI at 48.5%; May 2025 Manufacturing ISM Report On Business"
    ) == ("2025-05-01", "May", "2025")


def test_parse_report_extracts_metadata_metrics_rankings_comments_and_release():
    parsed = ism_official_report.parse_report(
        REPORT_HTML,
        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        fetched_at="2026-07-14T10:00:00Z",
    )

    assert parsed["report"] == {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        "source_hash": parsed["report"]["source_hash"],
        "source_name": "ismworld",
        "fetched_at": "2026-07-14T10:00:00Z",
        "parse_status": "ok",
        "next_report_period": "2026-07-01",
        "next_release_at": "2026-08-03T10:00:00-04:00",
        "next_release_label": "Monday, August 3, 2026 at 10:00 a.m. ET",
    }
    assert parsed["metrics"]["ism_manufacturing_pmi"] == 53.3
    assert parsed["metrics"]["ism_manufacturing_new_orders"] == 56.0
    assert parsed["metrics"]["ism_manufacturing_imports"] == 52.9
    assert parsed["rankings"][0] == {
        "date": "2026-06-01",
        "industry": "Printing & Related Support Activities",
        "direction": "growth",
        "rank": 14,
        "source": "ISM official report",
    }
    assert parsed["rankings"][-1] == {
        "date": "2026-06-01",
        "industry": "Wood Products",
        "direction": "contraction",
        "rank": -3,
        "source": "ISM official report",
    }
    assert len(parsed["at_a_glance_rows"]) == 11
    assert parsed["at_a_glance_rows"][0] == {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "series_id": "ism_manufacturing_pmi",
        "label": "Manufacturing PMI",
        "current_value": 53.3,
        "previous_value": 54.0,
        "point_change": -0.7,
        "direction": "Growing",
        "rate_of_change": "Slower",
        "trend_months": 6,
        "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        "source_hash": parsed["report"]["source_hash"],
    }
    assert parsed["comments"] == [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "industry": "Chemical Products",
            "comment_index": 1,
            "comment_text": "Input costs remain elevated across key categories.",
            "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
            "source_hash": parsed["report"]["source_hash"],
            "source": "ISM official report",
        },
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "industry": "Machinery",
            "comment_index": 2,
            "comment_text": "Conditions are optimistic but not yet booming.",
            "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
            "source_hash": parsed["report"]["source_hash"],
            "source": "ISM official report",
        },
    ]


def test_parse_report_accepts_reporting_contraction_ranking_wording():
    html = REPORT_HTML.replace(
        "The three industries in contraction are: Paper Products; Furniture & Related Products; and Wood Products.",
        "The three industries reporting contraction in June are: Paper Products; Furniture & Related Products; and Wood Products.",
    )

    parsed = ism_official_report.parse_report(
        html,
        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        fetched_at="2026-07-14T10:00:00Z",
    )

    assert parsed["rankings"][-3:] == [
        {
            "date": "2026-06-01",
            "industry": "Paper Products",
            "direction": "contraction",
            "rank": -1,
            "source": "ISM official report",
        },
        {
            "date": "2026-06-01",
            "industry": "Furniture & Related Products",
            "direction": "contraction",
            "rank": -2,
            "source": "ISM official report",
        },
        {
            "date": "2026-06-01",
            "industry": "Wood Products",
            "direction": "contraction",
            "rank": -3,
            "source": "ISM official report",
        },
    ]


def test_parse_report_accepts_singular_contraction_ranking_wording():
    html = REPORT_HTML.replace(
        "The 14 manufacturing industries reporting growth in June",
        "The 16 manufacturing industries reporting growth in June",
    ).replace(
        "The three industries in contraction are: Paper Products; Furniture & Related Products; and Wood Products.",
        "The only industry reporting contraction in June is Wood Products.",
    )

    parsed = ism_official_report.parse_report(
        html,
        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        fetched_at="2026-07-14T10:00:00Z",
    )

    assert parsed["rankings"][-1] == {
        "date": "2026-06-01",
        "industry": "Wood Products",
        "direction": "contraction",
        "rank": -1,
        "source": "ISM official report",
    }


def test_parse_report_accepts_past_tense_single_contraction_wording():
    html = REPORT_HTML.replace(
        "The three industries in contraction are: Paper Products; Furniture & Related Products; and Wood Products.",
        "The only industry in contraction was Chemical Products.",
    )

    parsed = ism_official_report.parse_report(
        html,
        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        fetched_at="2026-07-14T10:00:00Z",
    )

    assert parsed["rankings"][-1] == {
        "date": "2026-06-01",
        "industry": "Chemical Products",
        "direction": "contraction",
        "rank": -1,
        "source": "ISM official report",
    }


def test_parse_report_accepts_same_at_a_glance_rate():
    html = REPORT_HTML.replace(
        "Manufacturing PMI® 53.3 54.0 -0.7 Growing Slower 6",
        "Manufacturing PMI® 52.7 52.7 0.0 Growing Same 4",
    )

    parsed = ism_official_report.parse_report(
        html,
        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/june/",
        fetched_at="2026-07-14T10:00:00Z",
    )

    assert parsed["at_a_glance_rows"][0]["direction"] == "Growing"
    assert parsed["at_a_glance_rows"][0]["rate_of_change"] == "Same"


PRNEWSWIRE_HTML = """
<html>
<body>
<nav>Send a Release</nav>
<article>
<h1>Manufacturing PMI® at 53.3%; June 2026 ISM® Manufacturing PMI® Report</h1>
<p>WHAT RESPONDENTS ARE SAYING</p>
<ul>
<li>"Demand remains uneven." [Machinery]</li>
</ul>
<p>MANUFACTURING AT A GLANCE</p>
<p>June 2026</p>
<p>Manufacturing PMI®</p><p>53.3</p><p>54.0</p><p>-0.7</p><p>Growing</p><p>Slower</p><p>6</p>
<p>New Orders</p><p>56.0</p><p>56.8</p><p>-0.8</p><p>Growing</p><p>Slower</p><p>6</p>
<p>Production</p><p>52.2</p><p>54.3</p><p>-2.1</p><p>Growing</p><p>Slower</p><p>8</p>
<p>Employment</p><p>49.7</p><p>48.6</p><p>+1.1</p><p>Contracting</p><p>Slower</p><p>33</p>
<p>Supplier Deliveries</p><p>57.4</p><p>60.6</p><p>-3.2</p><p>Slowing</p><p>Slower</p><p>7</p>
<p>Inventories</p><p>51.4</p><p>49.9</p><p>+1.5</p><p>Growing</p><p>From Contracting</p><p>1</p>
<p>Customers' Inventories</p><p>42.3</p><p>42.7</p><p>-0.4</p><p>Too Low</p><p>Faster</p><p>21</p>
<p>Prices</p><p>73.0</p><p>82.1</p><p>-9.1</p><p>Increasing</p><p>Slower</p><p>21</p>
<p>Backlog of Orders</p><p>50.5</p><p>52.2</p><p>-1.7</p><p>Growing</p><p>Slower</p><p>6</p>
<p>New Export Orders</p><p>48.5</p><p>50.6</p><p>-2.1</p><p>Contracting</p><p>From Growing</p><p>1</p>
<p>Imports</p><p>52.9</p><p>53.0</p><p>-0.1</p><p>Growing</p><p>Slower</p><p>5</p>
<p>The 14 manufacturing industries reporting growth in June — listed in order — are: Printing & Related Support Activities; Electrical Equipment, Appliances & Components; and Food, Beverage & Tobacco Products. The three industries in contraction are: Paper Products; Furniture & Related Products; and Wood Products.</p>
<p>The next ISM® Manufacturing PMI® Report featuring July 2026 data will be released at 10:00 a.m. ET on Monday, August 3, 2026.</p>
</article>
<footer>Contact PR Newswire</footer>
</body>
</html>
"""


HOSPITAL_HTML = """
<html><body>
<h1>June 2026 ISM Hospital PMI Report</h1>
<p>Hospital PMI at 52.0 percent.</p>
</body></html>
"""

GENERIC_ISM_HTML = """
<html><body>
<h1>ISM 2026 Annual Conference Announcement</h1>
<p>The Institute for Supply Management will hold its annual conference.</p>
</body></html>
"""


def test_parse_report_rejects_hospital_document():
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_official_report.parse_report(
            HOSPITAL_HTML,
            "https://example.com/hospital.html",
            "2026-07-15T10:00:00Z",
        )


def test_parse_report_rejects_generic_ism_release():
    with pytest.raises(ValueError, match="survey mismatch"):
        ism_official_report.parse_report(
            GENERIC_ISM_HTML,
            "https://example.com/generic.html",
            "2026-07-15T10:00:00Z",
        )


def test_parse_report_accepts_all_caps_marker():
    html = """
    <html><body>
    <h1>MANUFACTURING PMI AT 53.3%</h1>
    <h1>June 2026 ISM Manufacturing PMI Report</h1>
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
    <p>The 2 manufacturing industries reporting growth in June are: Chemical Products; and Machinery.</p>
    <p>The one industry reporting contraction in June is: Paper Products.</p>
    <p>The next ISM Manufacturing PMI Report featuring July 2026 data will be released at 10:00 a.m. ET on Monday, August 3, 2026.</p>
    </body></html>
    """
    parsed = ism_official_report.parse_report(
        html,
        "https://example.com/allcaps.html",
        "2026-07-15T10:00:00Z",
    )
    assert parsed["report"]["report_id"] == "ism_manufacturing_2026_06"


def test_parse_report_handles_prnewswire_article_body_table():
    parsed = ism_official_report.parse_report(
        PRNEWSWIRE_HTML,
        "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html",
        fetched_at="2026-07-15T10:00:00Z",
        source_name="prnewswire",
    )

    assert parsed["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert parsed["report"]["source_name"] == "prnewswire"
    assert parsed["metrics"]["ism_manufacturing_pmi"] == 53.3
    assert len(parsed["at_a_glance_rows"]) == 11
    assert parsed["at_a_glance_rows"][6]["direction"] == "Too Low"
    assert parsed["at_a_glance_rows"][6]["rate_of_change"] == "Faster"


def test_parse_report_extracts_prnewswire_straight_quote_comments():
    parsed = ism_official_report.parse_report(
        PRNEWSWIRE_HTML,
        "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html",
        fetched_at="2026-07-15T10:00:00Z",
        source_name="prnewswire",
    )

    assert parsed["comments"] == [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "industry": "Machinery",
            "comment_index": 1,
            "comment_text": "Demand remains uneven.",
            "source_url": "https://www.prnewswire.com/news-releases/manufacturing-pmi-at-53-3-june-2026-ism-manufacturing-pmi-report-302814991.html",
            "source_hash": parsed["report"]["source_hash"],
            "source": "ISM official report",
        }
    ]


def test_prepare_report_for_ai_validates_and_cleans_report_text():
    html = """
    <html>
      <head><title>Jan 2026 Manufacturing PMI® at 52.6%; January 2026 ISM® Manufacturing PMI® Report</title></head>
      <body>
        <nav>Subscribe Share Contact</nav>
        <article>
          <h1>Jan 2026 Manufacturing PMI® at 52.6%; January 2026 ISM® Manufacturing PMI® Report</h1>
          <p>The Manufacturing PMI® registered 52.6 percent in January.</p>
          <p>MANUFACTURING AT A GLANCE</p>
          <p>New Orders 55.1 53.2 +1.9 Growing Faster 2</p>
        </article>
        <footer>PR Newswire legal boilerplate</footer>
      </body>
    </html>
    """

    prepared = ism_official_report.prepare_report_for_ai(
        html,
        "https://example.com/january.html",
        "2026-07-15T00:00:00Z",
        source_name="prnewswire",
    )

    assert prepared["report_id"] == "ism_manufacturing_2026_01"
    assert prepared["report_month"] == "2026-01-01"
    assert "Manufacturing PMI" in prepared["report_text"]
    assert "PR Newswire legal boilerplate" not in prepared["report_text"]


def test_prepare_report_for_ai_removes_about_this_report_tail():
    html = """
    <html>
      <body>
        <article>
          <h1>Jan 2026 Manufacturing PMI® at 52.6%; January 2026 ISM® Manufacturing PMI® Report</h1>
          <p>The Manufacturing PMI® registered 52.6 percent in January.</p>
          <p>MANUFACTURING AT A GLANCE</p>
          <p>New Orders 55.1 53.2 +1.9 Growing Faster 2</p>
          <p>About This Report</p>
          <p>This monthly report is based on survey data and methodology notes.</p>
          <p>Contact: ISM Research Manager</p>
        </article>
      </body>
    </html>
    """

    prepared = ism_official_report.prepare_report_for_ai(
        html,
        "https://example.com/january.html",
        "2026-07-15T00:00:00Z",
        source_name="prnewswire",
    )

    assert "MANUFACTURING AT A GLANCE" in prepared["report_text"]
    assert "About This Report" not in prepared["report_text"]
    assert "methodology notes" not in prepared["report_text"]


def test_prepare_report_for_ai_removes_buying_policy_tail():
    html = """
    <html>
      <body>
        <article>
          <h1>Jan 2026 Manufacturing PMI® at 52.6%; January 2026 ISM® Manufacturing PMI® Report</h1>
          <p>The Manufacturing PMI® registered 52.6 percent in January.</p>
          <p>MANUFACTURING AT A GLANCE</p>
          <p>New Orders 55.1 53.2 +1.9 Growing Faster 2</p>
          <p>Buying Policy</p>
          <p>The average commitment lead time for Capital Expenditures was 172 days.</p>
          <p>Contact: ISM Research Manager</p>
        </article>
      </body>
    </html>
    """

    prepared = ism_official_report.prepare_report_for_ai(
        html,
        "https://example.com/january.html",
        "2026-07-15T00:00:00Z",
        source_name="prnewswire",
    )

    assert "MANUFACTURING AT A GLANCE" in prepared["report_text"]
    assert "Buying Policy" not in prepared["report_text"]
    assert "Capital Expenditures" not in prepared["report_text"]
