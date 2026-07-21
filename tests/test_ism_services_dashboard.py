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
        us_rates_liquidity.replace_macro_indicator_points(
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


def test_load_detail_computes_history_based_metrics(tmp_path):
    from app.db import macro_indicators, us_rates_liquidity
    from app.db import growth_cycle as growth_cycle_db
    from app.db import ism_surveys

    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    series_values = {
        "ism_services_pmi": [53.0, 54.0],
        "ism_services_business_activity": [54.0, 55.0],
        "ism_services_new_orders": [53.5, 55.1],
        "ism_services_order_backlog": [50.0, 52.0],
    }
    for series_id, values in series_values.items():
        us_rates_liquidity.replace_macro_indicator_points(
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
                "date": "2026-05-01",
                "industry": "Construction",
                "direction": "contraction",
                "rank": -2,
                "source": "test",
            },
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 12,
                "source": "test",
            },
            {
                "date": "2026-05-01",
                "industry": "Retail Trade",
                "direction": "contraction",
                "rank": -1,
                "source": "test",
            },
            {
                "date": "2026-06-01",
                "industry": "Retail Trade",
                "direction": "contraction",
                "rank": -5,
                "source": "test",
            },
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    industries = {ind["industry"]: ind for ind in result["industries"]["industries"]}
    con.close()

    construction = industries["Construction"]
    assert construction["direction_change"] == "contraction_to_growth"
    assert construction["rank_change"] == 14
    assert construction["positive_streak"] == 1

    retail = industries["Retail Trade"]
    assert retail["direction_change"] is None
    assert retail["rank_change"] == -4
    assert retail["negative_streak"] == 2


def test_load_detail_filters_stale_industries_without_signal_period(tmp_path):
    from app.db import macro_indicators, us_rates_liquidity
    from app.db import growth_cycle as growth_cycle_db
    from app.db import ism_surveys

    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    series_values = {
        "ism_services_pmi": [53.0, 54.0],
        "ism_services_business_activity": [54.0, 55.0],
        "ism_services_new_orders": [53.5, 55.1],
        "ism_services_order_backlog": [50.0, 52.0],
    }
    for series_id, values in series_values.items():
        us_rates_liquidity.replace_macro_indicator_points(
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
                "date": "2026-05-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
                "source": "test",
            },
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    con.close()

    assert result["industries"]["industries"] == []


def test_load_detail_empty_for_pending_signal(tmp_path):
    from app.db import macro_indicators, us_rates_liquidity
    from app.db import growth_cycle as growth_cycle_db
    from app.db import ism_surveys

    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "ism_services_pmi",
            "title": "ISM Services PMI",
            "units": "index",
            "source": "test",
        },
        [{"date": "2026-06-01", "value": 54.0, "source": "test"}],
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
            }
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    con.close()

    assert result["signal"]["state"] == "pending_inputs"
    assert result["industries"]["industries"] == []


def test_load_detail_empty_for_stale_signal(tmp_path):
    from app.db import macro_indicators, us_rates_liquidity
    from app.db import growth_cycle as growth_cycle_db
    from app.db import ism_surveys

    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "ism_services_pmi",
            "title": "ISM Services PMI",
            "units": "index",
            "source": "test",
        },
        [{"date": "2026-06-01", "value": 54.0, "source": "test"}],
    )
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "ism_services_business_activity",
            "title": "ISM Services Business Activity",
            "units": "index",
            "source": "test",
        },
        [{"date": "2026-05-01", "value": 55.0, "source": "test"}],
    )
    us_rates_liquidity.replace_macro_indicator_points(
        con,
        {
            "series_id": "ism_services_new_orders",
            "title": "ISM Services New Orders",
            "units": "index",
            "source": "test",
        },
        [{"date": "2026-05-01", "value": 55.0, "source": "test"}],
    )
    ism_surveys.replace_industry_rankings(
        con,
        "services",
        [
            {
                "date": "2026-05-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
                "source": "test",
            }
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    con.close()

    assert result["signal"]["state"] == "stale_periods"
    assert result["industries"]["industries"] == []


def test_load_detail_caps_rankings_at_signal_period(tmp_path):
    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    for series_id, value in {
        "ism_services_pmi": 54.0,
        "ism_services_business_activity": 55.0,
        "ism_services_new_orders": 55.1,
        "ism_services_order_backlog": 52.0,
    }.items():
        us_rates_liquidity.replace_macro_indicator_points(
            con,
            {
                "series_id": series_id,
                "title": series_id,
                "units": "index",
                "source": "test",
            },
            [{"date": "2026-06-01", "value": value, "source": "test"}],
        )
    ism_surveys.replace_industry_rankings(
        con,
        "services",
        [
            {
                "date": "2026-05-01",
                "industry": "Construction",
                "direction": "contraction",
                "rank": -2,
                "source": "test",
            },
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 12,
                "source": "test",
            },
            {
                "date": "2026-07-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 15,
                "source": "test",
            },
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    con.close()

    industries = {ind["industry"]: ind for ind in result["industries"]["industries"]}
    construction = industries["Construction"]
    assert construction["latest_date"] == "2026-06-01"
    assert construction["direction_change"] == "contraction_to_growth"
    assert construction["rank_change"] == 14
    assert construction["positive_streak"] == 1


def test_load_detail_excludes_future_rankings(tmp_path):
    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    for series_id, values in {
        "ism_services_pmi": [54.0],
        "ism_services_business_activity": [55.0],
        "ism_services_new_orders": [55.1],
        "ism_services_order_backlog": [52.0],
    }.items():
        us_rates_liquidity.replace_macro_indicator_points(
            con,
            {
                "series_id": series_id,
                "title": series_id,
                "units": "index",
                "source": "test",
            },
            [{"date": "2026-06-01", "value": values[0], "source": "test"}],
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
                "date": "2026-07-01",
                "industry": "Retail Trade",
                "direction": "growth",
                "rank": 2,
                "source": "test",
            },
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    con.close()

    assert result["signal"]["period"] == "2026-06-01"
    industries = {ind["industry"] for ind in result["industries"]["industries"]}
    assert "Construction" in industries
    assert "Retail Trade" not in industries


def test_load_detail_scopes_comments_to_signal_period(tmp_path):
    macro_indicators.connect(tmp_path / "market.sqlite").close()
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle_db.init_db(con)
    for series_id, values in {
        "ism_services_pmi": [54.0],
        "ism_services_business_activity": [55.0],
        "ism_services_new_orders": [55.1],
        "ism_services_order_backlog": [52.0],
    }.items():
        us_rates_liquidity.replace_macro_indicator_points(
            con,
            {
                "series_id": series_id,
                "title": series_id,
                "units": "index",
                "source": "test",
            },
            [{"date": "2026-06-01", "value": values[0], "source": "test"}],
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
            }
        ],
    )
    ism_surveys.insert_industry_comments(
        con,
        "services",
        [
            {
                "report_month": "2026-05-01",
                "industry": "Construction",
                "comment_index": 0,
                "comment_text": "May comment",
                "source": "test",
            },
            {
                "report_month": "2026-06-01",
                "industry": "Construction",
                "comment_index": 0,
                "comment_text": "June comment",
                "source": "test",
            },
        ],
    )
    result = ism_services_dashboard.load_detail(con)
    con.close()

    construction = result["industries"]["industries"][0]
    assert construction["comments"] == ["June comment"]
