import pytest

from app.tools import ism_services


def points(pmi, activity, orders, previous=(50.0, 50.0, 50.0), backlog=52.0):
    values = {
        "ism_services_pmi": (previous[0], pmi),
        "ism_services_business_activity": (previous[1], activity),
        "ism_services_new_orders": (previous[2], orders),
        "ism_services_order_backlog": (50.0, backlog),
    }
    return {
        series_id: [
            {"date": "2026-05-01", "value": pair[0], "source": "test"},
            {"date": "2026-06-01", "value": pair[1], "source": "test"},
        ]
        for series_id, pair in values.items()
    }


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        (points(54.0, 55.4, 55.1), "supports_growth"),
        (points(54.0, 49.0, 55.1), "growth_caution"),
        (points(47.0, 48.0, 49.0, previous=(48.0, 49.0, 50.0)), "supports_contraction"),
        (points(47.0, 48.0, 49.0, previous=(46.0, 47.0, 49.5)), "contraction_easing"),
        (points(50.0, 50.0, 50.0), "mixed"),
    ],
)
def test_build_signal_states(series, expected):
    assert ism_services.build_signal(series)["state"] == expected


def test_build_signal_reports_missing_required_series():
    result = ism_services.build_signal({"ism_services_pmi": []})
    assert result["state"] == "pending_inputs"
    assert result["missing_inputs"] == [
        "Business Activity",
        "New Orders",
        "Services PMI",
    ]


def test_build_latest_payload_returns_latest_values():
    data = points(54.0, 55.4, 55.1)
    result = ism_services.build_latest_payload(data)
    assert result["pmi"] == 54.0
    assert result["business_activity"] == 55.4
    assert result["new_orders"] == 55.1
    assert result["order_backlog"] == 52.0
    assert result["period"] == "2026-06-01"


def test_build_signal_returns_backlog_confirmation():
    result = ism_services.build_signal(points(54.0, 55.4, 55.1))
    assert result["backlog_confirmation"] == "supports_growth"


def test_build_signal_contraction_backlog():
    result = ism_services.build_signal(
        points(47.0, 48.0, 49.0, previous=(48.0, 49.0, 50.0), backlog=47.0)
    )
    assert result["backlog_confirmation"] == "supports_contraction"


def test_build_card_returns_four_segments():
    signal = ism_services.build_signal(points(54.0, 55.4, 55.1))
    breadth = {"growing": 5, "contracting": 2}
    card = ism_services.build_card(signal, breadth)
    assert set(card["segments"]) == {
        "services_cycle",
        "business_activity",
        "new_orders",
        "industry_breadth",
    }


def test_build_card_industry_breadth():
    signal = ism_services.build_signal(points(54.0, 55.4, 55.1))
    breadth = {"growing": 5, "contracting": 2}
    card = ism_services.build_card(signal, breadth)
    assert card["segments"]["industry_breadth"]["growing"] == 5


def test_build_detail_contains_expected_keys():
    signal = ism_services.build_signal(points(54.0, 55.4, 55.1))
    data = points(54.0, 55.4, 55.1)
    detail = ism_services.build_detail(data, signal, {"industries": []})
    assert detail["detail_id"] == "ism_services"
    assert detail["title"] == "ISM Services"
    assert "charts" in detail
    assert "latest" in detail
    assert "signal" in detail
    assert "industries" in detail


def test_build_detail_heat_map_includes_all_at_a_glance_series():
    data = points(54.0, 55.4, 55.1)
    for index, series_id in enumerate(
        [
            "ism_services_employment",
            "ism_services_supplier_deliveries",
            "ism_services_inventories",
            "ism_services_inventory_sentiment",
            "ism_services_prices",
            "ism_services_new_export_orders",
            "ism_services_imports",
        ]
    ):
        data[series_id] = [
            {
                "date": "2026-06-01",
                "value": 50.0 + index,
                "source": "test",
            }
        ]

    detail = ism_services.build_detail(
        data,
        ism_services.build_signal(data),
        {"industries": []},
    )

    heat_map = detail["charts"][0]
    assert heat_map["keys"] == [
        "pmi",
        "business_activity",
        "new_orders",
        "employment",
        "supplier_deliveries",
        "inventories",
        "prices",
        "order_backlog",
        "new_export_orders",
        "imports",
        "inventory_sentiment",
    ]
    assert heat_map["labels"]["pmi"] == "Services PMI"
    assert len(heat_map["series"][-1]) == 12


def test_build_latest_presentation_returns_expected_structure():
    rows = [
        {
            "series_id": "ism_services_pmi",
            "current_value": 54.0,
            "label": "Services PMI",
            "previous_value": 53.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_business_activity",
            "current_value": 55.4,
            "label": "Business Activity",
            "previous_value": 54.0,
            "point_change": 1.4,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_new_orders",
            "current_value": 55.1,
            "label": "New Orders",
            "previous_value": 53.0,
            "point_change": 2.1,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_order_backlog",
            "current_value": 52.0,
            "label": "Order Backlog",
            "previous_value": 50.0,
            "point_change": 2.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_employment",
            "current_value": 51.0,
            "label": "Employment",
            "previous_value": 50.5,
            "point_change": 0.5,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_inventories",
            "current_value": 49.0,
            "label": "Inventories",
            "previous_value": 48.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_inventory_sentiment",
            "current_value": 45.0,
            "label": "Inventory Sentiment",
            "previous_value": 44.0,
            "point_change": 1.0,
            "direction": "Contracting",
            "rate_of_change": "Slower",
            "trend_months": 4,
        },
        {
            "series_id": "ism_services_prices",
            "current_value": 65.0,
            "label": "Prices",
            "previous_value": 62.0,
            "point_change": 3.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 6,
        },
        {
            "series_id": "ism_services_supplier_deliveries",
            "current_value": 52.0,
            "label": "Supplier Deliveries",
            "previous_value": 51.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_new_export_orders",
            "current_value": 53.0,
            "label": "New Export Orders",
            "previous_value": 52.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_imports",
            "current_value": 47.0,
            "label": "Imports",
            "previous_value": 48.0,
            "point_change": -1.0,
            "direction": "Contracting",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
    ]
    presentation = ism_services.build_latest_presentation(rows)
    assert presentation["detail_groups"] == [
        {"label": "Business Cycle", "keys": ["pmi"]},
        {
            "label": "Demand & Activity",
            "keys": [
                "business_activity",
                "new_orders",
                "order_backlog",
                "new_export_orders",
                "imports",
            ],
        },
        {
            "label": "Labor & Inventories",
            "keys": ["employment", "inventories", "inventory_sentiment"],
        },
        {"label": "Inflation & Supply", "keys": ["prices", "supplier_deliveries"]},
    ]
    assert len(presentation["latest"]) == 11
    assert presentation["latest_metadata"]["order_backlog"]["tone"] == "green"
    assert presentation["latest_metadata"]["imports"]["tone"] == "red"
    assert presentation["latest_metadata"]["prices"]["tone"] == "amber"
    assert presentation["latest_metadata"]["supplier_deliveries"]["tone"] == "amber"


def test_build_latest_presentation_omits_absent_rows():
    rows = [
        {
            "series_id": "ism_services_pmi",
            "current_value": 54.0,
            "label": "Services PMI",
            "previous_value": 53.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_unknown",
            "current_value": 99.0,
            "label": "Unknown",
            "previous_value": 98.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
    ]
    presentation = ism_services.build_latest_presentation(rows)
    assert len(presentation["latest"]) == 1
    assert "pmi" in presentation["latest"]
    assert len(presentation["detail_groups"]) == 1
    assert presentation["detail_groups"][0] == {
        "label": "Business Cycle",
        "keys": ["pmi"],
    }


def test_build_signal_backlog_stale_when_period_differs():
    by_series = {
        "ism_services_pmi": [{"date": "2026-06-01", "value": 54.0}],
        "ism_services_business_activity": [{"date": "2026-06-01", "value": 55.0}],
        "ism_services_new_orders": [{"date": "2026-06-01", "value": 55.1}],
        "ism_services_order_backlog": [{"date": "2026-05-01", "value": 52.0}],
    }
    signal = ism_services.build_signal(by_series)
    assert signal["backlog_confirmation"] == "unavailable"
