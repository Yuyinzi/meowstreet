import pytest

from app.db import consumer_sentiment, macro_indicators


def _michigan_series(series_id, title):
    return {
        "series_id": series_id,
        "title": title,
        "units": "index_points",
        "source": "University of Michigan Table 1",
    }


def _capacity_series(series_id, title):
    return {
        "series_id": series_id,
        "title": title,
        "units": "percent",
        "source": "FRED test",
    }


def test_replace_michigan_series_stores_all_three(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    consumer_sentiment.replace_michigan_series(
        con,
        [
            {
                "series": _michigan_series("umcsi_aggregate", "UMCSI Aggregate"),
                "points": [
                    {
                        "date": "2026-06-01",
                        "value": 70.0,
                        "source": "University of Michigan Table 1",
                    }
                ],
            },
            {
                "series": _michigan_series("umcsi_expectations", "UMCSI Expectations"),
                "points": [
                    {
                        "date": "2026-06-01",
                        "value": 68.0,
                        "source": "University of Michigan Table 5",
                    }
                ],
            },
            {
                "series": _michigan_series(
                    "umcsi_current_conditions", "UMCSI Current Conditions"
                ),
                "points": [
                    {
                        "date": "2026-06-01",
                        "value": 75.0,
                        "source": "University of Michigan Table 5",
                    }
                ],
            },
        ],
    )
    series = macro_indicators.load_macro_indicator_series(con)
    series_ids = {s["series_id"] for s in series}
    assert series_ids == {
        "umcsi_aggregate",
        "umcsi_expectations",
        "umcsi_current_conditions",
    }


def test_replace_michigan_series_rejects_invalid_series_id(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    with pytest.raises(ValueError, match="not a valid michigan series id"):
        consumer_sentiment.replace_michigan_series(
            con,
            [
                {
                    "series": {
                        "series_id": "invalid_series",
                        "title": "Bad",
                        "units": "x",
                        "source": "test",
                    },
                    "points": [],
                },
            ],
        )


def test_replace_michigan_series_preserves_unrelated_series(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    macro_indicators.replace_macro_indicator_points(
        con,
        {
            "series_id": "treasury_10y",
            "title": "10Y",
            "units": "percent",
            "source": "test",
        },
        [{"date": "2026-06-01", "value": 4.5, "source": "test"}],
    )

    consumer_sentiment.replace_michigan_series(
        con,
        [
            {
                "series": _michigan_series("umcsi_aggregate", "UMCSI Aggregate"),
                "points": [{"date": "2026-06-01", "value": 70.0, "source": "test"}],
            },
        ],
    )
    treasury = macro_indicators.load_macro_indicator_points(con, "treasury_10y")
    assert len(treasury) == 1


def test_replace_capacity_series_stores_all_four(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    series_list = []
    for sid in consumer_sentiment.CAPACITY_SERIES_IDS:
        series_list.append(
            {
                "series": _capacity_series(sid, sid),
                "points": [
                    {"date": "2026-06-01", "value": 10.0, "source": "FRED test"}
                ],
            }
        )
    consumer_sentiment.replace_capacity_series(con, series_list)
    series = macro_indicators.load_macro_indicator_series(con)
    stored_ids = {s["series_id"] for s in series}
    assert stored_ids == consumer_sentiment.CAPACITY_SERIES_IDS


def test_replace_capacity_series_rejects_invalid_series_id(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    with pytest.raises(ValueError, match="not a valid capacity series id"):
        consumer_sentiment.replace_capacity_series(
            con,
            [
                {
                    "series": {
                        "series_id": "bad",
                        "title": "Bad",
                        "units": "x",
                        "source": "test",
                    },
                    "points": [],
                },
            ],
        )


def test_load_overview_series_returns_all_consumer_series(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    consumer_sentiment.replace_michigan_series(
        con,
        [
            {
                "series": _michigan_series("umcsi_aggregate", "UMCSI Aggregate"),
                "points": [{"date": "2026-06-01", "value": 70.0, "source": "test"}],
            },
        ],
    )
    result = consumer_sentiment.load_overview_series(con)
    assert "umcsi_aggregate" in result


def test_load_detail_series_returns_all_consumer_series(tmp_path):
    con = consumer_sentiment.connect(tmp_path / "market.sqlite")
    result = consumer_sentiment.load_detail_series(con)
    assert isinstance(result, dict)
