import json
import threading

import pytest

from app.db import market_assistant
from app.tools import market_setup_evidence_facts
from app.tools import market_setup_explanation_snapshot
from app.tools import market_setup_v2


def _monthly_period(effective_date="2026-06-30", reference_period="2026-06"):
    return {
        "effective_date": effective_date,
        "reference_period": reference_period,
        "release_date": "2026-07-01",
    }


def _daily_period(effective_date="2026-07-01", observation_date="2026-07-01"):
    return {
        "effective_date": effective_date,
        "observation_date": observation_date,
    }


def _expected_growth(direction="slowing", status=None, source_period=None):
    record = {
        "direction": direction,
        "source_period": (
            source_period if source_period is not None else _monthly_period()
        ),
    }
    if status is not None:
        record["status"] = status
    return {
        "source_module": "ism_survey_synthesis",
        "method_version": "ism_survey_synthesis_v1",
        "facts": {"survey_growth_direction": record},
    }


def _financial_conditions(state="neutral", vix=15.0, credit_status="healthy"):
    relationship = {
        "mixed": "neutral",
        "healthy": "neutral",
        "confirms_expansion": "conflicts",
        "confirms_contraction_risk": "supports",
        "transition_warning": "neutral",
    }.get(state, state)
    facts = {
        "macro_financial_conditions": {
            "relationship_to_growth_direction": relationship,
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        },
        "credit_conditions": {
            "status": credit_status,
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        },
    }
    if vix is not None:
        facts["vix_level"] = {
            "level": vix,
            "source_period": _daily_period(),
        }
    return {
        "source_module": "us_rates_liquidity",
        "method_version": "us_rates_liquidity_v1",
        "facts": facts,
    }


def _policy_response(state="support_confirmed", m2_status="expanding"):
    relationship = {
        "support_confirmed": "conflicts",
        "support_possible": "neutral",
        "support_constrained": "neutral",
        "restrictive_confirmed": "supports",
        "no_clear_response": "neutral",
        "policy_liquidity_conflict": "neutral",
    }.get(state, state)
    facts = {
        "macro_policy_response": {
            "relationship_to_growth_direction": relationship,
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        },
    }
    if m2_status is not None:
        facts["m2_liquidity"] = {
            "status": m2_status,
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        }
    return {
        "source_module": "fomc_policy_tone",
        "method_version": "fomc_policy_tone_v1",
        "facts": facts,
    }


def _market_environment(state="bull_market", source_period=None):
    return {
        "source_module": "market_phase",
        "method_version": "market_phase_v1",
        "facts": {
            "sp500_market_phase": {
                "phase": state,
                "source_period": (
                    source_period if source_period is not None else _daily_period()
                ),
            }
        },
    }


def _inputs(equity_breadth=50.0, vix=15.0):
    observation_only = {
        "equity_breadth": {
            "value": equity_breadth,
            "source_period": _daily_period(),
        },
        "jobless_claims": {
            "claims_direction": "deteriorating",
            "source_period": _monthly_period(),
        },
        "cyclical_commodities": {
            "status": "extreme",
            "source_period": _monthly_period(),
        },
    }
    return {
        "expected_growth": _expected_growth("slowing"),
        "market_environment": _market_environment("bull_market"),
        "financial_conditions": _financial_conditions("mixed", vix=vix),
        "policy_response": _policy_response("support_confirmed", m2_status="expanding"),
        "observation_only": observation_only,
        "context_only": {
            "economic_confirmation": {
                "status": "confirmed",
                "source_period": _monthly_period(),
            }
        },
        "manual_review": {
            "nfib_regional_evidence": {
                "state": "mixed",
                "source_period": _monthly_period(),
            }
        },
    }


def snapshot_state(equity_breadth=50.0, vix=15.0):
    inputs = _inputs(equity_breadth=equity_breadth, vix=vix)
    setup_result = market_setup_v2.build_market_setup_v2(**inputs)
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup_result,
        inputs=inputs,
        evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )
    method_contracts = market_setup_v2.build_explanation_method_contracts()
    return market_setup_explanation_snapshot.build_snapshot_state(
        setup_result=setup_result,
        evidence=evidence,
        method_contracts=method_contracts,
        as_of="2026-08-10",
        evidence_through=setup_result["evidence_through"],
        input_registry_version="market_setup_input_registry_v1",
        explanation_surface_version="market_assistant_surface_v1",
    )


def snapshot_artifact():
    return {
        "artifact_id": "ctx_123_counterfactuals",
        "artifact_kind": "explanation_snapshot",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "decision_fact",
        "market_setup_relation": "authoritative_snapshot",
        "payload": {"context_id": "ctx_123", "counterfactuals": []},
        "object_index": [
            {
                "object_type": "confirmation_test",
                "object_id": "vix_downside",
                "authority": "decision_fact",
                "payload": {},
            }
        ],
        "integrity_hash": "e" * 64,
    }


def knowledge_record_artifact():
    return {
        "artifact_id": "krec_vix_level_v1",
        "artifact_kind": "knowledge_record",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "method_knowledge",
        "market_setup_relation": "non_decision",
        "payload": {"indicator_id": "vix_level", "definition": "VIX volatility index"},
        "object_index": [
            {
                "object_type": "method_knowledge",
                "object_id": "vix_level",
                "authority": "method_knowledge",
                "payload": {},
            }
        ],
        "integrity_hash": "a" * 64,
    }


def exploration_result_artifact():
    return {
        "artifact_id": "expl_vix_history_v1",
        "artifact_kind": "exploration_result",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "local_observation",
        "market_setup_relation": "non_decision",
        "payload": {"query_contract": {"operation": "indicator_history"}},
        "object_index": [
            {
                "object_type": "observation",
                "object_id": "vix_history",
                "authority": "local_observation",
                "payload": {},
            }
        ],
        "integrity_hash": "b" * 64,
    }


def research_result_artifact():
    return {
        "artifact_id": "res_article_v1",
        "artifact_kind": "research_result",
        "schema_version": "market_assistant_artifact_v1",
        "primary_authority": "external_research",
        "market_setup_relation": "non_decision",
        "payload": {"task": {"purpose": "document_summary"}},
        "object_index": [
            {
                "object_type": "source",
                "object_id": "src_1",
                "authority": "external_research",
                "payload": {},
            }
        ],
        "integrity_hash": "c" * 64,
    }


def answer_trace():
    return {
        "answer_trace_id": "trace_123",
        "message_id": "msg_456",
        "resolution": {
            "mode": "current",
            "resolved_at": "2026-08-10T02:00:00Z",
            "previous_context_id": "ctx_A",
            "current_context_id": "ctx_B",
            "context_changed": True,
        },
        "explanation_context_id": "ctx_B",
        "knowledge_references": ["vix_definition"],
        "snapshot_artifact_ids": [],
        "exploration_result_ids": [],
        "research_result_ids": [],
        "plan": {
            "intent": "decision_explanation",
            "context_mode": "current",
            "operations": [
                {"operation_id": "resolve_current_explanation", "parameters": {}}
            ],
            "answer_depth": "standard",
            "research_tier": None,
        },
        "structured_claims": None,
        "generation_status": "validated_first_pass",
        "attempts": {"plan": 1, "draft": 1, "repair": 0},
        "validation_error_codes": [],
        "prompt": {"version": "market_assistant_prompt_v1", "hash": "a" * 64},
        "model_configuration_fingerprint": {
            "provider": "openai_responses",
            "model": "assistant-model",
            "research_model": "research-model",
            "tool_schema_versions": {"artifacts": "market_assistant_artifact_v1"},
            "assistant_policy_version": "market_assistant_policy_v1",
            "prompt_version": "market_assistant_prompt_v1",
        },
        "tool_schema_versions": {"artifacts": "market_assistant_artifact_v1"},
        "answer_text": "Market Setup remains macro_improving.",
        "answer_text_hash": "b" * 64,
        "generated_time": "2026-08-10T02:00:00Z",
    }


class TestSnapshotRepository:
    def test_same_explanation_fingerprint_reuses_existing_context(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        first = market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        second = market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_B", created_at="2026-08-10T02:00:00Z"
        )

        assert second["context_id"] == first["context_id"] == "ctx_A"

    def test_snapshot_has_no_update_or_replace_api(self):
        assert not hasattr(market_assistant, "update_snapshot")
        assert not hasattr(market_assistant, "replace_snapshot")

    def test_get_or_create_returns_validated_snapshot(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        snapshot = market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        assert snapshot["context_id"] == "ctx_A"
        assert (
            snapshot["snapshot_schema_version"]
            == "market_setup_explanation_snapshot_v1"
        )
        assert len(snapshot["snapshot_hash"]) == 64
        assert market_assistant.load_snapshot(con, "ctx_A") == snapshot

    def test_load_snapshot_round_trip_is_identical(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        first = market_assistant.load_snapshot(con, "ctx_A")
        second = market_assistant.load_snapshot(con, "ctx_A")
        assert first == second
        expected = market_setup_explanation_snapshot.finalize_snapshot(
            snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        assert first["decision_fingerprint"] == expected["decision_fingerprint"]
        assert first["explanation_fingerprint"] == expected["explanation_fingerprint"]
        assert first["snapshot_hash"] == expected["snapshot_hash"]

    def test_snapshot_json_column_stores_canonical_json(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        expected = market_setup_explanation_snapshot.canonical_json(
            market_setup_explanation_snapshot.finalize_snapshot(
                snapshot_state(),
                context_id="ctx_A",
                created_at="2026-08-10T01:00:00Z",
            )
        ).decode("utf-8")
        market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        row = con.execute(
            "select snapshot_json from explanation_snapshots where context_id = ?",
            ("ctx_A",),
        ).fetchone()
        assert row["snapshot_json"] == expected

    def test_load_snapshot_returns_none_for_unknown_context(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        assert market_assistant.load_snapshot(con, "missing_ctx") is None

    def test_load_latest_snapshot_returns_newest(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        market_assistant.get_or_create_snapshot(
            con,
            snapshot_state(equity_breadth=50.0),
            context_id="ctx_A",
            created_at="2026-08-10T01:00:00Z",
        )
        market_assistant.get_or_create_snapshot(
            con,
            snapshot_state(equity_breadth=42.0),
            context_id="ctx_B",
            created_at="2026-08-10T02:00:00Z",
        )
        latest = market_assistant.load_latest_snapshot(con)
        assert latest["context_id"] == "ctx_B"
        assert latest["created_at"] == "2026-08-10T02:00:00Z"

    def test_load_latest_snapshot_returns_none_when_empty(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        assert market_assistant.load_latest_snapshot(con) is None

    def test_load_snapshot_rejects_tampered_json(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        con.execute(
            "update explanation_snapshots set snapshot_json = ? where context_id = ?",
            ("not valid json", "ctx_A"),
        )
        con.commit()
        with pytest.raises(
            ValueError, match="explanation snapshot integrity check failed"
        ):
            market_assistant.load_snapshot(con, "ctx_A")

    def test_load_snapshot_rejects_tampered_hash_in_json(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        snapshot = market_assistant.load_snapshot(con, "ctx_A")
        corrupted = dict(snapshot)
        corrupted["snapshot_hash"] = "0" * 64
        con.execute(
            "update explanation_snapshots set snapshot_json = ? where context_id = ?",
            (json.dumps(corrupted), "ctx_A"),
        )
        con.commit()
        with pytest.raises(
            ValueError, match="explanation snapshot integrity check failed"
        ):
            market_assistant.load_snapshot(con, "ctx_A")

    def test_load_snapshot_rejects_tampered_duplicated_column(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        con.execute(
            "update explanation_snapshots set decision_fingerprint = ? where context_id = ?",
            ("0" * 64, "ctx_A"),
        )
        con.commit()
        with pytest.raises(
            ValueError, match="explanation snapshot integrity check failed"
        ):
            market_assistant.load_snapshot(con, "ctx_A")

    def test_load_snapshot_rejects_tampered_stable_reference(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        market_assistant.get_or_create_snapshot(
            con, snapshot_state(), context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        snapshot = market_assistant.load_snapshot(con, "ctx_A")
        corrupted = dict(snapshot)
        corrupted["decision_path"] = [dict(step) for step in snapshot["decision_path"]]
        corrupted["decision_path"][0]["object_id"] = "not_a_layer"
        con.execute(
            "update explanation_snapshots set snapshot_json = ? where context_id = ?",
            (json.dumps(corrupted), "ctx_A"),
        )
        con.commit()
        with pytest.raises(
            ValueError, match="explanation snapshot integrity check failed"
        ):
            market_assistant.load_snapshot(con, "ctx_A")


class TestConcurrentGetOrCreate:
    def test_concurrent_get_or_create_persists_one_row(self, tmp_path):
        db_path = tmp_path / "assistant.sqlite"
        market_assistant.connect(db_path).close()
        results = {}
        errors = {}
        barrier = threading.Barrier(2)

        def worker(name):
            con = market_assistant.connect(db_path)
            con.execute("pragma busy_timeout = 10000")
            try:
                barrier.wait(timeout=10)
                results[name] = market_assistant.get_or_create_snapshot(
                    con,
                    snapshot_state(),
                    context_id=name,
                    created_at="2026-08-10T01:00:00Z",
                )
            except Exception as exc:
                errors[name] = exc
            finally:
                con.close()

        threads = [
            threading.Thread(target=worker, args=(name,)) for name in ("ctx_A", "ctx_B")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors
        assert results["ctx_A"]["context_id"] == results["ctx_B"]["context_id"]
        con = market_assistant.connect(db_path)
        row = con.execute("select count(*) from explanation_snapshots").fetchone()
        assert row[0] == 1
        con.close()

        threads = [
            threading.Thread(target=worker, args=(name,)) for name in ("ctx_A", "ctx_B")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors
        assert results["ctx_A"]["context_id"] == results["ctx_B"]["context_id"]
        con = market_assistant.connect(db_path)
        row = con.execute("select count(*) from explanation_snapshots").fetchone()
        assert row[0] == 1
        con.close()


class TestAnswerBundle:
    def test_save_answer_bundle_round_trip(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        artifacts = [
            snapshot_artifact(),
            knowledge_record_artifact(),
            exploration_result_artifact(),
            research_result_artifact(),
        ]
        trace = answer_trace()
        market_assistant.save_answer_bundle(
            con, artifacts=artifacts, answer_trace=trace
        )
        assert (
            market_assistant.load_answer_trace(con, trace["answer_trace_id"]) == trace
        )
        assert market_assistant.load_answer_trace(con, "missing_trace") is None
        for table in (
            "snapshot_artifacts",
            "knowledge_records",
            "exploration_results",
            "research_results",
        ):
            row = con.execute(f"select count(*) from {table}").fetchone()
            assert row[0] == 1

    def test_save_answer_bundle_identical_artifact_is_idempotent(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        artifact = knowledge_record_artifact()
        first = answer_trace()
        second = answer_trace()
        second["answer_trace_id"] = "trace_second"
        second["message_id"] = "msg_second"
        market_assistant.save_answer_bundle(
            con, artifacts=[artifact], answer_trace=first
        )
        market_assistant.save_answer_bundle(
            con, artifacts=[artifact], answer_trace=second
        )
        assert (
            market_assistant.load_answer_trace(con, first["answer_trace_id"]) == first
        )
        assert (
            market_assistant.load_answer_trace(con, second["answer_trace_id"]) == second
        )
        row = con.execute(
            "select count(*) from knowledge_records where artifact_id = ?",
            (artifact["artifact_id"],),
        ).fetchone()
        assert row[0] == 1

    def test_save_answer_bundle_conflicting_artifact_id_raises(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        first = knowledge_record_artifact()
        conflicting = knowledge_record_artifact()
        conflicting["integrity_hash"] = "b" * 64
        first_trace = answer_trace()
        second_trace = answer_trace()
        second_trace["answer_trace_id"] = "trace_conflict"
        second_trace["message_id"] = "msg_conflict"
        market_assistant.save_answer_bundle(
            con, artifacts=[first], answer_trace=first_trace
        )
        with pytest.raises(ValueError, match="artifact id conflicts"):
            market_assistant.save_answer_bundle(
                con, artifacts=[conflicting], answer_trace=second_trace
            )
        assert (
            market_assistant.load_answer_trace(con, first_trace["answer_trace_id"])
            == first_trace
        )
        assert (
            market_assistant.load_answer_trace(con, second_trace["answer_trace_id"])
            is None
        )

    def test_full_answer_trace_round_trips_all_design_19_fields(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        trace = answer_trace()
        trace["structured_claims"] = [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "c1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [
                            {
                                "artifact_id": "ctx_B",
                                "object_type": "confirmation_test",
                                "object_id": "vix_downside",
                            }
                        ],
                        "template": "The test is {result}.",
                        "bindings": {
                            "result": {
                                "value": "not confirming",
                                "source": {
                                    "artifact_id": "ctx_B",
                                    "object_type": "confirmation_test",
                                    "object_id": "vix_downside",
                                    "field": "result",
                                },
                            }
                        },
                    }
                ],
            }
        ]
        trace["validation_error_codes"] = ["UNBOUND_FACTUAL_LITERAL"]
        trace["attempts"] = {"plan": 1, "draft": 2, "repair": 1}
        market_assistant.save_answer_bundle(
            con, artifacts=[knowledge_record_artifact()], answer_trace=trace
        )
        loaded = market_assistant.load_answer_trace(con, trace["answer_trace_id"])
        assert loaded == trace

    def test_save_answer_bundle_rejects_invalid_trace_requiring_full_shape(
        self, tmp_path
    ):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        trace = answer_trace()
        trace["generation_status"] = "unexpected_status"
        with pytest.raises(
            ValueError, match="answer trace generation status is invalid"
        ):
            market_assistant.save_answer_bundle(con, artifacts=[], answer_trace=trace)
        assert market_assistant.load_answer_trace(con, trace["answer_trace_id"]) is None

    def test_save_answer_bundle_rejects_trace_with_secret_in_fingerprint(
        self, tmp_path
    ):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        trace = answer_trace()
        trace["model_configuration_fingerprint"]["api_key"] = "sk-secret"
        with pytest.raises(ValueError, match="answer trace fingerprint is invalid"):
            market_assistant.save_answer_bundle(con, artifacts=[], answer_trace=trace)
        assert market_assistant.load_answer_trace(con, trace["answer_trace_id"]) is None

    def test_save_answer_bundle_rejects_invalid_artifact_atomically(self, tmp_path):
        con = market_assistant.connect(tmp_path / "assistant.sqlite")
        valid = knowledge_record_artifact()
        invalid = {"artifact_id": "bad_artifact", "artifact_kind": "research_result"}
        trace = answer_trace()
        with pytest.raises(ValueError):
            market_assistant.save_answer_bundle(
                con, artifacts=[valid, invalid], answer_trace=trace
            )
        assert market_assistant.load_answer_trace(con, trace["answer_trace_id"]) is None
        for table in (
            "knowledge_records",
            "exploration_results",
            "research_results",
            "answer_traces",
        ):
            row = con.execute(f"select count(*) from {table}").fetchone()
            assert row[0] == 0
