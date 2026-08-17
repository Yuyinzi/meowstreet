import pytest

from app.tools.market_assistant_routes import ROUTE_IDS
from app.tools.market_assistant_routes import budget_for_mode
from app.tools.market_assistant_routes import route_question
from app.tools.market_assistant_routes import validate_route

_ROUTE_QUESTIONS = {
    "current_setup_overview": "现在市场怎么样？",
    "indicator_question": "VIX是什么？",
    "why_setup_layer": "为什么当前宏观环境如此？",
    "react": "讲个笑话",
}


def standard_budget():
    return {
        "max_rounds": 2,
        "max_parallel_calls": 4,
        "max_tool_calls": 8,
        "max_tool_result_bytes": 32 * 1024,
        "deadline_seconds": 90.0,
    }


def deep_analysis_budget():
    return {
        "max_rounds": 4,
        "max_parallel_calls": 4,
        "max_tool_calls": 12,
        "max_tool_result_bytes": 96 * 1024,
        "deadline_seconds": 300.0,
    }


def test_standard_budget_is_bounded():
    assert budget_for_mode(False) == standard_budget()


def test_deep_analysis_budget_is_independent_and_larger():
    assert budget_for_mode(True) == deep_analysis_budget()


def test_chinese_setup_question_uses_deterministic_fast_path():
    route = route_question("现在市场怎么样？", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"
    assert route["routing_source"] == "deterministic"
    assert [item["operation_id"] for item in route["initial_operations"]] == [
        "get_setup_overview",
        "get_macro_regime_explanation",
        "get_confirmation_tests",
        "get_posture_explanation",
        "get_approved_counterfactuals",
    ]


def test_ambiguous_composite_question_falls_through_to_react():
    route = route_question(
        "VIX、信贷和ISM最近的变化彼此有什么关系？",
        deep_analysis=True,
    )
    assert route["route_id"] == "react"
    assert route["routing_source"] == "react"
    assert route["initial_operations"] == []
    assert route["budget"]["max_rounds"] == 4


def test_english_setup_question_routes_to_overview():
    route = route_question("How is the market doing?", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"


def test_english_posture_question_routes_to_posture():
    route = route_question(
        "Why is the portfolio posture Mild Risk-Off?", deep_analysis=False
    )
    assert route["route_id"] == "why_setup_layer"


def test_english_confirmation_question_routes_to_confirmation():
    route = route_question(
        "Why is the market confirmation missing?", deep_analysis=False
    )
    assert route["route_id"] == "why_setup_layer"


def test_chinese_indicator_definition_routes_to_definition():
    route = route_question("VIX是什么？", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["initial_operations"][0]["indicator_id"] == "vix"


def test_chinese_indicator_method_routes_to_method():
    route = route_question("VIX怎么计算？", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["initial_operations"][0]["indicator_id"] == "vix"


def test_chinese_indicator_confirmation_routes_to_confirmation():
    route = route_question("ISM的确认信号怎么样？", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["initial_operations"][0]["indicator_id"] == "ism_manufacturing_pmi"


def test_chinese_why_confirmation_with_vix_routes_to_indicator_confirmation():
    route = route_question("VIX 为什么没有确认", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["initial_operations"][0]["indicator_id"] == "vix"


def test_chinese_why_partial_confirmation_routes_to_market_confirmation():
    route = route_question("为什么只是部分确认", deep_analysis=False)
    assert route["route_id"] == "why_setup_layer"


def test_english_why_indicator_confirmation_routes_to_indicator_confirmation():
    route = route_question("why is the ism confirmation weak", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["initial_operations"][0]["indicator_id"] == "ism_manufacturing_pmi"


def test_chinese_why_indicator_confirmation_routes_to_indicator_confirmation():
    route = route_question("为什么ISM的确认信号这么低？", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["initial_operations"][0]["indicator_id"] == "ism_manufacturing_pmi"


def test_english_indicator_question_uses_deep_analysis_budget():
    route = route_question("What is the VIX?", deep_analysis=True)
    assert route["route_id"] == "indicator_question"
    assert route["budget"] == deep_analysis_budget()


def test_whitespace_normalized_chinese_question_matches_marker():
    route = route_question("   现在市场    怎么样？  ", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"


def test_explain_current_market_setup_routes_to_overview():
    route = route_question("解释当前 Market Setup", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"
    assert route["routing_source"] == "deterministic"
    assert route["initial_operations"]


def test_explain_the_current_market_setup_routes_to_overview():
    route = route_question("explain the current market setup", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"
    assert route["routing_source"] == "deterministic"


def test_explain_the_market_setup_routes_to_overview():
    route = route_question("explain the market setup", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"
    assert route["routing_source"] == "deterministic"
    assert route["initial_operations"]


def test_chinese_explain_market_state_routes_to_overview():
    route = route_question("解释市场状态", deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"
    assert route["routing_source"] == "deterministic"
    assert route["initial_operations"]


@pytest.mark.parametrize(
    "question",
    [
        "explain the setup",
        "explain the current setup",
        "explain the market situation",
        "explain the current market situation",
        "what is the market setup",
        "解释市场情况",
    ],
)
def test_overview_variant_questions_route_to_overview(question):
    route = route_question(question, deep_analysis=False)
    assert route["route_id"] == "current_setup_overview"
    assert route["routing_source"] == "deterministic"
    assert route["initial_operations"]


def test_why_market_setup_question_not_hijacked_by_overview_marker():
    route = route_question(
        "why is the market setup partially confirmed", deep_analysis=False
    )
    assert route["route_id"] != "current_setup_overview"
    assert route["routing_source"] != "deterministic"
    assert route["route_id"] == "react"


@pytest.mark.parametrize(
    "question",
    [
        "explain the market setup and show VIX history",
        "what is the market setup and how has credit changed over six months?",
        "解释市场状态，并比较最近六个月的VIX和信贷变化",
        "explain the market setup and how has credit changed over six months?",
        "what is the current market setup and how has vix trended recently",
    ],
)
def test_compound_overview_questions_route_to_react(question):
    route = route_question(question, deep_analysis=False)
    assert route["route_id"] == "react"
    assert route["routing_source"] == "react"
    assert route["initial_operations"] == []


def test_simple_overview_questions_still_route_to_overview():
    for question in (
        "explain the market setup",
        "现在市场怎么样",
        "what is the current market setup",
        "解释市场情况",
    ):
        route = route_question(question, deep_analysis=False)
        assert route["route_id"] == "current_setup_overview", question


def test_explain_how_indicator_is_calculated_stays_on_indicator_route():
    route = route_question("explain how vix is calculated", deep_analysis=False)
    assert route["route_id"] == "indicator_question"
    assert route["routing_source"] == "deterministic"


def test_why_mild_risk_on_routes_to_posture():
    route = route_question("为什么是 Mild Risk-On", deep_analysis=False)
    assert route["route_id"] == "why_setup_layer"
    assert route["routing_source"] == "deterministic"
    assert [item["operation_id"] for item in route["initial_operations"]] == [
        "get_macro_regime_explanation",
        "get_confirmation_tests",
        "get_posture_explanation",
    ]


def test_why_mildly_positive_routes_to_posture():
    route = route_question("为什么是轻度偏积极", deep_analysis=False)
    assert route["route_id"] == "why_setup_layer"
    assert route["routing_source"] == "deterministic"


def test_why_mild_risk_on_english_routes_to_posture():
    route = route_question("why is the regime mild risk on?", deep_analysis=False)
    assert route["route_id"] == "why_setup_layer"
    assert route["routing_source"] == "deterministic"


def test_empty_question_raises_value_error():
    with pytest.raises(ValueError, match="question is required"):
        route_question("   ", deep_analysis=False)


def test_non_string_question_raises_value_error():
    with pytest.raises(ValueError, match="question is required"):
        route_question(None, deep_analysis=False)


def test_validate_route_rejects_extra_field():
    route = route_question("现在市场怎么样？", deep_analysis=False)
    route["unexpected"] = "x"
    with pytest.raises(ValueError, match="extra route fields are not permitted"):
        validate_route(route)


def test_validate_route_rejects_unknown_route_id():
    route = route_question("现在市场怎么样？", deep_analysis=False)
    route["route_id"] = "forecast"
    with pytest.raises(ValueError, match="route id is unknown"):
        validate_route(route)


def test_validate_route_rejects_invalid_budget():
    route = route_question("现在市场怎么样？", deep_analysis=False)
    route["budget"]["max_rounds"] = "many"
    with pytest.raises(ValueError, match="route budget is invalid"):
        validate_route(route)


def test_validate_route_rejects_missing_field():
    route = route_question("现在市场怎么样？", deep_analysis=False)
    del route["view_type"]
    with pytest.raises(ValueError, match="route is missing required field: view_type"):
        validate_route(route)


def test_react_route_requires_react_routing_source():
    route = route_question("讲个笑话", deep_analysis=False)
    route["routing_source"] = "deterministic"
    with pytest.raises(ValueError, match="react route must use react routing source"):
        validate_route(route)


@pytest.mark.parametrize("route_id", ROUTE_IDS)
def test_no_route_exposes_research_tools(route_id):
    route = route_question(_ROUTE_QUESTIONS[route_id], deep_analysis=False)
    assert route["route_id"] == route_id
    assert not any(
        tool.startswith("research_") for tool in route["supplementary_tools"]
    )


def test_react_route_has_no_initial_operations():
    route = route_question("讲个笑话", deep_analysis=True)
    assert route["route_id"] == "react"
    assert route["routing_source"] == "react"
    assert route["initial_operations"] == []
    assert route["supplementary_tools"] == []
    assert route["budget"] == deep_analysis_budget()


@pytest.mark.parametrize(
    "question",
    [
        "现在市场怎么样？",
        "为什么当前宏观环境如此？",
        "为什么市场确认信号缺失？",
        "为什么当前组合姿态如此？",
        "VIX是什么？",
        "VIX怎么计算？",
        "ISM的确认信号怎么样？",
        "讲个笑话",
    ],
)
def test_routed_payloads_validate_cleanly(question):
    route = route_question(question, deep_analysis=False)
    assert validate_route(route) == route


@pytest.mark.parametrize(
    ("route_id", "view_type"),
    [
        ("current_setup_overview", "setup_explanation"),
        ("indicator_question", "indicator_explanation"),
        ("why_setup_layer", "setup_explanation"),
        ("react", "react_anchor"),
    ],
)
def test_route_view_type_uses_shared_view_vocabulary(route_id, view_type):
    route = route_question(_ROUTE_QUESTIONS[route_id], deep_analysis=False)
    assert route["route_id"] == route_id
    assert route["view_type"] == view_type
