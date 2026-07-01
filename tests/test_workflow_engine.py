from app import workflow_engine


def method_payload():
    return {
        "version": "v1",
        "source_documents": [],
        "concepts": [],
        "workflow_nodes": [
            {
                "id": "instrument_identity",
                "title": "Instrument Identity",
                "decision_question": "Is this tradable?",
                "description": "Confirms symbol identity.",
                "required_inputs": ["symbol"],
                "criteria": ["Symbol is present."],
                "tool_hooks": [],
                "incoming_edges": [],
                "outgoing_edges": ["technical_timing"],
                "source_refs": [],
            },
            {
                "id": "technical_timing",
                "title": "Technical Timing",
                "decision_question": "Is timing supportive?",
                "description": "Checks long and short timing.",
                "required_inputs": ["signals.trend"],
                "criteria": ["Long wants uptrend; short wants downtrend."],
                "tool_hooks": [],
                "incoming_edges": ["instrument_identity"],
                "outgoing_edges": ["final_synthesis"],
                "source_refs": [],
            },
            {
                "id": "final_synthesis",
                "title": "Final Synthesis",
                "decision_question": "What is the decision?",
                "description": "Aggregates outputs.",
                "required_inputs": [],
                "criteria": ["Aggregate checks."],
                "tool_hooks": [],
                "incoming_edges": ["technical_timing"],
                "outgoing_edges": [],
                "source_refs": [],
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
                "missing_message": "Symbol missing.",
                "fail_effect": "reject",
                "source_refs": [],
            },
            {
                "id": "long_trend",
                "node_id": "technical_timing",
                "title": "Long trend",
                "field": "signals.trend",
                "operator": "equals",
                "value": "up",
                "side": "long",
                "required": False,
                "missing_message": "Trend missing.",
                "fail_effect": "wait_for_timing",
                "source_refs": [],
            },
            {
                "id": "short_trend",
                "node_id": "technical_timing",
                "title": "Short trend",
                "field": "signals.trend",
                "operator": "equals",
                "value": "down",
                "side": "short",
                "required": False,
                "missing_message": "Trend missing.",
                "fail_effect": "wait_for_timing",
                "source_refs": [],
            },
        ],
        "decision_rules": [],
        "extraction_warnings": [],
    }


def test_evaluate_workflow_method_returns_long_watchlist():
    result = workflow_engine.evaluate_workflow_method(
        method_payload(),
        {"symbol": "NVDA", "observations": {"signals": {"trend": "up"}}},
    )

    assert result["symbol"] == "NVDA"
    assert result["final_status"] == "long_watchlist"
    assert result["nodes"][1]["long"]["status"] == "pass"
    assert result["nodes"][1]["short"]["status"] == "fail"


def test_evaluate_workflow_method_returns_short_watchlist():
    result = workflow_engine.evaluate_workflow_method(
        method_payload(),
        {"symbol": "NVDA", "observations": {"signals": {"trend": "down"}}},
    )

    assert result["final_status"] == "short_watchlist"


def test_evaluate_workflow_method_returns_wait_for_timing_when_optional_timing_missing():
    result = workflow_engine.evaluate_workflow_method(
        method_payload(),
        {"symbol": "NVDA", "observations": {}},
    )

    assert result["final_status"] == "wait_for_timing"
    assert result["missing_information"]
    assert "wait_for_timing" in result["next_actions"]


def test_evaluate_workflow_method_uses_computed_indicator_values():
    payload = method_payload()
    payload["workflow_nodes"][1]["indicators"] = [
        {
            "id": "estimate_skew",
            "title": "Estimate Skew",
            "description": "Mean estimate compared with midpoint.",
            "formula": "mean - ((low + high) / 2)",
            "required_inputs": [
                "estimates.next_year_eps_low",
                "estimates.next_year_eps_high",
                "estimates.next_year_eps_mean",
            ],
            "compute_status": "computed",
            "source_refs": [],
        }
    ]
    payload["node_checks"].append(
        {
            "id": "positive_estimate_skew",
            "node_id": "technical_timing",
            "title": "Positive estimate skew",
            "field": "estimates.next_year_eps_skew",
            "operator": "gt",
            "value": 0,
            "side": "long",
            "required": False,
            "fail_effect": "watchlist",
            "source_refs": [],
        }
    )

    result = workflow_engine.evaluate_workflow_method(
        payload,
        {
            "symbol": "NVDA",
            "observations": {
                "signals": {"trend": "up"},
                "estimates": {
                    "next_year_eps_low": 1,
                    "next_year_eps_high": 2,
                    "next_year_eps_mean": 1.75,
                },
            },
        },
    )

    technical_node = result["nodes"][1]
    estimate_check = next(
        check
        for check in technical_node["checks"]
        if check["check_id"] == "positive_estimate_skew"
    )
    assert estimate_check["actual"] == 0.25
    assert estimate_check["status"] == "pass"
    assert technical_node["indicators"][0]["id"] == "estimate_skew"


def test_evaluate_workflow_method_uses_tool_runner_observations():
    payload = method_payload()
    payload["workflow_nodes"][0]["id"] = "data_readiness"
    payload["workflow_nodes"][0]["title"] = "Data Readiness"
    payload["workflow_nodes"][0]["tool_hooks"] = ["market_data"]
    payload["workflow_nodes"][0]["required_inputs"] = ["symbol", "metrics.price"]
    payload["node_checks"][0]["node_id"] = "data_readiness"
    payload["node_checks"][0]["group"] = "instrument_identity"
    payload["workflow_nodes"][1]["incoming_edges"] = ["data_readiness"]
    payload["node_checks"].append(
        {
            "id": "market_price_available",
            "node_id": "data_readiness",
            "title": "Market price available",
            "field": "metrics.price",
            "operator": "exists",
            "side": "both",
            "required": True,
            "missing_message": "Market price missing.",
            "fail_effect": "insufficient_data",
            "source_refs": [],
            "group": "market_data",
        }
    )

    def tool_runner(method, observation_payload):
        assert observation_payload["symbol"] == "AAPL"
        return {
            "signals": {
                "trend": "up",
            },
            "metrics": {
                "price": 123.45,
            },
        }

    result = workflow_engine.evaluate_workflow_method(
        payload,
        {"symbol": "AAPL", "observations": {}},
        tool_runner=tool_runner,
    )

    readiness_node = next(
        node for node in result["nodes"] if node["node_id"] == "data_readiness"
    )
    price_check = next(
        check
        for check in readiness_node["checks"]
        if check["check_id"] == "market_price_available"
    )

    assert price_check["status"] == "pass"
    assert price_check["actual"] == 123.45
    assert price_check["group"] == "market_data"
    assert result["final_status"] == "long_watchlist"
    assert result["final_status"] == "long_watchlist"
