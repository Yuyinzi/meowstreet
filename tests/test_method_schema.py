import pytest

from app import method_schema


def valid_method():
    return {
        "version": " v1 ",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "source_documents": [{"path": "", "title": "P1"}],
        "concepts": [],
        "workflow_nodes": [
            {
                "id": "instrument_identity",
                "title": "Instrument Identity",
                "decision_question": "Is this tradable?",
                "description": "Confirms symbol identity.",
                "required_inputs": ["symbol"],
                "criteria": ["Symbol is present."],
                "tool_hooks": ["symbol_profile"],
                "incoming_edges": [],
                "outgoing_edges": ["final_synthesis"],
                "source_refs": [
                    {
                        "document": "",
                        "section": "Methodology / Workflow",
                    }
                ],
            },
            {
                "id": "final_synthesis",
                "title": "Final Synthesis",
                "decision_question": "What is the decision?",
                "description": "Aggregates outputs.",
                "required_inputs": [],
                "criteria": ["Combine checks."],
                "tool_hooks": [],
                "incoming_edges": ["instrument_identity"],
                "outgoing_edges": [],
                "source_refs": [
                    {
                        "document": "",
                        "section": "Methodology / Workflow",
                    }
                ],
            },
        ],
        "node_checks": [
            {
                "id": "symbol_present",
                "node_id": "instrument_identity",
                "title": "Symbol present",
                "field": "symbol",
                "operator": "exists",
                "side": "both",
                "required": True,
                "missing_message": "Symbol is missing.",
                "fail_effect": "reject",
                "source_refs": [
                    {
                        "document": "",
                        "section": "Actionable Checklist",
                    }
                ],
            }
        ],
        "decision_rules": [],
        "extraction_warnings": [],
    }


def test_normalize_method_payload_trims_version_and_keeps_graph():
    payload = method_schema.normalize_method_payload(valid_method())

    assert payload["version"] == "v1"
    assert payload["workflow_nodes"][0]["id"] == "instrument_identity"
    assert payload["node_checks"][0]["side"] == "both"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p.pop("version"), "method method version is required"),
        (
            lambda p: p.__setitem__("workflow_nodes", []),
            "workflow_nodes must not be empty",
        ),
        (lambda p: p.__setitem__("node_checks", []), "node_checks must not be empty"),
        (
            lambda p: p["workflow_nodes"][0].pop("decision_question"),
            "workflow node instrument_identity decision_question is required",
        ),
        (
            lambda p: p["workflow_nodes"][0].__setitem__(
                "outgoing_edges", ["missing_node"]
            ),
            "workflow node instrument_identity outgoing_edges references unknown node",
        ),
        (
            lambda p: p["node_checks"][0].__setitem__("side", "bad"),
            "node check symbol_present side is invalid",
        ),
        (
            lambda p: p["node_checks"][0].__setitem__("node_id", "missing_node"),
            "node check symbol_present references unknown node",
        ),
    ],
)
def test_normalize_method_payload_validates_contract(mutation, message):
    payload = valid_method()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        method_schema.normalize_method_payload(payload)


def test_normalize_graph_observation_payload_requires_symbol_and_observations():
    normalized = method_schema.normalize_graph_observation_payload(
        {"symbol": " nvda ", "observations": {"metrics": {"price": 100}}}
    )

    assert normalized["symbol"] == "NVDA"
    assert normalized["observations"]["metrics"]["price"] == 100


def test_normalize_graph_observation_payload_rejects_bad_symbol():
    with pytest.raises(ValueError, match="observation symbol is invalid"):
        method_schema.normalize_graph_observation_payload(
            {"symbol": "bad symbol", "observations": {}}
        )
