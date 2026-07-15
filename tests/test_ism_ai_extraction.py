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
        "ai_summary": {
            "compared_to_report_month": "2026-05-01",
            "headline_changes": [
                {
                    "label": "Headline PMI",
                    "series_id": "ism_manufacturing_pmi",
                    "point_change": 1.3,
                }
            ],
            "major_changes": [
                "Transportation Equipment moved into expansion.",
            ],
            "summary_text": "Compared with May, Headline PMI rose 1.3 points.",
        },
    }


def valid_report_text():
    return """
    June 2026 ISM Manufacturing PMI Report.
    WHAT RESPONDENTS ARE SAYING
    "Input costs remain elevated." [Chemical Products]
    MANUFACTURING AT A GLANCE
    Metric table.
    COMMODITIES REPORTED UP/DOWN IN PRICE AND IN SHORT SUPPLY
    Aluminum is up in price.
    JUNE 2026 MANUFACTURING INDEX SUMMARIES
    Manufacturing PMI text. New Orders text.
    """


def test_validate_extraction_accepts_complete_payload():
    result = ism_ai_extraction.validate_extraction(valid_extraction())

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"


def test_validate_extraction_accepts_month_over_month_summary():
    payload = valid_extraction()
    payload["ai_summary"] = {
        "compared_to_report_month": "2026-05-01",
        "headline_changes": [
            {
                "label": "Headline PMI",
                "series_id": "ism_manufacturing_pmi",
                "point_change": 1.3,
            },
            {
                "label": "New Orders",
                "series_id": "ism_manufacturing_new_orders",
                "point_change": 2.4,
            },
        ],
        "major_changes": [
            "Transportation Equipment moved into expansion.",
            "Steel was added to commodities up in price.",
            "Supplier delivery delays increased.",
        ],
        "summary_text": (
            "Compared with May, Headline PMI rose 1.3 points, New Orders rose "
            "2.4 points, Production rose 1.8 points, and Prices fell 0.6 points. "
            "Major changes: Transportation Equipment moved into expansion; Steel "
            "was added to commodities up in price; Supplier delivery delays increased."
        ),
    }

    result = ism_ai_extraction.validate_extraction(payload)

    assert result["ai_summary"]["compared_to_report_month"] == "2026-05-01"
    assert result["ai_summary"]["headline_changes"][0]["point_change"] == 1.3
    assert "Supplier delivery delays increased" in result["ai_summary"]["summary_text"]


def test_validate_extraction_normalizes_summary_comparison_to_previous_month():
    payload = valid_extraction()
    payload["report"]["report_id"] = "ism_manufacturing_2026_01"
    payload["report"]["report_month"] = "2026-01-01"
    payload["ai_summary"]["compared_to_report_month"] = "2026-01-01"

    result = ism_ai_extraction.validate_extraction(payload)

    assert result["ai_summary"]["compared_to_report_month"] == "2025-12-01"


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
    payload = valid_extraction()

    class FakeClient:
        def complete_json(self, prompt):
            if "Extract only report metadata" in prompt:
                return {"report": payload["report"]}
            if "Extract only MANUFACTURING AT A GLANCE" in prompt:
                return {"at_a_glance_rows": payload["at_a_glance_rows"]}
            if "Extract only industry signal lists" in prompt:
                return {"industry_signals": payload["industry_signals"]}
            if "Extract only respondent comments and commodities" in prompt:
                return {
                    "respondent_comments": payload["respondent_comments"],
                    "commodities": payload["commodities"],
                }
            if "Extract only narrative facts and AI summary" in prompt:
                return {
                    "narrative_facts": payload["narrative_facts"],
                    "ai_summary": payload["ai_summary"],
                }
            raise AssertionError(prompt)

    result = ism_ai_extraction.extract_with_client(
        valid_report_text(),
        FakeClient(),
    )

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"


def test_extract_with_client_repairs_invalid_schema_response():
    prompts = []

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def complete_json(self, prompt):
            prompts.append(prompt)
            self.calls += 1
            if self.calls == 1:
                return {
                    "report": "June 2026 ISM Manufacturing PMI Report",
                    "at_a_glance_rows": [],
                }
            return valid_extraction()

    client = FakeClient()

    result = ism_ai_extraction.extract_single_payload_with_client(
        "June 2026 ISM report text",
        client,
    )

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert client.calls == 2
    assert "Your previous JSON failed schema validation" in prompts[1]
    assert "report must be an object" in prompts[1]
    assert "at_a_glance_rows must contain exactly 11 rows" in prompts[1]


def test_extract_with_client_uses_split_section_prompts():
    prompts = []
    payload = valid_extraction()

    class FakeClient:
        def complete_json(self, prompt):
            prompts.append(prompt)
            if "Extract only report metadata" in prompt:
                return {"report": payload["report"]}
            if "Extract only MANUFACTURING AT A GLANCE" in prompt:
                return {"at_a_glance_rows": payload["at_a_glance_rows"]}
            if "Extract only industry signal lists" in prompt:
                return {"industry_signals": payload["industry_signals"]}
            if "Extract only respondent comments and commodities" in prompt:
                return {
                    "respondent_comments": payload["respondent_comments"],
                    "commodities": payload["commodities"],
                }
            if "Extract only narrative facts and AI summary" in prompt:
                return {
                    "narrative_facts": payload["narrative_facts"],
                    "ai_summary": payload["ai_summary"],
                }
            raise AssertionError(prompt)

    result = ism_ai_extraction.extract_with_client(
        valid_report_text(),
        FakeClient(),
    )

    assert result == payload
    assert len(prompts) == 5
    assert all("Return only valid JSON" in prompt for prompt in prompts)


def test_extract_with_client_repairs_invalid_split_section():
    prompts = []
    payload = valid_extraction()

    class FakeClient:
        def __init__(self):
            self.at_a_glance_calls = 0

        def complete_json(self, prompt):
            prompts.append(prompt)
            if "Extract only report metadata" in prompt:
                return {"report": payload["report"]}
            if "Extract only MANUFACTURING AT A GLANCE" in prompt:
                self.at_a_glance_calls += 1
                if self.at_a_glance_calls == 1:
                    return {
                        "at_a_glance_rows": [
                            {"index_name": "Manufacturing PMI", "jan": 52.6}
                        ]
                    }
                return {"at_a_glance_rows": payload["at_a_glance_rows"]}
            if "Extract only industry signal lists" in prompt:
                return {"industry_signals": payload["industry_signals"]}
            if "Extract only respondent comments and commodities" in prompt:
                return {
                    "respondent_comments": payload["respondent_comments"],
                    "commodities": payload["commodities"],
                }
            if "Extract only narrative facts and AI summary" in prompt:
                return {
                    "narrative_facts": payload["narrative_facts"],
                    "ai_summary": payload["ai_summary"],
                }
            raise AssertionError(prompt)

    result = ism_ai_extraction.extract_with_client(
        valid_report_text(),
        FakeClient(),
    )

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert any("Your previous JSON failed schema validation" in p for p in prompts)


def test_extract_with_client_repairs_comment_text_not_found_in_source():
    prompts = []
    payload = valid_extraction()

    class FakeClient:
        def __init__(self):
            self.comment_calls = 0

        def complete_json(self, prompt):
            prompts.append(prompt)
            if "Extract only report metadata" in prompt:
                return {"report": payload["report"]}
            if "Extract only MANUFACTURING AT A GLANCE" in prompt:
                return {"at_a_glance_rows": payload["at_a_glance_rows"]}
            if "Extract only industry signal lists" in prompt:
                return {"industry_signals": payload["industry_signals"]}
            if "Extract only respondent comments and commodities" in prompt:
                self.comment_calls += 1
                if self.comment_calls == 1:
                    return {
                        "respondent_comments": [
                            {
                                "industry": "Chemical Products",
                                "comment_text": "This comment is not in the report.",
                            }
                        ],
                        "commodities": payload["commodities"],
                    }
                return {
                    "respondent_comments": payload["respondent_comments"],
                    "commodities": payload["commodities"],
                }
            if "Extract only narrative facts and AI summary" in prompt:
                return {
                    "narrative_facts": payload["narrative_facts"],
                    "ai_summary": payload["ai_summary"],
                }
            raise AssertionError(prompt)

    client = FakeClient()

    result = ism_ai_extraction.extract_with_client(valid_report_text(), client)

    assert result["respondent_comments"][0]["comment_text"] == (
        "Input costs remain elevated."
    )
    assert client.comment_calls == 2
    assert any("respondent comment text is not present in source" in p for p in prompts)


def test_report_section_texts_reduce_each_prompt_to_relevant_slice():
    report_text = """
    Intro headline and PMI details.
    WHAT RESPONDENTS ARE SAYING
    "Comment one" [Machinery]
    MANUFACTURING AT A GLANCE
    New Orders 57.1 47.4 +9.7 Growing Faster 1
    COMMODITIES REPORTED UP/DOWN IN PRICE AND IN SHORT SUPPLY
    Commodities Up in Price Steel.
    JANUARY 2026 MANUFACTURING INDEX SUMMARIES
    Manufacturing PMI text. New Orders text.
    Buying Policy
    Non-core lead time details.
    """

    sections = ism_ai_extraction.report_section_texts(report_text)

    assert "Intro headline" in sections["report"]
    assert "WHAT RESPONDENTS" not in sections["report"]
    assert "MANUFACTURING AT A GLANCE" in sections["at_a_glance_rows"]
    assert "COMMODITIES REPORTED" not in sections["at_a_glance_rows"]
    assert "New Orders text" in sections["industry_signals"]
    assert "Comment one" in sections["comments_commodities"]
    assert "Commodities Up in Price Steel" in sections["comments_commodities"]
    assert "Non-core lead time details" not in sections["narrative_summary"]


def test_build_prompt_requests_summary_with_major_changes():
    prompt = ism_ai_extraction.build_prompt("June 2026 ISM report text")

    assert "ai_summary" in prompt
    assert "Compared with" in prompt
    assert "Headline PMI" in prompt
    assert "New Orders" in prompt
    assert "major_changes" in prompt
    assert "Do not invent changes" in prompt
