import json
from pathlib import Path

import pytest

from app.tools import market_setup_evidence_facts
from app.tools import market_setup_v2

ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = ROOT / "data" / "local_system" / "market_assistant_surface.v1.json"

_SURFACE_FACT_IDS = [
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
]


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


def _inputs(vix_data_status="available", stale_breadth=False, direction="slowing"):
    financial_conditions = _financial_conditions("mixed", vix=15.0)
    if vix_data_status == "missing":
        financial_conditions["facts"].pop("vix_level")
    elif vix_data_status == "stale":
        financial_conditions["facts"]["vix_level"]["source_period"] = {}
    elif vix_data_status == "invalid":
        financial_conditions["facts"]["vix_level"] = {
            "level": None,
            "source_period": _daily_period(),
        }
    observation_only = {
        "equity_breadth": {
            "state": "broad",
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
    if stale_breadth:
        observation_only["equity_breadth"]["source_period"] = {}
    return {
        "expected_growth": _expected_growth(direction),
        "market_environment": _market_environment("bull_market"),
        "financial_conditions": financial_conditions,
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


def _build_facts_from(inputs):
    setup_result = market_setup_v2.build_market_setup_v2(**inputs)
    return market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup_result,
        inputs=inputs,
        evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )


def build_facts(vix_data_status="available", stale_breadth=False):
    return _build_facts_from(
        _inputs(vix_data_status=vix_data_status, stale_breadth=stale_breadth)
    )


def fact_by_id(facts, fact_id):
    return next(fact for fact in facts if fact["fact_id"] == fact_id)


def _write_surface(tmp_path, mutate):
    payload = json.loads(SURFACE_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    destination = tmp_path / "market_assistant_surface.v1.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


class TestExplanationSurface:
    def test_load_explanation_surface_loads_the_versioned_allowlist(self):
        surface = market_setup_evidence_facts.load_explanation_surface()
        assert surface["version"] == "market_assistant_surface_v1"
        assert surface["facts"] == _SURFACE_FACT_IDS

    def test_load_explanation_surface_rejects_unknown_fact_id(self, tmp_path):
        path = _write_surface(tmp_path, lambda s: s["facts"].append("not_a_real_fact"))

        with pytest.raises(ValueError, match="unknown"):
            market_setup_evidence_facts.load_explanation_surface(path)

    def test_load_explanation_surface_rejects_duplicate_fact_id(self, tmp_path):
        path = _write_surface(tmp_path, lambda s: s["facts"].append("vix_level"))

        with pytest.raises(ValueError, match="duplicate"):
            market_setup_evidence_facts.load_explanation_surface(path)

    def test_load_explanation_surface_rejects_empty_fact_id(self, tmp_path):
        path = _write_surface(tmp_path, lambda s: s["facts"].append(""))

        with pytest.raises(ValueError, match="empty"):
            market_setup_evidence_facts.load_explanation_surface(path)


class TestEvidenceFactsSemantics:
    def test_survey_direction_is_the_only_macro_selector(self):
        facts = build_facts()
        survey = fact_by_id(facts, "survey_growth_direction")
        financial = fact_by_id(facts, "macro_financial_conditions")

        assert survey["role"]["function"] == "selector"
        assert survey["decision_result"]["kind"] == "selector"
        assert financial["role"]["function"] == "contextual_relationship"
        assert financial["decision_result"]["kind"] == "relationship"

    def test_watch_only_and_stale_are_orthogonal(self):
        fact = fact_by_id(build_facts(stale_breadth=True), "equity_breadth")

        assert fact["role"]["function"] == "watch_only"
        assert fact["data_status"]["state"] == "stale"
        assert fact["participation"] == {
            "state": "not_applied",
            "reason_code": "watch_only",
        }

    def test_confirmation_facts_are_confirmation_tests_and_m2_is_offset(self):
        facts = build_facts()
        for fact_id in ("sp500_market_phase", "credit_conditions", "vix_level"):
            fact = fact_by_id(facts, fact_id)
            assert fact["role"]["function"] == "confirmation_test"
            assert fact["decision_result"]["kind"] == "confirmation_test"
            assert fact["participation"] == {"state": "applied"}
        m2 = fact_by_id(facts, "m2_liquidity")
        assert m2["role"]["function"] == "offset"
        assert m2["decision_result"] == {"kind": "offset", "state": "active"}

    def test_display_only_facts_are_visible_without_decision_authority(self):
        facts = build_facts()
        for fact_id in (
            "economic_confirmation",
            "cyclical_commodities",
            "nfib_regional_evidence",
        ):
            fact = fact_by_id(facts, fact_id)
            assert fact["role"]["function"] == "display_only"
            assert fact["decision_result"]["kind"] == "none"
            assert fact["participation"] == {
                "state": "not_applied",
                "reason_code": "display_only",
            }

    def test_level_and_direction_are_separate_classification_dimensions(self):
        facts = build_facts()
        survey = fact_by_id(facts, "survey_growth_direction")
        vix = fact_by_id(facts, "vix_level")
        assert survey["classifications"] == {"direction": "slowing"}
        assert vix["classifications"] == {"level": 15.0}

    def test_confirmation_fact_freezes_the_executed_predicate_and_evaluation(self):
        inputs = _inputs()
        setup_result = market_setup_v2.build_market_setup_v2(**inputs)
        evidence = setup_result["market_confirmation"]["evidence"]["equity_trend"]
        fact = fact_by_id(_build_facts_from(inputs), "sp500_market_phase")
        assert fact["decision_result"]["predicate_ref"] == evidence["predicate_ref"]
        assert fact["decision_result"]["predicate"] == evidence["predicate"]
        assert fact["decision_result"]["evaluation"] == evidence["evaluation"]

    @pytest.mark.parametrize(
        ("status", "participation_reason", "evaluation_state"),
        [
            ("missing", "data_missing", "not_evaluated"),
            ("stale", "data_stale", "not_evaluated"),
            ("invalid", "data_invalid", "not_evaluated"),
        ],
    )
    def test_unusable_confirmation_fact_is_not_a_failed_test(
        self, status, participation_reason, evaluation_state
    ):
        fact = fact_by_id(build_facts(vix_data_status=status), "vix_level")
        assert fact["participation"] == {
            "state": "not_applied",
            "reason_code": participation_reason,
        }
        assert fact["decision_result"]["evaluation"]["state"] == evaluation_state
        assert "result" not in fact["decision_result"]["evaluation"]

    def test_confirmation_fact_is_not_applied_when_regime_is_stable(self):
        inputs = _inputs(direction="stable")
        facts = _build_facts_from(inputs)
        vix = fact_by_id(facts, "vix_level")
        assert vix["data_status"]["state"] == "available"
        assert vix["participation"] == {
            "state": "not_applied",
            "reason_code": "target_layer_not_applicable",
        }

    def test_available_fact_missing_from_inputs_is_reported_missing(self):
        inputs = _inputs()
        inputs["consumer_demand"] = None
        facts = _build_facts_from(inputs)
        fact = fact_by_id(facts, "consumer_demand_outlook")
        assert fact["data_status"]["state"] == "missing"
        assert fact["participation"] == {
            "state": "not_applied",
            "reason_code": "data_missing",
        }

    def test_source_synchronization_status_is_not_in_explanation_surface(self):
        facts = build_facts()
        baseline = [fact for fact in facts]
        inputs = _inputs()
        inputs["financial_conditions"]["facts"]["vix_level"]["sync_status"] = (
            "refresh_available"
        )
        with_sync = _build_facts_from(inputs)
        assert with_sync == baseline
        assert "refresh_available" not in json.dumps(baseline)


class TestGovernanceIndex:
    def test_governance_index_is_an_exact_derived_index(self):
        facts = build_facts()
        governance = market_setup_evidence_facts.build_governance_index(facts)
        assert list(governance) == [fact["fact_id"] for fact in facts]
        for fact in facts:
            entry = governance[fact["fact_id"]]
            assert entry == {
                "decision_scope": fact["role"]["decision_scope"],
                "function": fact["role"]["function"],
                "target_layer": fact["role"]["target_layer"],
                "participation": fact["participation"],
                "decision_result_kind": fact["decision_result"]["kind"],
            }

    def test_governance_index_reflects_fact_payload_mutation(self):
        facts = build_facts()
        facts = [dict(fact) for fact in facts]
        facts[0]["participation"] = {
            "state": "not_applied",
            "reason_code": "data_missing",
        }
        governance = market_setup_evidence_facts.build_governance_index(facts)
        assert (
            governance[facts[0]["fact_id"]]["participation"]
            == facts[0]["participation"]
        )
