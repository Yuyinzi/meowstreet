import json
from pathlib import Path

import pytest

from app.tools import market_setup_v2

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "local_system" / "market_setup_input_registry.v1.json"


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


def _consumer_demand(state="neutral"):
    relationship = {
        "confirms_expansion": "supports",
        "confirms_downside_risk": "supports",
        "transition": "neutral",
    }.get(state, state)
    return {
        "source_module": "consumer_sentiment",
        "method_version": "market_setup_v2_consumer_demand_v1",
        "facts": {
            "consumer_demand_outlook": {
                "relationship_to_growth_direction": relationship,
                "source_period": _monthly_period(),
            }
        },
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


def _registry():
    return market_setup_v2.load_input_registry(REGISTRY_PATH)


def _write_registry(tmp_path, mutate):
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    destination = tmp_path / "market_setup_input_registry.v1.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


class TestInputRegistry:
    def test_market_setup_v2_registry_enforces_fact_layer_boundaries(self):
        registry = _registry()

        assert registry["version"] == "market_setup_input_registry_v1"
        assert registry["facts"]["survey_growth_direction"]["decision_scope"] == (
            "decision_input"
        )
        assert registry["facts"]["survey_growth_direction"]["target_layers"] == [
            "macro_regime"
        ]
        assert registry["facts"]["survey_growth_direction"]["allowed_effects"] == [
            "regime_selector"
        ]
        assert registry["facts"]["credit_conditions"]["target_layers"] == [
            "market_confirmation"
        ]
        assert registry["facts"]["macro_financial_conditions"]["target_layers"] == [
            "macro_regime"
        ]
        assert registry["facts"]["m2_liquidity"]["allowed_effects"] == ["offset"]
        assert registry["facts"]["economic_confirmation"]["allowed_effects"] == [
            "display_only"
        ]
        assert registry["facts"]["nfib_regional_evidence"]["decision_scope"] == (
            "manual_review"
        )

    def test_registry_rejects_fact_without_target_layers(self, tmp_path):
        path = _write_registry(
            tmp_path,
            lambda r: r["facts"]["credit_conditions"].pop("target_layers"),
        )

        with pytest.raises(ValueError, match="target_layers"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_effect_not_allowed_for_target_layer(self, tmp_path):
        path = _write_registry(
            tmp_path,
            lambda r: r["facts"]["credit_conditions"].__setitem__(
                "target_layers", ["macro_regime"]
            ),
        )

        with pytest.raises(ValueError, match="not allowed for target layer"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_display_only_required_fact(self, tmp_path):
        path = _write_registry(
            tmp_path,
            lambda r: r["facts"]["economic_confirmation"].__setitem__(
                "required_for_layer", ["macro_regime"]
            ),
        )

        with pytest.raises(ValueError, match="display.only"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_missing_version(self, tmp_path):
        path = _write_registry(tmp_path, lambda r: r.pop("version"))

        with pytest.raises(ValueError, match="version"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_unknown_scope(self, tmp_path):
        path = _write_registry(
            tmp_path,
            lambda r: r["facts"]["survey_growth_direction"].__setitem__(
                "decision_scope", "not_a_scope"
            ),
        )

        with pytest.raises(ValueError, match="decision scope"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_unknown_target_layer(self, tmp_path):
        path = _write_registry(
            tmp_path,
            lambda r: r["facts"]["survey_growth_direction"].__setitem__(
                "target_layers", ["not_a_layer"]
            ),
        )

        with pytest.raises(ValueError, match="target layer"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_duplicate_fact_id(self, tmp_path):
        def mutate(payload):
            duplicate = dict(payload["facts"]["vix_level"])
            payload["facts"]["credit_conditions"] = duplicate

        path = _write_registry(tmp_path, mutate)

        with pytest.raises(ValueError, match="duplicate"):
            market_setup_v2.load_input_registry(path)

    def test_registry_rejects_missing_required_record_key(self, tmp_path):
        path = _write_registry(
            tmp_path,
            lambda r: r["facts"]["vix_level"].pop("source_module"),
        )

        with pytest.raises(ValueError, match="required record key"):
            market_setup_v2.load_input_registry(path)


class TestRuntimeLayerEnforcement:
    def test_macro_regime_ignores_credit_fact_passed_in_financial_bundle(self):
        registry = _registry()
        financial = _financial_conditions("mixed")
        financial["facts"]["credit_conditions"]["status"] = "crisis_stress"
        extracted = market_setup_v2._extract(
            registry,
            financial,
            "credit_conditions",
            "macro_regime",
            ["supports", "conflicts"],
        )
        assert extracted is None

    def test_market_confirmation_ignores_financial_fact_passed_in_financial_bundle(
        self,
    ):
        registry = _registry()
        financial = _financial_conditions("confirms_contraction_risk")
        extracted = market_setup_v2._extract(
            registry,
            financial,
            "macro_financial_conditions",
            "market_confirmation",
            ["confirmation_test"],
        )
        assert extracted is None

    def test_builders_reject_fact_not_allowed_for_the_layer_effect(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response(
                "support_confirmed", m2_status="expanding"
            ),
        )
        credit_findings = [
            entry["finding"]
            for entry in result["market_confirmation"]["evidence"].values()
        ]
        assert any("credit conditions" in finding for finding in credit_findings)
        macro_source_ids = [
            entry["source_id"] for entry in result["macro_regime"]["supports"]
        ] + [entry["source_id"] for entry in result["macro_regime"]["conflicts"]]
        assert "credit_conditions" not in macro_source_ids

    def test_macro_regime_drops_supporting_fact_removed_from_registry_layer(
        self,
        monkeypatch,
    ):
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        registry["facts"]["macro_financial_conditions"]["target_layers"] = []
        monkeypatch.setattr(
            market_setup_v2, "load_input_registry", lambda *args, **kwargs: registry
        )
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing"),
            _financial_conditions("confirms_contraction_risk"),
            _policy_response("restrictive_confirmed"),
        )
        source_ids = [entry["source_id"] for entry in result["supports"]]
        assert "macro_financial_conditions" not in source_ids
        assert "macro_financial_conditions" in result["excluded_inputs"]

    def test_macro_regime_drops_policy_fact_removed_from_registry_layer(
        self,
        monkeypatch,
    ):
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        registry["facts"]["macro_policy_response"]["allowed_effects"] = []
        monkeypatch.setattr(
            market_setup_v2, "load_input_registry", lambda *args, **kwargs: registry
        )
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing"),
            _financial_conditions("confirms_contraction_risk"),
            _policy_response("restrictive_confirmed"),
        )
        source_ids = [entry["source_id"] for entry in result["supports"]]
        assert "macro_policy_response" not in source_ids
        assert "macro_policy_response" in result["excluded_inputs"]


class TestMacroRegime:
    def test_macro_regime_maps_slowing_survey_growth_to_growth_decelerating(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing"),
            _financial_conditions("mixed"),
            _policy_response("restrictive_confirmed"),
        )
        assert result["code"] == "growth_decelerating"
        assert result["label"] == "Growth Decelerating"
        assert result["primary_source"] == "ism_survey_synthesis"

    def test_macro_regime_does_not_reverse_survey_direction_from_context_inputs(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing"),
            _financial_conditions("confirms_expansion"),
            _policy_response("support_confirmed"),
        )
        assert result["code"] == "growth_decelerating"
        assert result["conflicts"]

    def test_macro_regime_rising_maps_to_growth_accelerating(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("rising"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "growth_accelerating"
        assert result["label"] == "Growth Accelerating"

    def test_macro_regime_falling_maps_to_contraction_risk_rising(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("falling"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "contraction_risk_rising"
        assert result["label"] == "Contraction Risk Rising"

    def test_macro_regime_improving_maps_to_early_recovery(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("improving"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "early_recovery"
        assert result["label"] == "Early Recovery"

    def test_macro_regime_rebound_risk_maps_to_early_recovery(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("rebound_risk"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "early_recovery"

    def test_macro_regime_stable_maps_to_growth_stable(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("stable"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "growth_stable"
        assert result["label"] == "Growth Stable"

    def test_macro_regime_missing_survey_returns_insufficient_data(self):
        result = market_setup_v2.build_macro_regime(
            None,
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "insufficient_data"
        assert result["missing_inputs"] == ["ISM survey synthesis"]

    def test_macro_regime_unknown_direction_returns_insufficient_data(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("sideways"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "insufficient_data"

    def test_macro_regime_stale_survey_returns_insufficient_data(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing", source_period={}),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["code"] == "insufficient_data"
        assert result["missing_inputs"] == ["ISM survey synthesis"]

    def test_macro_regime_supports_and_conflicts_consume_relationship_field(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing"),
            _financial_conditions("confirms_contraction_risk"),
            _policy_response("restrictive_confirmed"),
            consumer_demand=_consumer_demand("confirms_downside_risk"),
        )
        source_ids = [entry["source_id"] for entry in result["supports"]]
        assert "macro_financial_conditions" in source_ids
        assert "macro_policy_response" in source_ids
        assert "consumer_demand_outlook" in source_ids

    def test_macro_regime_method_version_and_source_periods(self):
        result = market_setup_v2.build_macro_regime(
            _expected_growth("slowing"),
            _financial_conditions("mixed"),
            _policy_response("no_clear_response"),
        )
        assert result["method_version"] == "market_setup_v2_macro_regime_v1"
        assert result["source_periods"]["survey_growth_direction"]["effective_date"]


class TestMarketConfirmation:
    def test_downside_is_not_broadly_confirmed_without_price_credit_or_volatility_confirmation(
        self,
    ):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "not_confirming_downside"
        assert result["label"] == "Downside Not Broadly Confirmed"
        assert result["confirmation_test_count"] == 0
        assert result["evidence"]["equity_trend"]["state"] == "bull_market"
        assert result["offsets"][0]["id"] == "m2_liquidity_support"

    def test_downside_one_test_partially_confirms_downside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "partially_confirming_downside"
        assert result["label"] == "Downside Partially Confirmed"
        assert result["confirmation_test_count"] == 1

    def test_downside_two_tests_partially_confirm_downside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=15.0, credit_status="risk_rising"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "partially_confirming_downside"
        assert result["confirmation_test_count"] == 2

    def test_downside_three_tests_broadly_confirm_downside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "contraction_risk_rising"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=20.0, credit_status="risk_rising"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "confirming_downside"
        assert result["label"] == "Downside Broadly Confirmed"
        assert result["confirmation_test_count"] == 3

    def test_upside_zero_tests_not_confirming_upside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_accelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=25.0, credit_status="risk_rising"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "not_confirming_upside"
        assert result["label"] == "Upside Not Broadly Confirmed"
        assert result["confirmation_test_count"] == 0

    def test_upside_one_test_partially_confirms_upside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_accelerating"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=25.0, credit_status="risk_rising"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "partially_confirming_upside"
        assert result["label"] == "Upside Partially Confirmed"
        assert result["confirmation_test_count"] == 1

    def test_upside_three_tests_broadly_confirm_upside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_accelerating"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=15.0, credit_status="supportive"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "confirming_upside"
        assert result["label"] == "Upside Broadly Confirmed"
        assert result["confirmation_test_count"] == 3

    def test_growth_stable_returns_not_applicable_with_null_count(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_stable"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "not_applicable"
        assert result["label"] == "Confirmation Pending a Directional Regime"
        assert result["confirmation_test_count"] is None

    def test_missing_market_phase_returns_insufficient_data(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            None,
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "insufficient_data"
        assert result["label"] == "Insufficient Market Confirmation Evidence"
        assert result["confirmation_test_count"] is None
        assert "S&P 500 market phase" in result["missing_inputs"]

    def test_missing_credit_returns_insufficient_data(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bull_market"),
            None,
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "insufficient_data"
        assert "credit conditions" in result["missing_inputs"]
        assert "VIX" in result["missing_inputs"]

    def test_unknown_credit_status_is_handled_as_unavailable(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=20.0, credit_status="mystery"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "insufficient_data"
        assert "credit conditions" in result["missing_inputs"]

    def test_weak_credit_warning_is_known_but_not_confirming_downside(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions(
                "healthy", vix=15.0, credit_status="weak_credit_warning"
            ),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "partially_confirming_downside"
        assert result["confirmation_test_count"] == 1
        assert result["evidence"]["credit"]["confirms"] is False

    def test_mixed_credit_status_is_known_but_not_confirming(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=15.0, credit_status="mixed"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "partially_confirming_downside"
        assert "credit conditions" not in result["missing_inputs"]

    def test_selective_credit_status_is_known_and_not_missing(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=15.0, credit_status="selective"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["code"] == "partially_confirming_downside"
        assert "credit conditions" not in result["missing_inputs"]

    def test_known_credit_statuses_do_not_trigger_insufficient_data(self):
        for status in ("weak_credit_warning", "mixed", "selective"):
            result = market_setup_v2.build_market_confirmation(
                {"code": "growth_decelerating"},
                _market_environment("bear_market"),
                _financial_conditions("healthy", vix=15.0, credit_status=status),
                _policy_response("support_confirmed", m2_status="expanding"),
            )
            assert result["code"] != "insufficient_data", status

    def test_m2_shock_creates_liquidity_offset(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="shock"),
        )
        assert result["offsets"][0]["id"] == "m2_liquidity_support"

    def test_m2_expanding_does_not_add_a_confirmation_vote(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert result["confirmation_test_count"] == 1
        assert result["evidence"]["equity_trend"]["confirms"] is True

    def test_missing_m2_does_not_change_confirmation_test_count(self):
        with_expansion = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        without_m2 = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bull_market"),
            _financial_conditions("healthy", vix=15.0),
            _policy_response("support_confirmed", m2_status=None),
        )
        assert with_expansion["confirmation_test_count"] == 0
        assert without_m2["confirmation_test_count"] == 0

    def test_market_confirmation_evidence_records_are_separate(self):
        result = market_setup_v2.build_market_confirmation(
            {"code": "growth_decelerating"},
            _market_environment("bear_market"),
            _financial_conditions("healthy", vix=20.0, credit_status="risk_rising"),
            _policy_response("support_confirmed", m2_status="expanding"),
        )
        assert set(result["evidence"]) == {
            "equity_trend",
            "credit",
            "volatility",
            "liquidity",
        }
        assert result["evidence"]["credit"]["state"] == "risk_rising"
        assert result["evidence"]["volatility"]["state"] == "stress"
        assert result["evidence"]["liquidity"]["state"] == "expanding"


def _downside_not_confirmed_inputs():
    return {
        "expected_growth": _expected_growth("slowing"),
        "market_environment": _market_environment("bull_market"),
        "financial_conditions": _financial_conditions("healthy", vix=15.0),
        "policy_response": _policy_response("support_confirmed", m2_status="expanding"),
    }


def _decision_tuple(result):
    return (
        result["macro_regime"]["code"],
        result["market_confirmation"]["code"],
        result["market_confirmation"]["confirmation_test_count"],
        result["market_setup"]["code"],
        result["market_setup"]["agreement"],
        result["portfolio_posture"]["code"],
        tuple(result["missing_inputs"]),
        tuple(trigger["id"] for trigger in result["next_triggers"]),
    )


class TestMarketSetupV2Composite:
    def test_v2_returns_neutral_selective_when_macro_weakens_without_market_confirmation(
        self,
    ):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response(
                "support_confirmed", m2_status="expanding"
            ),
        )
        assert result["version"] == "market_setup_v2"
        assert result["macro_regime"]["code"] == "growth_decelerating"
        assert result["market_confirmation"]["code"] == "not_confirming_downside"
        assert result["market_setup"] == {
            "code": "macro_weakening_price_not_confirming",
            "label": "Macro Weakening, Price Not Confirming",
            "agreement": "conflicting",
        }
        assert result["portfolio_posture"]["code"] == "neutral_selective"
        assert result["portfolio_posture"]["net_exposure"] == "neutral"
        assert result["portfolio_posture"]["gross_exposure"] == "moderate"
        assert result["generated_at"]
        assert result["interpretation"]
        assert result["method_versions"]
        assert result["supports"] == []
        assert result["excluded_inputs"]

    def test_v2_downside_broadly_confirmed_is_defensive(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("falling"),
            market_environment=_market_environment("bear_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=20.0, credit_status="risk_rising"
            ),
            policy_response=_policy_response("restrictive_confirmed"),
        )
        assert result["macro_regime"]["code"] == "contraction_risk_rising"
        assert result["market_confirmation"]["code"] == "confirming_downside"
        assert result["market_setup"]["code"] == "macro_weakening_market_confirming"
        assert result["market_setup"]["agreement"] == "aligned"
        assert result["portfolio_posture"]["code"] == "defensive"

    def test_v2_upside_zero_tests_is_neutral_selective(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("rising"),
            market_environment=_market_environment("bear_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=25.0, credit_status="risk_rising"
            ),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["macro_regime"]["code"] == "growth_accelerating"
        assert result["market_confirmation"]["code"] == "not_confirming_upside"
        assert result["market_setup"]["code"] == "macro_improving_price_not_confirming"
        assert result["market_setup"]["agreement"] == "conflicting"
        assert result["portfolio_posture"]["code"] == "neutral_selective"

    def test_v2_upside_one_test_is_mild_risk_on(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("rising"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=25.0, credit_status="risk_rising"
            ),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["market_confirmation"]["code"] == "partially_confirming_upside"
        assert result["market_setup"]["code"] == "macro_improving_partially_confirmed"
        assert result["market_setup"]["agreement"] == "mixed"
        assert result["portfolio_posture"]["code"] == "mild_risk_on"

    def test_v2_upside_two_tests_is_mild_risk_on(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("rising"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=15.0, credit_status="risk_rising"
            ),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["market_confirmation"]["code"] == "partially_confirming_upside"
        assert result["market_confirmation"]["confirmation_test_count"] == 2
        assert result["market_setup"]["code"] == "macro_improving_partially_confirmed"
        assert result["portfolio_posture"]["code"] == "mild_risk_on"

    def test_v2_early_recovery_confirmed_is_mild_risk_on(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("improving"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=15.0, credit_status="supportive"
            ),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["macro_regime"]["code"] == "early_recovery"
        assert result["market_confirmation"]["code"] == "confirming_upside"
        assert result["market_setup"]["code"] == "early_recovery_confirmed"
        assert result["portfolio_posture"]["code"] == "mild_risk_on"

    def test_v2_early_recovery_partially_confirmed_is_mild_risk_on(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("rebound_risk"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=15.0, credit_status="risk_rising"
            ),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["macro_regime"]["code"] == "early_recovery"
        assert result["market_confirmation"]["code"] == "partially_confirming_upside"
        assert result["market_setup"]["code"] == "early_recovery_partially_confirmed"
        assert result["portfolio_posture"]["code"] == "mild_risk_on"

    def test_v2_early_recovery_price_not_confirming_is_neutral_selective(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("improving"),
            market_environment=_market_environment("bear_market"),
            financial_conditions=_financial_conditions(
                "healthy", vix=25.0, credit_status="risk_rising"
            ),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["macro_regime"]["code"] == "early_recovery"
        assert result["market_confirmation"]["code"] == "not_confirming_upside"
        assert result["market_setup"]["code"] == "early_recovery_price_not_confirming"
        assert result["portfolio_posture"]["code"] == "neutral_selective"

    def test_v2_unknown_market_phase_returns_insufficient_data(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("mystery_phase"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["market_confirmation"]["code"] == "insufficient_data"
        assert result["market_setup"]["code"] == "insufficient_data"
        assert "S&P 500 market phase" in result["missing_inputs"]

    def test_v2_unknown_vix_returns_insufficient_data(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("bear_market"),
            financial_conditions=_financial_conditions("healthy", vix=None),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["market_confirmation"]["code"] == "insufficient_data"
        assert result["market_setup"]["code"] == "insufficient_data"
        assert "VIX" in result["missing_inputs"]

    def test_every_posture_returns_complete_positioning_and_avoid_arrays(self):
        postures = {
            "risk_on",
            "mild_risk_on",
            "neutral_selective",
            "mild_risk_off",
            "defensive",
            "insufficient_data",
        }
        for posture in postures:
            config = market_setup_v2._PORTFOLIO_POSTURE_MATRIX
            entry = next(item for item in config.values() if item["code"] == posture)
            assert entry["positioning"]
            assert entry["avoid"]
            assert isinstance(entry["net_exposure"], str)
            assert entry["net_exposure"]

    def test_v2_growth_stable_is_mixed_or_transition(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("stable"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["macro_regime"]["code"] == "growth_stable"
        assert result["market_confirmation"]["code"] == "not_applicable"
        assert result["market_setup"]["code"] == "mixed_or_transition"
        assert result["market_setup"]["agreement"] == "mixed"
        assert result["portfolio_posture"]["code"] == "neutral_selective"
        assert result["market_confirmation"]["confirmation_test_count"] is None

    def test_v2_returns_insufficient_data_for_missing_primary_inputs(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=None,
            market_environment=None,
            financial_conditions=None,
            policy_response=None,
        )
        assert result["market_setup"]["code"] == "insufficient_data"
        assert result["portfolio_posture"]["code"] == "insufficient_data"
        assert result["missing_inputs"] == [
            "ISM survey synthesis",
            "S&P 500 market phase",
            "credit conditions",
            "VIX",
        ]
        assert result["market_confirmation"]["confirmation_test_count"] is None
        assert result["evidence_through"] is None

    def test_observation_only_input_does_not_change_v2_result(self):
        inputs = _downside_not_confirmed_inputs()
        baseline = market_setup_v2.build_market_setup_v2(**inputs)
        inputs["observation_only"] = {"cyclical_commodities": {"status": "extreme"}}
        changed = market_setup_v2.build_market_setup_v2(**inputs)
        assert _decision_tuple(changed) == _decision_tuple(baseline)

    def test_v2_evidence_through_is_earliest_required_effective_date(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth(
                "slowing", source_period=_monthly_period(effective_date="2026-06-15")
            ),
            market_environment=_market_environment(
                "bull_market", source_period=_daily_period(effective_date="2026-07-01")
            ),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response(
                "support_confirmed", m2_status="expanding"
            ),
        )
        assert result["evidence_through"] == "2026-06-15"

    def test_v2_evidence_through_is_null_when_required_fact_missing_date(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing", source_period={}),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response(
                "support_confirmed", m2_status="expanding"
            ),
        )
        assert result["evidence_through"] is None

    def test_macro_financial_fact_cannot_change_market_confirmation(self):
        baseline = market_setup_v2.build_market_setup_v2(
            **_downside_not_confirmed_inputs()
        )
        financial_conditions = _financial_conditions("healthy", vix=15.0)
        financial_conditions["facts"]["macro_financial_conditions"][
            "relationship_to_growth_direction"
        ] = "supports"
        changed = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=financial_conditions,
            policy_response=_policy_response(
                "support_confirmed", m2_status="expanding"
            ),
        )
        assert (
            changed["market_confirmation"]["code"]
            == baseline["market_confirmation"]["code"]
        )
        assert (
            changed["market_confirmation"]["confirmation_test_count"]
            == baseline["market_confirmation"]["confirmation_test_count"]
        )

    def test_credit_fact_cannot_change_macro_regime(self):
        baseline = market_setup_v2.build_market_setup_v2(
            **_downside_not_confirmed_inputs()
        )
        financial_conditions = _financial_conditions("healthy", vix=15.0)
        financial_conditions["facts"]["credit_conditions"]["status"] = "risk_rising"
        changed = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=financial_conditions,
            policy_response=_policy_response(
                "support_confirmed", m2_status="expanding"
            ),
        )
        assert changed["macro_regime"]["code"] == baseline["macro_regime"]["code"]

    def test_v2_consumes_source_issued_relationship_field(self):
        captured = {}

        class FakeRegistry:
            pass

        original = market_setup_v2.load_input_registry
        registry = original(REGISTRY_PATH)
        financial_conditions = _financial_conditions("healthy", vix=15.0)
        captured["relationship"] = financial_conditions["facts"][
            "macro_financial_conditions"
        ]["relationship_to_growth_direction"]

        result = market_setup_v2.build_market_setup_v2(
            **_downside_not_confirmed_inputs()
        )
        assert captured["relationship"] == "neutral"
        assert result["macro_regime"]["code"] == "growth_decelerating"


class TestTriggersAndWatchItems:
    def test_directional_regime_emits_all_valid_source_triggers(self):
        result = market_setup_v2.build_market_setup_v2(
            **_downside_not_confirmed_inputs()
        )
        trigger_ids = [trigger["id"] for trigger in result["next_triggers"]]
        assert set(trigger_ids) == {
            "sp500_market_phase_change",
            "credit_conditions_risk_state",
            "vix_stress_threshold",
            "ism_survey_direction_change",
        }
        for trigger in result["next_triggers"]:
            assert set(trigger) == {"id", "label", "condition_ref", "effect"}
            assert trigger["condition_ref"] in {
                "market_phase_v1",
                "credit_conditions_v1",
                "vix_confirmation_v2",
                "ism_survey_synthesis_v1",
            }

    def test_triggers_include_current_source_state_in_label(self):
        result = market_setup_v2.build_market_setup_v2(
            **_downside_not_confirmed_inputs()
        )
        labels = {trigger["label"] for trigger in result["next_triggers"]}
        assert "S&P 500 market phase changes from bull_market" in labels
        assert "Credit Conditions changes from healthy" in labels
        assert "VIX crosses the approved confirmation threshold from normal" in labels
        assert "ISM survey direction changes from slowing" in labels

    def test_growth_stable_emits_only_ism_trigger_and_projects_market_facts_as_watch(
        self,
    ):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("stable"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response("support_confirmed"),
        )
        assert [trigger["id"] for trigger in result["next_triggers"]] == [
            "ism_survey_direction_change"
        ]
        watch_labels = {item["label"] for item in result["watch_items"]}
        assert watch_labels == {
            "S&P 500 market phase",
            "Credit Conditions",
            "VIX",
        }
        for item in result["watch_items"]:
            assert "condition_ref" not in item
            assert item["decision_effect"] == "none"

    def test_missing_facts_stay_in_missing_inputs_and_emit_no_trigger(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=None,
            financial_conditions=None,
            policy_response=_policy_response("support_confirmed"),
        )
        assert result["missing_inputs"] == [
            "S&P 500 market phase",
            "credit conditions",
            "VIX",
        ]
        trigger_ids = [trigger["id"] for trigger in result["next_triggers"]]
        assert "sp500_market_phase_change" not in trigger_ids
        assert "credit_conditions_risk_state" not in trigger_ids
        assert "vix_stress_threshold" not in trigger_ids
        assert "ism_survey_direction_change" in trigger_ids

    def test_stale_fact_does_not_emit_direction_change_trigger(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("slowing"),
            market_environment=_market_environment("bull_market", source_period={}),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response("support_confirmed"),
        )
        trigger_ids = [trigger["id"] for trigger in result["next_triggers"]]
        assert "sp500_market_phase_change" not in trigger_ids
        assert "S&P 500 market phase" in result["missing_inputs"]

    def test_equity_breadth_and_jobless_claims_are_watch_items_only(self):
        result = market_setup_v2.build_market_setup_v2(
            expected_growth=_expected_growth("stable"),
            market_environment=_market_environment("bull_market"),
            financial_conditions=_financial_conditions("healthy", vix=15.0),
            policy_response=_policy_response("support_confirmed"),
            observation_only={
                "equity_breadth": {"state": "broad"},
                "jobless_claims": {"state": "elevated"},
            },
        )
        watch_labels = {item["label"] for item in result["watch_items"]}
        assert "Equity breadth" in watch_labels
        assert "Jobless claims" in watch_labels
        for item in result["watch_items"]:
            assert "condition_ref" not in item
        trigger_ids = [trigger["id"] for trigger in result["next_triggers"]]
        assert "equity_breadth" not in trigger_ids
        assert "jobless_claims" not in trigger_ids
