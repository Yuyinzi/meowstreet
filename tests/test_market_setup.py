from copy import deepcopy

from app.tools import market_setup


def _market_phase_payload(state="bull_market"):
    return {
        "markets": [
            {
                "benchmark_id": "us_sp500",
                "title": "S&P 500",
                "region": "US",
                "data_through": "2026-06-01",
                "latest": {
                    "close": 5500,
                    "rolling_high": 5600,
                    "bear_market_level": 4480,
                    "drawdown_pct": -1.79,
                    "market_phase_status": state,
                },
            }
        ]
    }


def _ism_macro_signal(cycle_state="expansion_rising", growth_impulse="supports_growth"):
    return {
        "version": "ism_macro_signal_v1",
        "status": "available",
        "period": "2026-06",
        "phase": "expansion",
        "momentum": "rising",
        "cycle_state": cycle_state,
        "growth_impulse": growth_impulse,
        "confidence": "high",
        "evidence": ["PMI is above 50 and rising month over month"],
        "metrics": {"pmi": {"current": 52.5, "previous": 51.0, "point_change": 1.5}},
    }


def _rates_liquidity_payload(
    curve_status="steep", credit_status="healthy", vix=15.0, real_rate=0.5
):
    return {
        "as_of": "2026-06-01",
        "derived": {
            "curve_status": curve_status,
            "credit_conditions_status": credit_status,
            "vix": vix,
            "ten_year_real_rate": real_rate,
            "cpi_based_real_rate": real_rate - 2.5,
        },
    }


def _fomc_tone_headline(marker_tone="dovish", policy_action="cut"):
    return {
        "id": "fomc_tone",
        "period": "2026-06-01",
        "status": "context",
        "latest_tone": {
            "marker_tone": marker_tone,
            "policy_action": policy_action,
        },
    }


def _m2_headline(status="expanding"):
    return {
        "id": "m2_money_supply",
        "period": "2026-06-01",
        "status": status,
        "status_label": status.title(),
        "state": {
            "m2_yoy_pct_change": 0.05,
            "m2_yoy_percent_rank": 0.75,
            "m2_money_stock": 21000,
        },
        "change": {"m2_3m_momentum": 0.01},
    }


def _inflation_context(status="near_target"):
    return {
        "id": "inflation_context",
        "period": "2026-06-01",
        "status": status,
        "core_pce_yoy": 0.025 if status == "above_target" else 0.021,
        "gap": 0.005 if status == "above_target" else 0.001,
    }


def _fed_balance_sheet():
    return {
        "id": "fed_balance_sheet",
        "period": "2026-06-01",
        "status": "context",
        "total_assets": 7500000,
        "total_assets_yoy": 0.03,
    }


class TestBuildMarketEnvironment:
    def test_bull_market(self):
        result = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        assert result["state"] == "bull_market"
        assert result["starting_posture"] == "long"
        assert result["data_status"] == "available"

    def test_bear_market(self):
        result = market_setup.build_market_environment(
            _market_phase_payload("bear_market")
        )
        assert result["state"] == "bear_market"
        assert result["starting_posture"] == "short_or_neutral"

    def test_no_data(self):
        result = market_setup.build_market_environment(None)
        assert result["state"] == "unavailable"
        assert result["starting_posture"] == "neutral"

    def test_unknown_phase_transitions_to_neutral(self):
        result = market_setup.build_market_environment(
            _market_phase_payload("unknown_phase")
        )
        assert result["state"] == "transition"
        assert result["starting_posture"] == "neutral"


class TestBuildExpectedGrowth:
    def test_expansion_rising(self):
        result = market_setup.build_expected_growth(
            _ism_macro_signal("expansion_rising", "supports_growth"), None
        )
        assert result["state"] == "expansion_rising"
        assert result["expected_gdp_direction"] == "rising"
        assert result["initial_bias"] == "long"

    def test_contraction_deepening(self):
        result = market_setup.build_expected_growth(
            _ism_macro_signal("contraction_deepening", "supports_contraction"), None
        )
        assert result["state"] == "contraction_deepening"
        assert result["expected_gdp_direction"] == "falling"
        assert result["initial_bias"] == "short"

    def test_peaking(self):
        result = market_setup.build_expected_growth(
            _ism_macro_signal("peaking", "growth_caution"), None
        )
        assert result["expected_gdp_direction"] == "slowing"
        assert result["initial_bias"] == "neutral"

    def test_troughing(self):
        result = market_setup.build_expected_growth(
            _ism_macro_signal("troughing", "turning_supportive"), None
        )
        assert result["expected_gdp_direction"] == "rebound_risk"
        assert result["initial_bias"] == "neutral_to_long"

    def test_contraction_improving(self):
        result = market_setup.build_expected_growth(
            _ism_macro_signal("contraction_improving", "contraction_easing"), None
        )
        assert result["expected_gdp_direction"] == "improving"
        assert result["initial_bias"] == "short"

    def test_no_signal(self):
        result = market_setup.build_expected_growth(None, None)
        assert result["state"] == "unavailable"
        assert result["data_status"] == "missing"


class TestBuildFinancialConditions:
    def test_expansion_confirmed(self):
        result = market_setup.build_financial_conditions(
            _rates_liquidity_payload("steep", "healthy", 12.0, 0.3)
        )
        assert result["state"] == "confirms_expansion"

    def test_contraction_risk_inverted_and_widening(self):
        result = market_setup.build_financial_conditions(
            _rates_liquidity_payload("inverted", "crisis_stress", 35.0, 2.5)
        )
        assert result["state"] == "confirms_contraction_risk"

    def test_flat_curve_no_credit_stress(self):
        result = market_setup.build_financial_conditions(
            _rates_liquidity_payload("flat", "healthy", 15.0, 1.0)
        )
        assert result["state"] == "transition_warning"

    def test_flat_curve_with_credit_stress(self):
        result = market_setup.build_financial_conditions(
            _rates_liquidity_payload("flat", "risk_rising", 25.0, 2.0)
        )
        assert result["state"] == "confirms_contraction_risk"

    def test_inverted_curve_but_stable_credit_is_mixed(self):
        result = market_setup.build_financial_conditions(
            _rates_liquidity_payload("inverted", "healthy", 15.0, 0.5)
        )
        assert result["state"] == "mixed"

    def test_no_data(self):
        result = market_setup.build_financial_conditions(None)
        assert result["state"] == "unavailable"
        assert result["data_status"] == "missing"


class TestBuildPolicyResponse:
    def test_dovish_and_expanding_m2(self):
        result = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("expanding"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        assert result["state"] == "support_confirmed"

    def test_dovish_and_contracting_m2_conflict(self):
        result = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("contracting"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        assert result["state"] == "policy_liquidity_conflict"

    def test_dovish_with_inflation_above_target(self):
        result = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("expanding"),
            _inflation_context("above_target"),
            _fed_balance_sheet(),
        )
        assert result["state"] == "support_constrained"

    def test_hawkish_and_contracting_m2(self):
        result = market_setup.build_policy_response(
            _fomc_tone_headline("hawkish", "hold"),
            _m2_headline("contracting"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        assert result["state"] == "restrictive_confirmed"

    def test_m2_shock_prompts_investigation(self):
        result = market_setup.build_policy_response(
            _fomc_tone_headline("neutral", "hold"),
            _m2_headline("shock"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        assert result["state"] == "no_clear_response"
        assert "requires investigation" in result["reasons"][0].lower()

    def test_no_data(self):
        result = market_setup.build_policy_response(None, None, None, None)
        assert result["state"] == "unavailable"
        assert result["data_status"] == "missing"


class TestClassifySetupType:
    def test_growth_and_conditions_aligned(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("expansion_rising", "supports_growth"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("steep", "healthy", 12.0, 0.5)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("expanding"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        result = market_setup.classify_setup_type(market_env, expected_growth, fc, pr)
        assert result["setup_type"] == "growth_and_conditions_aligned"
        assert "long" in result["portfolio_posture"]

    def test_contraction_risk_aligned(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bear_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("contraction_deepening", "supports_contraction"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("inverted", "crisis_stress", 35.0, 2.5)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("hawkish", "hold"),
            _m2_headline("contracting"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        result = market_setup.classify_setup_type(market_env, expected_growth, fc, pr)
        assert result["setup_type"] == "contraction_risk_aligned"

    def test_weak_growth_with_policy_support(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("contraction_improving", "contraction_easing"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("flat", "healthy", 18.0, 1.0)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("expanding"),
            _inflation_context("below_target"),
            _fed_balance_sheet(),
        )
        result = market_setup.classify_setup_type(market_env, expected_growth, fc, pr)
        assert result["setup_type"] == "weak_growth_with_policy_support"

    def test_growth_liquidity_conflict(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("expansion_rising", "supports_growth"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("inverted", "healthy", 20.0, 2.5)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("hawkish", "hold"),
            _m2_headline("contracting"),
            _inflation_context("above_target"),
            _fed_balance_sheet(),
        )
        result = market_setup.classify_setup_type(market_env, expected_growth, fc, pr)
        assert result["setup_type"] == "growth_liquidity_conflict"

    def test_unresolved_macro_conflict(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("stable", "mixed"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("steep", "healthy", 15.0, 0.5)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("neutral", "hold"),
            _m2_headline("mixed"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        result = market_setup.classify_setup_type(market_env, expected_growth, fc, pr)
        assert result["setup_type"] == "unresolved_macro_conflict"


class TestReconcilePortfolioPosture:
    def test_bull_phase_prevents_aggressive_short(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("contraction_deepening", "supports_contraction"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("inverted", "crisis_stress", 35.0, 2.5)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("hawkish", "hold"),
            _m2_headline("contracting"),
            _inflation_context("above_target"),
            _fed_balance_sheet(),
        )
        setup_result = market_setup.classify_setup_type(
            market_env, expected_growth, fc, pr
        )
        assert setup_result["setup_type"] == "contraction_risk_aligned"
        posture, conflicts, _ = market_setup.reconcile_portfolio_posture(
            market_env, setup_result, expected_growth
        )
        assert posture == "neutral"
        assert any("bull market" in c.lower() for c in conflicts)

    def test_bear_phase_prevents_aggressive_long(self):
        market_env = market_setup.build_market_environment(
            _market_phase_payload("bear_market")
        )
        expected_growth = market_setup.build_expected_growth(
            _ism_macro_signal("expansion_rising", "supports_growth"), None
        )
        fc = market_setup.build_financial_conditions(
            _rates_liquidity_payload("steep", "healthy", 15.0, 0.5)
        )
        pr = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("expanding"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        setup_result = market_setup.classify_setup_type(
            market_env, expected_growth, fc, pr
        )
        posture, conflicts, _ = market_setup.reconcile_portfolio_posture(
            market_env, setup_result, expected_growth
        )
        assert posture == "neutral"
        assert any("bear market" in c.lower() for c in conflicts)


class TestBuildIdeaGeneration:
    def test_no_industry_data(self):
        result = market_setup.build_idea_generation_clues(None)
        assert result["data_status"] == "missing"
        assert "ticker validation" in result["warning"]

    def test_industry_analysis_provides_clues(self):
        industry_data = {
            "industries": [
                {
                    "industry": "Tech Hardware",
                    "overall_signal": {"direction": "growth"},
                    "trend_summary": {"positive_month_streak": 3},
                },
                {
                    "industry": "Chemicals",
                    "overall_signal": {"direction": "contraction"},
                    "trend_summary": {
                        "eligible_month_count": 2,
                        "positive_month_streak": 0,
                        "negative_month_streak": 2,
                    },
                },
            ],
            "comments": [],
        }
        result = market_setup.build_idea_generation_clues(industry_data)
        assert "Tech Hardware" in result["industry_long_clues"]
        assert "Chemicals" in result["industry_short_clues"]
        assert result["data_status"] == "available"


class TestDeterminism:
    def test_same_inputs_produce_same_setup(self):
        inputs = {
            "market_phase_payload": _market_phase_payload("bull_market"),
            "ism_macro_signal": _ism_macro_signal(
                "expansion_rising", "supports_growth"
            ),
            "growth_cycle_bias_evidence": None,
            "rates_liquidity_payload": _rates_liquidity_payload("steep", "healthy"),
            "fomc_tone": _fomc_tone_headline("dovish", "cut"),
            "m2_headline": _m2_headline("expanding"),
            "inflation_context": _inflation_context("near_target"),
            "fed_balance_sheet": _fed_balance_sheet(),
        }
        result1 = market_setup.build_market_setup(**deepcopy(inputs))
        result2 = market_setup.build_market_setup(**deepcopy(inputs))
        assert result1["setup_type"] == result2["setup_type"]
        assert result1["portfolio_posture"] == result2["portfolio_posture"]
        assert result1["trade_implications"] == result2["trade_implications"]


class TestMissingAndPendingData:
    def test_missing_inputs_when_no_data(self):
        result = market_setup.build_market_setup()
        assert len(result["missing_inputs"]) > 0
        assert result["status"] == "partial"

    def test_pending_confirmations_are_later_method_items(self):
        result = market_setup.build_market_setup()
        pending = result.get("pending_confirmations", [])
        assert "ISM Services" in pending
        assert all(isinstance(item, str) for item in pending)

    def test_gdp_not_a_current_signal(self):
        result = market_setup.build_market_setup(
            market_phase_payload=_market_phase_payload("bull_market"),
            ism_macro_signal=_ism_macro_signal("expansion_rising", "supports_growth"),
            rates_liquidity_payload=_rates_liquidity_payload("steep", "healthy"),
            fomc_tone=_fomc_tone_headline("dovish", "cut"),
            m2_headline=_m2_headline("expanding"),
            inflation_context=_inflation_context("near_target"),
            fed_balance_sheet=_fed_balance_sheet(),
        )
        expected_growth = result.get("expected_growth", {})
        assert expected_growth.get("expected_gdp_direction") is not None
        assert expected_growth.get("source_module") == "ism_macro_signal"
        reasons_text = " ".join(
            result.get("agreements", []) + result.get("conflicts", [])
        )
        assert "GDP" not in reasons_text
