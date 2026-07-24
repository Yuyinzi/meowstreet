from app.tools import ism_survey_synthesis


def manufacturing_signal(
    pmi_level="expanding",
    pmi_momentum="falling",
    orders_level="expanding",
    orders_momentum="falling",
    period="2026-06-01",
):
    return {
        "version": "ism_macro_signal_v1",
        "status": "available",
        "period": period,
        "growth_impulse": "mixed",
        "metrics": {
            "pmi": {
                "current": 53.3,
                "previous": 54.0,
                "level_state": pmi_level,
                "momentum": pmi_momentum,
            },
            "new_orders": {
                "current": 55.4,
                "previous": 56.0,
                "level_state": orders_level,
                "momentum": orders_momentum,
            },
        },
    }


def services_signal(
    pmi_level="expanding",
    pmi_momentum="falling",
    orders_level="expanding",
    orders_momentum="falling",
    activity_level=None,
    activity_momentum=None,
    backlog_confirmation="supports_growth",
    period="2026-06-01",
):
    ba_level = activity_level if activity_level is not None else pmi_level
    ba_momentum = activity_momentum if activity_momentum is not None else pmi_momentum
    return {
        "version": "ism_services_signal_v1",
        "state": "supports_growth",
        "period": period,
        "metrics": {
            "pmi": {
                "value": 54.0,
                "previous_value": 54.5,
                "level": pmi_level,
                "momentum": pmi_momentum,
            },
            "business_activity": {
                "value": 55.4,
                "previous_value": 56.0,
                "level": ba_level,
                "momentum": ba_momentum,
            },
            "new_orders": {
                "value": 55.1,
                "previous_value": 56.2,
                "level": orders_level,
                "momentum": orders_momentum,
            },
            "order_backlog": {
                "value": 53.0,
                "previous_value": 52.0,
                "level": "expanding",
                "momentum": "rising",
            },
        },
        "backlog_confirmation": backlog_confirmation,
        "missing_inputs": [],
    }


def test_aligned_expansion_with_falling_momentum_is_slower_growth():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(),
        services_signal(),
    )

    assert result["version"] == "ism_survey_synthesis_v1"
    assert result["status"] == "available"
    assert result["economic_direction"] == "aligned_expansion"
    assert result["growth_momentum"] == "falling"
    assert result["survey_alignment"] == "aligned"
    assert result["demand_alignment"] == "aligned_falling"
    assert result["expected_gdp_direction"] == "slowing"
    assert result["survey_portfolio_implication"] == "long"
    assert result["bias_confirmation"] == "awaiting_confirmation"
    assert result["leading_side"] == "not_applicable"
    assert "turning_point" not in result


def test_aligned_expansion_rising_maps_to_rising_and_long():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(pmi_momentum="rising", orders_momentum="rising"),
        services_signal(pmi_momentum="rising", orders_momentum="rising"),
    )
    assert result["expected_gdp_direction"] == "rising"
    assert result["survey_portfolio_implication"] == "long"
    assert result["bias_confirmation"] == "not_required"


def test_aligned_contraction_falling_maps_to_falling_and_short_or_neutral():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            pmi_level="contracting",
            orders_level="contracting",
        ),
        services_signal(
            pmi_level="contracting",
            orders_level="contracting",
        ),
    )
    assert result["economic_direction"] == "aligned_contraction"
    assert result["expected_gdp_direction"] == "falling"
    assert result["survey_portfolio_implication"] == "short_or_neutral"
    assert result["bias_confirmation"] == "not_required"


def test_contraction_demand_reason_matches_contracting_level():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            pmi_level="contracting",
            pmi_momentum="falling",
            orders_level="contracting",
            orders_momentum="falling",
        ),
        services_signal(
            pmi_level="contracting",
            pmi_momentum="falling",
            orders_level="contracting",
            orders_momentum="falling",
            activity_level="contracting",
            activity_momentum="falling",
        ),
    )
    reasons = result["reasons"]
    reason_text = " ".join(reasons)
    assert "Demand remains expansionary" not in reason_text, f"got reasons: {reasons}"
    assert any(
        "contraction" in r or "slowing" in r or "weakens" in r for r in reasons
    ), f"got reasons: {reasons}"


def test_aligned_contraction_rising_maps_to_improving():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            pmi_level="contracting",
            pmi_momentum="rising",
            orders_level="contracting",
            orders_momentum="rising",
        ),
        services_signal(
            pmi_level="contracting",
            pmi_momentum="rising",
            orders_level="contracting",
            orders_momentum="rising",
        ),
    )
    assert result["economic_direction"] == "aligned_contraction"
    assert result["expected_gdp_direction"] == "improving"
    assert result["survey_portfolio_implication"] == "short_or_neutral"
    assert result["bias_confirmation"] == "awaiting_confirmation"


def test_cross_survey_divergence_is_not_averaged():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            pmi_level="contracting",
            orders_level="contracting",
        ),
        services_signal(),
    )
    assert result["economic_direction"] == "divergent"
    assert result["survey_alignment"] == "divergent"
    assert result["expected_gdp_direction"] == "mixed"
    assert result["survey_portfolio_implication"] == "neutral"
    assert result["bias_confirmation"] == "not_required"
    assert result["cross_sector_comparison"] == "services_stronger"
    assert result["conflicts"]


def test_one_missing_survey_is_partial_without_combined_direction():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(),
        None,
    )
    assert result["status"] == "partial"
    assert result["expected_gdp_direction"] is None
    assert result["survey_portfolio_implication"] is None
    assert result["bias_confirmation"] is None
    assert result["cross_sector_comparison"] is None
    assert result["missing_inputs"] == ["ISM Services"]


def test_mixed_periods_do_not_create_combined_direction():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(period="2026-06-01"),
        services_signal(period="2026-05-01"),
    )
    assert result["status"] == "mixed_periods"
    assert result["expected_gdp_direction"] is None
    assert result["period"] is None
    assert result["conflicts"] == [
        "Manufacturing and Services observation periods differ"
    ]


def test_synthesis_has_no_invented_score_or_future_method_inputs():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(),
        services_signal(),
    )
    assert "confidence" not in result
    assert "score" not in result
    assert "weighted_average" not in result
    assert "consumer" not in result
    assert "labor" not in result


def test_services_unusable_state_is_partial():
    broken = {
        "version": "ism_services_signal_v1",
        "state": "pending_inputs",
        "period": "2026-06-01",
        "metrics": {},
        "missing_inputs": ["Services PMI"],
    }
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(),
        broken,
    )
    assert result["status"] == "partial"
    assert result["missing_inputs"] == ["ISM Services"]


def test_manufacturing_unavailable_is_partial():
    broken = {
        "version": "ism_macro_signal_v1",
        "status": "unavailable",
        "period": "2026-06-01",
        "metrics": {},
    }
    result = ism_survey_synthesis.build_survey_synthesis(
        broken,
        services_signal(),
    )
    assert result["status"] == "partial"
    assert result["cross_sector_comparison"] is None
    assert result["bias_confirmation"] is None
    assert result["missing_inputs"] == ["ISM Manufacturing"]


def test_both_missing_is_not_available():
    result = ism_survey_synthesis.build_survey_synthesis(None, None)
    assert result["status"] == "partial"
    assert result["cross_sector_comparison"] is None
    assert result["bias_confirmation"] is None
    assert result["missing_inputs"] == ["ISM Manufacturing", "ISM Services"]
    assert result["economic_direction"] is None
    assert result["expected_gdp_direction"] is None


def test_aligned_neutral_flat_maps_to_stable_and_neutral():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            pmi_level="neutral",
            pmi_momentum="flat",
            orders_level="neutral",
            orders_momentum="flat",
        ),
        services_signal(
            pmi_level="neutral",
            pmi_momentum="flat",
            orders_level="neutral",
            orders_momentum="flat",
        ),
    )
    assert result["economic_direction"] == "aligned_neutral"
    assert result["expected_gdp_direction"] == "stable"
    assert result["survey_portfolio_implication"] == "neutral"
    assert result["bias_confirmation"] == "not_required"


def test_demand_alignment_mixed_momentum():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(orders_momentum="rising"),
        services_signal(orders_momentum="falling"),
    )
    assert result["demand_alignment"] == "mixed_momentum"


def test_demand_alignment_divergent_levels():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(orders_level="contracting", orders_momentum="falling"),
        services_signal(orders_level="expanding", orders_momentum="falling"),
    )
    assert result["demand_alignment"] == "divergent"


def test_synthesis_compares_manufacturing_new_orders_with_services_activity():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            pmi_level="expanding",
            orders_level="contracting",
            orders_momentum="falling",
        ),
        services_signal(
            pmi_level="expanding",
            activity_level="expanding",
            activity_momentum="rising",
        ),
    )

    assert result["components"]["services"]["activity_level"] == "expanding"
    assert result["components"]["services"]["activity_momentum"] == "rising"
    assert result["cross_sector_comparison"] == "services_stronger"
    assert result["leading_side"] == "services"


def test_synthesis_cross_sector_aligned_when_same_level_and_momentum():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            orders_level="expanding",
            orders_momentum="falling",
        ),
        services_signal(
            activity_level="expanding",
            activity_momentum="falling",
        ),
    )
    assert result["cross_sector_comparison"] == "aligned"
    assert result["leading_side"] == "not_applicable"


def test_synthesis_cross_sector_manufacturing_stronger():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            orders_level="expanding",
            orders_momentum="rising",
        ),
        services_signal(
            pmi_level="expanding",
            activity_level="expanding",
            activity_momentum="falling",
        ),
    )
    assert result["cross_sector_comparison"] == "manufacturing_stronger"
    assert result["leading_side"] == "manufacturing"


def test_backlog_is_visible_supporting_evidence_without_changing_direction():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(pmi_level="expanding"),
        services_signal(
            pmi_level="expanding",
            backlog_confirmation="supports_contraction",
        ),
    )

    assert result["economic_direction"] == "aligned_expansion"
    assert result["backlog_confirmation"] == "supports_contraction"
    assert any("backlog" in reason.lower() for reason in result["reasons"])


def test_backlog_supports_growth_reason():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(pmi_level="expanding"),
        services_signal(
            pmi_level="expanding",
            backlog_confirmation="supports_growth",
        ),
    )
    assert result["backlog_confirmation"] == "supports_growth"
    assert any("backlog" in reason.lower() for reason in result["reasons"])


def test_backlog_neutral_reason():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(pmi_level="expanding"),
        services_signal(
            pmi_level="expanding",
            backlog_confirmation="neutral",
        ),
    )
    assert result["backlog_confirmation"] == "neutral"
    assert any("backlog" in reason.lower() for reason in result["reasons"])


def test_synthesis_cross_sector_unresolved_when_unclear():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(
            orders_level="contracting",
            orders_momentum="rising",
        ),
        services_signal(
            pmi_level="contracting",
            activity_level="neutral",
            activity_momentum="falling",
        ),
    )
    assert result["cross_sector_comparison"] == "unresolved"
    assert result["leading_side"] == "unresolved"


def test_expansion_with_one_period_slowing_keeps_long_bias_pending_confirmation():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(pmi_level="expanding", pmi_momentum="falling"),
        services_signal(pmi_level="expanding", pmi_momentum="falling"),
    )

    assert result["expected_gdp_direction"] == "slowing"
    assert result["survey_portfolio_implication"] == "long"
    assert result["bias_confirmation"] == "awaiting_confirmation"
    assert "turning_point" not in result
    assert "peak" not in result
    assert "trough" not in result


def test_mixed_headline_momentum_when_surveys_disagree():
    result = ism_survey_synthesis.build_survey_synthesis(
        manufacturing_signal(pmi_momentum="rising"),
        services_signal(pmi_momentum="falling"),
    )
    assert result["growth_momentum"] == "mixed"
    assert result["survey_alignment"] == "aligned"
