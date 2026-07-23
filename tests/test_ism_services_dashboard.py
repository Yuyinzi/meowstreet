from copy import deepcopy

import pytest

from app.db import growth_cycle, ism_surveys, macro_indicators, us_rates_liquidity
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


def test_build_official_report_summary_preserves_services_evidence():
    evidence = {
        "at_a_glance_rows": [
            {
                "series_id": "ism_services_pmi",
                "label": "Services PMI",
                "current_value": 54.0,
                "previous_value": 53.8,
                "point_change": 0.2,
                "direction": "Growing",
                "rate_of_change": "Faster",
                "trend_months": 2,
            },
            {
                "series_id": "ism_services_prices",
                "label": "Prices",
                "current_value": 61.2,
                "previous_value": 59.4,
                "point_change": 1.8,
                "direction": "Increasing",
                "rate_of_change": "Faster",
                "trend_months": 3,
            },
        ],
        "component_industries": [
            {
                "signal_type": "business_activity",
                "direction": "growth",
                "industry": "Construction",
                "rank": 1,
            }
        ],
        "respondent_comments": [
            {"industry": "Construction", "comment_text": "Demand improved."}
        ],
        "commodities": [
            {"commodity": "Aluminum", "signal_type": "up_in_price", "months": 4}
        ],
        "narrative_facts": {"consecutive_expansion_months": 24},
        "source": {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_url": "https://www.ismworld.org/example",
            "source_hash": "abc123",
        },
    }
    original = deepcopy(evidence)

    summary = ism_services_dashboard._build_official_report_summary(evidence)

    assert summary["source_type"] == "report_extracted"
    assert summary["period"] == "2026-06-01"
    assert summary["headline"] == (
        "Services PMI 54.0, +0.2 points from prior month; Growing / Faster."
    )
    assert summary["major_changes"] == [
        "Prices: 61.2, +1.8 points; Increasing / Faster."
    ]
    assert summary["comment_preview_count"] == 3
    assert summary["source_url"] == evidence["source"]["source_url"]
    assert summary["respondent_comments"] == evidence["respondent_comments"]
    assert evidence == original


def test_load_detail_attaches_summary_and_complete_rich_evidence(
    services_connection,
    monkeypatch,
):
    evidence = {
        "at_a_glance_rows": [],
        "component_industries": [],
        "respondent_comments": [],
        "commodities": [],
        "narrative_facts": {},
        "source": {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_url": "https://www.ismworld.org/example",
            "source_hash": "abc123",
        },
    }
    monkeypatch.setattr(
        ism_services_dashboard,
        "_load_rich_evidence",
        lambda con, signal_period: evidence,
    )

    result = ism_services_dashboard.load_detail(services_connection)

    assert result["rich_evidence"] is evidence
    assert result["official_report_summary"]["report_id"] == "ism_services_2026_06"


def test_load_detail_attaches_services_industry_analysis(
    services_connection,
    monkeypatch,
):
    monkeypatch.setattr(
        ism_surveys,
        "load_latest_report_snapshot",
        lambda con, survey_type: {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_url": "https://example.com/services/june",
            "source_hash": "abc123",
        },
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signals",
        lambda con, report_id: [
            {
                "signal_type": "business_activity",
                "direction": "growth",
                "industry": "Construction",
                "rank": 1,
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signal_coverage",
        lambda con, report_id: [
            {
                "signal_type": "business_activity",
                "direction": "growth",
                "list_present": True,
                "declared_count": 12,
                "extracted_count": 12,
                "validation_status": "complete",
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6, survey_type="manufacturing": [
            {
                "report_id": "ism_services_2026_06",
                "report_month": "2026-06-01",
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signals_for_reports",
        lambda con, report_ids: [],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signal_coverage_for_reports",
        lambda con, report_ids: [],
    )

    result = ism_services_dashboard.load_detail(services_connection)

    analysis = result["industry_analysis"]
    assert analysis["status"] == "available"
    assert analysis["period"] == "2026-06-01"
    construction = next(
        row for row in analysis["industries"] if row["industry"] == "Construction"
    )
    assert construction["component_signals"][0]["signal_type"] == "business_activity"
    assert "score" not in construction


def test_load_detail_includes_signal_trend_on_each_industry(
    services_connection,
    monkeypatch,
):
    monkeypatch.setattr(
        ism_surveys,
        "load_latest_report_snapshot",
        lambda con, survey_type: {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_url": "https://example.com/services/june",
            "source_hash": "abc123",
        },
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signals",
        lambda con, report_id: [
            {
                "signal_type": "business_activity",
                "direction": "increase",
                "industry": "Construction",
                "rank": 1,
                "report_id": report_id,
                "source_excerpt": "increase",
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signal_coverage",
        lambda con, report_id: [
            {
                "signal_type": "business_activity",
                "direction": "increase",
                "list_present": True,
                "declared_count": 8,
                "extracted_count": 8,
                "validation_status": "complete",
                "evidence_text": "",
                "source_url": "",
                "source_hash": "",
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6, survey_type="manufacturing": [
            {
                "report_id": "ism_services_2026_06",
                "report_month": "2026-06-01",
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signals_for_reports",
        lambda con, report_ids: [
            {
                "report_id": report_ids[0],
                "signal_type": "business_activity",
                "direction": "increase",
                "industry": "Construction",
                "rank": 1,
                "source_excerpt": "increase",
            }
        ],
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signal_coverage_for_reports",
        lambda con, report_ids: [
            {
                "report_id": report_ids[0],
                "signal_type": "business_activity",
                "direction": "increase",
                "list_present": True,
                "declared_count": 8,
                "extracted_count": 8,
                "validation_status": "complete",
                "evidence_text": "",
                "source_url": "",
                "source_hash": "",
            }
        ],
    )

    result = ism_services_dashboard.load_detail(services_connection)

    analysis = result["industry_analysis"]
    assert analysis["status"] == "available"
    for ind in analysis.get("industries", []):
        assert "signal_trend" in ind, f"{ind['industry']} missing signal_trend"
        assert len(ind["signal_trend"]) <= 6
        assert all("overall" in p and "components" in p for p in ind["signal_trend"])


def test_load_detail_attaches_latest_values_presentation(
    services_connection,
    monkeypatch,
):
    at_a_glance_rows = [
        {
            "series_id": "ism_services_pmi",
            "label": "Services PMI",
            "current_value": 54.0,
            "previous_value": 53.8,
            "point_change": 0.2,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_business_activity",
            "label": "Business Activity",
            "current_value": 55.0,
            "previous_value": 54.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_new_orders",
            "label": "New Orders",
            "current_value": 55.1,
            "previous_value": 53.5,
            "point_change": 1.6,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_order_backlog",
            "label": "Order Backlog",
            "current_value": 52.0,
            "previous_value": 50.0,
            "point_change": 2.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_employment",
            "label": "Employment",
            "current_value": 52.0,
            "previous_value": 51.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_inventories",
            "label": "Inventories",
            "current_value": 50.0,
            "previous_value": 49.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_inventory_sentiment",
            "label": "Inventory Sentiment",
            "current_value": 48.0,
            "previous_value": 47.0,
            "point_change": 1.0,
            "direction": "Contracting",
            "rate_of_change": "Slower",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_prices",
            "label": "Prices",
            "current_value": 61.2,
            "previous_value": 59.4,
            "point_change": 1.8,
            "direction": "Increasing",
            "rate_of_change": "Faster",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_supplier_deliveries",
            "label": "Supplier Deliveries",
            "current_value": 54.0,
            "previous_value": 53.0,
            "point_change": 1.0,
            "direction": "Slowing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_new_export_orders",
            "label": "New Export Orders",
            "current_value": 51.0,
            "previous_value": 50.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_imports",
            "label": "Imports",
            "current_value": 50.5,
            "previous_value": 49.5,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
    ]
    monkeypatch.setattr(
        ism_services_dashboard,
        "_load_rich_evidence",
        lambda con, signal_period: {
            "at_a_glance_rows": at_a_glance_rows,
            "source": {"report_month": signal_period},
        },
    )

    detail = ism_services_dashboard.load_detail(services_connection)

    assert len(detail["latest"]) == 11
    assert len(detail["latest_metadata"]) == 11
    assert [group["label"] for group in detail["detail_groups"]] == [
        "Business Cycle",
        "Demand & Activity",
        "Labor & Inventories",
        "Inflation & Supply",
    ]
    assert detail["signal"]["version"] == "ism_services_signal_v1"
    assert set(detail["signal"]["metrics"]) == {
        "pmi",
        "business_activity",
        "new_orders",
        "order_backlog",
    }


def test_load_detail_stale_report_omits_presentation(
    services_connection,
    monkeypatch,
):
    at_a_glance_rows = [
        {
            "series_id": "ism_services_pmi",
            "label": "Services PMI",
            "current_value": 54.0,
            "previous_value": 53.8,
            "point_change": 0.2,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_business_activity",
            "label": "Business Activity",
            "current_value": 55.0,
            "previous_value": 54.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_new_orders",
            "label": "New Orders",
            "current_value": 55.1,
            "previous_value": 53.5,
            "point_change": 1.6,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_order_backlog",
            "label": "Order Backlog",
            "current_value": 52.0,
            "previous_value": 50.0,
            "point_change": 2.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_employment",
            "label": "Employment",
            "current_value": 52.0,
            "previous_value": 51.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_inventories",
            "label": "Inventories",
            "current_value": 50.0,
            "previous_value": 49.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_inventory_sentiment",
            "label": "Inventory Sentiment",
            "current_value": 48.0,
            "previous_value": 47.0,
            "point_change": 1.0,
            "direction": "Contracting",
            "rate_of_change": "Slower",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_prices",
            "label": "Prices",
            "current_value": 61.2,
            "previous_value": 59.4,
            "point_change": 1.8,
            "direction": "Increasing",
            "rate_of_change": "Faster",
            "trend_months": 3,
        },
        {
            "series_id": "ism_services_supplier_deliveries",
            "label": "Supplier Deliveries",
            "current_value": 54.0,
            "previous_value": 53.0,
            "point_change": 1.0,
            "direction": "Slowing",
            "rate_of_change": "Faster",
            "trend_months": 2,
        },
        {
            "series_id": "ism_services_new_export_orders",
            "label": "New Export Orders",
            "current_value": 51.0,
            "previous_value": 50.0,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
        {
            "series_id": "ism_services_imports",
            "label": "Imports",
            "current_value": 50.5,
            "previous_value": 49.5,
            "point_change": 1.0,
            "direction": "Growing",
            "rate_of_change": "Faster",
            "trend_months": 1,
        },
    ]
    monkeypatch.setattr(
        ism_services_dashboard,
        "_load_rich_evidence",
        lambda con, signal_period: {
            "at_a_glance_rows": at_a_glance_rows,
            "source": {"report_month": "2026-05-01"},
        },
    )

    detail = ism_services_dashboard.load_detail(services_connection)

    assert "latest_metadata" not in detail
    assert "detail_groups" not in detail
    assert len(detail["latest"]) == 4


def test_load_detail_does_not_join_stale_services_component_evidence(
    services_connection,
    monkeypatch,
):
    monkeypatch.setattr(
        ism_surveys,
        "load_latest_report_snapshot",
        lambda con, survey_type: {
            "report_id": "ism_services_2026_05",
            "report_month": "2026-05-01",
            "title": "May 2026 ISM Services PMI Report",
            "source_url": "https://example.com/services/may",
            "source_hash": "abc123",
        },
    )
    monkeypatch.setattr(
        growth_cycle,
        "load_ism_report_industry_signals",
        lambda con, report_id: (_ for _ in ()).throw(
            AssertionError("stale component signals must not load")
        ),
    )

    result = ism_services_dashboard.load_detail(services_connection)

    construction = next(
        row
        for row in result["industry_analysis"]["industries"]
        if row["industry"] == "Construction"
    )
    assert construction["component_signals"] == []
    assert result["industry_analysis"]["source_url"] is None
