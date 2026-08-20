import hashlib
import json
from copy import deepcopy
import pytest

from app.resources import resource_path
from app.tools import market_setup_evidence_facts
from app.tools import market_setup_explanation_snapshot
from app.tools import market_setup_v2

REGISTRY_PATH = resource_path("market_setup_inputs")


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


def finalized_snapshot(context_id="ctx_A", created_at="2026-08-10T01:00:00Z", **kwargs):
    return market_setup_explanation_snapshot.finalize_snapshot(
        snapshot_state(**kwargs),
        context_id=context_id,
        created_at=created_at,
    )


class TestSnapshotHashes:
    def test_explanation_only_change_preserves_decision_fingerprint(self):
        before = snapshot_state()
        after = deepcopy(before)
        policy = next(
            fact
            for fact in after["evidence"]
            if fact["fact_id"] == "macro_policy_response"
        )
        policy["explanation"] = {"policy_read": {"policy_action": "hold"}}
        assert market_setup_explanation_snapshot.compute_decision_fingerprint(
            before
        ) == market_setup_explanation_snapshot.compute_decision_fingerprint(after)
        assert market_setup_explanation_snapshot.compute_explanation_fingerprint(
            before
        ) != market_setup_explanation_snapshot.compute_explanation_fingerprint(after)

    def test_watch_only_change_invalidates_explanation_not_decision(self):
        before = snapshot_state(equity_breadth=50.0)
        after = snapshot_state(equity_breadth=42.0)

        assert market_setup_explanation_snapshot.compute_decision_fingerprint(
            before
        ) == market_setup_explanation_snapshot.compute_decision_fingerprint(after)
        assert market_setup_explanation_snapshot.compute_explanation_fingerprint(
            before
        ) != market_setup_explanation_snapshot.compute_explanation_fingerprint(after)

    def test_identity_changes_only_snapshot_hash(self):
        state = snapshot_state()
        first = market_setup_explanation_snapshot.finalize_snapshot(
            state, context_id="ctx_A", created_at="2026-08-10T01:00:00Z"
        )
        second = market_setup_explanation_snapshot.finalize_snapshot(
            state, context_id="ctx_B", created_at="2026-08-10T02:00:00Z"
        )

        assert first["decision_fingerprint"] == second["decision_fingerprint"]
        assert first["explanation_fingerprint"] == second["explanation_fingerprint"]
        assert first["snapshot_hash"] != second["snapshot_hash"]

    def test_decision_input_change_invalidates_both_fingerprints(self):
        before = snapshot_state(vix=15.0)
        after = snapshot_state(vix=25.0)

        assert market_setup_explanation_snapshot.compute_decision_fingerprint(
            before
        ) != market_setup_explanation_snapshot.compute_decision_fingerprint(after)
        assert market_setup_explanation_snapshot.compute_explanation_fingerprint(
            before
        ) != market_setup_explanation_snapshot.compute_explanation_fingerprint(after)

    def test_decision_input_change_invalidates_decision_even_when_results_unchanged(
        self,
    ):
        before = snapshot_state(vix=15.0)
        after = snapshot_state(vix=19.0)

        assert [
            before["results"][layer]["code"]
            for layer in (
                "macro_regime",
                "market_confirmation",
                "market_setup",
                "portfolio_posture",
            )
        ] == [
            after["results"][layer]["code"]
            for layer in (
                "macro_regime",
                "market_confirmation",
                "market_setup",
                "portfolio_posture",
            )
        ]
        assert market_setup_explanation_snapshot.compute_decision_fingerprint(
            before
        ) != market_setup_explanation_snapshot.compute_decision_fingerprint(after)

    def test_canonical_json_normalizes_unicode_nfc_equivalence(self):
        first = market_setup_explanation_snapshot.canonical_json(
            {"label": "cafe\u0301"}
        )
        second = market_setup_explanation_snapshot.canonical_json(
            {"label": "caf\u00e9"}
        )
        assert first == second

    def test_canonical_json_sorts_unordered_lists(self):
        first = market_setup_explanation_snapshot.canonical_json(
            {"items": [{"id": "b"}, {"id": "a"}]}
        )
        second = market_setup_explanation_snapshot.canonical_json(
            {"items": [{"id": "a"}, {"id": "b"}]}
        )
        assert first == second

    def test_canonical_json_preserves_ordered_time_series_lists(self):
        first = market_setup_explanation_snapshot.canonical_json(
            {"rows": [{"t": 1, "v": 10}, {"t": 2, "v": 20}]}
        )
        second = market_setup_explanation_snapshot.canonical_json(
            {"rows": [{"t": 2, "v": 20}, {"t": 1, "v": 10}]}
        )
        assert first != second

    def test_canonical_json_preserves_governance_order(self):
        first = market_setup_explanation_snapshot.canonical_json(
            {"governance": [{"fact_id": "b"}, {"fact_id": "a"}]}
        )
        second = market_setup_explanation_snapshot.canonical_json(
            {"governance": [{"fact_id": "a"}, {"fact_id": "b"}]}
        )
        assert first != second

    def test_canonical_json_sorts_dict_keys_recursively(self):
        first = market_setup_explanation_snapshot.canonical_json(
            {"b": 1, "a": {"d": 2, "c": 3}}
        )
        second = market_setup_explanation_snapshot.canonical_json(
            {"a": {"c": 3, "d": 2}, "b": 1}
        )
        assert first == second

    def test_canonical_json_rejects_non_finite_numbers(self):
        with pytest.raises(ValueError, match="finite"):
            market_setup_explanation_snapshot.canonical_json({"value": float("nan")})
        with pytest.raises(ValueError, match="finite"):
            market_setup_explanation_snapshot.canonical_json({"value": float("inf")})

    def test_canonical_json_normalizes_negative_zero(self):
        first = market_setup_explanation_snapshot.canonical_json({"value": -0.0})
        second = market_setup_explanation_snapshot.canonical_json({"value": 0.0})
        assert first == second
        assert b"-0.0" not in first

    def test_canonical_json_normalizes_utc_timestamps(self):
        first = market_setup_explanation_snapshot.canonical_json(
            {"created_at": "2026-08-10T01:00:00+00:00"}
        )
        second = market_setup_explanation_snapshot.canonical_json(
            {"created_at": "2026-08-10T01:00:00Z"}
        )
        assert first == second


class TestSnapshotIntegrity:
    def test_snapshot_hash_excludes_itself(self):
        snapshot = finalized_snapshot()
        payload = {
            key: value for key, value in snapshot.items() if key != "snapshot_hash"
        }
        expected = hashlib.sha256(
            market_setup_explanation_snapshot.canonical_json(payload)
        ).hexdigest()
        assert snapshot["snapshot_hash"] == expected

    def test_validate_snapshot_rejects_mutated_results(self):
        snapshot = finalized_snapshot()
        snapshot["results"]["market_setup"]["code"] = (
            "macro_improving_market_confirming"
        )
        with pytest.raises(ValueError, match="fingerprint"):
            market_setup_explanation_snapshot.validate_snapshot(snapshot)

    def test_validate_snapshot_rejects_corrupted_snapshot_hash(self):
        snapshot = finalized_snapshot()
        snapshot["snapshot_hash"] = "0" * 64
        with pytest.raises(ValueError, match="snapshot hash"):
            market_setup_explanation_snapshot.validate_snapshot(snapshot)

    def test_validate_snapshot_rejects_corrupted_explanation_fingerprint(self):
        snapshot = finalized_snapshot()
        snapshot["explanation_fingerprint"] = "0" * 64
        with pytest.raises(ValueError, match="explanation"):
            market_setup_explanation_snapshot.validate_snapshot(snapshot)


class TestSnapshotState:
    def test_snapshot_state_has_the_design_top_level_fields(self):
        state = snapshot_state()
        assert (
            state["snapshot_schema_version"] == "market_setup_explanation_snapshot_v1"
        )
        assert state["market_setup_version"] == "market_setup_v2"
        assert state["input_registry_version"] == "market_setup_input_registry_v1"
        assert state["explanation_surface_version"] == "market_assistant_surface_v1"
        assert state["as_of"] == "2026-08-10"
        assert state["evidence_through"] == "2026-06-30"
        assert set(state) == {
            "snapshot_schema_version",
            "as_of",
            "evidence_through",
            "market_setup_version",
            "input_registry_version",
            "explanation_surface_version",
            "method_manifest",
            "results",
            "decision_path",
            "evidence",
            "method_contracts",
            "counterfactuals",
            "next_triggers",
            "governance",
        }

    def test_snapshot_results_equal_the_engine_result(self):
        state = snapshot_state()
        inputs = _inputs()
        setup_result = market_setup_v2.build_market_setup_v2(**inputs)
        assert state["results"]["macro_regime"] == setup_result["macro_regime"]
        assert (
            state["results"]["market_confirmation"]
            == setup_result["market_confirmation"]
        )
        assert state["results"]["market_setup"] == setup_result["market_setup"]
        assert (
            state["results"]["portfolio_posture"] == setup_result["portfolio_posture"]
        )

    def test_decision_path_has_four_stable_steps(self):
        state = snapshot_state()
        assert [step["step_id"] for step in state["decision_path"]] == [
            "macro_thesis",
            "market_test",
            "setup_relationship",
            "portfolio_action",
        ]
        for step in state["decision_path"]:
            assert step["object_id"] in state["results"]
            assert step["code"] == state["results"][step["object_id"]]["code"]

    def test_snapshot_embeds_the_method_contracts_export(self):
        state = snapshot_state()
        contracts = market_setup_v2.build_explanation_method_contracts()
        assert state["method_contracts"] == contracts

    def test_governance_index_matches_evidence_order(self):
        state = snapshot_state()
        assert [entry["fact_id"] for entry in state["governance"]] == [
            fact["fact_id"] for fact in state["evidence"]
        ]


class TestSemanticDelta:
    def test_delta_reports_watch_only_value_change(self):
        before = finalized_snapshot(equity_breadth=50.0)
        after = finalized_snapshot(equity_breadth=42.0)
        delta = market_setup_explanation_snapshot.build_semantic_delta(before, after)
        assert delta == {
            "results_changed": False,
            "changes": [
                {
                    "object_type": "evidence_fact",
                    "object_id": "equity_breadth",
                    "field_id": "accepted_value",
                    "before": 50.0,
                    "after": 42.0,
                }
            ],
        }

    def test_delta_reports_result_change(self):
        before = finalized_snapshot(vix=15.0)
        after = finalized_snapshot(vix=25.0)
        delta = market_setup_explanation_snapshot.build_semantic_delta(before, after)
        assert delta["results_changed"] is True
        vix_changes = [
            change
            for change in delta["changes"]
            if change["object_id"] == "vix_level"
            and change["field_id"] == "accepted_value"
        ]
        assert vix_changes == [
            {
                "object_type": "evidence_fact",
                "object_id": "vix_level",
                "field_id": "accepted_value",
                "before": 15.0,
                "after": 25.0,
            }
        ]

    def test_delta_is_empty_for_identical_snapshots(self):
        first = finalized_snapshot()
        second = finalized_snapshot()
        delta = market_setup_explanation_snapshot.build_semantic_delta(first, second)
        assert delta == {"results_changed": False, "changes": []}

    def test_delta_with_no_previous_marks_results_changed(self):
        current = finalized_snapshot()
        delta = market_setup_explanation_snapshot.build_semantic_delta(None, current)
        assert delta["results_changed"] is True
        assert delta["changes"] == []


class TestCounterfactuals:
    def test_counterfactuals_reference_predicate_refs_not_threshold_literals(self):
        state = snapshot_state()
        crossings = [
            cf
            for cf in state["counterfactuals"]
            if cf["object_type"] == "confirmation_test"
        ]
        assert crossings
        for cf in crossings:
            assert "operand" not in json.dumps(cf)
            assert set(cf["predicate_ref"]) == {
                "method_id",
                "method_version",
                "predicate_id",
            }

    def test_counterfactuals_are_stable_under_watch_only_change(self):
        before = snapshot_state(equity_breadth=50.0)
        after = snapshot_state(equity_breadth=42.0)
        assert before["counterfactuals"] == after["counterfactuals"]

    def test_counterfactuals_describe_setup_matrix_transitions(self):
        state = snapshot_state()
        transitions = [
            cf for cf in state["counterfactuals"] if cf["object_type"] == "market_setup"
        ]
        assert transitions
        for cf in transitions:
            assert cf["from_code"] == "macro_weakening_price_not_confirming"
            assert cf["to_code"]
            assert cf["posture_change"]["from"] == "neutral_selective"
