import pytest

from app.tools.market_assistant_plans import _OPERATIONS
from app.tools.market_assistant_plans import deterministic_plan
from app.tools.market_assistant_plans import registered_operation_ids
from app.tools.market_assistant_plans import validate_operation
from app.tools.market_assistant_plans import validate_task_plan

_RESEARCH_TIERS = {
    "research_focused": "focused",
    "research_standard": "standard",
    "research_deep": "deep",
}


def valid_plan(intent="definition", **overrides):
    plan = {
        "intent": intent,
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "get_indicator_definition",
                "parameters": {"indicator_id": "vix"},
            }
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }
    plan.update(overrides)
    return plan


def research_plan(**overrides):
    plan = {
        "intent": "external_research",
        "context_mode": "current",
        "operations": [
            {
                "operation_id": "research_focused",
                "parameters": {
                    "purpose": "current_events",
                    "queries": ["latest official ism report"],
                    "expected_source_class": "official_publication",
                },
            }
        ],
        "answer_depth": "detailed",
        "research_tier": "focused",
    }
    plan.update(overrides)
    return plan


def operation_parameters(operation_id):
    return {
        "resolve_current_explanation": {},
        "get_historical_snapshot": {"context_id": "ctx_A"},
        "get_snapshot_object": {
            "object_type": "confirmation_test",
            "object_id": "vix_downside_confirmation",
        },
        "get_counterfactuals": {"context_id": "ctx_A"},
        "compare_snapshots": {"context_a_id": "ctx_A", "context_b_id": "ctx_B"},
        "get_indicator_definition": {"indicator_id": "vix"},
        "get_indicator_method": {"indicator_id": "vix"},
        "get_indicator_source": {"indicator_id": "vix"},
        "get_indicator_current": {"indicator_id": "vix"},
        "query_indicator_history": {
            "indicator_id": "vix",
            "start": "2026-01-01",
            "end": "2026-06-30",
        },
        "compare_indicator_periods": {
            "indicator_id": "vix",
            "period_a": {"start": "2026-01-01", "end": "2026-03-31"},
            "period_b": {"start": "2026-04-01", "end": "2026-06-30"},
        },
        "query_release_history": {
            "indicator_id": "vix",
            "start": "2026-01-01",
            "end": "2026-06-30",
        },
        "research_focused": {
            "purpose": "current_events",
            "queries": ["latest ism report"],
            "expected_source_class": "official_publication",
        },
        "research_standard": {
            "purpose": "current_events",
            "queries": ["latest ism report"],
            "expected_source_class": "official_publication",
        },
        "research_deep": {
            "purpose": "current_events",
            "queries": ["latest ism report"],
            "expected_source_class": "official_publication",
        },
        "get_setup_overview": {},
        "get_macro_regime_explanation": {},
        "get_confirmation_test": {"test_id": "vix"},
        "get_confirmation_tests": {"test_ids": ["vix"]},
        "get_posture_explanation": {},
        "get_approved_counterfactuals": {},
        "get_indicator_knowledge": {
            "indicator_id": "vix",
            "topic": "definition",
        },
    }[operation_id]


def test_plan_rejects_arbitrary_operation():
    payload = valid_plan()
    payload["operations"] = [
        {"operation_id": "run_sql", "parameters": {"sql": "select 1"}}
    ]

    with pytest.raises(ValueError, match="task plan is invalid"):
        validate_task_plan(payload)


def test_current_intent_cannot_select_historical_context():
    payload = valid_plan(intent="decision_explanation")
    payload["context_mode"] = "historical"
    with pytest.raises(
        ValueError, match="historical context requires historical intent"
    ):
        validate_task_plan(payload)


@pytest.mark.parametrize(
    "question",
    [
        "Why is the current setup Mild Risk-Off?",
        "Explain the market setup",
        "Explain the current market setup",
        "Why this setup?",
    ],
)
def test_decision_explanation_does_not_search_when_snapshot_is_sufficient(question):
    plan = deterministic_plan(question)

    assert plan["intent"] == "decision_explanation"
    assert [operation["operation_id"] for operation in plan["operations"]] == [
        "resolve_current_explanation"
    ]


def test_explicit_latest_external_request_uses_focused_research():
    plan = deterministic_plan("Search the latest official ISM report")
    assert plan["operations"][0]["operation_id"] == "research_focused"


def test_operation_registry_matches_approved_ids():
    assert _OPERATIONS == {
        "resolve_current_explanation",
        "get_historical_snapshot",
        "get_snapshot_object",
        "get_counterfactuals",
        "compare_snapshots",
        "get_indicator_definition",
        "get_indicator_method",
        "get_indicator_source",
        "get_indicator_current",
        "query_indicator_history",
        "compare_indicator_periods",
        "query_release_history",
        "research_focused",
        "research_standard",
        "research_deep",
        "get_setup_overview",
        "get_macro_regime_explanation",
        "get_confirmation_test",
        "get_confirmation_tests",
        "get_posture_explanation",
        "get_approved_counterfactuals",
        "get_indicator_knowledge",
    }
    assert registered_operation_ids() == _OPERATIONS


def test_valid_plan_returns_validated_plain_dict():
    plan = validate_task_plan(valid_plan())
    assert plan == valid_plan()
    assert isinstance(plan, dict)


@pytest.mark.parametrize("operation_id", ["run_sql", "drop_table", "search_web"])
def test_unknown_operation_id_rejected(operation_id):
    payload = valid_plan()
    payload["operations"] = [
        {"operation_id": operation_id, "parameters": {"anything": "ignored"}}
    ]
    with pytest.raises(ValueError, match="task plan is invalid"):
        validate_task_plan(payload)


def test_unknown_intent_rejected():
    with pytest.raises(ValueError, match="task plan intent is unknown"):
        validate_task_plan(valid_plan(intent="forecast"))


def test_unknown_context_mode_rejected():
    with pytest.raises(ValueError, match="task plan context mode is unknown"):
        validate_task_plan(valid_plan(context_mode="live"))


def test_unknown_answer_depth_rejected():
    with pytest.raises(ValueError, match="task plan answer depth is unknown"):
        validate_task_plan(valid_plan(answer_depth="verbose"))


def test_empty_operations_rejected():
    with pytest.raises(ValueError, match="task plan operations are required"):
        validate_task_plan(valid_plan(operations=[]))


def test_extra_field_rejected():
    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        validate_task_plan(valid_plan(unexpected="x"))


def test_historical_intent_requires_historical_context():
    with pytest.raises(
        ValueError, match="historical intent requires historical context"
    ):
        validate_task_plan(valid_plan(intent="historical_snapshot"))


def test_historical_plan_valid_when_context_matches():
    payload = valid_plan(intent="historical_snapshot", context_mode="historical")
    payload["operations"] = [
        {
            "operation_id": "get_historical_snapshot",
            "parameters": {"context_id": "ctx_A"},
        }
    ]
    plan = validate_task_plan(payload)
    assert plan["context_mode"] == "historical"


def test_operation_parameters_missing_required_field_rejected():
    payload = valid_plan()
    payload["operations"] = [
        {"operation_id": "get_historical_snapshot", "parameters": {}}
    ]
    with pytest.raises(ValueError, match="task plan operation parameters are invalid"):
        validate_task_plan(payload)


def test_operation_parameters_extra_field_rejected():
    payload = valid_plan()
    payload["operations"] = [
        {
            "operation_id": "get_indicator_definition",
            "parameters": {"indicator_id": "vix", "sql": "select 1"},
        }
    ]
    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        validate_task_plan(payload)


def test_operation_parameters_invalid_date_rejected():
    payload = valid_plan()
    payload["operations"] = [
        {
            "operation_id": "query_indicator_history",
            "parameters": {
                "indicator_id": "vix",
                "start": "2026-99-99",
                "end": "2026-06-30",
            },
        }
    ]
    with pytest.raises(ValueError, match="task plan operation parameters are invalid"):
        validate_task_plan(payload)


def test_research_operation_requires_research_tier():
    with pytest.raises(ValueError, match="research operation requires research tier"):
        validate_task_plan(research_plan(research_tier=None))


def test_research_operation_requires_matching_tier():
    with pytest.raises(
        ValueError, match="research tier does not match research operation"
    ):
        validate_task_plan(research_plan(research_tier="deep"))


def test_research_plan_valid_with_matching_tier():
    plan = validate_task_plan(research_plan())
    assert plan["research_tier"] == "focused"


def test_research_queries_reject_forbidden_content():
    payload = research_plan()
    payload["operations"][0]["parameters"]["queries"] = [
        "https://example.test/search?token=abc"
    ]
    with pytest.raises(ValueError, match="task plan operation parameters are invalid"):
        validate_task_plan(payload)


@pytest.mark.parametrize("operation_id", sorted(_OPERATIONS))
def test_every_registered_operation_validates(operation_id):
    payload = valid_plan()
    payload["operations"] = [
        {"operation_id": operation_id, "parameters": operation_parameters(operation_id)}
    ]
    if operation_id in _RESEARCH_TIERS:
        payload["research_tier"] = _RESEARCH_TIERS[operation_id]
    plan = validate_task_plan(payload)
    assert plan["operations"][0]["operation_id"] == operation_id


def test_deterministic_definition_question_routes_to_definition():
    plan = deterministic_plan("What is the definition of the VIX?")
    assert plan["intent"] == "definition"
    assert plan["operations"] == [
        {
            "operation_id": "get_indicator_definition",
            "parameters": {"indicator_id": "vix"},
        }
    ]


def test_deterministic_method_question_routes_to_method():
    plan = deterministic_plan("How is the VIX calculated?")
    assert plan["intent"] == "method"
    assert plan["operations"] == [
        {
            "operation_id": "get_indicator_method",
            "parameters": {"indicator_id": "vix"},
        }
    ]


def test_deterministic_source_question_routes_to_source():
    plan = deterministic_plan("What is the source of the ISM PMI?")
    assert plan["intent"] == "source"
    assert plan["operations"] == [
        {
            "operation_id": "get_indicator_source",
            "parameters": {"indicator_id": "ism_manufacturing_pmi"},
        }
    ]


def test_deterministic_history_question_routes_to_history():
    plan = deterministic_plan(
        "What was the VIX history between 2026-01-01 and 2026-06-30?"
    )
    assert plan["intent"] == "local_history"
    assert plan["operations"] == [
        {
            "operation_id": "query_indicator_history",
            "parameters": {
                "indicator_id": "vix",
                "start": "2026-01-01",
                "end": "2026-06-30",
                "statistics": [],
            },
        }
    ]


def test_deterministic_history_question_without_window_is_unsupported():
    plan = deterministic_plan("What was the VIX history?")
    assert plan["intent"] == "unsupported"
    assert plan["operations"] == []


def test_unsupported_question_returns_typed_unsupported_plan():
    plan = deterministic_plan("Tell me a joke")
    assert plan["intent"] == "unsupported"
    assert plan["context_mode"] == "current"
    assert plan["answer_depth"] == "standard"
    assert plan["operations"] == []
    assert plan["reason_code"] == "unsupported_request"


def test_deterministic_plans_are_validated():
    questions = (
        "Why is the current setup Mild Risk-Off?",
        "Search the latest official ISM report",
        "What is the definition of the VIX?",
        "How is the VIX calculated?",
        "What is the source of the ISM PMI?",
        "What was the VIX history between 2026-01-01 and 2026-06-30?",
    )
    for question in questions:
        plan = deterministic_plan(question)
        assert validate_task_plan(plan) == plan


def test_validate_operation_returns_plain_dict():
    result = validate_operation("get_indicator_definition", {"indicator_id": "vix"})
    assert result == {
        "operation_id": "get_indicator_definition",
        "parameters": {"indicator_id": "vix"},
    }
    assert isinstance(result, dict)


def test_validate_operation_rejects_unknown_operation():
    with pytest.raises(ValueError, match="operation is invalid"):
        validate_operation("run_sql", {"sql": "select 1"})


def test_validate_operation_rejects_invalid_parameters():
    with pytest.raises(ValueError, match="operation is invalid"):
        validate_operation("get_confirmation_test", {"test_id": "gold"})


@pytest.mark.parametrize(
    "operation_id",
    [
        "get_setup_overview",
        "get_macro_regime_explanation",
        "get_confirmation_test",
        "get_confirmation_tests",
        "get_posture_explanation",
        "get_approved_counterfactuals",
        "get_indicator_knowledge",
    ],
)
def test_validate_operation_covers_focused_operations(operation_id):
    result = validate_operation(operation_id, operation_parameters(operation_id))
    assert result["operation_id"] == operation_id


def test_validate_operation_rejects_model_supplied_context_id_on_snapshot():
    with pytest.raises(ValueError, match="operation is invalid"):
        validate_operation(
            "get_setup_overview",
            {"context_id": "ctx_other"},
        )


@pytest.mark.parametrize(
    "operation_id",
    [
        "resolve_current_explanation",
        "get_historical_snapshot",
        "get_snapshot_object",
        "get_counterfactuals",
        "compare_snapshots",
        "get_indicator_definition",
        "get_indicator_method",
        "get_indicator_source",
        "get_indicator_current",
        "query_indicator_history",
        "compare_indicator_periods",
        "query_release_history",
        "research_focused",
        "research_standard",
        "research_deep",
    ],
)
def test_validate_operation_keeps_existing_operations_valid(operation_id):
    result = validate_operation(operation_id, operation_parameters(operation_id))
    assert result["operation_id"] == operation_id
