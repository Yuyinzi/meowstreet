import pytest

from app.tools import market_assistant_artifacts


def valid_artifact(**overrides):
    artifact = {
        "artifact_id": "ctx_123",
        "artifact_kind": "explanation_snapshot",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": {"context_id": "ctx_123"},
        "object_index": [
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"value": 18.4},
            }
        ],
        "integrity_hash": "a" * 64,
    }
    artifact.update(overrides)
    return artifact


def test_local_observation_cannot_explain_a_decision():
    assert not market_assistant_artifacts.authority_allows_purpose(
        "local_observation", "decision_explanation"
    )


def test_reference_resolves_stable_object_id_not_json_path():
    artifact = valid_artifact(
        object_index=[
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"value": 18.4},
            }
        ]
    )
    resolved = market_assistant_artifacts.resolve_artifact_ref(
        {artifact["artifact_id"]: artifact},
        {
            "artifact_id": artifact["artifact_id"],
            "object_type": "evidence_fact",
            "object_id": "vix_level",
        },
    )
    assert resolved["payload"]["value"] == 18.4


def test_authority_purpose_matrix_is_exact():
    allowed = {
        "decision_explanation": {"decision_fact"},
        "counterfactual_explanation": {"decision_fact"},
        "method_explanation": {"method_knowledge"},
        "source_explanation": {"method_knowledge", "external_research"},
        "governance_explanation": {"decision_fact", "method_knowledge"},
        "observation": {"local_observation", "external_research"},
        "bounded_interpretation": {"local_observation", "external_research"},
        "illustration": {"hypothetical"},
    }
    authorities = [
        "decision_fact",
        "method_knowledge",
        "local_observation",
        "external_research",
        "hypothetical",
    ]
    for authority in authorities:
        for purpose in allowed:
            expected = authority in allowed[purpose]
            assert (
                market_assistant_artifacts.authority_allows_purpose(authority, purpose)
                is expected
            )


def test_validate_artifact_returns_plain_dict():
    artifact = valid_artifact()
    assert market_assistant_artifacts.validate_artifact(artifact) == artifact


def test_validate_artifact_rejects_unknown_artifact_kind():
    with pytest.raises(ValueError, match="artifact payload is invalid"):
        market_assistant_artifacts.validate_artifact(
            valid_artifact(artifact_kind="bogus")
        )


def test_validate_artifact_rejects_unknown_primary_authority():
    with pytest.raises(ValueError, match="artifact payload is invalid"):
        market_assistant_artifacts.validate_artifact(
            valid_artifact(primary_authority="bogus")
        )


def test_validate_artifact_rejects_wrong_primary_authority_for_kind():
    with pytest.raises(ValueError, match="artifact primary authority is not permitted"):
        market_assistant_artifacts.validate_artifact(
            valid_artifact(primary_authority="method_knowledge")
        )


def test_validate_artifact_rejects_wrong_market_setup_relation_for_kind():
    with pytest.raises(ValueError, match="artifact market setup relation is invalid"):
        market_assistant_artifacts.validate_artifact(
            valid_artifact(market_setup_relation="non_decision")
        )


def test_validate_artifact_rejects_object_authority_not_permitted_by_kind():
    artifact = valid_artifact(
        object_index=[
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "external_research",
                "payload": {"value": 18.4},
            }
        ]
    )
    with pytest.raises(ValueError, match="artifact authority is not permitted"):
        market_assistant_artifacts.validate_artifact(artifact)


def test_validate_artifact_allows_method_knowledge_object_inside_snapshot():
    artifact = valid_artifact(
        object_index=[
            {
                "object_type": "method_contract",
                "object_id": "vix_confirmation",
                "authority": "method_knowledge",
                "payload": {"method_id": "vix_confirmation_v2"},
            }
        ]
    )
    assert (
        market_assistant_artifacts.validate_artifact(artifact)["object_index"][0][
            "authority"
        ]
        == "method_knowledge"
    )


def test_validate_artifact_rejects_duplicate_object_reference():
    artifact = valid_artifact(
        object_index=[
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"value": 18.4},
            },
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"value": 19.0},
            },
        ]
    )
    with pytest.raises(ValueError, match="artifact object is duplicated"):
        market_assistant_artifacts.validate_artifact(artifact)


def test_build_object_index_allows_same_object_id_across_types():
    index = market_assistant_artifacts.build_object_index(
        [
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"value": 18.4},
            },
            {
                "object_type": "confirmation_test",
                "object_id": "vix_level",
                "authority": "decision_fact",
                "payload": {"predicate_id": "primary"},
            },
        ]
    )
    assert len(index) == 2


def test_build_object_index_rejects_invalid_object():
    with pytest.raises(ValueError, match="artifact object is invalid"):
        market_assistant_artifacts.build_object_index(
            [
                {
                    "object_type": "evidence_fact",
                    "object_id": "vix_level",
                    "authority": "not_an_authority",
                    "payload": {},
                }
            ]
        )


def test_resolve_artifact_ref_rejects_missing_artifact():
    with pytest.raises(ValueError, match="artifact reference is not found"):
        market_assistant_artifacts.resolve_artifact_ref(
            {},
            {
                "artifact_id": "ctx_999",
                "object_type": "evidence_fact",
                "object_id": "vix_level",
            },
        )


def test_resolve_artifact_ref_rejects_missing_object():
    artifact = valid_artifact()
    with pytest.raises(ValueError, match="artifact object is not found"):
        market_assistant_artifacts.resolve_artifact_ref(
            {artifact["artifact_id"]: artifact},
            {
                "artifact_id": artifact["artifact_id"],
                "object_type": "evidence_fact",
                "object_id": "missing_fact",
            },
        )


def test_resolve_artifact_ref_rejects_invalid_reference():
    artifact = valid_artifact()
    with pytest.raises(ValueError, match="artifact reference is invalid"):
        market_assistant_artifacts.resolve_artifact_ref(
            {artifact["artifact_id"]: artifact},
            {"artifact_id": artifact["artifact_id"], "object_id": "vix_level"},
        )


def test_resolve_artifact_ref_returns_object_authority():
    artifact = valid_artifact()
    resolved = market_assistant_artifacts.resolve_artifact_ref(
        {artifact["artifact_id"]: artifact},
        {
            "artifact_id": artifact["artifact_id"],
            "object_type": "evidence_fact",
            "object_id": "vix_level",
        },
    )
    assert resolved["authority"] == "decision_fact"
