import copy
import json

import pytest

from app.tools import market_assistant_evidence_detail_registry


EXPECTED_FACT_IDS = {
    "survey_growth_direction",
    "macro_financial_conditions",
    "macro_policy_response",
    "consumer_demand_outlook",
    "sp500_market_phase",
    "credit_conditions",
    "vix_level",
    "m2_liquidity",
    "equity_breadth",
    "jobless_claims",
    "economic_confirmation",
    "cyclical_commodities",
    "nfib_regional_evidence",
}

_ENABLED_SPECS = [
    (
        "survey_growth_direction",
        "decision_input",
        "survey_synthesis",
        ("current", "drivers", "source"),
        (
            "manufacturing and services",
            "ISM survey",
            "survey direction",
            "制造业和服务业",
            "调查方向",
            "增长方向依据",
        ),
        "ism_survey_synthesis",
        "market_assistant_survey_synthesis_detail_v1",
    ),
    (
        "macro_financial_conditions",
        "decision_input",
        "financial_conditions",
        ("current", "drivers", "source"),
        (
            "financial conditions",
            "yield curve",
            "real rates",
            "金融条件",
            "收益率曲线",
            "实际利率",
        ),
        "us_rates_liquidity",
        "market_assistant_financial_conditions_detail_v1",
    ),
    (
        "macro_policy_response",
        "decision_input",
        "policy_response",
        ("current", "drivers", "source"),
        (
            "FOMC",
            "Fed",
            "monetary policy",
            "美联储",
            "货币政策",
            "利率决定",
            "鹰派",
            "鸽派",
        ),
        "fomc_policy_tone",
        "market_assistant_policy_response_detail_v1",
    ),
    (
        "consumer_demand_outlook",
        "confirmation_input",
        "consumer_demand",
        ("current", "drivers", "source"),
        (
            "consumer expectations",
            "consumer demand",
            "consumer confidence",
            "消费者预期",
            "消费者需求",
            "消费者信心",
        ),
        "consumer_sentiment",
        "market_assistant_consumer_demand_detail_v1",
    ),
    (
        "sp500_market_phase",
        "confirmation_input",
        "market_phase",
        ("current", "method", "source"),
        (
            "S&P 500 phase",
            "S&P 500",
            "market phase",
            "标普市场阶段",
            "标普",
            "牛市阶段",
            "熊市阶段",
        ),
        "market_phase",
        "market_assistant_market_phase_detail_v1",
    ),
    (
        "credit_conditions",
        "confirmation_input",
        "credit_conditions",
        ("current", "method", "source"),
        ("credit conditions", "credit spreads", "信贷条件", "信用条件", "信用利差"),
        "us_rates_liquidity",
        "market_assistant_credit_conditions_detail_v1",
    ),
    (
        "vix_level",
        "confirmation_input",
        "vix",
        ("current", "method", "source"),
        ("VIX", "波动率", "恐慌指数"),
        "us_rates_liquidity",
        "market_assistant_vix_detail_v1",
    ),
    (
        "m2_liquidity",
        "context_only",
        "m2_liquidity",
        ("current", "method", "source"),
        ("M2 liquidity", "M2 supply", "M2 流动性", "M2 货币供应"),
        "m2_money_supply",
        "market_assistant_m2_liquidity_detail_v1",
    ),
]

_DISABLED_SPECS = [
    ("equity_breadth", "observation_only", "observation_only"),
    ("jobless_claims", "observation_only", "observation_only"),
    ("economic_confirmation", "context_only", "economic_confirmation"),
    ("cyclical_commodities", "observation_only", "cyclical_commodities"),
    ("nfib_regional_evidence", "manual_review", "nfib_sbo_regional"),
]

_UNSUPPORTED_VERSION = "market_assistant_evidence_detail_unsupported_v1"


def _record(
    fact_id, scope, detail_kind, topics, aliases, source_module, projection_version
):
    return {
        "fact_id": fact_id,
        "scope": scope,
        "detail_kind": detail_kind,
        "supported_topics": list(topics),
        "default_topics": list(topics),
        "aliases": list(aliases),
        "source_module": source_module,
        "projection_version": projection_version,
    }


def valid_registry():
    facts = [_record(*spec) for spec in _ENABLED_SPECS] + [
        _record(
            fact_id, scope, "unsupported", (), (), source_module, _UNSUPPORTED_VERSION
        )
        for fact_id, scope, source_module in _DISABLED_SPECS
    ]
    return {"version": "market_assistant_evidence_details_v1", "facts": facts}


def _load_payload(tmp_path, payload):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return market_assistant_evidence_detail_registry.load_evidence_detail_registry(path)


def test_registry_covers_surface_exactly_once():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    ids = [record["fact_id"] for record in registry["facts"]]
    assert set(ids) == EXPECTED_FACT_IDS
    assert len(ids) == len(set(ids))


def test_registry_enables_only_eight_core_facts():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    enabled = {
        record["fact_id"] for record in registry["facts"] if record["supported_topics"]
    }
    assert enabled == {
        "survey_growth_direction",
        "macro_financial_conditions",
        "macro_policy_response",
        "consumer_demand_outlook",
        "sp500_market_phase",
        "credit_conditions",
        "vix_level",
        "m2_liquidity",
    }


def test_evidence_detail_fact_ids_match_surface():
    assert (
        set(market_assistant_evidence_detail_registry.EVIDENCE_DETAIL_FACT_IDS)
        == EXPECTED_FACT_IDS
    )
    assert len(
        market_assistant_evidence_detail_registry.EVIDENCE_DETAIL_FACT_IDS
    ) == len(set(market_assistant_evidence_detail_registry.EVIDENCE_DETAIL_FACT_IDS))


def test_registry_enabled_facts_have_exact_detail_contracts():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    records = {record["fact_id"]: record for record in registry["facts"]}
    for (
        fact_id,
        scope,
        detail_kind,
        topics,
        _,
        source_module,
        projection_version,
    ) in _ENABLED_SPECS:
        record = records[fact_id]
        assert record["scope"] == scope
        assert record["detail_kind"] == detail_kind
        assert record["supported_topics"] == list(topics)
        assert record["default_topics"] == list(topics)
        assert record["aliases"]
        assert record["source_module"] == source_module
        assert record["projection_version"] == projection_version


def test_registry_disabled_facts_are_governed_unsupported():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    records = {record["fact_id"]: record for record in registry["facts"]}
    for fact_id, scope, source_module in _DISABLED_SPECS:
        record = records[fact_id]
        assert record["scope"] == scope
        assert record["detail_kind"] == "unsupported"
        assert record["supported_topics"] == []
        assert record["default_topics"] == []
        assert record["aliases"] == []
        assert record["source_module"] == source_module
        assert record["projection_version"] == _UNSUPPORTED_VERSION


def test_registry_includes_required_aliases():
    required_aliases = {
        "survey_growth_direction": ["manufacturing and services", "制造业和服务业"],
        "macro_financial_conditions": [
            "financial conditions",
            "yield curve",
            "金融条件",
            "收益率曲线",
        ],
        "macro_policy_response": ["FOMC", "monetary policy", "美联储", "货币政策"],
        "consumer_demand_outlook": ["consumer expectations", "消费者预期"],
        "sp500_market_phase": ["S&P 500 phase", "标普市场阶段"],
        "credit_conditions": ["credit conditions", "信贷条件"],
        "vix_level": ["VIX", "波动率"],
        "m2_liquidity": ["M2 liquidity", "M2 流动性"],
    }
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    records = {record["fact_id"]: record for record in registry["facts"]}
    for fact_id, aliases in required_aliases.items():
        for alias in aliases:
            assert alias in records[fact_id]["aliases"]


def test_registry_valid_payload_returns_plain_dicts(tmp_path):
    registry = _load_payload(tmp_path, valid_registry())
    assert registry["version"] == "market_assistant_evidence_details_v1"
    assert all(isinstance(record, dict) for record in registry["facts"])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload["facts"].append(payload["facts"][0]), "duplicated"),
        (
            lambda payload: payload["facts"][0]["supported_topics"].append("bogus"),
            "record is invalid",
        ),
        (
            lambda payload: payload["facts"][0]["default_topics"].append("method"),
            "wrong default topics",
        ),
        (
            lambda payload: payload["facts"][0].update({"aliases": []}),
            "wrong aliases",
        ),
        (
            lambda payload: payload["facts"][0]["supported_topics"].append("current"),
            "topic is duplicated",
        ),
        (
            lambda payload: payload["facts"].append(
                _record(
                    "bogus_fact",
                    "observation_only",
                    "unsupported",
                    (),
                    (),
                    "observation_only",
                    _UNSUPPORTED_VERSION,
                )
            ),
            "is unknown",
        ),
        (lambda payload: payload["facts"].pop(), "is missing"),
        (
            lambda payload: payload["facts"][0].update({"extra_field": True}),
            "record is invalid",
        ),
    ],
)
def test_load_evidence_detail_registry_rejects_invalid_payload(
    tmp_path, mutate, message
):
    payload = valid_registry()
    mutate(payload)
    with pytest.raises(ValueError, match=message):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_unknown_version(tmp_path):
    payload = valid_registry()
    payload["version"] = "bogus_version"
    with pytest.raises(ValueError, match="version is unknown"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_missing_facts(tmp_path):
    payload = valid_registry()
    del payload["facts"]
    with pytest.raises(ValueError, match="facts are required"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_unregistered_projection_kind(
    tmp_path,
):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["detail_kind"] = "unregistered_kind"
    with pytest.raises(ValueError, match="wrong detail kind"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_unsupported_declaring_topics(
    tmp_path,
):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "equity_breadth":
            record["supported_topics"] = ["current"]
    with pytest.raises(ValueError, match="unsupported"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_enabled_without_topics(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["supported_topics"] = []
    with pytest.raises(ValueError, match="supported topics"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_fact_bound_to_wrong_kind(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["detail_kind"] = "vix"
    with pytest.raises(ValueError, match="detail kind"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_enabled_fact_disabled(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["detail_kind"] = "unsupported"
            record["supported_topics"] = []
            record["default_topics"] = []
            record["aliases"] = []
    with pytest.raises(ValueError, match="detail kind"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_disabled_fact_enabled(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "equity_breadth":
            record["detail_kind"] = "vix"
            record["supported_topics"] = ["current"]
            record["default_topics"] = ["current"]
            record["aliases"] = ["test"]
    with pytest.raises(ValueError, match="not enabled"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_topics_builder_cannot_produce(
    tmp_path,
):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "sp500_market_phase":
            record["supported_topics"] = ["current", "drivers"]
            record["default_topics"] = ["current", "drivers"]
    with pytest.raises(ValueError, match="topics"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_wrong_projection_version(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["projection_version"] = "bogus_version"
    with pytest.raises(ValueError, match="projection version"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_wrong_scope(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["scope"] = "manual_review"
    with pytest.raises(ValueError, match="scope"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_wrong_default_topics(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["default_topics"] = ["current"]
    with pytest.raises(ValueError, match="default topics"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_wrong_source_module(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["source_module"] = "bogus_module"
    with pytest.raises(ValueError, match="source module"):
        _load_payload(tmp_path, payload)


def test_load_evidence_detail_registry_rejects_wrong_aliases(tmp_path):
    payload = valid_registry()
    for record in payload["facts"]:
        if record["fact_id"] == "macro_policy_response":
            record["aliases"] = ["VIX"]
    with pytest.raises(ValueError, match="aliases"):
        _load_payload(tmp_path, payload)


def test_evidence_detail_record_returns_enabled_record():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    record = market_assistant_evidence_detail_registry.evidence_detail_record(
        registry, "macro_policy_response"
    )
    assert record["fact_id"] == "macro_policy_response"
    assert record["detail_kind"] == "policy_response"


def test_evidence_detail_record_returns_unsupported_record():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    record = market_assistant_evidence_detail_registry.evidence_detail_record(
        registry, "equity_breadth"
    )
    assert record["detail_kind"] == "unsupported"
    assert record["supported_topics"] == []


def test_evidence_detail_record_rejects_unregistered_fact():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    with pytest.raises(ValueError, match="not registered"):
        market_assistant_evidence_detail_registry.evidence_detail_record(
            registry, "bogus_fact"
        )


@pytest.mark.parametrize(
    ("fact_id", "aliases"),
    [
        ("macro_policy_response", ["FOMC", "monetary policy", "美联储", "货币政策"]),
        (
            "macro_financial_conditions",
            ["financial conditions", "yield curve", "金融条件", "收益率曲线"],
        ),
        (
            "consumer_demand_outlook",
            ["consumer expectations", "消费者预期"],
        ),
        (
            "survey_growth_direction",
            ["manufacturing and services", "制造业和服务业"],
        ),
        ("sp500_market_phase", ["S&P 500 phase", "标普市场阶段"]),
        ("credit_conditions", ["credit conditions", "信贷条件"]),
        ("vix_level", ["VIX", "波动率"]),
        ("m2_liquidity", ["M2 liquidity", "M2 流动性"]),
    ],
)
def test_evidence_detail_tool_catalog_lists_enabled_facts_with_aliases(
    fact_id, aliases
):
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    catalog = market_assistant_evidence_detail_registry.evidence_detail_tool_catalog(
        registry
    )
    assert fact_id in catalog
    for alias in aliases:
        assert alias in catalog


def test_evidence_detail_tool_catalog_includes_supported_topics():
    catalog = market_assistant_evidence_detail_registry.evidence_detail_tool_catalog()
    assert "topics=current,drivers,source" in catalog
    assert "topics=current,method,source" in catalog


def test_evidence_detail_tool_catalog_omits_unsupported_facts():
    catalog = market_assistant_evidence_detail_registry.evidence_detail_tool_catalog()
    for fact_id in (
        "equity_breadth",
        "jobless_claims",
        "economic_confirmation",
        "cyclical_commodities",
        "nfib_regional_evidence",
    ):
        assert fact_id not in catalog


def test_evidence_detail_tool_catalog_is_registry_ordered_and_deterministic():
    registry = market_assistant_evidence_detail_registry.load_evidence_detail_registry()
    first = market_assistant_evidence_detail_registry.evidence_detail_tool_catalog(
        registry
    )
    second = market_assistant_evidence_detail_registry.evidence_detail_tool_catalog(
        registry
    )
    assert first == second
    enabled_ids = [
        record["fact_id"] for record in registry["facts"] if record["supported_topics"]
    ]
    positions = [catalog_position(first, fact_id) for fact_id in enabled_ids]
    assert positions == sorted(positions)


def test_evidence_detail_tool_catalog_uses_custom_registry(tmp_path):
    registry = _load_payload(tmp_path, valid_registry())
    catalog = market_assistant_evidence_detail_registry.evidence_detail_tool_catalog(
        registry
    )
    assert "macro_policy_response" in catalog
    assert "FOMC" in catalog


def catalog_position(text, fact_id):
    return text.index(fact_id)
