import pytest

from app.db import consumer_sentiment, macro_indicators, us_rates_liquidity
from app.services import consumer_sentiment_dashboard


@pytest.fixture
def consumer_con(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    yield con
    con.close()


def _monthly_history(count, start_year=2006, start_month=6):
    points = []
    for offset in range(count):
        month_index = start_month - 1 + offset
        year = start_year + month_index // 12
        month = month_index % 12 + 1
        points.append(
            {
                "date": f"{year:04d}-{month:02d}-01",
                "value": float(offset),
                "source": "test",
            }
        )
    return points


def _seed_all_series(con, sentiment_points=None):
    sentiment_points = sentiment_points or [
        {"date": "2026-05-01", "value": 75.0, "source": "test"},
        {"date": "2026-06-01", "value": 78.0, "source": "test"},
    ]
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
                "points": sentiment_points,
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
    assert result["method_version"] == 2
    assert result["percentile_method"]["window_months"] == 240
    assert result["primary_signal"]["series_id"] == "umcsi_expectations"
    assert "confirmation" in result
    assert "ability_read" in result
    assert "evidence_state" not in result
    assert "willingness_read" not in result
    assert "as_of" in result
    assert "data_status" in result
    assert "aggregate" in result
    assert "expectations" in result
    assert "current_conditions" in result
    assert "large_expectations_decline" in result
    assert "capacity_completeness" in result
    assert "capacity_evidence" in result
    assert "aligned_month" in result
    assert result["aggregate"]["value"] == 78.0
    assert result["expectations"]["percentile_zone"] == ("percentile_unavailable")


def test_load_overview_returns_populated_v2_percentile(consumer_con):
    _seed_all_series(consumer_con, sentiment_points=_monthly_history(240))

    result = consumer_sentiment_dashboard.load_overview(consumer_con)

    assert result["expectations"]["percentile_rank"] == 99.79
    assert result["expectations"]["percentile_zone"] == "elevated"
    assert result["primary_signal"]["headline"] == "Elevated \u00b7 Improving"
    assert result["confirmation"]["state"] == "broadly_confirmed"


def test_load_overview_insufficient_data_when_empty(consumer_con):
    result = consumer_sentiment_dashboard.load_overview(consumer_con)
    assert result["data_status"] == "missing"


def test_load_detail_returns_history(consumer_con):
    _seed_all_series(consumer_con)
    result = consumer_sentiment_dashboard.load_detail(consumer_con)
    assert result["detail_id"] == "consumer_sentiment"
    assert "history" in result
    assert "capacity" in result
    assert len(result["history"]["umcsi_aggregate"]) == 2
    assert "percentile_windows" in result
    assert "context" in result
    assert "treasury_10y" in result["context"]
    assert "tips_10y" in result["context"]
    assert "cpi_yoy" in result["context"]
    assert "real_rate" in result["context"]
    assert "fomc_tone" not in result["context"]
    assert "capacity_interpretations" in result
    assert "household_debt_gdp_quarter_note" in result


def test_load_detail_preserves_rate_source_workbook(consumer_con):
    us_rates_liquidity.replace_rate_series_points(
        consumer_con,
        {
            "series_id": "treasury_10y",
            "title": "10-Year Treasury",
            "instrument_type": "nominal",
            "maturity_months": 120,
            "units": "percent",
            "source_workbook": "Rates.xlsx",
            "source_sheet": "Treasury",
        },
        [
            {
                "date": "2026-06-01",
                "value": 4.25,
                "source_workbook": "Rates.xlsx",
                "source_sheet": "Treasury",
            }
        ],
    )

    result = consumer_sentiment_dashboard.load_detail(consumer_con)

    assert result["context"]["treasury_10y"] == [
        {"date": "2026-06-01", "value": 4.25, "source": "Rates.xlsx"}
    ]


def test_normalize_rate_source_does_not_invent_missing_source():
    result = consumer_sentiment_dashboard._normalize_rate_source(
        [{"date": "2026-06-01", "value": 4.25}]
    )

    assert result == [{"date": "2026-06-01", "value": 4.25, "source": None}]
