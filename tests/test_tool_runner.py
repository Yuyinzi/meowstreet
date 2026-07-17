from app import tool_runner


def method_with_market_data_hook():
    return {
        "workflow_nodes": [
            {
                "id": "data_readiness",
                "tool_hooks": ["market_data"],
            }
        ]
    }


def method_without_market_data_hook():
    return {
        "workflow_nodes": [
            {
                "id": "process_discipline",
                "tool_hooks": [],
            }
        ]
    }


def test_apply_tools_merges_market_data_observations():
    def fetch_market_data(symbol):
        assert symbol == "AAPL"
        return {
            "symbol": "AAPL",
            "metrics": {
                "price": 123.45,
            },
            "prices": {
                "dates": ["2026-06-30"],
                "adjusted_close": [123.45],
            },
            "data": {
                "price_series_current": True,
                "uses_adjusted_close": True,
                "no_missing_required_fields": True,
            },
        }

    enriched = tool_runner.apply_tools(
        method_with_market_data_hook(),
        {"symbol": "AAPL", "observations": {"signals": {"trend": "up"}}},
        market_data_fetcher=fetch_market_data,
    )

    assert enriched == {
        "signals": {
            "trend": "up",
        },
        "metrics": {
            "price": 123.45,
        },
        "prices": {
            "dates": ["2026-06-30"],
            "adjusted_close": [123.45],
        },
        "data": {
            "price_series_current": True,
            "uses_adjusted_close": True,
            "no_missing_required_fields": True,
        },
    }


def test_apply_tools_does_not_fetch_when_market_data_hook_absent():
    def fetch_market_data(symbol):
        raise AssertionError("market data should not be fetched")

    enriched = tool_runner.apply_tools(
        method_without_market_data_hook(),
        {"symbol": "AAPL", "observations": {"signals": {"trend": "up"}}},
        market_data_fetcher=fetch_market_data,
    )

    assert enriched == {"signals": {"trend": "up"}}


def test_apply_tools_preserves_user_observation_over_tool_value():
    def fetch_market_data(symbol):
        return {
            "symbol": "AAPL",
            "metrics": {
                "price": 123.45,
            },
            "prices": {
                "dates": ["2026-06-30"],
                "adjusted_close": [123.45],
            },
            "data": {
                "price_series_current": True,
            },
        }

    enriched = tool_runner.apply_tools(
        method_with_market_data_hook(),
        {
            "symbol": "AAPL",
            "observations": {
                "metrics": {
                    "price": 999.0,
                }
            },
        },
        market_data_fetcher=fetch_market_data,
    )

    assert enriched["metrics"]["price"] == 999.0
    assert enriched["prices"]["adjusted_close"] == [123.45]


def method_with_macro_dashboard_hook():
    return {
        "workflow_nodes": [
            {
                "id": "macro_regime",
                "tool_hooks": ["macro_dashboard"],
            }
        ]
    }


def test_apply_tools_merges_macro_dashboard_observations():
    def fetch_macro_dashboard():
        return {
            "macro": {
                "growth_cycle": {
                    "growth_cycle_bias": "long",
                }
            }
        }

    enriched = tool_runner.apply_tools(
        method_with_macro_dashboard_hook(),
        {"symbol": "AAPL", "observations": {}},
        macro_dashboard_fetcher=fetch_macro_dashboard,
    )

    assert enriched["macro"]["growth_cycle"]["growth_cycle_bias"] == "long"


def test_apply_tools_merges_growth_cycle_bias_evidence():
    def fetch_macro_dashboard():
        return {
            "macro": {
                "growth_cycle": {
                    "growth_cycle_bias": None,
                    "growth_cycle_bias_evidence": {
                        "version": "growth_cycle_bias_v2",
                        "status": "pending_inputs",
                        "bias": None,
                        "ism_contribution": "unavailable",
                        "components": {
                            "ism_manufacturing": "unavailable",
                            "ism_services": "unavailable",
                            "labor": "unavailable",
                        },
                        "missing_inputs": ["ISM Manufacturing"],
                        "reasons": ["ISM Manufacturing data is unavailable"],
                    },
                }
            }
        }

    enriched = tool_runner.apply_tools(
        method_with_macro_dashboard_hook(),
        {"symbol": "AAPL", "observations": {}},
        macro_dashboard_fetcher=fetch_macro_dashboard,
    )

    assert (
        enriched["macro"]["growth_cycle"]["growth_cycle_bias_evidence"]["version"]
        == "growth_cycle_bias_v2"
    )
    assert enriched["macro"]["growth_cycle"]["growth_cycle_bias"] is None


def test_apply_tools_does_not_overwrite_user_observations_with_bias_evidence():
    def fetch_macro_dashboard():
        return {
            "macro": {
                "growth_cycle": {
                    "growth_cycle_bias": "long",
                    "growth_cycle_bias_evidence": {
                        "version": "growth_cycle_bias_v2",
                        "status": "available",
                        "bias": "long",
                        "ism_contribution": "supports_long",
                        "components": {
                            "ism_manufacturing": "supports_growth",
                            "ism_services": "available",
                            "labor": "stable",
                        },
                        "missing_inputs": [],
                        "reasons": ["Manufacturing and services both expanding"],
                    },
                }
            }
        }

    enriched = tool_runner.apply_tools(
        method_with_macro_dashboard_hook(),
        {
            "symbol": "AAPL",
            "observations": {
                "macro": {
                    "growth_cycle": {
                        "growth_cycle_bias": "user_override",
                    }
                }
            },
        },
        macro_dashboard_fetcher=fetch_macro_dashboard,
    )

    assert enriched["macro"]["growth_cycle"]["growth_cycle_bias"] == "user_override"
    assert (
        enriched["macro"]["growth_cycle"]["growth_cycle_bias_evidence"]["version"]
        == "growth_cycle_bias_v2"
    )
