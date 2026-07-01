from app.tools import macro_dashboard, macro_growth_cycle


def test_macro_dashboard_groups_list_required_metrics():
    group_ids = [group["id"] for group in macro_dashboard.MACRO_DASHBOARD_GROUPS]

    assert group_ids == [
        "growth_cycle",
        "rates_liquidity",
        "risk_sentiment",
        "international_macro",
        "market_phase",
        "macro_bias",
    ]

    fields = [
        field["field"]
        for group in macro_dashboard.MACRO_DASHBOARD_GROUPS
        for field in group["fields"]
    ]

    assert "macro.growth_cycle.ism_pmi" in fields
    assert "macro.rates_liquidity.real_interest_rate" in fields
    assert "macro.risk_sentiment.vix_index" in fields
    assert "macro.international_macro.china_official_pmi" in fields
    assert "macro.market_phase.index_drawdown_pct" in fields
    assert "macro.bias.portfolio_bias" in fields


def test_macro_dashboard_growth_cycle_fields_match_tool_contract():
    growth_cycle_group = [
        group
        for group in macro_dashboard.MACRO_DASHBOARD_GROUPS
        if group["id"] == "growth_cycle"
    ][0]

    assert growth_cycle_group["fields"] == macro_growth_cycle.GROWTH_CYCLE_DASHBOARD_FIELDS


def test_fetch_macro_dashboard_is_empty_without_inputs():
    assert macro_dashboard.fetch_macro_dashboard() is None


def test_fetch_macro_dashboard_uses_growth_cycle_builder_when_inputs_are_provided():
    result = macro_dashboard.fetch_macro_dashboard(
        growth_cycle_inputs={
            "ism_manufacturing": {
                "period": "2026-06",
                "pmi": 51.2,
                "new_orders": 52.0,
                "production": 50.4,
                "employment": 49.8,
                "supplier_deliveries": 50.1,
                "inventories": 48.6,
            }
        }
    )

    assert result["macro"]["growth_cycle"]["ism_pmi"] == 51.2
