import pytest

from app.db import ism_surveys, macro_indicators, us_rates_liquidity
from app.db import growth_cycle as growth_cycle_db
from app.services import ism_services_dashboard


@pytest.fixture
def services_connection(tmp_path):
    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    ism_surveys.init_db(con)
    series_values = {
        "ism_services_pmi": [53.0, 54.0],
        "ism_services_business_activity": [54.0, 55.0],
        "ism_services_new_orders": [53.5, 55.1],
        "ism_services_order_backlog": [50.0, 52.0],
    }
    for series_id, values in series_values.items():
        macro_indicators.replace_macro_indicator_points(
            con,
            {
                "series_id": series_id,
                "title": series_id,
                "units": "index",
                "source": "test",
            },
            [
                {"date": "2026-05-01", "value": values[0], "source": "test"},
                {"date": "2026-06-01", "value": values[1], "source": "test"},
            ],
        )
    ism_surveys.replace_industry_rankings(
        con,
        "services",
        [
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
                "source": "test",
            },
            {
                "date": "2026-06-01",
                "industry": "Educational Services",
                "direction": "contraction",
                "rank": -1,
                "source": "test",
            },
        ],
    )
    yield con
    con.close()


def test_load_overview_builds_four_segment_card(services_connection):
    result = ism_services_dashboard.load_overview(services_connection)

    assert result["card"]["id"] == "ism_services"
    assert list(result["card"]["segments"]) == [
        "services_cycle",
        "business_activity",
        "new_orders",
        "industry_breadth",
    ]


def test_load_detail_is_separate_from_manufacturing(services_connection):
    result = ism_services_dashboard.load_detail(services_connection)
    assert result["detail_id"] == "ism_services"
    assert all("manufacturing" not in chart["id"] for chart in result["charts"])
