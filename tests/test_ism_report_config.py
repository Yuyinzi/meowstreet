"""Tests for ISM survey configuration adapters."""

import pytest
from app.tools import ism_report_config as config


class TestLoadSurveyConfig:
    def test_manufacturing_config_returns_expected_fields(self):
        cfg = config.load_survey_config("manufacturing")
        assert cfg["survey_type"] == "manufacturing"
        assert cfg["report_id_prefix"] == "ism_manufacturing"
        assert isinstance(cfg["allowed_metric_series"], frozenset)
        assert "ism_manufacturing_pmi" in cfg["allowed_metric_series"]
        assert "ism_services_pmi" not in cfg["allowed_metric_series"]
        assert cfg["has_ai_extraction"] is True

    def test_services_config_returns_expected_fields(self):
        cfg = config.load_survey_config("services")
        assert cfg["survey_type"] == "services"
        assert cfg["report_id_prefix"] == "ism_services"
        assert isinstance(cfg["allowed_metric_series"], frozenset)
        assert "ism_services_pmi" in cfg["allowed_metric_series"]
        assert "ism_manufacturing_pmi" not in cfg["allowed_metric_series"]
        assert cfg["has_ai_extraction"] is False

    def test_manufacturing_config_builds_ismworld_url(self):
        cfg = config.load_survey_config("manufacturing")
        url = cfg["ismworld_monthly_url"]("june")
        assert "pmi/june/" in url
        assert url.startswith("https://www.ismworld.org/")

    def test_services_config_builds_ismworld_url(self):
        cfg = config.load_survey_config("services")
        url = cfg["ismworld_monthly_url"]("june")
        assert "services/june/" in url
        assert url.startswith("https://www.ismworld.org/")

    def test_manufacturing_report_id_prefix(self):
        cfg = config.load_survey_config("manufacturing")
        assert cfg["report_id_prefix"] == "ism_manufacturing"

    def test_services_report_id_prefix(self):
        cfg = config.load_survey_config("services")
        assert cfg["report_id_prefix"] == "ism_services"

    def test_unknown_survey_type_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown survey type: invalid"):
            config.load_survey_config("invalid")

    def test_config_is_immutable_by_default(self):
        cfg = config.load_survey_config("manufacturing")
        assert "survey_type" in cfg


class TestManufacturingPrnewswireMatcher:
    def test_matches_manufacturing_pmi_title(self):
        cfg = config.load_survey_config("manufacturing")
        matcher = cfg["prnewswire_title_matcher"]
        assert matcher("ISM Manufacturing PMI Report for June 2026")
        assert matcher("ISM Manufacturing PMI Report for July 2026")

    def test_rejects_services_title(self):
        cfg = config.load_survey_config("manufacturing")
        matcher = cfg["prnewswire_title_matcher"]
        assert not matcher("ISM Services PMI Report for June 2026")

    def test_rejects_hospital_title(self):
        cfg = config.load_survey_config("manufacturing")
        matcher = cfg["prnewswire_title_matcher"]
        assert not matcher("ISM Hospital PMI Report for June 2026")

    def test_rejects_non_ism_title(self):
        cfg = config.load_survey_config("manufacturing")
        matcher = cfg["prnewswire_title_matcher"]
        assert not matcher("Some Other Press Release")


class TestServicesPrnewswireMatcher:
    def test_matches_services_pmi_title(self):
        cfg = config.load_survey_config("services")
        matcher = cfg["prnewswire_title_matcher"]
        assert matcher("ISM Services PMI Report for June 2026")
        assert matcher("ISM Services PMI Report for July 2026")

    def test_rejects_manufacturing_title(self):
        cfg = config.load_survey_config("services")
        matcher = cfg["prnewswire_title_matcher"]
        assert not matcher("ISM Manufacturing PMI Report for June 2026")

    def test_rejects_non_ism_title(self):
        cfg = config.load_survey_config("services")
        matcher = cfg["prnewswire_title_matcher"]
        assert not matcher("Some Other Press Release")


class TestParseReportAdapter:
    def test_manufacturing_parse_report_rejects_empty_html(self):
        cfg = config.load_survey_config("manufacturing")
        with pytest.raises(Exception):
            cfg["parse_report"]("", "http://example.com", "2026-06-01T12:00:00")

    def test_services_parse_report_rejects_empty_html(self):
        cfg = config.load_survey_config("services")
        with pytest.raises(Exception):
            cfg["parse_report"]("", "http://example.com", "2026-06-01T12:00:00")


class TestNormalizeIndustry:
    def test_manufacturing_normalize_industry(self):
        cfg = config.load_survey_config("manufacturing")
        assert cfg["normalize_industry"] is not None
        result = cfg["normalize_industry"]("Fabricated Metal Products")
        assert result == "Fabricated Metal Products"

    def test_services_normalize_industry(self):
        cfg = config.load_survey_config("services")
        assert cfg["normalize_industry"] is not None
        result = cfg["normalize_industry"]("Construction")
        assert result == "Construction"


class TestValidSurveyTypes:
    def test_returns_both_surveys(self):
        types = config.valid_survey_types()
        assert "manufacturing" in types
        assert "services" in types
        assert len(types) == 2
