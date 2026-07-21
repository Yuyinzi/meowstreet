import pytest

from app.db import consumer_sentiment, macro_indicators, us_rates_liquidity
from app.services import consumer_sentiment_dashboard


@pytest.fixture
def consumer_con(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    yield con
    con.close()


def _seed_all_series(con):
    # michigan series
    series_list = []
    for sid, title in [
        ("umcsi_aggregate", "UMCSI Aggregate"),
        ("umcsi_expectations", "UMCSI Expectations"),
        ("umcsi_current_conditions", "UMCSI Current Conditions"),
    ]:
        series_list.append(
            {
                "series": {
                    "series_id": sid,
                    "title": title,
                    "units": "index_points",
                    "source": "University of Michigan Table 1"
                    if sid == "umcsi_aggregate"
                    else "University of Michigan Table 5",
                },
                "points": [
                    {"date": "2026-05-01", "value": 75.0, "source": "test"},
                    {"date": "2026-06-01", "value": 78.0, "source": "test"},
                ],
            }
        )
    consumer_sentiment.replace_michigan_series(con, series_list)
    for sid, title, val in [
        ("household_debt_to_gdp", "Household Debt to GDP", 80.0),
        ("household_debt_service_ratio", "Debt Service Ratio", 9.8),
        ("personal_saving_rate", "Saving Rate", 7.5),
        ("one_to_four_family_mortgage_liabilities", "Mortgage Liabilities", 12000000.0),
    ]:
        consumer_sentiment.replace_capacity_series(
            con,
            [
                {
                    "series": {
                        "series_id": sid,
                        "title": title,
                        "units": "percent",
                        "source": "FRED test",
                    },
                    "points": [
                        {"date": "2026-03-01", "value": val, "source": "test"},
                    ],
                }
            ],
        )


def test_load_overview_returns_summary(consumer_con):
    _seed_all_series(consumer_con)
    result = consumer_sentiment_dashboard.load_overview(consumer_con)
    assert result["version"] == 1
    assert "as_of" in result
    assert "data_status" in result
    assert "evidence_state" in result
    assert "aggregate" in result
    assert "expectations" in result
    assert "current_conditions" in result
    assert "large_expectations_decline" in result
    assert "capacity_completeness" in result
    assert result["aggregate"]["value"] == 78.0


def test_load_overview_insufficient_data_when_empty(consumer_con):
    result = consumer_sentiment_dashboard.load_overview(consumer_con)
    assert result["evidence_state"] == "insufficient_data"


def test_load_detail_returns_history(consumer_con):
    _seed_all_series(consumer_con)
    result = consumer_sentiment_dashboard.load_detail(consumer_con)
    assert result["detail_id"] == "consumer_sentiment"
    assert "history" in result
    assert "capacity" in result
    assert len(result["history"]["umcsi_aggregate"]) == 2
