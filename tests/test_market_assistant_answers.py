import pytest

from app.tools.market_assistant_artifacts import validate_artifact
from app.tools.market_assistant_answers import _SECTION_BY_PURPOSE
from app.tools.market_assistant_answers import DraftValidationError
from app.tools.market_assistant_answers import build_validation_report
from app.tools.market_assistant_answers import calculate_hypothetical
from app.tools.market_assistant_answers import collect_citations
from app.tools.market_assistant_answers import detect_answer_language
from app.tools.market_assistant_answers import render_answer
from app.tools.market_assistant_answers import render_fallback
from app.tools.market_assistant_answers import render_unvalidated_debug_answer
from app.tools.market_assistant_answers import validate_answer_draft
from app.tools.market_assistant_answers import validate_answer_draft_schema


def snapshot_artifact():
    return {
        "artifact_id": "ctx_123",
        "artifact_kind": "explanation_snapshot",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": {
            "context_id": "ctx_123",
            "results": {
                "macro_regime": {
                    "code": "growth_decelerating",
                    "label": "Growth Decelerating",
                },
                "market_confirmation": {
                    "code": "downside_confirmation",
                    "label": "Downside Confirmation",
                },
                "market_setup": {
                    "code": "downside_setup",
                    "label": "Downside Setup",
                },
                "portfolio_posture": {
                    "code": "defensive",
                    "label": "Defensive Posture",
                },
            },
            "decision_path": [
                {
                    "step_id": "macro_thesis",
                    "object_type": "market_setup_result",
                    "object_id": "macro_regime",
                    "label": "Macro Thesis",
                    "code": "growth_decelerating",
                },
                {
                    "step_id": "market_test",
                    "object_type": "market_setup_result",
                    "object_id": "market_confirmation",
                    "label": "Market Test",
                    "code": "downside_confirmation",
                },
                {
                    "step_id": "setup_relationship",
                    "object_type": "market_setup_result",
                    "object_id": "market_setup",
                    "label": "Setup Relationship",
                    "code": "downside_setup",
                },
                {
                    "step_id": "portfolio_action",
                    "object_type": "market_setup_result",
                    "object_id": "portfolio_posture",
                    "label": "Portfolio Action",
                    "code": "defensive",
                },
            ],
            "evidence": [
                {
                    "fact_id": "vix_level",
                    "label": "VIX",
                    "accepted_values": {"level": 18.4},
                    "data_status": {"state": "available"},
                }
            ],
            "method_contracts": {
                "version": "market_setup_explanation_methods_v1",
                "methods": {
                    "vix_confirmation_v2": {
                        "method_version": "vix_confirmation_v2",
                        "kind": "predicate_method",
                        "decision_contract": {
                            "input_contract": {
                                "fact_id": "vix_level",
                                "field_id": "level",
                                "type": "number",
                                "unit": "index",
                            },
                            "predicates": {
                                "downside": {
                                    "predicate_id": "downside",
                                    "field_id": "level",
                                    "operator": "gte",
                                    "operand": 20.0,
                                },
                                "upside": {
                                    "predicate_id": "upside",
                                    "field_id": "level",
                                    "operator": "lt",
                                    "operand": 20.0,
                                },
                            },
                        },
                        "explanation_contract": {
                            "description": "VIX downside confirmation requires level >= 20.0"
                        },
                    }
                },
            },
        },
        "object_index": [
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"level": 18.4, "indicator_id": "vix", "label": "VIX"},
            },
            {
                "object_type": "confirmation_test",
                "object_id": "vix_downside_confirmation",
                "authority": "decision_fact",
                "payload": {
                    "accepted_value": 18.4,
                    "threshold": 20.0,
                    "operator": "gte",
                    "evaluation": {"result": False},
                },
            },
            {
                "object_type": "method_contract",
                "object_id": "vix_confirmation_v2",
                "authority": "method_knowledge",
                "payload": {
                    "method_id": "vix_confirmation_v2",
                    "predicates": {
                        "downside": {"operand": 20.0, "operator": "gte"},
                        "upside": {"operand": 20.0, "operator": "lt"},
                    },
                },
            },
        ],
        "integrity_hash": "a" * 64,
    }


def exploration_artifact():
    return {
        "artifact_id": "expl_1",
        "artifact_kind": "exploration_result",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "local_observation",
        "market_setup_relation": "non_decision",
        "payload": {
            "exploration_result_id": "expl_1",
            "query_contract": {
                "query_kind": "indicator_history",
                "indicator_id": "vix",
                "start": "2026-07-01",
                "end": "2026-08-01",
            },
            "observed_window": {"start": "2026-07-01", "end": "2026-08-01"},
            "rows": [
                {"date": "2026-07-01", "value": 15.0},
                {"date": "2026-08-01", "value": 18.4},
            ],
            "deterministic_statistics": {
                "first_value": 15.0,
                "last_value": 18.4,
                "absolute_change": 3.4,
                "count": 2,
            },
            "gaps": {"policy": "not_applicable", "missing_periods": None},
        },
        "object_index": [
            {
                "object_type": "indicator_history",
                "object_id": "vix_history",
                "authority": "local_observation",
                "payload": {
                    "rows": [
                        {"date": "2026-07-01", "value": 15.0},
                        {"date": "2026-08-01", "value": 18.4},
                    ],
                    "first_value": 15.0,
                    "last_value": 18.4,
                    "absolute_change": 3.4,
                    "classifications": {"level": "elevated"},
                },
            }
        ],
        "integrity_hash": "b" * 64,
    }


def research_artifact():
    return {
        "artifact_id": "res_1",
        "artifact_kind": "research_result",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "external_research",
        "market_setup_relation": "non_decision",
        "payload": {
            "research_result_id": "res_1",
            "sources": [
                {
                    "source_id": "src_1",
                    "canonical_url": "https://www.federalreserve.gov/press-release.htm",
                    "title": "Federal Reserve Press Release",
                    "publisher": "federalreserve.gov",
                    "publication_date": "2026-08-09",
                    "event_date": "2026-08-09",
                },
                {
                    "source_id": "src_2",
                    "canonical_url": "https://finance.example.com/news/rates",
                    "title": "Example Finance News",
                    "publisher": "finance.example.com",
                    "publication_date": "2026-08-09",
                    "event_date": "2026-08-08",
                },
            ],
            "findings": [
                {
                    "finding_id": "fnd_1",
                    "statement": "The Federal Reserve reported a rate decision.",
                    "purpose": "current_events",
                    "framing": "reported",
                    "source_refs": ["src_1"],
                    "cited_spans": ["The Federal Reserve announced a rate decision."],
                }
            ],
        },
        "object_index": [
            {
                "object_type": "research_source",
                "object_id": "src_1",
                "authority": "external_research",
                "payload": {
                    "source_id": "src_1",
                    "canonical_url": "https://www.federalreserve.gov/press-release.htm",
                    "title": "Federal Reserve Press Release",
                    "publisher": "federalreserve.gov",
                    "publication_date": "2026-08-09",
                    "event_date": "2026-08-09",
                },
            },
            {
                "object_type": "research_source",
                "object_id": "src_2",
                "authority": "external_research",
                "payload": {
                    "source_id": "src_2",
                    "canonical_url": "https://finance.example.com/news/rates",
                    "title": "Example Finance News",
                    "publisher": "finance.example.com",
                    "publication_date": "2026-08-09",
                    "event_date": "2026-08-08",
                },
            },
            {
                "object_type": "research_finding",
                "object_id": "fnd_1",
                "authority": "external_research",
                "payload": {
                    "finding_id": "fnd_1",
                    "statement": "The Federal Reserve reported a rate decision.",
                },
            },
        ],
        "integrity_hash": "c" * 64,
    }


def knowledge_artifact():
    return {
        "artifact_id": "kn_1",
        "artifact_kind": "knowledge_record",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "method_knowledge",
        "market_setup_relation": "non_decision",
        "payload": {
            "record_id": "vix_definition",
            "version": "vix_confirmation_v2",
            "object_type": "indicator_definition",
            "authority": "method_knowledge",
            "title": "VIX Definition",
            "explanation": "The VIX measures expected 30-day volatility priced by S&P 500 index options.",
            "source": {
                "source_module": "market_setup_evidence_facts",
                "method_version": "vix_confirmation_v2",
            },
        },
        "object_index": [
            {
                "object_type": "indicator_definition",
                "object_id": "vix_definition",
                "authority": "method_knowledge",
                "payload": {
                    "title": "VIX Definition",
                    "explanation": "The VIX measures expected 30-day volatility priced by S&P 500 index options.",
                },
            }
        ],
        "integrity_hash": "d" * 64,
    }


def artifacts():
    return {
        artifact["artifact_id"]: artifact
        for artifact in (
            snapshot_artifact(),
            exploration_artifact(),
            research_artifact(),
            knowledge_artifact(),
        )
    }


def snapshot_ref(object_id, object_type="confirmation_test", **overrides):
    ref = {
        "artifact_id": "ctx_123",
        "object_type": object_type,
        "object_id": object_id,
    }
    ref.update(overrides)
    return ref


def exploration_ref(object_id, object_type="indicator_history", **overrides):
    ref = {
        "artifact_id": "expl_1",
        "object_type": object_type,
        "object_id": object_id,
    }
    ref.update(overrides)
    return ref


def research_ref(object_id, object_type="research_source", **overrides):
    ref = {
        "artifact_id": "res_1",
        "object_type": object_type,
        "object_id": object_id,
    }
    ref.update(overrides)
    return ref


def draft(claim, kind=None):
    section_kind = kind or _SECTION_BY_PURPOSE.get(claim["purpose"], "decision")
    return {"sections": [{"kind": section_kind, "claims": [claim]}]}


def valid_claim(**overrides):
    claim = {
        "claim_id": "c1",
        "purpose": "decision_explanation",
        "authority": "decision_fact",
        "refs": [snapshot_ref("vix_downside_confirmation")],
        "template": (
            "The approved downside rule requires VIX ≥ {vix_threshold}, and this "
            "confirmation test is not confirming."
        ),
        "bindings": {
            "vix_threshold": {
                "value": 20.0,
                "source": snapshot_ref("vix_downside_confirmation", field="threshold"),
            }
        },
    }
    claim.update(overrides)
    return claim


def observation_claim(template, **overrides):
    claim = {
        "claim_id": "c2",
        "purpose": "observation",
        "authority": "local_observation",
        "refs": [exploration_ref("vix_history")],
        "template": template,
        "bindings": {
            "first": {
                "value": 15.0,
                "source": exploration_ref("vix_history", field="first_value"),
            },
            "last": {
                "value": 18.4,
                "source": exploration_ref("vix_history", field="last_value"),
            },
        },
    }
    claim.update(overrides)
    return claim


def hypothetical_claim(template, bindings=None, arithmetic=None, **overrides):
    claim = {
        "claim_id": "h1",
        "purpose": "illustration",
        "authority": "hypothetical",
        "template": template,
        "bindings": bindings if bindings is not None else {},
    }
    if arithmetic is not None:
        claim["arithmetic"] = arithmetic
    claim.update(overrides)
    return claim


def vix_decision_draft():
    claim = {
        "claim_id": "vix_decision",
        "purpose": "decision_explanation",
        "authority": "decision_fact",
        "refs": [
            snapshot_ref("vix_level", object_type="evidence_fact"),
            snapshot_ref("vix_downside_confirmation"),
        ],
        "template": (
            "Current VIX is {vix_value}. The approved downside rule requires VIX ≥ "
            "{vix_threshold}, so this confirmation test is not confirming."
        ),
        "bindings": {
            "vix_value": {
                "value": 18.4,
                "source": snapshot_ref(
                    "vix_level", object_type="evidence_fact", field="level"
                ),
            },
            "vix_threshold": {
                "value": 20.0,
                "source": snapshot_ref("vix_downside_confirmation", field="threshold"),
            },
        },
    }
    return draft(claim)


def test_claim_cannot_cross_authority_boundary():
    claim = valid_claim(
        refs=[
            snapshot_ref("vix_downside_confirmation"),
            exploration_ref("vix_history"),
        ],
    )
    with pytest.raises(ValueError, match="claim crosses authority boundary"):
        validate_answer_draft(draft(claim), artifacts())


def test_unapproved_materiality_language_is_rejected():
    claim = observation_claim("VIX rose significantly from {first} to {last}.")
    with pytest.raises(ValueError, match="unsupported materiality language"):
        validate_answer_draft(draft(claim), artifacts())


def test_renderer_only_inserts_validated_bindings():
    validated = validate_answer_draft(vix_decision_draft(), artifacts())
    assert render_answer(validated, artifacts(), []) == (
        "Current VIX is 18.4. The approved downside rule requires VIX ≥ 20.0, "
        "so this confirmation test is not confirming."
    )


def test_artifacts_are_valid_envelopes():
    for artifact in artifacts().values():
        assert validate_artifact(artifact) == artifact


def test_valid_decision_claim_passes_validation():
    validated = validate_answer_draft(draft(valid_claim()), artifacts())
    assert validated is not None
    assert validated["sections"][0]["claims"][0]["claim_id"] == "c1"


def test_authority_purpose_mismatch_rejected():
    claim = valid_claim(
        purpose="decision_explanation",
        authority="local_observation",
        refs=[exploration_ref("vix_history")],
    )
    with pytest.raises(ValueError, match="authority does not permit purpose"):
        validate_answer_draft(draft(claim), artifacts())


def test_reference_to_missing_object_rejected():
    claim = valid_claim(refs=[snapshot_ref("missing_object")])
    with pytest.raises(ValueError, match="artifact object is not found"):
        validate_answer_draft(draft(claim), artifacts())


def test_reference_to_missing_artifact_rejected():
    claim = valid_claim(
        refs=[
            {
                "artifact_id": "ctx_999",
                "object_type": "confirmation_test",
                "object_id": "vix_downside_confirmation",
            }
        ]
    )
    with pytest.raises(ValueError, match="artifact reference is not found"):
        validate_answer_draft(draft(claim), artifacts())


def test_non_decision_claim_cannot_use_authoritative_snapshot():
    claim = {
        "claim_id": "c3",
        "purpose": "method_explanation",
        "authority": "method_knowledge",
        "refs": [snapshot_ref("vix_confirmation_v2", object_type="method_contract")],
        "template": "The VIX confirmation method uses the {method_operand} threshold.",
        "bindings": {
            "method_operand": {
                "value": 20.0,
                "source": snapshot_ref(
                    "vix_confirmation_v2",
                    object_type="method_contract",
                    field="predicates.downside.operand",
                ),
            }
        },
    }
    with pytest.raises(ValueError, match="authoritative snapshot"):
        validate_answer_draft(draft(claim, kind="knowledge"), artifacts())


def test_binding_field_not_found_rejected():
    claim = valid_claim(
        bindings={
            "vix_threshold": {
                "value": 20.0,
                "source": snapshot_ref(
                    "vix_downside_confirmation", field="missing_field"
                ),
            }
        }
    )
    with pytest.raises(ValueError, match="binding field is not found"):
        validate_answer_draft(draft(claim), artifacts())


def test_binding_value_mismatch_rejected():
    claim = valid_claim(
        bindings={
            "vix_threshold": {
                "value": 19.0,
                "source": snapshot_ref("vix_downside_confirmation", field="threshold"),
            }
        }
    )
    with pytest.raises(ValueError, match="binding value does not match"):
        validate_answer_draft(draft(claim), artifacts())


def test_unbound_factual_number_rejected():
    claim = valid_claim(
        template="Current VIX is {vix_threshold}, below the 20.0 floor."
    )
    with pytest.raises(ValueError, match="unbound factual literal"):
        validate_answer_draft(draft(claim), artifacts())


def test_unbound_factual_enum_rejected():
    claim = valid_claim(
        template="The regime is growth_decelerating today.", bindings={}
    )
    with pytest.raises(ValueError, match="unbound factual literal"):
        validate_answer_draft(draft(claim), artifacts())


def test_schema_only_validation_accepts_claim_policy_violation():
    claim = valid_claim(
        template="VIX is 18.4.",
        bindings={},
    )
    payload = draft(claim)

    with pytest.raises(DraftValidationError) as exc_info:
        validate_answer_draft(payload, artifacts())

    normalized = validate_answer_draft_schema(payload)

    assert exc_info.value.errors[0]["code"] == "UNBOUND_FACTUAL_LITERAL"
    assert normalized["sections"][0]["claims"][0]["template"] == "VIX is 18.4."


def test_schema_only_validation_still_rejects_invalid_shape():
    with pytest.raises(DraftValidationError) as exc_info:
        validate_answer_draft_schema({"sections": []})

    assert exc_info.value.errors[0]["code"] == "SCHEMA_INVALID"


def test_unvalidated_debug_renderer_substitutes_scalar_bindings_as_prose():
    payload = draft(
        valid_claim(
            template="现在的市场可以理解为：经济增长正在{direction}，但市场只确认了{confirmation}风险。",
            bindings={"direction": "放慢", "confirmation": "一部分"},
        )
    )

    rendered = render_unvalidated_debug_answer(payload, language="zh")

    assert (
        rendered == "现在的市场可以理解为：经济增长正在放慢，但市场只确认了一部分风险。"
    )
    assert "sections" not in rendered
    assert "bindings" not in rendered
    assert "authority" not in rendered


def test_unvalidated_debug_renderer_uses_annotated_value_without_resolving_source():
    claim = valid_claim(
        template="当前系统采用的是{posture}。",
        bindings={
            "posture": {
                "value": "轻度防守",
                "source": snapshot_ref(
                    "missing_object",
                    object_type="market_setup_result",
                    field="label",
                ),
            }
        },
    )

    assert (
        render_unvalidated_debug_answer(draft(claim), language="zh")
        == "当前系统采用的是轻度防守。"
    )


def test_unvalidated_debug_renderer_marks_unresolved_reference_unavailable():
    claim = valid_claim(
        template="当前波动率为{vix}。",
        bindings={
            "vix": snapshot_ref(
                "vix_level",
                object_type="evidence_fact",
                field="observed.value",
            )
        },
    )

    assert (
        render_unvalidated_debug_answer(draft(claim), language="zh")
        == "当前波动率为暂不可用。"
    )


def test_unvalidated_debug_renderer_replaces_missing_placeholder():
    claim = valid_claim(template="当前状态是{missing}。", bindings={})

    assert (
        render_unvalidated_debug_answer(draft(claim), language="zh")
        == "当前状态是暂不可用。"
    )


def test_non_hypothetical_scalar_binding_rejected():
    claim = valid_claim(
        template="Current VIX is {vix_value}.",
        bindings={"vix_value": 99.9},
    )
    with pytest.raises(ValueError, match="unbound factual literal"):
        validate_answer_draft(draft(claim), artifacts())


def test_hypothetical_scalar_binding_is_valid():
    claim = hypothetical_claim(
        "If the VIX were {vix_value}, the test would flip.",
        bindings={"vix_value": 25.0},
    )
    validated = validate_answer_draft(draft(claim, kind="illustration"), artifacts())
    assert validated is not None


def test_decision_language_rejected_for_observation_claim():
    claim = observation_claim("You should buy when the VIX exceeds {first}.")
    with pytest.raises(ValueError, match="prohibited decision claim"):
        validate_answer_draft(draft(claim), artifacts())


def test_prohibited_decision_language_rejected_for_decision_fact_claim():
    claim = valid_claim(template="You should buy NVDA now.")
    with pytest.raises(ValueError, match="prohibited decision claim"):
        validate_answer_draft(draft(claim), artifacts())


def test_predictive_language_rejected_for_decision_fact_claim():
    claim = valid_claim(template="This setup predicts a market crash.")
    with pytest.raises(ValueError, match="unsupported materiality language"):
        validate_answer_draft(draft(claim), artifacts())


def test_materiality_language_rejected_for_decision_fact_claim():
    claim = valid_claim(template="The setup is a strong downside setup.")
    with pytest.raises(ValueError, match="unsupported materiality language"):
        validate_answer_draft(draft(claim), artifacts())


def test_referenced_classification_allows_word_for_decision_fact_claim():
    artifact = snapshot_artifact()
    for obj in artifact["object_index"]:
        if (
            obj["object_type"] == "confirmation_test"
            and obj["object_id"] == "vix_downside_confirmation"
        ):
            obj["payload"]["classifications"] = {"result": "elevated"}
    local = artifacts()
    local["ctx_123"] = artifact
    claim = valid_claim(
        template="The confirmation test is elevated in the snapshot.",
        bindings={},
    )
    validated = validate_answer_draft(draft(claim), local)
    assert validated is not None


def test_materiality_language_rejected_for_hypothetical_claim():
    claim = hypothetical_claim(
        "If the VIX were {vix_value}, the move would be extreme.",
        bindings={"vix_value": 25.0},
    )
    with pytest.raises(ValueError, match="unsupported materiality language"):
        validate_answer_draft(draft(claim, kind="illustration"), artifacts())


@pytest.mark.parametrize(
    "template",
    [
        "当前信号显著恶化，因此应该买入。",
        "当前市场明显转弱。",
        "这属于极端行情。",
        "这是危险信号。",
        "这确认了避险情绪。",
    ],
)
def test_chinese_materiality_language_rejected_for_decision_fact_claim(template):
    claim = valid_claim(template=template, bindings={})
    with pytest.raises(ValueError, match="unsupported materiality language"):
        validate_answer_draft(draft(claim), artifacts())


@pytest.mark.parametrize(
    "template",
    [
        "现在应该买入。",
        "现在应该卖出。",
        "建议建立头寸。",
        "建议平仓。",
        "可以加仓。",
        "建议减仓。",
    ],
)
def test_chinese_decision_language_rejected_for_decision_fact_claim(template):
    claim = valid_claim(template=template, bindings={})
    with pytest.raises(ValueError, match="prohibited decision claim"):
        validate_answer_draft(draft(claim), artifacts())


def test_external_source_title_word_does_not_exempt_materiality():
    source_artifact = research_artifact()
    source_artifact["artifact_id"] = "res_sig"
    source_artifact["payload"]["sources"][0]["title"] = "Significant Market Update"
    source_artifact["object_index"][0]["payload"]["title"] = "Significant Market Update"
    local = artifacts()
    local["res_sig"] = source_artifact
    claim = {
        "claim_id": "c8",
        "purpose": "bounded_interpretation",
        "authority": "external_research",
        "refs": [
            {
                "artifact_id": "res_sig",
                "object_type": "research_source",
                "object_id": "src_1",
            }
        ],
        "template": "The external report is a significant update.",
        "bindings": {},
    }
    with pytest.raises(ValueError, match="unsupported materiality language"):
        validate_answer_draft(draft(claim, kind="observation"), local)


def test_referenced_classification_field_allows_approved_word():
    source_artifact = research_artifact()
    source_artifact["artifact_id"] = "res_cls"
    source_artifact["object_index"][0]["payload"]["classifications"] = {
        "level": "elevated"
    }
    local = artifacts()
    local["res_cls"] = source_artifact
    claim = {
        "claim_id": "c9",
        "purpose": "bounded_interpretation",
        "authority": "external_research",
        "refs": [
            {
                "artifact_id": "res_cls",
                "object_type": "research_source",
                "object_id": "src_1",
            }
        ],
        "template": "The external report shows an elevated update.",
        "bindings": {},
    }
    validated = validate_answer_draft(draft(claim, kind="observation"), local)
    assert validated is not None


def test_hypothetical_claim_requires_illustration_purpose():
    claim = hypothetical_claim(
        "If the VIX were {vix_value}, the test would flip.",
        bindings={"vix_value": 25.0},
    )
    claim["purpose"] = "decision_explanation"
    with pytest.raises(ValueError, match="authority does not permit purpose"):
        validate_answer_draft(draft(claim), artifacts())


def test_hypothetical_claim_renders_example_label():
    claim = hypothetical_claim(
        "If the VIX were {vix_value}, the test would not confirm.",
        bindings={"vix_value": 25.0},
    )
    validated = validate_answer_draft(draft(claim, kind="illustration"), artifacts())
    assert render_answer(validated, artifacts(), []) == (
        "[Example] If the VIX were 25.0, the test would not confirm."
    )


def test_hypothetical_cannot_reference_artifacts():
    claim = hypothetical_claim(
        "If the VIX were {vix_value}, the test would flip.",
        bindings={"vix_value": 25.0},
    )
    claim["refs"] = [snapshot_ref("vix_level", object_type="evidence_fact")]
    with pytest.raises(ValueError, match="hypothetical"):
        validate_answer_draft(draft(claim, kind="illustration"), artifacts())


def test_hypothetical_binding_cannot_reference_semantic_field():
    claim = hypothetical_claim(
        "If the VIX were {vix_value}, the test would flip.",
        bindings={
            "vix_value": {
                "value": 25.0,
                "source": snapshot_ref(
                    "vix_level", object_type="evidence_fact", field="level"
                ),
            }
        },
    )
    with pytest.raises(ValueError, match="hypothetical"):
        validate_answer_draft(draft(claim, kind="illustration"), artifacts())


def test_hypothetical_arithmetic_computed_by_calculator():
    claim = hypothetical_claim(
        "If VIX were {vix_value} and the threshold {vix_threshold}, the gap is {gap}.",
        bindings={"vix_value": 18.4, "vix_threshold": 20.0},
        arithmetic={
            "operation": "add",
            "operands": [1.5, 2.5],
            "result_binding": "gap",
        },
    )
    validated = validate_answer_draft(draft(claim, kind="illustration"), artifacts())
    assert render_answer(validated, artifacts(), []) == (
        "[Example] If VIX were 18.4 and the threshold 20.0, the gap is 4.0."
    )


def test_hypothetical_division_by_zero_is_typed_unavailable():
    claim = hypothetical_claim(
        "The ratio would be {ratio}.",
        arithmetic={
            "operation": "divide",
            "operands": [5.0, 0.0],
            "result_binding": "ratio",
        },
    )
    validated = validate_answer_draft(draft(claim, kind="illustration"), artifacts())
    assert (
        render_answer(validated, artifacts(), [])
        == "[Example] The ratio would be unavailable."
    )


def test_arithmetic_only_permitted_for_hypothetical():
    claim = valid_claim(
        arithmetic={"operation": "add", "operands": [1, 2], "result_binding": "gap"}
    )
    with pytest.raises(
        ValueError, match="arithmetic is only permitted for hypothetical"
    ):
        validate_answer_draft(draft(claim), artifacts())


def test_research_claim_requires_source_citation():
    claim = {
        "claim_id": "c5",
        "purpose": "observation",
        "authority": "external_research",
        "refs": [research_ref("fnd_1", object_type="research_finding")],
        "template": "The report {fnd_statement} is relevant.",
        "bindings": {
            "fnd_statement": {
                "value": "The Federal Reserve reported a rate decision.",
                "source": research_ref(
                    "fnd_1", object_type="research_finding", field="statement"
                ),
            }
        },
    }
    with pytest.raises(ValueError, match="research citation is required"):
        validate_answer_draft(draft(claim), artifacts())


def test_valid_research_claim_collects_citation():
    claim = {
        "claim_id": "c6",
        "purpose": "source_explanation",
        "authority": "external_research",
        "refs": [research_ref("src_1")],
        "template": "The Federal Reserve published {pub_date}.",
        "bindings": {
            "pub_date": {
                "value": "2026-08-09",
                "source": research_ref("src_1", field="publication_date"),
            }
        },
    }
    validated = validate_answer_draft(draft(claim), artifacts())
    assert collect_citations(validated, artifacts()) == [
        {
            "source_id": "src_1",
            "title": "Federal Reserve Press Release",
            "url": "https://www.federalreserve.gov/press-release.htm",
            "publisher": "federalreserve.gov",
            "publication_date": "2026-08-09",
            "event_date": "2026-08-09",
        }
    ]


def test_collect_citations_only_includes_referenced_sources():
    claim = {
        "claim_id": "c7",
        "purpose": "source_explanation",
        "authority": "external_research",
        "refs": [research_ref("src_2")],
        "template": "Example Finance covered the {pub_date} release.",
        "bindings": {
            "pub_date": {
                "value": "2026-08-09",
                "source": research_ref("src_2", field="publication_date"),
            }
        },
    }
    validated = validate_answer_draft(draft(claim), artifacts())
    citations = collect_citations(validated, artifacts())
    assert [citation["source_id"] for citation in citations] == ["src_2"]


def test_unknown_template_placeholder_rejected():
    claim = valid_claim(template="Current VIX is {missing_placeholder}.")
    with pytest.raises(ValueError, match="template placeholder is not bound"):
        validate_answer_draft(draft(claim), artifacts())


def test_unused_binding_rejected():
    claim = valid_claim(template="The test is not confirming today.")
    claim["bindings"]["extra"] = 5.0
    with pytest.raises(ValueError, match="binding is not used in template"):
        validate_answer_draft(draft(claim), artifacts())


def test_duplicate_claim_ids_rejected():
    payload = {
        "sections": [
            {"kind": "decision", "claims": [valid_claim(claim_id="dup")]},
            {"kind": "decision", "claims": [valid_claim(claim_id="dup")]},
        ]
    }
    with pytest.raises(ValueError, match="claim id is duplicated"):
        validate_answer_draft(payload, artifacts())


def test_section_kind_mismatch_rejected():
    claim = valid_claim()
    with pytest.raises(ValueError, match="claim purpose does not match section kind"):
        validate_answer_draft(draft(claim, kind="research"), artifacts())


def test_claim_in_matching_section_is_valid():
    claim = valid_claim()
    validated = validate_answer_draft(draft(claim, kind="decision"), artifacts())
    assert validated is not None


def test_claim_limit_exceeded_rejected():
    claims = [valid_claim(claim_id=f"c{index}") for index in range(25)]
    payload = {"sections": [{"kind": "decision", "claims": claims}]}
    with pytest.raises(ValueError, match="answer exceeds the claim limit"):
        validate_answer_draft(payload, artifacts())


def test_malformed_claim_purpose_rejected_with_schema_code():
    claim = valid_claim(purpose="not_a_purpose")
    with pytest.raises(DraftValidationError) as exc_info:
        validate_answer_draft(draft(claim), artifacts())
    assert exc_info.value.errors[0]["code"] == "SCHEMA_INVALID"


def test_extra_draft_fields_rejected():
    payload = {
        "sections": [{"kind": "decision", "claims": [valid_claim()]}],
        "extra": 1,
    }
    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        validate_answer_draft(payload, artifacts())


def test_validation_error_carries_error_records():
    claim = valid_claim(
        purpose="decision_explanation",
        authority="local_observation",
        refs=[exploration_ref("vix_history")],
    )
    with pytest.raises(DraftValidationError) as exc_info:
        validate_answer_draft(draft(claim), artifacts())
    assert exc_info.value.errors[0]["code"] == "AUTHORITY_PURPOSE_MISMATCH"


def test_build_validation_report_is_sanitized():
    errors = [
        {
            "code": "UNSUPPORTED_MATERIALITY",
            "message": "unsupported materiality language",
            "claim_id": "c1",
            "field_id": "template",
            "expected": "no materiality language",
            "actual": "significantly",
            "traceback": "pretend stack trace",
        },
        {
            "code": "REFERENCE_AUTHORITY_MISMATCH",
            "message": "claim crosses authority boundary",
            "claim_id": "c2",
            "field_id": None,
            "expected": "decision_fact",
            "actual": "local_observation",
        },
    ]
    report = build_validation_report(errors)
    assert report["valid"] is False
    assert report["error_count"] == 2
    assert report["errors"][0]["code"] == "UNSUPPORTED_MATERIALITY"
    assert "traceback" not in report["errors"][0]
    assert report["errors"][1]["actual"] == "local_observation"


def test_build_validation_report_drops_unknown_codes():
    report = build_validation_report(
        [
            {"code": "NOT_A_CODE", "message": "boom", "claim_id": "c1"},
            {
                "code": "FIELD_NOT_FOUND",
                "message": "binding field is not found",
                "claim_id": "c2",
                "field_id": "level",
            },
        ]
    )
    assert report["error_count"] == 1
    assert report["errors"][0]["code"] == "FIELD_NOT_FOUND"


def test_build_validation_report_requires_error_list():
    with pytest.raises(ValueError, match="validation errors are required"):
        build_validation_report("nope")


def test_calculate_hypothetical_basic_operations():
    assert calculate_hypothetical("add", [1.5, 2.5]) == {
        "state": "calculated",
        "value": 4.0,
        "operation": "add",
        "operands": [1.5, 2.5],
    }
    assert calculate_hypothetical("subtract", [10, 3]) == {
        "state": "calculated",
        "value": 7,
        "operation": "subtract",
        "operands": [10, 3],
    }
    assert calculate_hypothetical("multiply", [3, 4]) == {
        "state": "calculated",
        "value": 12,
        "operation": "multiply",
        "operands": [3, 4],
    }


def test_calculate_hypothetical_division_by_zero():
    assert calculate_hypothetical("divide", [5.0, 0.0]) == {
        "state": "unavailable",
        "reason_code": "division_by_zero",
        "operation": "divide",
        "operands": [5.0, 0.0],
    }


def test_calculate_hypothetical_rejects_non_finite_operand():
    with pytest.raises(ValueError, match="operand must be finite"):
        calculate_hypothetical("add", [float("inf"), 1.0])
    with pytest.raises(ValueError, match="operand must be finite"):
        calculate_hypothetical("add", [1.0, float("nan")])


def test_calculate_hypothetical_rejects_unknown_operation():
    with pytest.raises(ValueError, match="operation is not supported"):
        calculate_hypothetical("pow", [2, 3])


def test_calculate_hypothetical_rejects_empty_operands():
    with pytest.raises(ValueError, match="operands are required"):
        calculate_hypothetical("add", [])


def test_render_appends_notices_and_escapes_unsafe_output():
    validated = validate_answer_draft(vix_decision_draft(), artifacts())
    rendered = render_answer(validated, artifacts(), [{"text": "Data as of <as_of>"}])
    assert rendered.endswith("Data as of &lt;as_of&gt;")
    assert "<as_of>" not in rendered


def test_render_escapes_claim_template_output():
    claim = valid_claim(template='Current VIX {vix_threshold} & above "quotes".')
    validated = validate_answer_draft(draft(claim), artifacts())
    rendered = render_answer(validated, artifacts(), [])
    assert "&amp;" in rendered
    assert '"' not in rendered.replace("&quot;", "")


def test_render_groups_sections_with_backend_headings():
    payload = {
        "sections": [
            {"kind": "decision", "claims": [valid_claim()]},
            {
                "kind": "observation",
                "claims": [
                    observation_claim("The VIX window runs from {first} to {last}.")
                ],
            },
        ]
    }
    validated = validate_answer_draft(payload, artifacts())
    rendered = render_answer(validated, artifacts(), [])
    assert "Local Observations" in rendered


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("现在市场怎么样？", "zh"),
        ("为什么是 Mild Risk-Off？", "zh"),
        ("Explain the market setup", "en"),
        ("", "en"),
    ],
)
def test_detect_answer_language(question, expected):
    assert detect_answer_language(question) == expected


def test_render_answer_localizes_chinese_observation_heading():
    claim = observation_claim("VIX 当前为 {first}，最新为 {last}。")
    validated = validate_answer_draft(draft(claim, kind="observation"), artifacts())

    rendered = render_answer(validated, artifacts(), [], language="zh")

    assert rendered.startswith("本地数据观察\n")
    assert "Local Observations" not in rendered


def test_render_fallback_decision_renders_four_layers_and_path():
    plan = _fallback_plan("decision_explanation")
    rendered = render_fallback(plan=plan, artifacts=artifacts(), notices=[])
    assert "Macro Regime" in rendered
    assert "growth_decelerating" in rendered
    assert "Defensive Posture" in rendered
    assert "Macro Thesis" in rendered
    assert "Portfolio Action" in rendered


def test_render_fallback_method_renders_contract_and_predicate():
    plan = _fallback_plan("method")
    rendered = render_fallback(plan=plan, artifacts=artifacts(), notices=[])
    assert "vix_confirmation_v2" in rendered
    assert "20.0" in rendered


def test_render_fallback_knowledge_renders_record_prose():
    plan = _fallback_plan("definition")
    rendered = render_fallback(plan=plan, artifacts=artifacts(), notices=[])
    assert "expected 30-day volatility" in rendered


def test_render_fallback_exploration_renders_rows_and_statistics():
    plan = _fallback_plan("local_history")
    rendered = render_fallback(plan=plan, artifacts=artifacts(), notices=[])
    assert "2026-07-01" in rendered
    assert "18.4" in rendered


def test_render_fallback_research_reports_unavailable_and_local_facts():
    plan = _fallback_plan("external_research")
    rendered = render_fallback(plan=plan, artifacts=artifacts(), notices=[])
    assert "unavailable" in rendered
    assert "VIX" in rendered


def test_render_fallback_teaching_reports_could_not_generate():
    plan = _fallback_plan("illustration")
    rendered = render_fallback(plan=plan, artifacts=artifacts(), notices=[])
    assert "could not be generated" in rendered


def test_render_fallback_unsupported_is_deterministic():
    plan = _fallback_plan("unsupported")
    rendered = render_fallback(plan=plan, artifacts={}, notices=[])
    assert "cannot be answered deterministically" in rendered


def test_render_fallback_missing_snapshot_is_deterministic():
    plan = _fallback_plan("decision_explanation")
    rendered = render_fallback(plan=plan, artifacts={}, notices=[])
    assert "unavailable" in rendered


def _fallback_plan(intent):
    return {
        "intent": intent,
        "context_mode": "current",
        "operations": [],
        "answer_depth": "standard",
        "research_tier": None,
    }
