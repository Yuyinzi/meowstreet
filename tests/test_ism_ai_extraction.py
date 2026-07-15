import pytest

from app.tools import ism_ai_extraction


def valid_extraction():
    return {
        "report": {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Manufacturing PMI Report",
            "source_name": "prnewswire",
            "source_url": "https://example.com/report.html",
        },
        "at_a_glance_rows": [
            {
                "series_id": series_id,
                "label": label,
                "current_value": 50.0 + index,
                "previous_value": 49.0 + index,
                "point_change": 1.0,
                "direction": "Growing",
                "rate_of_change": "Faster",
                "trend_months": index + 1,
            }
            for index, (label, series_id) in enumerate(
                ism_ai_extraction.METRIC_LABEL_TO_SERIES_ID.items()
            )
        ],
        "industry_signals": [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Printing & Related Support Activities",
                "rank": 1,
                "evidence_text": "The 14 manufacturing industries reporting growth...",
            },
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "industry": "Primary Metals",
                "rank": 1,
                "evidence_text": "The 11 manufacturing industries that reported growth in new orders...",
            },
        ],
        "respondent_comments": [
            {
                "industry": "Chemical Products",
                "comment_text": "Input costs remain elevated.",
            }
        ],
        "commodities": [
            {
                "commodity": "Aluminum",
                "signal_type": "up_in_price",
                "months": 31,
            }
        ],
        "narrative_facts": {
            "manufacturing_gdp_share_contracted_percent": 5.0,
            "manufacturing_gdp_share_strong_contraction_percent": 3.0,
            "pmi_implied_real_gdp_annualized_percent": 2.0,
            "largest_industries_expanded": [
                "Computer & Electronic Products",
                "Machinery",
            ],
        },
    }


def test_validate_extraction_accepts_complete_payload():
    result = ism_ai_extraction.validate_extraction(valid_extraction())

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert len(result["at_a_glance_rows"]) == 11


def test_validate_extraction_rejects_missing_metric_rows():
    payload = valid_extraction()
    payload["at_a_glance_rows"] = payload["at_a_glance_rows"][:-1]

    with pytest.raises(ValueError, match="exactly 11"):
        ism_ai_extraction.validate_extraction(payload)


def test_validate_extraction_rejects_unknown_signal_type():
    payload = valid_extraction()
    payload["industry_signals"][0]["signal_type"] = "random_signal"

    with pytest.raises(ValueError, match="random_signal|Input should be"):
        ism_ai_extraction.validate_extraction(payload)


def test_build_prompt_requests_full_rich_extraction_schema():
    prompt = ism_ai_extraction.build_prompt("June 2026 ISM report text")

    assert "at_a_glance_rows" in prompt
    assert "industry_signals" in prompt
    assert "new_orders" in prompt
    assert "backlog" in prompt
    assert "respondent_comments" in prompt
    assert "Return only valid JSON" in prompt


def test_extract_with_client_validates_json_response():
    class FakeClient:
        def complete_json(self, prompt):
            payload = valid_extraction()
            return payload

    result = ism_ai_extraction.extract_with_client(
        "June 2026 ISM report text",
        FakeClient(),
    )

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
