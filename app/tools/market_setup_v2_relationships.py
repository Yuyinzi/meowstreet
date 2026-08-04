RELATIONSHIP_METHOD_VERSION = "market_setup_v2_relationship_v1"

UPSIDE_DIRECTIONS = {"rising", "improving", "rebound_risk"}
DOWNSIDE_DIRECTIONS = {"slowing", "falling"}

_SUPPORTS_UPSIDE_STATES = {
    "macro_financial_conditions": {"confirms_expansion"},
    "macro_policy_response": {
        "support_confirmed",
        "support_possible",
        "support_constrained",
    },
    "consumer_demand_outlook": {"confirms_expansion"},
}

_SUPPORTS_DOWNSIDE_STATES = {
    "macro_financial_conditions": {"confirms_contraction_risk"},
    "macro_policy_response": {"restrictive_confirmed"},
    "consumer_demand_outlook": {"confirms_downside_risk"},
}

_UNAVAILABLE_STATES = {"unavailable", "missing"}


def relationship_to_growth_direction(fact_id, state, survey_direction):
    if state is None or state in _UNAVAILABLE_STATES:
        return "unavailable"
    if state in _SUPPORTS_UPSIDE_STATES.get(fact_id, set()):
        if survey_direction in UPSIDE_DIRECTIONS:
            return "supports"
        if survey_direction in DOWNSIDE_DIRECTIONS:
            return "conflicts"
        return "neutral"
    if state in _SUPPORTS_DOWNSIDE_STATES.get(fact_id, set()):
        if survey_direction in DOWNSIDE_DIRECTIONS:
            return "supports"
        if survey_direction in UPSIDE_DIRECTIONS:
            return "conflicts"
        return "neutral"
    return "neutral"
