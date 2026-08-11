import json

import pytest

from app.tools import market_assistant_knowledge


def valid_record(**overrides):
    record = {
        "record_id": "sample_definition",
        "version": "sample_v1",
        "object_type": "indicator_definition",
        "authority": "method_knowledge",
        "decision_effect": "none",
        "market_setup_relation": "non_decision",
        "source": {
            "source_module": "sample_module",
            "method_version": "sample_v1",
            "source_period": "monthly",
            "periods": ["sample accepted period"],
        },
        "source_period_required": True,
    }
    record.update(overrides)
    return record


def valid_catalog(*records):
    return {"version": "market_assistant_knowledge_v1", "records": list(records)}


def write_catalog(tmp_path, catalog):
    path = tmp_path / "market_assistant_knowledge.v1.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


def test_ism_definition_separates_level_and_direction():
    catalog = market_assistant_knowledge.load_knowledge_catalog()
    record = market_assistant_knowledge.get_knowledge_record(
        catalog, "ism_manufacturing_pmi_definition"
    )

    assert record["level_contract"]["below"] == "contraction"
    assert record["direction_contract"]["rule"] == "use approved direction method"
    assert "% Better + 0.5 × % Same" in record["formula"]


def test_load_knowledge_catalog_returns_plain_dict_catalog():
    catalog = market_assistant_knowledge.load_knowledge_catalog()
    assert catalog["version"] == "market_assistant_knowledge_v1"
    assert all(
        record["authority"] == "method_knowledge" for record in catalog["records"]
    )


def test_get_knowledge_record_returns_plain_dict():
    catalog = market_assistant_knowledge.load_knowledge_catalog()
    record = market_assistant_knowledge.get_knowledge_record(catalog, "vix_definition")
    assert isinstance(record, dict)
    assert record["record_id"] == "vix_definition"


def test_method_records_exist_for_core_indicators():
    catalog = market_assistant_knowledge.load_knowledge_catalog()
    method_ids = {
        (record["indicator_id"], record["object_type"])
        for record in catalog["records"]
        if record["object_type"] == "indicator_method"
    }
    assert {
        ("vix_level", "indicator_method"),
        ("ism_manufacturing_pmi", "indicator_method"),
        ("m2_liquidity", "indicator_method"),
        ("sp500_market_phase", "indicator_method"),
        ("credit_conditions", "indicator_method"),
        ("jobless_claims", "indicator_method"),
    }.issubset(method_ids)


def test_get_knowledge_record_with_version_returns_exact_version():
    catalog = market_assistant_knowledge.load_knowledge_catalog()
    record = market_assistant_knowledge.get_knowledge_record(
        catalog, "vix_definition", version="vix_confirmation_v2"
    )
    assert record["version"] == "vix_confirmation_v2"


def test_get_knowledge_record_returns_latest_version():
    catalog = valid_catalog(
        valid_record(version="sample_v1"),
        valid_record(version="sample_v2"),
    )
    record = market_assistant_knowledge.get_knowledge_record(
        catalog, "sample_definition"
    )
    assert record["version"] == "sample_v2"


def test_load_rejects_duplicate_record_id_and_version(tmp_path):
    path = write_catalog(
        tmp_path,
        valid_catalog(valid_record(), valid_record()),
    )
    with pytest.raises(ValueError, match="knowledge record sample_definition"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_load_allows_same_record_id_with_different_versions(tmp_path):
    path = write_catalog(
        tmp_path,
        valid_catalog(
            valid_record(version="sample_v1"),
            valid_record(version="sample_v2"),
        ),
    )
    catalog = market_assistant_knowledge.load_knowledge_catalog(path)
    assert len(catalog["records"]) == 2


def test_load_rejects_missing_required_fields(tmp_path):
    record = valid_record()
    del record["authority"]
    path = write_catalog(tmp_path, valid_catalog(record))
    with pytest.raises(ValueError, match="missing required fields"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_load_rejects_missing_source_periods(tmp_path):
    record = valid_record()
    del record["source"]["periods"]
    path = write_catalog(tmp_path, valid_catalog(record))
    with pytest.raises(ValueError, match="source periods are required"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_load_rejects_unapproved_formula(tmp_path):
    record = valid_record(formula="some invented formula")
    path = write_catalog(tmp_path, valid_catalog(record))
    with pytest.raises(ValueError, match="unapproved formula"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_load_rejects_unknown_object_type(tmp_path):
    record = valid_record(object_type="indicator_opinion")
    path = write_catalog(tmp_path, valid_catalog(record))
    with pytest.raises(ValueError, match="unknown object type"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_load_rejects_unknown_authority(tmp_path):
    record = valid_record(authority="decision_fact")
    path = write_catalog(tmp_path, valid_catalog(record))
    with pytest.raises(ValueError, match="unknown authority"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_load_rejects_claimed_decision_effect(tmp_path):
    record = valid_record(decision_effect="confirmation_test")
    path = write_catalog(tmp_path, valid_catalog(record))
    with pytest.raises(ValueError, match="no decision effect"):
        market_assistant_knowledge.load_knowledge_catalog(path)


def test_get_knowledge_record_rejects_unknown_record_id():
    catalog = valid_catalog(valid_record())
    with pytest.raises(
        ValueError, match="knowledge record unknown_definition is not available"
    ):
        market_assistant_knowledge.get_knowledge_record(catalog, "unknown_definition")


def test_get_knowledge_record_rejects_unknown_version():
    catalog = valid_catalog(valid_record(version="sample_v1"))
    with pytest.raises(
        ValueError,
        match="knowledge record sample_definition version sample_v9 is not available",
    ):
        market_assistant_knowledge.get_knowledge_record(
            catalog, "sample_definition", version="sample_v9"
        )
