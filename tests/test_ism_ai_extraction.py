import asyncio

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
                "evidence_text": "The one manufacturing industry reporting growth is Printing & Related Support Activities.",
            },
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "industry": "Primary Metals",
                "rank": 1,
                "evidence_text": "The one manufacturing industry that reported growth in new orders is Primary Metals.",
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
                    "point_change": 1.0,
                }
            ],
            "major_changes": [
                "Primary Metals moved into expansion.",
            ],
            "major_changes_zh": ["Primary Metals进入扩张。"],
            "summary_text": "Compared with May, Headline PMI rose 1.0 points.",
            "summary_text_zh": "PMI较上月改善。",
            "cat_takeaway_en": "Caicai, the Meowstreet trader cat, sees demand returning like a fish stall getting fresh orders.",
            "cat_takeaway_zh": "财财这只Meowstreet交易猫看到需求回来了，就像鱼摊又接到新订单。",
        },
    }


def valid_report_text():
    return """
    June 2026 ISM Manufacturing PMI Report.
    The one manufacturing industry reporting growth is Printing & Related Support Activities.
    WHAT RESPONDENTS ARE SAYING
    "Input costs remain elevated." [Chemical Products]
    MANUFACTURING AT A GLANCE
    Metric table.
    COMMODITIES REPORTED UP/DOWN IN PRICE AND IN SHORT SUPPLY
    Aluminum is up in price.
    JUNE 2026 MANUFACTURING INDEX SUMMARIES
    Manufacturing PMI text.
    The one manufacturing industry that reported growth in new orders is Primary Metals.
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
            "Primary Metals moved into expansion.",
            "Aluminum is up in price.",
            "Printing & Related Support Activities reported growth.",
        ],
        "summary_text": (
            "Compared with May, Headline PMI rose 1.3 points, New Orders rose "
            "2.4 points, Production rose 1.8 points, and Prices fell 0.6 points. "
            "Major changes: Primary Metals moved into expansion; Aluminum "
            "is up in price; Printing & Related Support Activities reported growth."
        ),
    }

    result = ism_ai_extraction.validate_extraction(payload)

    assert result["ai_summary"]["compared_to_report_month"] == "2026-05-01"
    assert result["ai_summary"]["headline_changes"][0]["point_change"] == 1.3
    assert "Primary Metals moved into expansion" in result["ai_summary"]["summary_text"]


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
            if "Extract only narrative facts from" in prompt:
                return {"narrative_facts": payload["narrative_facts"]}
            if "Summarize only the validated ISM Manufacturing facts" in prompt:
                return {
                    "summary_text": payload["ai_summary"]["summary_text"],
                    "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                    "headline_changes": payload["ai_summary"]["headline_changes"],
                    "major_changes": payload["ai_summary"]["major_changes"],
                    "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                    "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                    "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
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
            if "Extract only narrative facts from" in prompt:
                return {"narrative_facts": payload["narrative_facts"]}
            if "Summarize only the validated ISM Manufacturing facts" in prompt:
                return {
                    "summary_text": payload["ai_summary"]["summary_text"],
                    "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                    "headline_changes": payload["ai_summary"]["headline_changes"],
                    "major_changes": payload["ai_summary"]["major_changes"],
                    "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                    "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                    "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
                }
            raise AssertionError(prompt)

    result = ism_ai_extraction.extract_with_client(
        valid_report_text(),
        FakeClient(),
    )

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert "ai_summary" in result
    assert len(prompts) == 6
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
            if "Extract only narrative facts from" in prompt:
                return {"narrative_facts": payload["narrative_facts"]}
            if "Summarize only the validated ISM Manufacturing facts" in prompt:
                return {
                    "summary_text": payload["ai_summary"]["summary_text"],
                    "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                    "headline_changes": payload["ai_summary"]["headline_changes"],
                    "major_changes": payload["ai_summary"]["major_changes"],
                    "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                    "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                    "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
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
            if "Extract only narrative facts from" in prompt:
                return {"narrative_facts": payload["narrative_facts"]}
            if "Summarize only the validated ISM Manufacturing facts" in prompt:
                return {
                    "summary_text": payload["ai_summary"]["summary_text"],
                    "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                    "headline_changes": payload["ai_summary"]["headline_changes"],
                    "major_changes": payload["ai_summary"]["major_changes"],
                    "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                    "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                    "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
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
    Manufacturing PMI text. New Orders industries text.
    Buying Policy
    Non-core lead time details.
    """

    sections = ism_ai_extraction.report_section_texts(report_text)

    assert "Intro headline" in sections["report"]
    assert "WHAT RESPONDENTS" not in sections["report"]
    assert "MANUFACTURING AT A GLANCE" in sections["at_a_glance_rows"]
    assert "COMMODITIES REPORTED" not in sections["at_a_glance_rows"]
    assert "New Orders industries text" in sections["industry_signals"]
    assert "Comment one" in sections["comments_commodities"]
    assert "Commodities Up in Price Steel" in sections["comments_commodities"]
    assert "Non-core lead time details" not in sections["narrative_facts"]


def test_report_section_texts_include_comprehensive_overall_industry_list():
    report_text = """
    June 2026 ISM Manufacturing PMI Report.
    Five of the six largest manufacturing industries expanded in June.
    The 14 manufacturing industries reporting growth in June, listed in order, are:
    Printing & Related Support Activities; Machinery; and Chemical Products.
    WHAT RESPONDENTS ARE SAYING
    MANUFACTURING AT A GLANCE
    MANUFACTURING INDEX SUMMARIES
    New Orders industries text.
    """

    sections = ism_ai_extraction.report_section_texts(report_text)

    assert "The 14 manufacturing industries" in sections["industry_signals"]
    assert "Five of the six largest" not in sections["industry_signals"]
    assert "New Orders industries text" in sections["industry_signals"]


def test_report_section_texts_remove_non_industry_index_narrative():
    report_text = """
    June 2026 ISM Manufacturing PMI Report.
    WHAT RESPONDENTS ARE SAYING
    MANUFACTURING AT A GLANCE
    MANUFACTURING INDEX SUMMARIES
    New Orders expanded to 56 percent and remained above its historical threshold.
    The two industries reporting growth in new orders are: Machinery; and Primary Metals.
    New Orders 22.3 64.3 13.4 56.0
    Buying Policy
    """

    section = ism_ai_extraction.report_section_texts(report_text)["industry_signals"]

    assert "two industries reporting growth" in section
    assert "historical threshold" not in section
    assert "22.3 64.3" not in section


def test_industry_signal_validation_rejects_partial_overall_growth_list():
    evidence = (
        "Five of the six largest manufacturing industries expanded in June, "
        "with Petroleum & Coal Products the exception."
    )
    report_text = f"""
    {evidence}
    The 14 manufacturing industries reporting growth in June, listed in order,
    are: Printing & Related Support Activities; Machinery; and Chemical Products.
    """
    payload = {
        "industry_signals": [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": industry,
                "rank": rank,
                "evidence_text": evidence,
            }
            for rank, industry in enumerate(
                [
                    "Computer & Electronic Products",
                    "Machinery",
                    "Transportation Equipment",
                    "Chemical Products",
                    "Food, Beverage & Tobacco Products",
                ],
                start=1,
            )
        ]
    }

    with pytest.raises(ValueError, match="must contain 14 industries"):
        ism_ai_extraction._validate_industry_signals_against_source(
            payload,
            report_text,
        )


def test_industry_signal_validation_rejects_partial_subindex_list():
    evidence = (
        "The 11 manufacturing industries that reported growth in new orders "
        "are: Primary Metals; Machinery; and Chemical Products."
    )
    payload = {
        "industry_signals": [
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "industry": industry,
                "rank": rank,
                "evidence_text": evidence,
            }
            for rank, industry in enumerate(
                ["Primary Metals", "Machinery", "Chemical Products"],
                start=1,
            )
        ]
    }

    with pytest.raises(ValueError, match="must contain 11 industries"):
        ism_ai_extraction._validate_industry_signals_against_source(
            payload,
            evidence,
        )


def test_industry_signal_validation_uses_reported_subset_not_industry_universe():
    evidence = (
        "Of the 18 manufacturing industries, nine reported employment growth "
        "in June, in the following order: Printing; Paper; Primary Metals; "
        "Electrical Equipment; Plastics; Machinery; Miscellaneous Manufacturing; "
        "Transportation Equipment; and Chemical Products."
    )
    industries = [
        "Printing",
        "Paper",
        "Primary Metals",
        "Electrical Equipment",
        "Plastics",
        "Machinery",
        "Miscellaneous Manufacturing",
        "Transportation Equipment",
        "Chemical Products",
    ]
    payload = {
        "industry_signals": [
            {
                "signal_type": "employment",
                "direction": "growth",
                "industry": industry,
                "rank": rank,
                "evidence_text": evidence,
            }
            for rank, industry in enumerate(industries, start=1)
        ]
    }

    ism_ai_extraction._validate_industry_signals_against_source(payload, evidence)


def test_industry_signal_validation_uses_subset_without_manufacturing_qualifier():
    evidence = (
        "Of the 18 industries, 16 reported slower supplier deliveries in May, "
        "listed in the following order: Industry 1; Industry 2; Industry 3; "
        "Industry 4; Industry 5; Industry 6; Industry 7; Industry 8; "
        "Industry 9; Industry 10; Industry 11; Industry 12; Industry 13; "
        "Industry 14; Industry 15; and Industry 16."
    )
    payload = {
        "industry_signals": [
            {
                "signal_type": "supplier_deliveries",
                "direction": "slower",
                "industry": f"Industry {rank}",
                "rank": rank,
                "evidence_text": evidence,
            }
            for rank in range(1, 17)
        ]
    }

    ism_ai_extraction._validate_industry_signals_against_source(payload, evidence)


def test_grouped_industry_signal_normalizes_historical_growth_directions():
    result = ism_ai_extraction.IndustrySignalsSectionModel.model_validate(
        {
            "industry_signal_lists": [
                {
                    "signal_type": "backlog",
                    "direction": "growth",
                    "industries": ["Machinery"],
                    "evidence_text": (
                        "The industry reporting growth in order backlogs is "
                        "Machinery."
                    ),
                },
                {
                    "signal_type": "imports",
                    "direction": "decrease",
                    "industries": ["Primary Metals"],
                    "evidence_text": (
                        "The industry reporting a decrease in imports is "
                        "Primary Metals."
                    ),
                },
            ]
        }
    ).model_dump()

    assert result["industry_signal_lists"][0]["direction"] == "higher"
    assert result["industry_signal_lists"][1]["direction"] == "lower"


def test_grouped_industry_signal_accepts_explicit_empty_source_list():
    result = ism_ai_extraction.IndustrySignalsSectionModel.model_validate(
        {
            "industry_signal_lists": [
                {
                    "signal_type": "supplier_deliveries",
                    "direction": "faster",
                    "industries": [],
                    "evidence_text": (
                        "No industries reported faster supplier deliveries in October."
                    ),
                }
            ]
        }
    ).model_dump()

    assert result["industry_signal_lists"][0]["industries"] == []


def test_validate_factual_extraction_accepts_payload_without_summary():
    payload = valid_extraction()
    payload.pop("ai_summary")

    result = ism_ai_extraction.validate_factual_extraction(payload)

    assert result["report"]["report_id"] == "ism_manufacturing_2026_06"
    assert "ai_summary" not in result


def test_build_prompt_requests_summary_with_major_changes():
    prompt = ism_ai_extraction.build_prompt("June 2026 ISM report text")

    assert "ai_summary" in prompt
    assert "Compared with" in prompt
    assert "Headline PMI" in prompt
    assert "New Orders" in prompt
    assert "major_changes" in prompt
    assert "Do not invent changes" in prompt


def test_build_industry_signals_prompt_requests_grouped_lists():
    prompt = ism_ai_extraction.build_industry_signals_prompt("industry text")

    assert '"industry_signal_lists"' in prompt
    assert '"industries": ["Machinery", "Chemical Products"]' in prompt
    assert "do not add rank fields" in prompt


def test_extract_section_expands_grouped_industry_lists_to_flat_rows():
    evidence = (
        "The two manufacturing industries reporting growth are: Machinery; "
        "and Chemical Products."
    )
    report_text = f"""
    June 2026 ISM Manufacturing PMI Report.
    {evidence}
    WHAT RESPONDENTS ARE SAYING
    MANUFACTURING AT A GLANCE
    MANUFACTURING INDEX SUMMARIES
    """
    section_name, section_text, prompt, model = (
        ism_ai_extraction.factual_section_definition(
            "industry_signals",
            report_text,
        )
    )

    class FakeClient:
        def complete_json(self, prompt):
            return {
                "industry_signal_lists": [
                    {
                        "signal_type": "overall_growth",
                        "direction": "growth",
                        "industries": ["Machinery", "Chemical Products"],
                        "evidence_text": evidence,
                    }
                ]
            }

    result = ism_ai_extraction.extract_section_with_client(
        section_text,
        FakeClient(),
        section_name,
        prompt,
        model,
    )

    assert result == {
        "industry_signals": [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Machinery",
                "rank": 1,
                "evidence_text": evidence,
            },
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Chemical Products",
                "rank": 2,
                "evidence_text": evidence,
            },
        ]
    }
@pytest.mark.asyncio
async def test_extract_factual_with_client_async_runs_sections_with_concurrency_limit():
    payload = valid_extraction()
    payload.pop("ai_summary")

    class AsyncFakeClient:
        def __init__(self):
            self.active = 0
            self.max_seen = 0
            self.calls = []

        async def complete_json_async(self, prompt):
            self.active += 1
            self.max_seen = max(self.max_seen, self.active)
            try:
                await asyncio.sleep(0.01)
                self.calls.append(prompt)
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
                if "Extract only narrative facts" in prompt:
                    return {"narrative_facts": payload["narrative_facts"]}
                raise AssertionError(prompt)
            finally:
                self.active -= 1

    client = AsyncFakeClient()

    result = await ism_ai_extraction.extract_factual_with_client_async(
        valid_report_text(),
        client,
    )

    assert result == payload
    assert len(client.calls) == 5
    assert client.max_seen == 3


def test_build_validated_summary_prompt_uses_structured_payload_not_raw_report_text():
    factual = valid_extraction()
    factual.pop("ai_summary")

    prompt = ism_ai_extraction.build_validated_summary_prompt(factual)

    assert "Summarize only the validated ISM Manufacturing facts" in prompt
    assert "at_a_glance_rows" in prompt
    assert "industry_signals" in prompt
    assert "respondent_comments" in prompt
    assert "June 2026 ISM report text" not in prompt


def test_validate_summary_rejects_headline_change_that_does_not_match_facts():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary["headline_changes"][0]["point_change"] = 99.0

    with pytest.raises(ValueError, match="summary headline change does not match"):
        ism_ai_extraction.validate_summary_against_facts(summary, factual)


def test_validate_summary_rejects_major_change_not_grounded_in_facts():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary["major_changes"] = ["This change references nothing in the data."]

    with pytest.raises(ValueError, match="summary major_change is not grounded"):
        ism_ai_extraction.validate_summary_against_facts(summary, factual)


def test_validate_summary_accepts_major_change_grounded_in_narrative_facts():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary["major_changes"] = [
        "Five of the six largest manufacturing industries reported growth."
    ]

    result = ism_ai_extraction.validate_summary_against_facts(summary, factual)

    assert result["major_changes"] == summary["major_changes"]


def test_validate_summary_accepts_major_change_grounded_in_respondent_comments():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary["major_changes"] = ["Respondents said input costs remain elevated."]

    result = ism_ai_extraction.validate_summary_against_facts(summary, factual)

    assert result["major_changes"] == summary["major_changes"]


def test_validate_summary_rejects_summary_text_missing_headline_label():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary["summary_text"] = "Some text that does not include the label."

    with pytest.raises(ValueError, match="summary text does not mention headline"):
        ism_ai_extraction.validate_summary_against_facts(summary, factual)


def test_validate_summary_accepts_summary_text_with_metric_label_alias():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary["headline_changes"][0]["label"] = "Headline PMI"
    summary["summary_text"] = "Manufacturing PMI rose from the prior month."

    result = ism_ai_extraction.validate_summary_against_facts(summary, factual)

    assert result["summary_text"] == summary["summary_text"]


def test_validate_summary_accepts_bilingual_cat_fields():
    factual = valid_extraction()
    factual.pop("ai_summary")
    summary = valid_extraction()["ai_summary"]
    summary.update(
        {
            "summary_text_zh": "制造业PMI改善，新订单和生产都在扩张。",
            "major_changes_zh": ["新订单明显改善。"],
            "cat_takeaway_en": (
                "Caicai, the Meowstreet trader cat, sees factories restocking "
                "like a fish stall preparing for a busy morning."
            ),
            "cat_takeaway_zh": "财财这只Meowstreet交易猫看到工厂像鱼摊备货一样，准备迎接更忙的早市。",
        }
    )

    result = ism_ai_extraction.validate_summary_against_facts(summary, factual)

    assert result["summary_text_zh"]
    assert result["cat_takeaway_en"].startswith("Caicai")
    assert result["cat_takeaway_zh"].startswith("财财")


@pytest.mark.asyncio
async def test_extract_with_client_async_extracts_facts_then_summarizes_validated_payload():
    payload = valid_extraction()
    seen = {}

    class AsyncFakeClient:
        async def complete_json_async(self, prompt):
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
            if "Extract only narrative facts" in prompt:
                return {"narrative_facts": payload["narrative_facts"]}
            if "Summarize only the validated ISM Manufacturing facts" in prompt:
                seen["summary_prompt"] = prompt
                return {
                    "summary_text": payload["ai_summary"]["summary_text"],
                    "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                    "headline_changes": payload["ai_summary"]["headline_changes"],
                    "major_changes": payload["ai_summary"]["major_changes"],
                    "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                    "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                    "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
                }
            raise AssertionError(prompt)

    result = await ism_ai_extraction.extract_with_client_async(
        valid_report_text(),
        AsyncFakeClient(),
    )

    assert result == payload
    assert "June 2026 ISM report text" not in seen["summary_prompt"]
    assert "at_a_glance_rows" in seen["summary_prompt"]


def test_assemble_factual_payload_from_sections_validates_complete_set():
    payload = valid_extraction()
    factual = {key: value for key, value in payload.items() if key != "ai_summary"}
    sections = [
        {"section_name": "report", "payload_json": {"report": factual["report"]}},
        {
            "section_name": "at_a_glance_rows",
            "payload_json": {"at_a_glance_rows": factual["at_a_glance_rows"]},
        },
        {
            "section_name": "industry_signals",
            "payload_json": {"industry_signals": factual["industry_signals"]},
        },
        {
            "section_name": "comments_commodities",
            "payload_json": {
                "respondent_comments": factual["respondent_comments"],
                "commodities": factual["commodities"],
            },
        },
        {
            "section_name": "narrative_facts",
            "payload_json": {"narrative_facts": factual["narrative_facts"]},
        },
    ]

    result = ism_ai_extraction.assemble_factual_payload_from_sections(sections)

    assert result == factual


def test_assemble_factual_payload_from_sections_rejects_missing_section():
    payload = valid_extraction()
    sections = [
        {"section_name": "report", "payload_json": {"report": payload["report"]}},
    ]

    with pytest.raises(ValueError, match="missing factual sections"):
        ism_ai_extraction.assemble_factual_payload_from_sections(sections)


def test_facts_hash_is_stable_for_same_payload():
    payload = valid_extraction()
    factual = {key: value for key, value in payload.items() if key != "ai_summary"}

    first = ism_ai_extraction.facts_hash(factual)
    second = ism_ai_extraction.facts_hash(dict(reversed(list(factual.items()))))

    assert first == second
    assert len(first) == 64
