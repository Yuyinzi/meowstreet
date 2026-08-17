import pytest

from app.tools.market_assistant_claim_audit import AuditValidationError
from app.tools.market_assistant_claim_audit import build_audit_validation_report
from app.tools.market_assistant_claim_audit import validate_claim_audit


def setup_result_ref():
    return {
        "artifact_id": "ctx_123",
        "object_type": "market_setup_result",
        "object_id": "macro_regime",
    }


def exploration_ref():
    return {
        "artifact_id": "expl_1",
        "object_type": "indicator_history",
        "object_id": "vix_history",
    }


def setup_artifacts():
    snapshot = {
        "artifact_id": "ctx_123",
        "artifact_kind": "explanation_snapshot",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": {
            "context_id": "ctx_123",
            "results": {
                "macro_regime": {"code": "bull_market", "label": "Bull Market"},
                "market_confirmation": {
                    "code": "risk_rising",
                    "label": "Risk Rising",
                },
            },
        },
        "object_index": [
            {
                "object_type": "market_setup_result",
                "object_id": "macro_regime",
                "authority": "decision_fact",
                "payload": {
                    "code": "bull_market",
                    "label": "Bull Market",
                    "risk_score": 2,
                },
            },
            {
                "object_type": "market_setup_result",
                "object_id": "market_confirmation",
                "authority": "decision_fact",
                "payload": {
                    "code": "risk_rising",
                    "label": "Risk Rising",
                    "risk_level": 3,
                },
            },
        ],
        "integrity_hash": "a" * 64,
    }
    exploration = {
        "artifact_id": "expl_1",
        "artifact_kind": "exploration_result",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "local_observation",
        "market_setup_relation": "non_decision",
        "payload": {},
        "object_index": [
            {
                "object_type": "indicator_history",
                "object_id": "vix_history",
                "authority": "local_observation",
                "payload": {"first_value": 15.0, "last_value": 18.4},
            }
        ],
        "integrity_hash": "b" * 64,
    }
    return {
        snapshot["artifact_id"]: snapshot,
        exploration["artifact_id"]: exploration,
    }


def audit_payload(answer, **span_overrides):
    span = {
        "claim_id": "claim_1",
        "start": 0,
        "end": len(answer),
        "exact_text": answer,
        "purpose": "decision_explanation",
        "authority": "decision_fact",
        "refs": [setup_result_ref()],
        "values": [],
    }
    span.update(span_overrides)
    return {"claims": [span]}


def policy_detail_ref():
    return {
        "artifact_id": "ctx_123_evidence_detail_macro_policy_response",
        "object_type": "evidence_detail",
        "object_id": "ctx_123_evidence_detail_macro_policy_response",
    }


def policy_detail_artifacts():
    projection = {
        "fact_id": "macro_policy_response",
        "label": "Monetary Policy",
        "detail_kind": "policy_response",
        "topics": ["current", "drivers", "source"],
        "status": "available",
        "current": {
            "policy_action": "hold",
            "overall_bias": "mild_hawkish",
            "relationship_to_growth_direction": "conflicts",
        },
        "drivers": {"policy_reason": "detail_only_policy_reason_7f21"},
        "source": {
            "source_module": "fomc_policy_tone",
            "source_period": {
                "effective_date": "2026-07-01",
                "reference_period": "2026-06",
                "release_date": "2026-07-01",
            },
        },
    }
    ref = policy_detail_ref()
    artifact_id = ref["artifact_id"]
    decision_payload = {
        key: value
        for key, value in projection.items()
        if key not in ("method", "source")
    }
    return {
        artifact_id: {
            "artifact_id": artifact_id,
            "artifact_kind": "explanation_snapshot",
            "schema_version": "market_assistant_artifact_v1",
            "primary_authority": "decision_fact",
            "market_setup_relation": "authoritative_snapshot",
            "payload": {
                "fact_id": projection["fact_id"],
                "detail_kind": projection["detail_kind"],
                "topics": projection["topics"],
                "status": projection["status"],
                "detail": projection,
            },
            "object_index": [
                {
                    "object_type": "evidence_detail",
                    "object_id": artifact_id,
                    "authority": "decision_fact",
                    "payload": decision_payload,
                },
                {
                    "object_type": "evidence_detail_source",
                    "object_id": f"{artifact_id}_source",
                    "authority": "method_knowledge",
                    "payload": {"source": projection["source"]},
                },
            ],
            "integrity_hash": "c" * 64,
        }
    }


def test_audit_accepts_exact_referenced_span():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "start": 0,
                "end": len(answer),
                "exact_text": answer,
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [setup_result_ref()],
                "values": [],
            }
        ]
    }
    validated = validate_claim_audit(
        payload,
        answer_text=answer,
        artifacts=setup_artifacts(),
    )
    assert validated["coverage_ratio"] == 1.0
    assert validated["claims"][0]["claim_id"] == "claim_1"
    assert (
        validated["coverage"]["covered_chars"]
        == validated["coverage"]["eligible_chars"]
    )


def test_audit_rejects_wrong_exact_span():
    answer = "现在的市场偏积极。"
    payload = audit_payload(answer, exact_text="现在的市场非常积极。")
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_validation_error_carries_error_records():
    answer = "现在的市场偏积极。"
    payload = audit_payload(answer, exact_text="现在的市场非常积极。")
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())
    assert exc_info.value.errors[0]["code"] == "ANSWER_TEXT_MISMATCH"


def test_audit_accepts_exact_multiple_spans_union_coverage():
    answer = "现在的市场偏积极。市场尚未全面确认。"
    mid = 10
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "start": 0,
                "end": mid,
                "exact_text": answer[0:mid],
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [setup_result_ref()],
                "values": [],
            },
            {
                "claim_id": "claim_2",
                "start": mid,
                "end": len(answer),
                "exact_text": answer[mid : len(answer)],
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [setup_result_ref()],
                "values": [],
            },
        ]
    }
    validated = validate_claim_audit(
        payload,
        answer_text=answer,
        artifacts=setup_artifacts(),
    )
    assert validated["coverage_ratio"] == 1.0


def test_audit_rejects_local_observation_as_decision_explanation():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = audit_payload(
        answer,
        authority="local_observation",
        refs=[exploration_ref()],
    )
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_authority_crossing_reference():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = audit_payload(answer, refs=[exploration_ref()])
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_nonexistent_semantic_ref():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = audit_payload(
        answer,
        refs=[
            {
                "artifact_id": "ctx_999",
                "object_type": "market_setup_result",
                "object_id": "macro_regime",
            }
        ],
    )
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_accepts_matching_bound_value():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = audit_payload(
        answer,
        values=[
            {
                "name": "risk_score",
                "value": 2,
                "source": {**setup_result_ref(), "field": "risk_score"},
            }
        ],
    )
    validated = validate_claim_audit(
        payload,
        answer_text=answer,
        artifacts=setup_artifacts(),
    )
    assert validated["coverage_ratio"] == 1.0


def test_audit_rejects_mismatched_bound_value():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = audit_payload(
        answer,
        values=[
            {
                "name": "risk_score",
                "value": 5,
                "source": {**setup_result_ref(), "field": "risk_score"},
            }
        ],
    )
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_string_value_for_numeric_field_without_coercion():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    payload = audit_payload(
        answer,
        values=[
            {
                "name": "risk_score",
                "value": "2",
                "source": {**setup_result_ref(), "field": "risk_score"},
            }
        ],
    )
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_accepts_policy_action_and_overall_bias_bindings():
    answer = "The latest decision was a hold and the approved read was mildly hawkish."
    payload = audit_payload(
        answer,
        refs=[policy_detail_ref()],
        values=[
            {
                "name": "policy_action",
                "value": "hold",
                "source": {**policy_detail_ref(), "field": "current.policy_action"},
                "text": "The latest decision was a hold and",
            },
            {
                "name": "overall_bias",
                "value": "mild_hawkish",
                "source": {**policy_detail_ref(), "field": "current.overall_bias"},
                "text": " the approved read was mildly hawkish.",
            },
        ],
    )
    validated = validate_claim_audit(
        payload,
        answer_text=answer,
        artifacts=policy_detail_artifacts(),
    )
    assert validated["coverage_ratio"] == 1.0
    assert validated["claims"][0]["claim_id"] == "claim_1"


def test_audit_rejects_mismatched_policy_action_binding():
    answer = "The latest decision was a cut and the approved read was mildly hawkish."
    payload = audit_payload(
        answer,
        refs=[policy_detail_ref()],
        values=[
            {
                "name": "policy_action",
                "value": "cut",
                "source": {**policy_detail_ref(), "field": "current.policy_action"},
            }
        ],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    assert any(
        error["code"] == "BINDING_VALUE_MISMATCH" for error in exc_info.value.errors
    )


def test_audit_rejects_supposed_quote_binding_to_nonexistent_exact_excerpt():
    answer = 'The FOMC statement reportedly used the phrase "remain patient".'
    payload = audit_payload(
        answer,
        refs=[policy_detail_ref()],
        values=[
            {
                "name": "exact_quote",
                "value": "remain patient",
                "source": {**policy_detail_ref(), "field": "exact_excerpt"},
            }
        ],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    matching = [
        error for error in exc_info.value.errors if error["code"] == "FIELD_NOT_FOUND"
    ]
    assert matching
    assert matching[0]["field_id"] == "exact_quote"
    assert matching[0]["expected"] == "exact_excerpt"


def test_audit_rejects_source_binding_via_decision_fact_authority():
    answer = "The data comes from the July policy meeting."
    payload = audit_payload(
        answer,
        refs=[policy_detail_ref()],
        values=[
            {
                "name": "source_period",
                "value": "2026-07-01",
                "source": {
                    **policy_detail_ref(),
                    "field": "source.source_period.effective_date",
                },
            }
        ],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    assert any(
        error["code"] in {"FIELD_NOT_FOUND", "REFERENCE_AUTHORITY_MISMATCH"}
        for error in exc_info.value.errors
    )


def test_audit_rejects_decision_fact_claim_referencing_source_object():
    answer = "The data comes from the July policy meeting."
    source_ref = {
        "artifact_id": "ctx_123_evidence_detail_macro_policy_response",
        "object_type": "evidence_detail_source",
        "object_id": "ctx_123_evidence_detail_macro_policy_response_source",
    }
    payload = audit_payload(
        answer,
        purpose="decision_explanation",
        authority="decision_fact",
        refs=[source_ref],
        values=[
            {
                "name": "source_period",
                "value": "2026-07-01",
                "source": {
                    **source_ref,
                    "field": "source.source_period.effective_date",
                },
            }
        ],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    assert any(
        error["code"] == "REFERENCE_AUTHORITY_MISMATCH"
        for error in exc_info.value.errors
    )


def test_audit_accepts_source_binding_via_method_knowledge_authority():
    answer = "The data comes from the 2026-07-01 policy meeting."
    ref = {
        "artifact_id": "ctx_123_evidence_detail_macro_policy_response",
        "object_type": "evidence_detail_source",
        "object_id": "ctx_123_evidence_detail_macro_policy_response_source",
    }
    payload = audit_payload(
        answer,
        purpose="source_explanation",
        authority="method_knowledge",
        refs=[ref],
        values=[
            {
                "name": "source_period",
                "value": "2026-07-01",
                "source": {**ref, "field": "source.source_period.effective_date"},
                "text": "The data comes from the 2026-07-01 policy meeting.",
            }
        ],
    )
    validated = validate_claim_audit(
        payload,
        answer_text=answer,
        artifacts=policy_detail_artifacts(),
    )
    assert validated["coverage_ratio"] == 1.0


def test_audit_rejects_method_binding_via_decision_fact_authority():
    answer = "The approved method determines the market phase."
    payload = audit_payload(
        answer,
        refs=[policy_detail_ref()],
        values=[
            {
                "name": "method_reference",
                "value": "fomc_policy_tone_method_v1",
                "source": {**policy_detail_ref(), "field": "method.method_references"},
            }
        ],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    assert any(
        error["code"] in {"REFERENCE_NOT_FOUND", "FIELD_NOT_FOUND"}
        for error in exc_info.value.errors
    )


def test_audit_rejects_exact_wording_claim_without_capable_artifact():
    answer = "The FOMC statement said remain patient."
    payload = audit_payload(
        answer,
        purpose="exact_wording",
        authority="method_knowledge",
        refs=[policy_detail_ref()],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    assert any(
        error["code"] == "EXACT_WORDING_UNAVAILABLE" for error in exc_info.value.errors
    )


def test_audit_rejects_exact_wording_claim_without_any_refs():
    answer = "The FOMC statement said remain patient."
    payload = audit_payload(
        answer,
        purpose="exact_wording",
        authority="method_knowledge",
        refs=[],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=policy_detail_artifacts(),
        )
    assert any(
        error["code"] == "EXACT_WORDING_UNAVAILABLE" for error in exc_info.value.errors
    )


def test_audit_rejects_exact_wording_without_approved_source_contract():
    answer = "The data comes from the July policy meeting."
    source_artifact = policy_detail_artifacts()
    ref = {
        "artifact_id": "ctx_123_evidence_detail_macro_policy_response",
        "object_type": "evidence_detail_source",
        "object_id": "ctx_123_evidence_detail_macro_policy_response_source",
    }
    payload = audit_payload(
        answer,
        purpose="exact_wording",
        authority="method_knowledge",
        refs=[ref],
        values=[
            {
                "name": "source_module",
                "value": "fomc_policy_tone",
                "source": {**ref, "field": "source.source_module"},
            }
        ],
    )
    with pytest.raises(AuditValidationError) as exc_info:
        validate_claim_audit(
            payload,
            answer_text=answer,
            artifacts=source_artifact,
        )
    assert any(
        error["code"] == "EXACT_WORDING_UNAVAILABLE" for error in exc_info.value.errors
    )


def test_audit_rejects_hypothetical_span_with_refs():
    answer = "如果市场风险上升，结果会不同。"
    payload = {
        "claims": [
            {
                "claim_id": "h1",
                "start": 0,
                "end": len(answer),
                "exact_text": answer,
                "purpose": "illustration",
                "authority": "hypothetical",
                "refs": [setup_result_ref()],
                "values": [],
            }
        ]
    }
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_accepts_hypothetical_span_without_refs():
    answer = "如果市场风险上升，结果会不同。"
    payload = {
        "claims": [
            {
                "claim_id": "h1",
                "start": 0,
                "end": len(answer),
                "exact_text": answer,
                "purpose": "illustration",
                "authority": "hypothetical",
                "refs": [],
                "values": [],
            }
        ]
    }
    validated = validate_claim_audit(
        payload,
        answer_text=answer,
        artifacts=setup_artifacts(),
    )
    assert validated["coverage_ratio"] == 1.0


def test_audit_rejects_more_than_twenty_four_spans():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    claims = []
    for index in range(25):
        claims.append(
            {
                "claim_id": f"claim_{index}",
                "start": 0,
                "end": len(answer),
                "exact_text": answer,
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [setup_result_ref()],
                "values": [],
            }
        )
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(
            {"claims": claims},
            answer_text=answer,
            artifacts=setup_artifacts(),
        )


def test_audit_rejects_overlapping_spans():
    answer = "现在的市场偏积极，但仍没有得到全面确认。"
    first_end = 10
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "start": 0,
                "end": first_end,
                "exact_text": answer[0:first_end],
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [setup_result_ref()],
                "values": [],
            },
            {
                "claim_id": "claim_2",
                "start": 8,
                "end": 16,
                "exact_text": answer[8:16],
                "purpose": "decision_explanation",
                "authority": "decision_fact",
                "refs": [setup_result_ref()],
                "values": [],
            },
        ]
    }
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_low_eligible_character_coverage():
    answer = "a" * 79 + " " + "b" * 21
    payload = audit_payload(answer, end=79, exact_text="a" * 79)
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


@pytest.mark.parametrize(
    "code",
    ["bull_market", "risk_rising", "modest_long"],
)
def test_audit_rejects_internal_code_in_beginner_narration(code):
    answer = f"当前市场处于{code}状态。"
    payload = audit_payload(answer)
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_unsupported_materiality_language():
    answer = "市场明显转弱。"
    payload = audit_payload(answer)
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_ticker_level_buy_sell_instruction():
    answer = "现在应该买入。"
    payload = audit_payload(answer)
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(payload, answer_text=answer, artifacts=setup_artifacts())


def test_audit_rejects_malformed_payload_shape():
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(
            {"claims": []},
            answer_text="现在的市场偏积极。",
            artifacts=setup_artifacts(),
        )
    with pytest.raises(ValueError, match="claim audit validation failed"):
        validate_claim_audit(
            "not a dict",
            answer_text="现在的市场偏积极。",
            artifacts=setup_artifacts(),
        )


def test_audit_report_is_sanitized():
    errors = [
        {
            "code": "COVERAGE_TOO_LOW",
            "message": "claim spans do not cover the required answer share",
            "claim_id": None,
            "field_id": None,
            "expected": "80%",
            "actual": "79%",
            "traceback": "pretend stack trace",
            "sql": "SELECT * FROM secrets;",
            "credentials": "api_key=abc123",
            "path": "/private/var/secrets/audit.log",
        },
        {
            "code": "ANSWER_TEXT_MISMATCH",
            "message": "claim span does not match the answer text",
            "claim_id": "claim_1",
            "field_id": "exact_text",
            "expected": "现在的市场偏积极。",
            "actual": "现在的市场非常积极。",
        },
    ]
    report = build_audit_validation_report(errors)
    assert report["valid"] is False
    assert report["error_count"] == 2
    assert report["errors"][0]["code"] == "COVERAGE_TOO_LOW"
    assert "traceback" not in report["errors"][0]
    assert "sql" not in report["errors"][0]
    assert "credentials" not in report["errors"][0]
    assert "path" not in report["errors"][0]
    assert report["errors"][1]["actual"] == "现在的市场非常积极。"


def test_audit_report_drops_unknown_codes():
    report = build_audit_validation_report(
        [
            {"code": "NOT_A_CODE", "message": "boom", "claim_id": "c1"},
            {
                "code": "FIELD_NOT_FOUND",
                "message": "bound field is not found",
                "claim_id": "c2",
            },
        ]
    )
    assert report["error_count"] == 1
    assert report["errors"][0]["code"] == "FIELD_NOT_FOUND"


def test_audit_report_requires_error_list():
    with pytest.raises(ValueError, match="validation errors are required"):
        build_audit_validation_report("nope")
