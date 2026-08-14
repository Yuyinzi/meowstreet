import pytest

from app.tools.market_assistant_tools import TOOL_IDS
from app.tools.market_assistant_tools import normalized_tool_call_key
from app.tools.market_assistant_tools import tool_definitions
from app.tools.market_assistant_tools import validate_tool_call

_ROUTE_SUPPLEMENTARY_TOOL_IDS = [
    "get_indicator_current",
    "get_indicator_definition",
    "get_indicator_method",
    "query_indicator_history",
]


def test_snapshot_tool_rejects_model_supplied_context_id():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_1",
                "tool_name": "get_confirmation_test",
                "arguments": {"test_id": "vix", "context_id": "ctx_other"},
            },
            {"get_confirmation_test"},
        )


def test_history_tool_rejects_url_and_unknown_indicator():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_2",
                "tool_name": "query_indicator_history",
                "arguments": {
                    "indicator_id": "https://example.com/vix",
                    "window": "6m",
                },
            },
            {"query_indicator_history"},
        )


def test_normalized_key_detects_reordered_duplicate_arguments():
    left = {
        "call_id": "a",
        "tool_name": "get_indicator_knowledge",
        "arguments": {"indicator_id": "vix", "topic": "definition"},
    }
    right = {
        "call_id": "b",
        "tool_name": "get_indicator_knowledge",
        "arguments": {"topic": "definition", "indicator_id": "vix"},
    }
    assert normalized_tool_call_key(left) == normalized_tool_call_key(right)


def test_valid_snapshot_tool_call_returns_plain_dict():
    call = {
        "call_id": "call_3",
        "tool_name": "get_setup_overview",
        "arguments": {},
    }
    assert validate_tool_call(call, {"get_setup_overview"}) == call


def test_tool_not_in_allowed_ids_rejected():
    call = {
        "call_id": "call_4",
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": "vix"},
    }
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(call, {"get_setup_overview"})


def test_unknown_tool_rejected_even_when_allowed():
    call = {
        "call_id": "call_5",
        "tool_name": "run_sql",
        "arguments": {"sql": "select 1"},
    }
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(call, {"run_sql"})


@pytest.mark.parametrize("call_id", ["", "   ", None, 123])
def test_empty_or_malformed_call_id_rejected(call_id):
    call = {
        "call_id": call_id,
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": "vix"},
    }
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(call, {"get_confirmation_test"})


@pytest.mark.parametrize("test_id", ["equity", "credit", "vix"])
def test_confirmation_test_accepts_each_test_id(test_id):
    validated = validate_tool_call(
        {
            "call_id": "call_6",
            "tool_name": "get_confirmation_test",
            "arguments": {"test_id": test_id},
        },
        {"get_confirmation_test"},
    )
    assert validated["arguments"]["test_id"] == test_id


def test_confirmation_test_rejects_unknown_test_id():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_7",
                "tool_name": "get_confirmation_test",
                "arguments": {"test_id": "gold"},
            },
            {"get_confirmation_test"},
        )


def test_confirmation_tests_requires_non_empty_list():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_8",
                "tool_name": "get_confirmation_tests",
                "arguments": {"test_ids": []},
            },
            {"get_confirmation_tests"},
        )


def test_confirmation_tests_accepts_multiple_test_ids():
    validated = validate_tool_call(
        {
            "call_id": "call_9",
            "tool_name": "get_confirmation_tests",
            "arguments": {"test_ids": ["equity", "credit", "vix"]},
        },
        {"get_confirmation_tests"},
    )
    assert validated["arguments"]["test_ids"] == ["equity", "credit", "vix"]


def test_indicator_knowledge_rejects_unknown_topic():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_10",
                "tool_name": "get_indicator_knowledge",
                "arguments": {"indicator_id": "vix", "topic": "sql"},
            },
            {"get_indicator_knowledge"},
        )


def test_indicator_knowledge_rejects_sql_shaped_indicator():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_11",
                "tool_name": "get_indicator_knowledge",
                "arguments": {"indicator_id": "vix; drop table", "topic": "definition"},
            },
            {"get_indicator_knowledge"},
        )


def test_history_accepts_iso_dates():
    validated = validate_tool_call(
        {
            "call_id": "call_12",
            "tool_name": "query_indicator_history",
            "arguments": {
                "indicator_id": "vix",
                "start": "2026-01-01",
                "end": "2026-06-30",
            },
        },
        {"query_indicator_history"},
    )
    assert validated["arguments"]["start"] == "2026-01-01"
    assert validated["arguments"]["end"] == "2026-06-30"
    assert validated["arguments"]["window"] is None


def test_history_rejects_both_window_and_dates():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_13",
                "tool_name": "query_indicator_history",
                "arguments": {
                    "indicator_id": "vix",
                    "window": "6m",
                    "start": "2026-01-01",
                    "end": "2026-06-30",
                },
            },
            {"query_indicator_history"},
        )


def test_history_rejects_neither_window_nor_dates():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_14",
                "tool_name": "query_indicator_history",
                "arguments": {"indicator_id": "vix"},
            },
            {"query_indicator_history"},
        )


def test_history_rejects_invalid_iso_date():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_15",
                "tool_name": "query_indicator_history",
                "arguments": {
                    "indicator_id": "vix",
                    "start": "not-a-date",
                    "end": "2026-06-30",
                },
            },
            {"query_indicator_history"},
        )


def test_compare_snapshots_accepts_context_pairs():
    validated = validate_tool_call(
        {
            "call_id": "call_16",
            "tool_name": "compare_snapshots",
            "arguments": {"context_a_id": "ctx_a", "context_b_id": "ctx_b"},
        },
        {"compare_snapshots"},
    )
    assert validated["arguments"]["context_a_id"] == "ctx_a"
    assert validated["arguments"]["context_b_id"] == "ctx_b"


def test_research_tool_uses_bounded_research_contract():
    validated = validate_tool_call(
        {
            "call_id": "call_17",
            "tool_name": "research_focused",
            "arguments": {
                "purpose": "current_events",
                "queries": ["latest ism report"],
                "expected_source_class": "official_publication",
            },
        },
        {"research_focused"},
    )
    assert validated["arguments"]["queries"] == ["latest ism report"]


def test_research_tool_rejects_url_query():
    with pytest.raises(ValueError, match="tool call is invalid"):
        validate_tool_call(
            {
                "call_id": "call_18",
                "tool_name": "research_deep",
                "arguments": {
                    "purpose": "current_events",
                    "queries": ["https://example.test/search"],
                    "expected_source_class": "official_publication",
                },
            },
            {"research_deep"},
        )


@pytest.mark.parametrize("tool_id", TOOL_IDS)
def test_every_registered_tool_produces_valid_function_schema(tool_id):
    definitions = tool_definitions([tool_id])
    assert len(definitions) == 1
    definition = definitions[0]
    assert definition["type"] == "function"
    assert definition["name"] == tool_id
    assert definition["parameters"]["type"] == "object"
    assert definition["parameters"]["additionalProperties"] is False


def test_tool_definitions_support_route_supplementary_ids():
    definitions = tool_definitions(_ROUTE_SUPPLEMENTARY_TOOL_IDS)
    assert [definition["name"] for definition in definitions] == [
        "get_indicator_current",
        "get_indicator_definition",
        "get_indicator_method",
        "query_indicator_history",
    ]


def test_tool_definitions_reject_forbidden_tool_id():
    with pytest.raises(ValueError, match="tool is not registered"):
        tool_definitions(["run_sql"])


def test_tool_definitions_omit_research_unless_requested():
    definitions = tool_definitions(["get_setup_overview", "get_confirmation_tests"])
    assert [definition["name"] for definition in definitions] == [
        "get_setup_overview",
        "get_confirmation_tests",
    ]


def test_tool_definitions_include_research_when_requested():
    definitions = tool_definitions(["research_deep"])
    assert definitions[0]["name"] == "research_deep"


def test_duplicate_call_keys_ignore_call_id():
    first = {
        "call_id": "a",
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": "vix"},
    }
    second = {
        "call_id": "b",
        "tool_name": "get_confirmation_test",
        "arguments": {"test_id": "vix"},
    }
    assert normalized_tool_call_key(first) == normalized_tool_call_key(second)


def test_no_schema_contains_forbidden_properties():
    forbidden = {"url", "sql", "provider", "path", "context_id"}
    for tool_id in TOOL_IDS:
        definition = tool_definitions([tool_id])[0]
        names = _schema_property_names(definition["parameters"])
        assert not (names & forbidden)


def _schema_property_names(schema):
    names = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "properties":
                names.update(value.keys())
            else:
                names.update(_schema_property_names(value))
    elif isinstance(schema, list):
        for item in schema:
            names.update(_schema_property_names(item))
    return names
