from app.tools import ism_services_report


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


def test_parse_report_extracts_operational_metrics_and_evidence():
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
