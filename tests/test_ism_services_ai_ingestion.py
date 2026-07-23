import json
import re
from copy import deepcopy
import sqlite3
from pathlib import Path

import pytest

from app.db import growth_cycle, us_rates_liquidity

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"

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


class FakeAiClient:
    def __init__(self):
        self.model = "test-model"
        self.call_count = 0

    async def complete_json_async(self, prompt):
        self.call_count += 1
        section = re.search(r"Section: (\w+)", prompt)
        name = section.group(1) if section else "unknown"
        return _response_for_section(name)


def _response_for_section(section_name):
    if section_name == "report":
        return {
            "report": {
                "report_id": "ism_services_2026_06",
                "report_month": "2026-06-01",
                "title": "June 2026 ISM Services PMI Report",
                "source_name": "ismworld",
                "source_url": "https://example.test/services/",
            }
        }
    if section_name == "at_a_glance_rows":
        return {
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
                    "source_excerpt": "Construction reported growth in June.",
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
                }
            ],
        }
    if section_name == "narrative_facts":
        return {
            "narrative_facts": {
                "consecutive_expansion_months": 6,
                "services_economy_gdp_share_percent": None,
                "broad_based_expansion_mentioned": True,
                "inflationary_pressure_mentioned": True,
            }
        }
    return {}


def _prepare_for_test(html_path, url="https://example.test/services/"):
    html = (FIXTURE_DIR / html_path).read_text()
    from app.tools.ism_services_report import prepare_report_for_ai

    return prepare_report_for_ai(html, url, "2026-07-03T14:00:00Z")


class TestBudgetEnforcement:
    def test_extract_all_regions_passes_with_real_ismworld_report(self):
        from app.services.ism_services_ai_ingestion import _extract_all_regions

        prepared = _prepare_for_test("ism_services_report.html")
        regions = _extract_all_regions(prepared["source_text"])
        assert len(regions) == 5
        total = sum(len(t) for t in regions.values())
        cleaned_len = len(prepared["source_text"])
        assert total <= 1.5 * cleaned_len
        for name, text in regions.items():
            assert len(text) <= 0.6 * cleaned_len

    def test_extract_all_regions_passes_with_prnewswire_report(self):
        from app.services.ism_services_ai_ingestion import _extract_all_regions

        prepared = _prepare_for_test("ism_services_prnewswire_report.html")
        regions = _extract_all_regions(prepared["source_text"])
        assert len(regions) == 5
        total = sum(len(t) for t in regions.values())
        cleaned_len = len(prepared["source_text"])
        assert total <= 1.5 * cleaned_len

    def test_extract_all_regions_passes_with_live_page_has_component_lists(self):
        from app.services.ism_services_ai_ingestion import _extract_all_regions

        prepared = _prepare_for_test("ism_services_live_page.html")
        regions = _extract_all_regions(prepared["source_text"])
        assert len(regions) == 5
        total = sum(len(t) for t in regions.values())
        cleaned_len = len(prepared["source_text"])
        assert total <= 1.5 * cleaned_len
        for name, text in regions.items():
            assert len(text) <= 0.6 * cleaned_len
        assert "reporting growth in business activity" in regions["industry_signals"]
        assert "Business Activity" in regions["industry_signals"]
        assert "New Orders" in regions["industry_signals"]

    def test_missing_region_raises(self):
        from app.services.ism_services_ai_ingestion import _extract_all_regions

        with pytest.raises(ValueError, match="failed to extract"):
            _extract_all_regions("No recognized sections here at all.")

    def test_make_prompt_builder_returns_focused_texts(self):
        from app.services.ism_services_ai_ingestion import _make_prompt_builder
        from app.tools.ism_services_ai_extraction import BUILD_PROMPT_FOR_SECTION

        prepared = _prepare_for_test("ism_services_report.html")
        build = _make_prompt_builder(
            prepared["source_text"],
            prepared["source_url"],
            prepared["source_name"],
        )
        for section_name in BUILD_PROMPT_FOR_SECTION:
            prompt = build(section_name, prepared["source_text"])
            assert "Section: " + section_name in prompt
        report_prompt = build("report", prepared["source_text"])
        assert prepared["source_url"] in report_prompt
        assert prepared["source_name"] in report_prompt


class TestRankingReplacement:
    def test_rankings_replaced_per_month(self, tmp_path):
        from app.db.ism_services_ai import promote_services_extraction

        db_path = tmp_path / "test.db"
        con = us_rates_liquidity.connect(db_path)
        growth_cycle.init_db(con)

        prev_ranking = {
            "survey_type": "services",
            "date": "2026-06-01",
            "industry": "Stale Industry",
            "direction": "growth",
            "rank": 1,
            "source": "ISM workbook",
        }
        con.execute(
            "insert into ism_industry_rankings values (?, ?, ?, ?, ?, ?)",
            tuple(prev_ranking.values()),
        )
        con.commit()

        extraction = _valid_extraction()
        source = _valid_source()
        result = promote_services_extraction(con, extraction, source)

        assert result["rankings"] >= 1
        rows = con.execute(
            "select industry from ism_industry_rankings where survey_type = 'services' and date = '2026-06-01'"
        ).fetchall()
        industries = {r["industry"] for r in rows}
        con.close()
        assert "Stale Industry" not in industries
        assert "Construction" in industries

    def test_empty_rankings_clears_month(self, tmp_path):
        from app.db.ism_services_ai import _replace_services_rankings

        db_path = tmp_path / "test.db"
        con = us_rates_liquidity.connect(db_path)
        growth_cycle.init_db(con)
        con.execute(
            "insert into ism_industry_rankings values "
            "('services', '2026-06-01', 'Stale', 'growth', 1, 'old'), "
            "('services', '2026-06-01', 'Stale2', 'contraction', 2, 'old')"
        )
        con.commit()

        payload = {
            "report": {"report_month": "2026-06-01"},
            "industry_signals": [],
        }
        _replace_services_rankings(con, payload, commit=True)

        remaining = con.execute(
            "select count(*) from ism_industry_rankings where survey_type = 'services' and date = '2026-06-01'"
        ).fetchone()
        assert remaining[0] == 0
        con.close()

    def test_ranking_does_not_affect_other_months(self, tmp_path):
        from app.db.ism_services_ai import _replace_services_rankings

        db_path = tmp_path / "test.db"
        con = us_rates_liquidity.connect(db_path)
        growth_cycle.init_db(con)
        con.execute(
            "insert into ism_industry_rankings values "
            "('services', '2026-05-01', 'OtherMonth', 'growth', 1, 'old')"
        )
        con.commit()

        payload = {
            "report": {"report_month": "2026-06-01"},
            "industry_signals": [],
        }
        _replace_services_rankings(con, payload, commit=True)

        remaining = con.execute(
            "select count(*) from ism_industry_rankings where date = '2026-05-01'"
        ).fetchone()
        assert remaining[0] == 1
        con.close()


class TestBackfillInvariants:
    def test_first_run_promotes_zero_calls_on_second_run(self, tmp_path):
        from app.services.ism_ai_section_runner import extract_sections
        from app.tools.ism_services_ai_extraction import (
            BUILD_PROMPT_FOR_SECTION,
            FACTUAL_SECTION_NAMES,
            SECTION_PROMPT_VERSIONS,
            SECTION_RESPONSE_MODELS,
            validate_section_payload,
        )

        prepared = _prepare_for_test("ism_services_report.html")
        prepared["source_text"] = _source_text_with_matching_values()
        db_path = tmp_path / "test.db"
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        growth_cycle.init_db(con)

        def fake_build_prompt(sn, source_text):
            return "Section: " + sn + "\n" + source_text[:100]

        def fake_validate(sn, payload, source_text):
            return validate_section_payload(sn, payload, source_text)

        def fake_model(sn):
            return SECTION_RESPONSE_MODELS[sn]

        client = FakeAiClient()
        result1 = asyncio_run(
            extract_sections(
                con,
                client,
                prepared,
                FACTUAL_SECTION_NAMES,
                SECTION_PROMPT_VERSIONS,
                fake_build_prompt,
                fake_model,
                fake_validate,
            )
        )
        assert client.call_count == 5

        client2 = FakeAiClient()
        result2 = asyncio_run(
            extract_sections(
                con,
                client2,
                prepared,
                FACTUAL_SECTION_NAMES,
                SECTION_PROMPT_VERSIONS,
                fake_build_prompt,
                fake_model,
                fake_validate,
            )
        )
        assert client2.call_count == 0
        assert len(result2["section_payloads"]) == 5
        con.close()

    def test_one_section_invalidation_reruns_only_that_section(self, tmp_path):
        from app.services.ism_ai_section_runner import extract_sections
        from app.tools.ism_services_ai_extraction import (
            BUILD_PROMPT_FOR_SECTION,
            FACTUAL_SECTION_NAMES,
            SECTION_PROMPT_VERSIONS,
            SECTION_RESPONSE_MODELS,
            validate_section_payload,
        )

        prepared = _prepare_for_test("ism_services_report.html")
        prepared["source_text"] = _source_text_with_matching_values()
        db_path = tmp_path / "test.db"
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        growth_cycle.init_db(con)

        def fake_build_prompt(sn, source_text):
            return "Section: " + sn + "\n" + source_text[:100]

        def fake_validate(sn, payload, source_text):
            return validate_section_payload(sn, payload, source_text)

        def fake_model(sn):
            return SECTION_RESPONSE_MODELS[sn]

        client = FakeAiClient()
        asyncio_run(
            extract_sections(
                con,
                client,
                prepared,
                FACTUAL_SECTION_NAMES,
                SECTION_PROMPT_VERSIONS,
                fake_build_prompt,
                fake_model,
                fake_validate,
            )
        )

        assert (
            SECTION_PROMPT_VERSIONS["industry_signals"] == "ism-services-industries-v7"
        )
        modified_versions = dict(SECTION_PROMPT_VERSIONS)
        modified_versions["industry_signals"] = "ism-services-industries-v8"
        client2 = FakeAiClient()
        result = asyncio_run(
            extract_sections(
                con,
                client2,
                prepared,
                FACTUAL_SECTION_NAMES,
                modified_versions,
                fake_build_prompt,
                fake_model,
                fake_validate,
            )
        )
        assert client2.call_count == 1
        con.close()

    def test_repaired_at_a_glance_section_promotes_report_month(self, tmp_path):
        from app.db.ism_services_ai import promote_services_extraction
        from app.services.ism_ai_section_runner import extract_sections
        from app.tools.ism_services_ai_extraction import (
            FACTUAL_SECTION_NAMES,
            SECTION_PROMPT_VERSIONS,
            SECTION_RESPONSE_MODELS,
            assemble_factual_extraction,
            validate_section_payload,
        )

        class RepairingClient(FakeAiClient):
            def __init__(self):
                super().__init__()
                self.at_a_glance_calls = 0

            async def complete_json_async(self, prompt):
                section = re.search(r"Section: (\w+)", prompt)
                section_name = section.group(1) if section else "unknown"
                self.call_count += 1
                response = deepcopy(_response_for_section(section_name))
                if section_name == "at_a_glance_rows":
                    self.at_a_glance_calls += 1
                    if self.at_a_glance_calls == 1:
                        response["at_a_glance_rows"][0]["trend_months"] = None
                return response

        prepared = _prepare_for_test("ism_services_report.html")
        prepared["source_text"] = _source_text_with_matching_values()
        con = us_rates_liquidity.connect(tmp_path / "test.db")
        growth_cycle.init_db(con)

        def fake_build_prompt(section_name, source_text):
            return f"Section: {section_name}\n{source_text}"

        section_result = asyncio_run(
            extract_sections(
                con,
                RepairingClient(),
                prepared,
                FACTUAL_SECTION_NAMES,
                SECTION_PROMPT_VERSIONS,
                fake_build_prompt,
                lambda name: SECTION_RESPONSE_MODELS[name],
                validate_section_payload,
            )
        )
        extraction = assemble_factual_extraction(section_result["section_payloads"])
        promoted = promote_services_extraction(
            con,
            extraction,
            {
                "source_url": prepared["source_url"],
                "source_hash": "source-hash",
                "model": "test-model",
                "updated_at": prepared["fetched_at"],
            },
        )

        assert section_result["call_counts"]["at_a_glance_rows"] == 2
        assert promoted["at_a_glance_rows"] == 11
        assert growth_cycle.load_existing_ism_report_months(con, "services") == {
            "2026-06-01"
        }
        con.close()


class TestSignalCoverage:
    def test_signal_coverage_persisted(self, tmp_path):
        from app.db.ism_services_ai import promote_services_extraction

        con = us_rates_liquidity.connect(tmp_path / "test.db")
        growth_cycle.init_db(con)

        extraction = _valid_extraction()
        source = _valid_source()
        promote_services_extraction(con, extraction, source)

        rows = con.execute(
            "select * from ism_report_industry_signal_coverage where report_id = ?",
            ("ism_services_2026_06",),
        ).fetchall()
        assert len(rows) >= 1
        con.close()


def _source_text_with_matching_values():
    rows = []
    for i, sid in enumerate(SERVICES_COMPONENTS):
        val = 50.0 + i * 0.5
        label = sid.replace("ism_services_", "").replace("_", " ").title()
        rows.append(f"{label} Index at {val:.1f} percent.")
    return (
        "June 2026 ISM Services PMI Report\n"
        + "\n".join(rows)
        + "\nSERVICES AT A GLANCE\n"
        + "\n".join(
            f"{sid} {50.0 + i * 0.5}" for i, sid in enumerate(SERVICES_COMPONENTS)
        )
        + "\nINDUSTRY PERFORMANCE\n"
        + "Construction reported growth in June.\n"
        + "COMMODITIES REPORTED\n"
        + "Construction Labor up in price.\n"
        + "Pipeline remains healthy.\n"
        + "inflationary pressure\n"
        + "broad based expansion\n"
        + "6 consecutive months\n"
    )


def _valid_extraction():
    return {
        "report": {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_name": "ismworld",
            "source_url": "https://example.test/services/",
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
            for i, sid in enumerate(SERVICES_COMPONENTS)
        ],
        "industry_signals": [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Construction",
                "rank": 1,
                "source_excerpt": "Construction reported growth in June.",
            },
        ],
        "respondent_comments": [
            {
                "industry": "Construction",
                "comment_text": "Pipeline remains healthy.",
            },
        ],
        "commodities": [
            {
                "commodity": "Construction Labor",
                "signal_type": "up_in_price",
                "months": 2,
            },
        ],
        "narrative_facts": {
            "consecutive_expansion_months": 6,
            "services_economy_gdp_share_percent": None,
            "broad_based_expansion_mentioned": True,
            "inflationary_pressure_mentioned": True,
        },
    }


def _valid_source():
    return {
        "source_url": "https://example.test/services/",
        "source_hash": "abc123",
        "model": "test-model",
        "updated_at": "2026-07-03T14:00:00Z",
    }


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
