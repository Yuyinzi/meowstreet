from copy import deepcopy

from app.tools import market_setup


def _survey_synthesis(
    status="available",
    economic_direction="aligned_expansion",
    expected_gdp_direction="rising",
    survey_portfolio_implication="long",
    period="2026-06",
    agreements=None,
    conflicts=None,
    reasons=None,
):
    return {
        "version": "ism_survey_synthesis_v1",
        "status": status,
        "period": period,
        "economic_direction": economic_direction,
        "growth_momentum": "rising",
        "survey_alignment": "aligned",
        "demand_alignment": "aligned_rising",
        "leading_side": "not_applicable",
        "expected_gdp_direction": expected_gdp_direction,
        "survey_portfolio_implication": survey_portfolio_implication,
        "components": {},
        "agreements": agreements or ["Manufacturing and Services are both expanding"],
        "conflicts": conflicts or [],
        "missing_inputs": [],
        "pending_questions": [],
        "reasons": reasons or ["Business surveys indicate broad expansion"],
    }


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
    def test_aligned_expansion_slowing(self):
        result = market_setup.build_expected_growth(
            _survey_synthesis(
                expected_gdp_direction="slowing",
                survey_portfolio_implication="neutral",
            )
        )
        assert result["state"] == "aligned_expansion"
        assert result["expected_gdp_direction"] == "slowing"
        assert result["initial_bias"] == "neutral"
        assert result["source_module"] == "ism_survey_synthesis"
        assert result["data_status"] == "available"

    def test_aligned_contraction_falling(self):
        result = market_setup.build_expected_growth(
            _survey_synthesis(
                economic_direction="aligned_contraction",
                expected_gdp_direction="falling",
                survey_portfolio_implication="short_or_neutral",
                agreements=["Manufacturing and Services are both contracting"],
                reasons=["Business surveys indicate broad contraction"],
                period="2026-06",
            )
        )
        assert result["state"] == "aligned_contraction"
        assert result["expected_gdp_direction"] == "falling"
        assert result["initial_bias"] == "short_or_neutral"
        assert result["source_module"] == "ism_survey_synthesis"
        assert result["data_status"] == "available"

    def test_no_signal(self):
        result = market_setup.build_expected_growth(None)
        assert result["state"] == "unavailable"
        assert result["data_status"] == "missing"

    def test_partial_synthesis(self):
        result = market_setup.build_expected_growth(
            _survey_synthesis(
                status="partial",
                expected_gdp_direction=None,
                survey_portfolio_implication=None,
            )
        )
        assert result["state"] == "unavailable"
        assert result["data_status"] == "missing"

    def test_expected_growth_uses_survey_synthesis(self):
        result = market_setup.build_expected_growth(
            _survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="slowing",
                survey_portfolio_implication="neutral",
                reasons=["Both surveys are expanding but slowing"],
                agreements=["Both surveys are expanding"],
                period="2026-06",
            )
        )
        assert result["state"] == "aligned_expansion"
        assert result["expected_gdp_direction"] == "slowing"
        assert result["initial_bias"] == "neutral"
        assert result["source_module"] == "ism_survey_synthesis"
        assert result["data_status"] == "available"

    def test_expected_growth_rejects_partial_synthesis(self):
        result = market_setup.build_expected_growth(
            {
                "status": "partial",
                "period": None,
                "expected_gdp_direction": None,
                "survey_portfolio_implication": None,
                "missing_inputs": ["ISM Services"],
            }
        )
        assert result["state"] == "unavailable"
        assert result["data_status"] == "missing"
        assert result["missing_inputs"] == ["ISM Services"]

    def test_expected_growth_preserves_survey_components_and_alignment(self):
        synthesis = _survey_synthesis(
            economic_direction="aligned_expansion",
            expected_gdp_direction="slowing",
        )
        synthesis.update(
            {
                "growth_momentum": "falling",
                "survey_alignment": "aligned",
                "demand_alignment": "aligned_falling",
                "components": {
                    "manufacturing": {
                        "level": "expanding",
                        "momentum": "falling",
                        "demand_level": "expanding",
                        "demand_momentum": "falling",
                    },
                    "services": {
                        "level": "expanding",
                        "momentum": "falling",
                        "demand_level": "expanding",
                        "demand_momentum": "falling",
                    },
                },
            }
        )

        result = market_setup.build_expected_growth(synthesis)

        assert result["growth_momentum"] == "falling"
        assert result["survey_alignment"] == "aligned"
        assert result["demand_alignment"] == "aligned_falling"
        assert result["components"] == synthesis["components"]
        assert result["evidence_links"] == ["ism_manufacturing", "ism_services"]


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
            _survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            )
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
            _survey_synthesis(
                economic_direction="aligned_contraction",
                expected_gdp_direction="falling",
                survey_portfolio_implication="short_or_neutral",
                period="2026-06",
            )
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
            _survey_synthesis(
                economic_direction="aligned_contraction",
                expected_gdp_direction="improving",
                survey_portfolio_implication="neutral",
                period="2026-06",
            )
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
            _survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            )
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
            _survey_synthesis(
                economic_direction="aligned_neutral",
                expected_gdp_direction="mixed",
                survey_portfolio_implication="neutral",
                period="2026-06",
            )
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
            _survey_synthesis(
                economic_direction="aligned_contraction",
                expected_gdp_direction="falling",
                survey_portfolio_implication="short_or_neutral",
                period="2026-06",
            )
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
            _survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            )
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
            "survey_synthesis": _survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            ),
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
        assert "Labor trend" in pending
        assert "Consumer indicators" in pending
        assert all(isinstance(item, str) for item in pending)

    def test_gdp_not_a_current_signal(self):
        result = market_setup.build_market_setup(
            market_phase_payload=_market_phase_payload("bull_market"),
            survey_synthesis=_survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            ),
            rates_liquidity_payload=_rates_liquidity_payload("steep", "healthy"),
            fomc_tone=_fomc_tone_headline("dovish", "cut"),
            m2_headline=_m2_headline("expanding"),
            inflation_context=_inflation_context("near_target"),
            fed_balance_sheet=_fed_balance_sheet(),
        )
        expected_growth = result.get("expected_growth", {})
        assert expected_growth.get("expected_gdp_direction") is not None
        assert expected_growth.get("source_module") == "ism_survey_synthesis"
        reasons_text = " ".join(
            result.get("agreements", []) + result.get("conflicts", [])
        )
        assert "GDP" not in reasons_text


class TestMarketConclusion:
    def setup_method(self):
        self.market_env_bull = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        self.market_env_bear = market_setup.build_market_environment(
            _market_phase_payload("bear_market")
        )
        self.market_env_missing = market_setup.build_market_environment(None)

    def _setup_result(self, setup_type):
        return {
            "setup_type": setup_type,
            "portfolio_posture": "neutral",
            "trade_implications": [],
            "agreements": [],
            "conflicts": [],
        }

    def test_contraction_risk_bull_market_produces_macro_risk_rising(self):
        setup_result = self._setup_result("contraction_risk_aligned")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "neutral"
        )
        assert conclusion["code"] == "macro_risk_rising_bull_intact"
        assert conclusion["title"] == "Macro Risk Rising; Bull Market Intact"
        assert "bull market" in conclusion["title"].lower()

    def test_contraction_risk_bear_market_produces_market_confirmed(self):
        setup_result = self._setup_result("contraction_risk_aligned")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bear, "short_or_neutral"
        )
        assert conclusion["code"] == "contraction_risk_market_confirmed"

    def test_growth_aligned_bear_market_produces_macro_improving_trend_not_reversed(
        self,
    ):
        setup_result = self._setup_result("growth_and_conditions_aligned")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bear, "neutral"
        )
        assert conclusion["code"] == "macro_improving_trend_not_reversed"
        assert "bear market" in conclusion["title"].lower()

    def test_growth_aligned_bull_market_produces_trend_aligned(self):
        setup_result = self._setup_result("growth_and_conditions_aligned")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "long"
        )
        assert conclusion["code"] == "growth_and_trend_aligned"
        assert "long" in conclusion["summary"].lower()

    def test_insufficient_data_produces_fallback_conclusion(self):
        setup_result = self._setup_result("insufficient_data")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "neutral"
        )
        assert conclusion["code"] == "insufficient_evidence"

    def test_unresolved_macro_conflict_produces_evidence_unresolved(self):
        setup_result = self._setup_result("unresolved_macro_conflict")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "cautious"
        )
        assert conclusion["code"] == "evidence_unresolved"

    def test_growth_liquidity_conflict_produces_mismatch(self):
        setup_result = self._setup_result("growth_liquidity_conflict")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "neutral"
        )
        assert conclusion["code"] == "growth_liquidity_mismatch"

    def test_weak_growth_policy_support_bull_produces_policy_offset(self):
        setup_result = self._setup_result("weak_growth_with_policy_support")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "neutral_to_long"
        )
        assert conclusion["code"] == "weak_growth_policy_offset"

    def test_weak_growth_policy_support_bear_produces_policy_support_bear_trend(self):
        setup_result = self._setup_result("weak_growth_with_policy_support")
        conclusion = market_setup.build_market_conclusion(
            setup_result, self.market_env_bear, "neutral"
        )
        assert conclusion["code"] == "policy_support_bear_trend"

    def test_identical_inputs_produce_identical_conclusion(self):
        setup_result = self._setup_result("contraction_risk_aligned")
        c1 = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "neutral"
        )
        c2 = market_setup.build_market_conclusion(
            setup_result, self.market_env_bull, "neutral"
        )
        assert c1 == c2


class TestPortfolioGuidance:
    def test_long_posture(self):
        guidance = market_setup.build_portfolio_guidance("long")
        assert guidance["posture"] == "long"
        assert len(guidance["actions"]) > 0
        assert len(guidance["avoid"]) > 0
        assert "short" not in " ".join(guidance["actions"]).lower()

    def test_neutral_posture_does_not_recommend_short(self):
        guidance = market_setup.build_portfolio_guidance("neutral")
        assert guidance["posture"] == "neutral"
        text = " ".join(guidance["actions"]).lower()
        assert "short" not in text
        assert "long" not in text

    def test_cautious_posture(self):
        guidance = market_setup.build_portfolio_guidance("cautious")
        assert guidance["posture"] == "cautious"
        assert any("selective" in a.lower() for a in guidance["actions"])

    def test_short_or_neutral_posture(self):
        guidance = market_setup.build_portfolio_guidance("short_or_neutral")
        assert guidance["posture"] == "short_or_neutral"
        text = " ".join(guidance["actions"] + guidance["avoid"]).lower()
        assert "short" in text

    def test_identical_inputs_produce_identical_guidance(self):
        g1 = market_setup.build_portfolio_guidance("neutral")
        g2 = market_setup.build_portfolio_guidance("neutral")
        assert g1 == g2


class TestEvidenceChain:
    def _expected_growth(self, direction="rising", reason="ISM is above 50 and rising"):
        return {
            "state": "expansion_rising",
            "expected_gdp_direction": direction,
            "reason": reason,
            "data_status": "available",
            "evidence_links": ["ism_manufacturing"],
        }

    def _financial_conditions(self, state="confirms_expansion", vix=15.0):
        return {
            "state": state,
            "reasons": ["Yield curve is steep"],
            "evidence_links": ["yield_curve", "credit_conditions"],
            "details": {"vix": vix, "credit_conditions_status": "healthy"},
        }

    def _policy_response(self, state="support_confirmed"):
        return {
            "state": state,
            "reasons": ["Dovish FOMC tone with expanding M2"],
            "evidence_links": ["fomc_policy"],
            "details": {"m2_status": "expanding", "fomc_tone": "dovish"},
        }

    def test_growth_path_group_has_expected_structure(self):
        eg = self._expected_growth("rising")
        chain = market_setup.build_evidence_chain(
            eg, self._financial_conditions(), self._policy_response()
        )
        growth = next(g for g in chain if g["id"] == "growth_path")
        assert growth["id"] == "growth_path"
        assert growth["finding"]
        assert growth["implication"]
        assert growth["tone"] == "constructive"
        assert len(growth["evidence"]) > 0
        assert "ism_manufacturing" in growth["evidence_links"]

    def test_financial_group_has_expected_structure(self):
        fc = self._financial_conditions("confirms_contraction_risk")
        chain = market_setup.build_evidence_chain(
            self._expected_growth(), fc, self._policy_response()
        )
        fin = next(g for g in chain if g["id"] == "financial_confirmation")
        assert fin["tone"] == "defensive"
        assert fin["finding"]
        assert fin["implication"]

    def test_policy_group_has_expected_structure(self):
        pr = self._policy_response("restrictive_confirmed")
        chain = market_setup.build_evidence_chain(
            self._expected_growth(), self._financial_conditions(), pr
        )
        pol = next(g for g in chain if g["id"] == "policy_constraint")
        assert pol["tone"] == "defensive"
        assert pol["finding"]
        assert pol["implication"]

    def test_missing_input_does_not_produce_group(self):
        eg = self._expected_growth()
        eg["data_status"] = "missing"
        chain = market_setup.build_evidence_chain(
            eg, self._financial_conditions(), self._policy_response()
        )
        ids = [g["id"] for g in chain]
        assert "growth_path" not in ids


class TestConvictionLimits:
    def _default_inputs(self):
        return {
            "market_environment": market_setup.build_market_environment(
                _market_phase_payload("bull_market")
            ),
            "financial_conditions": market_setup.build_financial_conditions(
                _rates_liquidity_payload("flat", "risk_rising", vix=12.0, real_rate=2.3)
            ),
            "policy_response": market_setup.build_policy_response(
                _fomc_tone_headline("hawkish", "hold"),
                _m2_headline("expanding"),
                _inflation_context("above_target"),
                _fed_balance_sheet(),
            ),
            "setup_type_result": {
                "setup_type": "contraction_risk_aligned",
                "portfolio_posture": "short_or_neutral",
                "trade_implications": [],
                "agreements": [],
                "conflicts": [],
            },
        }

    def test_expanding_m2_appears_as_conviction_limit(self):
        inputs = self._default_inputs()
        limits = market_setup.build_conviction_limits(**inputs)
        assert limits is not None
        findings = [o["finding"] for o in limits["offsets"]]
        assert any("M2" in f for f in findings)

    def test_low_vix_appears_as_offset_when_conditions_defensive(self):
        inputs = self._default_inputs()
        limits = market_setup.build_conviction_limits(**inputs)
        assert limits is not None
        findings = [o["finding"] for o in limits["offsets"]]
        assert any("VIX" in f for f in findings)

    def test_bull_market_appears_as_offset_for_contraction_setup(self):
        inputs = self._default_inputs()
        limits = market_setup.build_conviction_limits(**inputs)
        assert limits is not None
        findings = [o["finding"] for o in limits["offsets"]]
        assert any("bull market" in f.lower() for f in findings)

    def test_no_limits_when_all_aligned(self):
        inputs = self._default_inputs()
        inputs["policy_response"] = market_setup.build_policy_response(
            _fomc_tone_headline("dovish", "cut"),
            _m2_headline("expanding"),
            _inflation_context("near_target"),
            _fed_balance_sheet(),
        )
        inputs["setup_type_result"]["setup_type"] = "growth_and_conditions_aligned"
        inputs["market_environment"] = market_setup.build_market_environment(
            _market_phase_payload("bull_market")
        )
        limits = market_setup.build_conviction_limits(**inputs)
        # Still may have M2 and VIX offsets, but no market-phase offset
        phase_offsets = [
            o
            for o in (limits["offsets"] if limits else [])
            if "bull market" in o.get("finding", "").lower()
        ]
        assert len(phase_offsets) == 0


class TestConfirmationConditions:
    def test_has_both_directions(self):
        conditions = market_setup.build_confirmation_conditions(
            {"setup_type": "contraction_risk_aligned"},
            {"state": "bull_market"},
        )
        assert len(conditions["more_defensive"]) > 0
        assert len(conditions["more_constructive"]) > 0

    def test_more_defensive_includes_bear_market(self):
        conditions = market_setup.build_confirmation_conditions(
            {"setup_type": "contraction_risk_aligned"},
            {"state": "bull_market"},
        )
        assert any("bear" in c.lower() for c in conditions["more_defensive"])

    def test_more_constructive_includes_ism_improve(self):
        conditions = market_setup.build_confirmation_conditions(
            {"setup_type": "contraction_risk_aligned"},
            {"state": "bull_market"},
        )
        assert any("ISM" in c for c in conditions["more_constructive"])

    def test_identical_inputs_produce_identical_conditions(self):
        c1 = market_setup.build_confirmation_conditions(
            {"setup_type": "contraction_risk_aligned"},
            {"state": "bull_market"},
        )
        c2 = market_setup.build_confirmation_conditions(
            {"setup_type": "contraction_risk_aligned"},
            {"state": "bull_market"},
        )
        assert c1 == c2


class TestNarrativeDeterminism:
    def test_identical_inputs_produce_identical_narrative_fields(self):
        inputs = {
            "market_phase_payload": _market_phase_payload("bull_market"),
            "survey_synthesis": _survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            ),
            "rates_liquidity_payload": _rates_liquidity_payload("steep", "healthy"),
            "fomc_tone": _fomc_tone_headline("dovish", "cut"),
            "m2_headline": _m2_headline("expanding"),
            "inflation_context": _inflation_context("near_target"),
            "fed_balance_sheet": _fed_balance_sheet(),
        }
        from copy import deepcopy

        r1 = market_setup.build_market_setup(**deepcopy(inputs))
        r2 = market_setup.build_market_setup(**deepcopy(inputs))
        assert r1["market_conclusion"] == r2["market_conclusion"]
        assert r1["portfolio_guidance"] == r2["portfolio_guidance"]
        assert r1["evidence_chain"] == r2["evidence_chain"]
        assert r1["confirmation_conditions"] == r2["confirmation_conditions"]

    def test_narrative_fields_present_in_full_build(self):
        result = market_setup.build_market_setup(
            market_phase_payload=_market_phase_payload("bull_market"),
            survey_synthesis=_survey_synthesis(
                economic_direction="aligned_expansion",
                expected_gdp_direction="rising",
                survey_portfolio_implication="long",
                period="2026-06",
            ),
            rates_liquidity_payload=_rates_liquidity_payload("steep", "healthy"),
            fomc_tone=_fomc_tone_headline("dovish", "cut"),
            m2_headline=_m2_headline("expanding"),
            inflation_context=_inflation_context("near_target"),
            fed_balance_sheet=_fed_balance_sheet(),
        )
        assert "market_conclusion" in result
        assert "portfolio_guidance" in result
        assert "evidence_chain" in result
        assert "conviction_limits" in result
        assert "confirmation_conditions" in result
        assert result["market_conclusion"]["code"]
        assert result["portfolio_guidance"]["posture"] == "long"
        assert len(result["evidence_chain"]) == 3
