import pytest

from app.tools import market_setup_v2_relationships


class TestRelationshipToGrowthDirection:
    def test_financial_confirms_expansion_supports_upside(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "confirms_expansion", "rising"
        )
        assert result == "supports"

    def test_financial_confirms_expansion_conflicts_downside(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "confirms_expansion", "slowing"
        )
        assert result == "conflicts"

    def test_financial_confirms_contraction_supports_downside(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "confirms_contraction_risk", "falling"
        )
        assert result == "supports"

    def test_financial_neutral_state_is_neutral(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "mixed", "rising"
        )
        assert result == "neutral"

    def test_policy_support_confirmed_supports_upside(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_policy_response", "support_confirmed", "rising"
        )
        assert result == "supports"

    def test_policy_restrictive_supports_downside(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_policy_response", "restrictive_confirmed", "slowing"
        )
        assert result == "supports"

    def test_consumer_confirms_downside_supports_downside(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "consumer_demand_outlook", "confirms_downside_risk", "falling"
        )
        assert result == "supports"

    def test_unavailable_state_returns_unavailable(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "unavailable", "rising"
        )
        assert result == "unavailable"

    def test_missing_state_returns_unavailable(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "missing", "rising"
        )
        assert result == "unavailable"

    def test_none_state_returns_unavailable(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", None, "rising"
        )
        assert result == "unavailable"

    def test_stable_direction_is_neutral(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_financial_conditions", "confirms_expansion", "stable"
        )
        assert result == "neutral"

    def test_unknown_state_is_neutral(self):
        result = market_setup_v2_relationships.relationship_to_growth_direction(
            "macro_policy_response", "no_clear_response", "rising"
        )
        assert result == "neutral"

    def test_method_version_is_explicit(self):
        assert market_setup_v2_relationships.RELATIONSHIP_METHOD_VERSION == (
            "market_setup_v2_relationship_v1"
        )
