import pytest

from app.tools import gdp_market_relationship


def relationships():
    return [
        {
            "relationship_id": "us_sp500_gdp",
            "title": "S&P 500 vs US GDP",
            "region": "US",
            "economy": "US GDP",
            "index_name": "S&P 500",
            "primary_lag_months": 6,
            "correlation_window_years": 10,
            "source_workbook": "GDP_Correlations.xlsx",
            "source_sheet": "S&P500_USGDP Correlation",
        }
    ]


def lag_rows():
    return [
        {
            "date": "2020-06-30",
            "lag_months": 0,
            "index_yoy": 0.05,
            "gdp_yoy": -0.09,
            "rolling_correlation": 0.17,
        },
        {
            "date": "2020-06-30",
            "lag_months": 3,
            "index_yoy": -0.08,
            "gdp_yoy": -0.09,
            "rolling_correlation": 0.26,
        },
        {
            "date": "2020-06-30",
            "lag_months": 6,
            "index_yoy": 0.29,
            "gdp_yoy": -0.09,
            "rolling_correlation": -0.09,
        },
        {
            "date": "2020-06-30",
            "lag_months": 9,
            "index_yoy": 0.32,
            "gdp_yoy": -0.09,
            "rolling_correlation": -0.12,
        },
        {
            "date": "2020-06-30",
            "lag_months": 12,
            "index_yoy": 0.35,
            "gdp_yoy": -0.09,
            "rolling_correlation": -0.15,
        },
    ]


def quad_rows():
    return [
        {
            "date": "2020-03-31",
            "period_label": "2020 Q1",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-06-30",
            "period_label": "2020 Q2",
            "quad_case": "0,0",
            "index_direction": 0,
            "gdp_direction": 0,
        },
        {
            "date": "2020-09-30",
            "period_label": "2020 Q3",
            "quad_case": "0,1",
            "index_direction": 0,
            "gdp_direction": 1,
        },
        {
            "date": "2020-12-31",
            "period_label": "2020 Q4",
            "quad_case": "1,0",
            "index_direction": 1,
            "gdp_direction": 0,
        },
    ]


def test_build_relationship_overview_excludes_series():
    payload = gdp_market_relationship.build_overview_payload(
        relationships(),
        lambda relationship_id: lag_rows(),
        lambda relationship_id: quad_rows(),
    )

    card = payload["relationships"][0]
    assert card["relationship_id"] == "us_sp500_gdp"
    assert card["latest"]["primary_lag_months"] == 6
    assert card["latest"]["rolling_index_gdp_correlation"] == -0.09
    assert card["latest"]["average_10y_correlation"] == -0.09
    assert card["latest"]["quadnomial_current_case"] == "1,0"
    assert card["latest"]["quadnomial_current_label"] == "D (INDEX UP / GDP DOWN)"
    assert card["latest"]["quadnomial_current_plain_label"] == "INDEX UP / GDP DOWN"
    assert card["same_direction_pct"] == 50.0
    assert card["method_explainable_pct"] == 75.0
    assert card["portfolio_bias_status"] == "Portfolio bias requires GDP forecast"
    assert "lag_series" not in card
    assert "quad_rows" not in card


def test_build_relationship_detail_includes_series():
    payload = gdp_market_relationship.build_detail_payload(
        relationships()[0],
        lag_rows(),
        quad_rows(),
    )

    assert payload["relationship_id"] == "us_sp500_gdp"
    assert len(payload["lag_correlations"]) == 5
    assert payload["lag_correlations"][2]["method_primary"] is True
    assert payload["lag_correlations"][2]["label"] == "6M lag"
    assert payload["lag_correlations"][2]["value"] == -0.09
    assert len(payload["lag_series"]) == 5
    assert payload["lag_correlation_series"][0]["lag_0"] == 0.17
    assert payload["lag_correlation_series"][0]["lag_12"] == -0.15
    assert payload["lag_correlation_labels"]["lag_12"] == "12M lag"
    assert len(payload["average_lag_correlations"]) == 5
    assert payload["average_lag_correlations"][2]["label"] == "6M lag"
    assert payload["average_lag_correlations"][2]["value"] == -0.09
    assert payload["average_lag_correlations"][2]["method_primary"] is True
    assert payload["quadnomial_distribution"][0]["case"] == "0,0"


def test_build_relationship_detail_includes_frontend_summary_fields():
    payload = gdp_market_relationship.build_detail_payload(
        relationships()[0],
        lag_rows(),
        quad_rows(),
    )

    assert payload["latest"]["primary_lag_months"] == 6
    assert payload["latest"]["rolling_index_gdp_correlation"] == -0.09
    assert payload["latest"]["average_10y_correlation"] == -0.09
    assert payload["latest"]["quadnomial_current_case"] == "1,0"
    assert payload["latest"]["quadnomial_current_plain_label"] == "INDEX UP / GDP DOWN"
    assert payload["latest"]["index_yoy"] == 0.29
    assert payload["latest"]["gdp_yoy"] == -0.09
    assert payload["latest"]["primary_lag_date"] == "2020-06-30"
    assert payload["latest"]["quadnomial_date"] == "2020-12-31"
    assert payload["latest"]["quadnomial_period_label"] == "2020 Q4"
    assert payload["same_direction_pct"] == 50.0
    assert payload["method_explainable_pct"] == 75.0
    assert payload["opposite_direction_pct"] == 50.0
    assert payload["relationship_signal_usability"] == "GDP relationship weak"
    assert payload["portfolio_bias_status"] == "Portfolio bias requires GDP forecast"
    assert payload["macro_relationship_confidence"] == "low"


def test_overview_includes_frontend_fields():
    payload = gdp_market_relationship.build_overview_payload(
        relationships(),
        lambda relationship_id: lag_rows(),
        lambda relationship_id: quad_rows(),
    )

    card = payload["relationships"][0]
    assert card["title"] == "S&P 500 vs US GDP"
    assert card["region"] == "US"
    assert card["economy"] == "US GDP"
    assert card["index_name"] == "S&P 500"
    assert card["primary_lag_months"] == 6
    assert card["correlation_window_years"] == 10
    assert card["relationship_signal_usability"] == "GDP relationship weak"
    assert card["opposite_direction_pct"] == 50.0
    assert card["macro_relationship_confidence"] == "low"


def test_overview_macro_relationship_confidence_high():
    high_quad_rows = [
        {
            "date": "2020-03-31",
            "period_label": "2020 Q1",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-06-30",
            "period_label": "2020 Q2",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-09-30",
            "period_label": "2020 Q3",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
    ]
    high_lag_rows = [
        {
            "date": "2020-06-30",
            "lag_months": 6,
            "index_yoy": 0.05,
            "gdp_yoy": 0.03,
            "rolling_correlation": 0.45,
        },
    ]

    payload = gdp_market_relationship.build_overview_payload(
        relationships(),
        lambda relationship_id: high_lag_rows,
        lambda relationship_id: high_quad_rows,
    )

    card = payload["relationships"][0]
    assert card["macro_relationship_confidence"] == "high"
    assert card["relationship_signal_usability"] == "GDP relationship usable"


def test_overview_signal_uses_average_10y_correlation():
    high_quad_rows = [
        {
            "date": "2020-03-31",
            "period_label": "2020 Q1",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-06-30",
            "period_label": "2020 Q2",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-09-30",
            "period_label": "2020 Q3",
            "quad_case": "0,0",
            "index_direction": 0,
            "gdp_direction": 0,
        },
    ]
    lag_rows_with_weak_latest = [
        {
            "date": "2020-03-31",
            "lag_months": 6,
            "index_yoy": 0.05,
            "gdp_yoy": 0.03,
            "rolling_correlation": 0.70,
        },
        {
            "date": "2020-06-30",
            "lag_months": 6,
            "index_yoy": 0.06,
            "gdp_yoy": 0.02,
            "rolling_correlation": 0.68,
        },
        {
            "date": "2020-09-30",
            "lag_months": 6,
            "index_yoy": 0.04,
            "gdp_yoy": 0.01,
            "rolling_correlation": 0.02,
        },
    ]

    payload = gdp_market_relationship.build_overview_payload(
        relationships(),
        lambda relationship_id: lag_rows_with_weak_latest,
        lambda relationship_id: high_quad_rows,
    )

    card = payload["relationships"][0]
    assert card["latest"]["rolling_index_gdp_correlation"] == 0.02
    assert card["latest"]["average_10y_correlation"] == pytest.approx(
        0.4666666666666666
    )
    assert card["macro_relationship_confidence"] == "high"
    assert card["relationship_signal_usability"] == "GDP relationship usable"


def test_overview_macro_relationship_confidence_medium():
    medium_quad_rows = [
        {
            "date": "2020-03-31",
            "period_label": "2020 Q1",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-06-30",
            "period_label": "2020 Q2",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-09-30",
            "period_label": "2020 Q3",
            "quad_case": "0,0",
            "index_direction": 0,
            "gdp_direction": 0,
        },
    ]
    medium_lag_rows = [
        {
            "date": "2020-06-30",
            "lag_months": 6,
            "index_yoy": 0.05,
            "gdp_yoy": 0.03,
            "rolling_correlation": 0.30,
        },
    ]

    payload = gdp_market_relationship.build_overview_payload(
        relationships(),
        lambda relationship_id: medium_lag_rows,
        lambda relationship_id: medium_quad_rows,
    )

    card = payload["relationships"][0]
    assert card["macro_relationship_confidence"] == "medium"
    assert (
        card["relationship_signal_usability"] == "GDP relationship usable with caution"
    )


def test_overview_china_always_low_confidence():
    china_rel = [
        dict(relationships()[0], region="china", relationship_id="china_sse_gdp")
    ]
    high_quad_rows = [
        {
            "date": "2020-03-31",
            "period_label": "2020 Q1",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
        {
            "date": "2020-06-30",
            "period_label": "2020 Q2",
            "quad_case": "1,1",
            "index_direction": 1,
            "gdp_direction": 1,
        },
    ]
    high_lag_rows = [
        {
            "date": "2020-06-30",
            "lag_months": 6,
            "index_yoy": 0.05,
            "gdp_yoy": 0.03,
            "rolling_correlation": 0.50,
        },
    ]

    payload = gdp_market_relationship.build_overview_payload(
        china_rel,
        lambda relationship_id: high_lag_rows,
        lambda relationship_id: high_quad_rows,
    )

    card = payload["relationships"][0]
    assert card["macro_relationship_confidence"] == "low"
    assert card["relationship_signal_usability"] == "Do not rely on GDP alone"


def test_detail_includes_correlation_series():
    rows = lag_rows() + [
        {
            "date": "2020-09-30",
            "lag_months": 6,
            "index_yoy": 0.31,
            "gdp_yoy": -0.04,
            "rolling_correlation": None,
        }
    ]
    payload = gdp_market_relationship.build_detail_payload(
        relationships()[0],
        rows,
        quad_rows(),
    )

    assert len(payload["correlation_series"]) == 1
    assert payload["correlation_series"][0] == {"date": "2020-06-30", "value": -0.09}


def test_detail_includes_yoy_series():
    payload = gdp_market_relationship.build_detail_payload(
        relationships()[0],
        lag_rows(),
        quad_rows(),
    )

    assert len(payload["yoy_series"]) == 1
    assert payload["yoy_series"][0] == {"date": "2020-06-30", "index": 5.0, "gdp": -9.0}


def test_detail_quadnomial_distribution_has_labels():
    payload = gdp_market_relationship.build_detail_payload(
        relationships()[0],
        lag_rows(),
        quad_rows(),
    )

    distribution = payload["quadnomial_distribution"]
    labels = {item["case"]: item["label"] for item in distribution}
    interpretations = {item["case"]: item["interpretation"] for item in distribution}
    assert labels["0,0"] == "A (INDEX DOWN / GDP DOWN)"
    assert labels["1,1"] == "B (INDEX UP / GDP UP)"
    assert labels["0,1"] == "C (INDEX DOWN / GDP UP)"
    assert labels["1,0"] == "D (INDEX UP / GDP DOWN)"
    assert interpretations["0,0"] == "Same direction; bearish macro confirmation"
    assert interpretations["1,1"] == "Same direction; bullish macro confirmation"
    assert (
        interpretations["0,1"]
        == "Opposite direction; possible profit-taking/correction"
    )
    assert (
        interpretations["1,0"]
        == "Opposite direction; lower-confidence/unpredictable case"
    )


def test_detail_quadnomial_distribution_counts():
    payload = gdp_market_relationship.build_detail_payload(
        relationships()[0],
        lag_rows(),
        quad_rows(),
    )

    distribution = {item["case"]: item for item in payload["quadnomial_distribution"]}
    assert distribution["1,1"]["count"] == 1
    assert distribution["0,0"]["count"] == 1
    assert distribution["0,1"]["count"] == 1
    assert distribution["1,1"]["value"] == 25.0


def test_overview_missing_lag_data():
    payload = gdp_market_relationship.build_overview_payload(
        relationships(),
        lambda relationship_id: [],
        lambda relationship_id: [],
    )

    card = payload["relationships"][0]
    assert card["latest"]["rolling_index_gdp_correlation"] is None
    assert card["same_direction_pct"] is None
    assert card["method_explainable_pct"] is None
    assert card["relationship_signal_usability"] is None


def test_overview_multiple_relationships():
    rels = relationships() + [
        {
            "relationship_id": "eu_stoxx_gdp",
            "title": "STOXX 600 vs EU GDP",
            "region": "EU",
            "economy": "EU GDP",
            "index_name": "STOXX 600",
            "primary_lag_months": 3,
            "correlation_window_years": 10,
            "source_workbook": "GDP_Correlations.xlsx",
            "source_sheet": "STOXX600_EUGDP Correlation",
        }
    ]

    def load_lag(rid):
        if rid == "us_sp500_gdp":
            return lag_rows()
        return [
            {
                "date": "2020-06-30",
                "lag_months": 3,
                "index_yoy": 0.02,
                "gdp_yoy": 0.01,
                "rolling_correlation": 0.55,
            }
        ]

    def load_quad(rid):
        if rid == "us_sp500_gdp":
            return quad_rows()
        return [
            {
                "date": "2020-06-30",
                "period_label": "2020 Q2",
                "quad_case": "1,1",
                "index_direction": 1,
                "gdp_direction": 1,
            }
        ]

    payload = gdp_market_relationship.build_overview_payload(rels, load_lag, load_quad)

    assert len(payload["relationships"]) == 2
    assert payload["relationships"][1]["relationship_id"] == "eu_stoxx_gdp"
    assert (
        payload["relationships"][1]["latest"]["rolling_index_gdp_correlation"] == 0.55
    )
