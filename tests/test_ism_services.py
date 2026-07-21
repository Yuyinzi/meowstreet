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
