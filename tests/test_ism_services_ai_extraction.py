import pytest
from pydantic import ValidationError

from pathlib import Path

from app.tools.ism_services_ai_extraction import (
    SERVICES_SERIES_IDS,
    SECTION_PROMPT_VERSIONS,
    FACTUAL_SECTION_NAMES,
    ServicesFactualExtractionModel,
    ServicesAtAGlanceRowModel,
    ServicesIndustrySignalModel,
    ServicesRespondentCommentModel,
    ServicesCommoditySignalModel,
    ServicesNarrativeFactsModel,
    validate_section_payload,
    assemble_factual_extraction,
    build_report_prompt,
    build_at_a_glance_prompt,
    build_industry_signals_prompt,
    build_comments_commodities_prompt,
    build_narrative_facts_prompt,
    BUILD_PROMPT_FOR_SECTION,
)
from app.tools.ism_services_report import (
    prepare_report_for_ai,
    _extract_at_a_glance_region,
    _extract_industry_signals_region,
    _extract_comments_commodities_region,
    _extract_narrative_region,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


SERVICES_COMPONENTS = {
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
}


def test_services_component_universe():
    assert SERVICES_SERIES_IDS == SERVICES_COMPONENTS
    assert len(SERVICES_SERIES_IDS) == 11


def test_section_prompt_versions_are_independent():
    assert SECTION_PROMPT_VERSIONS["report"] == "ism-services-report-v1"
    assert SECTION_PROMPT_VERSIONS["at_a_glance_rows"] == "ism-services-glance-v1"
    assert SECTION_PROMPT_VERSIONS["industry_signals"] == "ism-services-industries-v1"
    assert SECTION_PROMPT_VERSIONS["comments_commodities"] == "ism-services-comments-v1"
    assert SECTION_PROMPT_VERSIONS["narrative_facts"] == "ism-services-narrative-v1"
    versions = list(SECTION_PROMPT_VERSIONS.values())
    assert len(set(versions)) == 5


def test_factual_section_names():
    assert FACTUAL_SECTION_NAMES == [
        "report",
        "at_a_glance_rows",
        "industry_signals",
        "comments_commodities",
        "narrative_facts",
    ]


class TestAtAGlanceRowSchema:
    def test_valid_row(self):
        row = ServicesAtAGlanceRowModel(
            series_id="ism_services_pmi",
            label="Services PMI",
            current_value=54.0,
            previous_value=53.8,
            point_change=0.2,
            direction="Growing",
            rate_of_change="Faster",
            trend_months=2,
        )
        assert row.series_id == "ism_services_pmi"

    def test_rejects_extra_keys(self):
        with pytest.raises(ValidationError):
            ServicesAtAGlanceRowModel(
                series_id="ism_services_pmi",
                label="Services PMI",
                current_value=54.0,
                previous_value=53.8,
                point_change=0.2,
                direction="Growing",
                rate_of_change="Faster",
                trend_months=2,
                extra_key="bad",
            )

    def test_negative_trend_months_rejected(self):
        with pytest.raises(ValidationError):
            ServicesAtAGlanceRowModel(
                series_id="ism_services_pmi",
                label="Services PMI",
                current_value=54.0,
                previous_value=53.8,
                point_change=0.2,
                direction="Growing",
                rate_of_change="Faster",
                trend_months=-1,
            )


class TestIndustrySignalSchema:
    def test_valid_signal(self):
        signal = ServicesIndustrySignalModel(
            signal_type="overall_growth",
            direction="growth",
            industry="Construction",
            rank=1,
            source_excerpt="Construction reported growth.",
        )
        assert signal.industry == "Construction"

    def test_rejects_invalid_signal_type(self):
        with pytest.raises(ValidationError):
            ServicesIndustrySignalModel(
                signal_type="production",
                direction="growth",
                industry="Construction",
                rank=1,
                source_excerpt="test",
            )

    def test_rejects_invalid_direction(self):
        with pytest.raises(ValidationError):
            ServicesIndustrySignalModel(
                signal_type="overall_growth",
                direction="higher",
                industry="Construction",
                rank=1,
                source_excerpt="test",
            )


class TestRespondentCommentSchema:
    def test_valid_comment(self):
        comment = ServicesRespondentCommentModel(
            industry="Construction", comment_text="Pipeline remains healthy."
        )
        assert comment.industry == "Construction"

    def test_rejects_extra_keys(self):
        with pytest.raises(ValidationError):
            ServicesRespondentCommentModel(
                industry="Construction",
                comment_text="Pipeline remains healthy.",
                extra_field="bad",
            )


class TestCommoditySignalSchema:
    def test_valid_commodity(self):
        c = ServicesCommoditySignalModel(
            commodity="Construction Labor",
            signal_type="up_in_price",
            months=2,
        )
        assert c.commodity == "Construction Labor"

    def test_optional_months(self):
        c = ServicesCommoditySignalModel(
            commodity="Construction Labor",
            signal_type="up_in_price",
        )
        assert c.months is None

    def test_rejects_invalid_signal_type(self):
        with pytest.raises(ValidationError):
            ServicesCommoditySignalModel(
                commodity="Labor",
                signal_type="up",
            )


class TestNarrativeFactsSchema:
    def test_defaults(self):
        facts = ServicesNarrativeFactsModel()
        assert facts.consecutive_expansion_months is None
        assert facts.broad_based_expansion_mentioned is False
        assert facts.inflationary_pressure_mentioned is False

    def test_rejects_extra_keys(self):
        with pytest.raises(ValidationError):
            ServicesNarrativeFactsModel(invented_fact=True)


class TestFactualExtractionModel:
    def test_valid_full_payload(self):
        payload = _valid_factual_payload()
        model = ServicesFactualExtractionModel.model_validate(payload)
        assert model.report.report_id == "ism_services_2026_06"
        assert len(model.at_a_glance_rows) == 11

    def test_missing_component_rows_rejected(self):
        payload = _valid_factual_payload()
        payload["at_a_glance_rows"] = payload["at_a_glance_rows"][:5]
        with pytest.raises(ValidationError, match="11 rows"):
            ServicesFactualExtractionModel.model_validate(payload)

    def test_duplicate_component_rejected(self):
        payload = _valid_factual_payload()
        payload["at_a_glance_rows"].append(payload["at_a_glance_rows"][0])
        with pytest.raises(ValidationError):
            ServicesFactualExtractionModel.model_validate(payload)

    def test_extra_keys_rejected(self):
        payload = _valid_factual_payload()
        payload["extra_field"] = "bad"
        with pytest.raises(ValidationError):
            ServicesFactualExtractionModel.model_validate(payload)

    def test_non_services_report_id_rejected(self):
        payload = _valid_factual_payload()
        payload["report"]["report_id"] = "ism_manufacturing_2026_06"
        with pytest.raises(ValidationError):
            ServicesFactualExtractionModel.model_validate(payload)


class TestValidateSectionPayload:
    def test_valid_report_section(self):
        result = validate_section_payload(
            "report",
            {"report": _valid_report()},
            "ISM Services PMI Report for June 2026",
        )
        assert result["report"]["report_id"] == "ism_services_2026_06"

    def test_extra_keys_rejected(self):
        with pytest.raises(ValueError):
            validate_section_payload(
                "report",
                {"report": _valid_report(), "extra": "bad"},
                "ISM Services PMI Report for June 2026",
            )

    def test_unknown_section_raises(self):
        with pytest.raises(ValueError, match="unknown section"):
            validate_section_payload("unknown", {}, "")

    def test_source_grounding_excerpt_check(self):
        with pytest.raises(ValueError, match="source excerpt"):
            validate_section_payload(
                "industry_signals",
                {
                    "industry_signals": [
                        {
                            "signal_type": "overall_growth",
                            "direction": "growth",
                            "industry": "Construction",
                            "rank": 1,
                            "source_excerpt": "This sentence is not in the source.",
                        }
                    ]
                },
                "Some different source text here.",
            )


class TestAssembleFactualExtraction:
    def test_all_sections_assembles(self):
        section_payloads = _section_payloads()
        result = assemble_factual_extraction(section_payloads)
        assert result["report"]["report_id"] == "ism_services_2026_06"
        assert len(result["at_a_glance_rows"]) == 11

    def test_missing_section_raises(self):
        with pytest.raises(ValueError, match="missing factual sections"):
            assemble_factual_extraction([])

    def test_inconsistent_report_id_raises(self):
        section_payloads = _section_payloads()
        section_payloads[0]["payload"]["report"]["report_id"] = (
            "ism_manufacturing_2026_06"
        )
        with pytest.raises(ValueError, match="report_id must start with ism_services_"):
            assemble_factual_extraction(section_payloads)


class TestPromptBuilders:
    def test_report_prompt_contains_services_identity(self):
        prompt = build_report_prompt("June 2026 ISM Services PMI Report excerpt")
        assert "ism_services" in prompt
        assert "YYYY_MM" in prompt

    def test_at_a_glance_prompt_contains_all_components(self):
        prompt = build_at_a_glance_prompt("at a glance excerpt")
        for cid in SERVICES_COMPONENTS:
            assert cid in prompt

    def test_industry_signals_prompt_includes_allowed_types(self):
        prompt = build_industry_signals_prompt("industry excerpt")
        assert "overall_growth" in prompt
        assert "business_activity" in prompt
        assert "source_excerpt" in prompt
        assert "production" not in prompt

    def test_comments_commodities_prompt_has_both(self):
        prompt = build_comments_commodities_prompt("comments excerpt")
        assert "respondent_comments" in prompt
        assert "commodities" in prompt
        assert "up_in_price" in prompt
        assert "down_in_price" in prompt
        assert "short_supply" in prompt

    def test_narrative_facts_prompt_has_services_fields(self):
        prompt = build_narrative_facts_prompt("narrative excerpt")
        assert "consecutive_expansion_months" in prompt
        assert "services_economy_gdp_share_percent" in prompt
        assert "broad_based_expansion_mentioned" in prompt
        assert "inflationary_pressure_mentioned" in prompt

    def test_prompt_includes_excerpt_not_raw_html(self):
        excerpt = "June 2026 ISM Services PMI Report"
        prompt = build_report_prompt(excerpt)
        assert "raw html" not in prompt
        assert excerpt in prompt

    def test_prompt_only_owns_its_fields(self):
        prompt = build_report_prompt("excerpt")
        assert "at_a_glance_rows" not in prompt
        assert "industry_signals" not in prompt
        assert "respondent_comments" not in prompt
        assert "commodities" not in prompt
        prompt2 = build_at_a_glance_prompt("excerpt")
        assert "report_id" not in prompt2


def test_excerpt_budgets_are_within_limits():
    html = (FIXTURE_DIR / "ism_services_report.html").read_text()
    prepared = prepare_report_for_ai(
        html, "https://example.test/services/", "2026-07-03T14:00:00Z"
    )
    source_text = prepared["source_text"]
    cleaned_len = len(source_text)
    regions = {
        "report": source_text[:500],
        "at_a_glance_rows": _extract_at_a_glance_region(source_text),
        "industry_signals": _extract_industry_signals_region(source_text),
        "comments_commodities": _extract_comments_commodities_region(source_text),
        "narrative_facts": _extract_narrative_region(source_text),
    }
    for name, region_text in regions.items():
        region_len = len(region_text)
        assert region_len <= 0.6 * cleaned_len, (
            f"{name} excerpt is {region_len} chars ({region_len / cleaned_len:.1%}), "
            f"exceeds 60% of cleaned article ({cleaned_len} chars)"
        )
    total = sum(len(r) for r in regions.values())
    assert total <= 1.5 * cleaned_len, (
        f"total excerpt is {total} chars ({total / cleaned_len:.1%}), "
        f"exceeds 150% of cleaned article ({cleaned_len} chars)"
    )


def test_full_june_2026_services_payload():
    payload = {
        "report": {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_name": "ismworld",
            "source_url": "https://www.ismworld.org/services/june/",
        },
        "at_a_glance_rows": [
            {
                "series_id": sid,
                "label": sid.replace("ism_services_", "").replace("_", " ").title(),
                "current_value": 50.0 + i * 0.5,
                "previous_value": 49.0 + i * 0.5,
                "point_change": 1.0,
                "direction": "Growing",
                "rate_of_change": "Faster",
                "trend_months": 1,
            }
            for i, sid in enumerate(sorted(SERVICES_COMPONENTS))
        ],
        "industry_signals": [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Construction",
                "rank": 1,
                "source_excerpt": "The 12 services industries reporting growth in June are",
            },
            {
                "signal_type": "overall_contraction",
                "direction": "contraction",
                "industry": "Educational Services",
                "rank": 1,
                "source_excerpt": "The 5 services industries reporting contraction in June are",
            },
        ],
        "respondent_comments": [
            {"industry": "Construction", "comment_text": "Pipeline remains healthy."},
        ],
        "commodities": [
            {
                "commodity": "Construction Labor",
                "signal_type": "up_in_price",
                "months": 2,
            },
            {
                "commodity": "Diesel Fuel",
                "signal_type": "down_in_price",
                "months": None,
            },
            {
                "commodity": "Electrical Components",
                "signal_type": "short_supply",
                "months": 3,
            },
        ],
        "narrative_facts": {
            "consecutive_expansion_months": 6,
            "services_economy_gdp_share_percent": None,
            "broad_based_expansion_mentioned": True,
            "inflationary_pressure_mentioned": True,
        },
    }
    validated = ServicesFactualExtractionModel.model_validate(payload)
    dumped = validated.model_dump()
    assert dumped["report"]["report_id"] == "ism_services_2026_06"
    assert len(dumped["at_a_glance_rows"]) == 11
    assert len(dumped["commodities"]) == 3


def _valid_report():
    return {
        "report_id": "ism_services_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Services PMI Report",
        "source_name": "ismworld",
        "source_url": "https://www.ismworld.org/services/june/",
    }


def _valid_at_a_glance_rows():
    return [
        {
            "series_id": sid,
            "label": sid.replace("ism_services_", "").replace("_", " ").title(),
            "current_value": 50.0 + i,
            "previous_value": 49.0 + i,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        }
        for i, sid in enumerate(sorted(SERVICES_COMPONENTS))
    ]


def _valid_factual_payload():
    return {
        "report": _valid_report(),
        "at_a_glance_rows": _valid_at_a_glance_rows(),
        "industry_signals": [],
        "respondent_comments": [],
        "commodities": [],
        "narrative_facts": {
            "consecutive_expansion_months": None,
            "services_economy_gdp_share_percent": None,
            "broad_based_expansion_mentioned": False,
            "inflationary_pressure_mentioned": False,
        },
    }


def _section_payloads():
    return [
        {"section_name": "report", "payload": {"report": _valid_report()}},
        {
            "section_name": "at_a_glance_rows",
            "payload": {"at_a_glance_rows": _valid_at_a_glance_rows()},
        },
        {"section_name": "industry_signals", "payload": {"industry_signals": []}},
        {
            "section_name": "comments_commodities",
            "payload": {"respondent_comments": [], "commodities": []},
        },
        {
            "section_name": "narrative_facts",
            "payload": {
                "narrative_facts": {
                    "consecutive_expansion_months": None,
                    "services_economy_gdp_share_percent": None,
                    "broad_based_expansion_mentioned": False,
                    "inflationary_pressure_mentioned": False,
                }
            },
        },
    ]
