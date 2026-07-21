import pytest

from app.db import macro_indicators


def _series():
    return {
        "series_id": "bbb_corporate_yield",
        "title": "BBB Corporate Yield",
        "units": "percent",
        "source": "test",
    }


def _points():
    return [
        {"date": "2021-01-06", "value": 2.20, "source": "test"},
        {"date": "2021-01-07", "value": 2.16, "source": "test"},
    ]


def test_replace_macro_indicator_points_loads_sorted_rows(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    saved = macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    loaded_series = macro_indicators.load_macro_indicator_series(con)
    loaded_points = macro_indicators.load_macro_indicator_points(
        con, "bbb_corporate_yield"
    )

    assert saved == {"series": 1, "points": 2}
    assert loaded_series[0]["series_id"] == "bbb_corporate_yield"
    assert loaded_points[0]["date"] == "2021-01-06"
    assert loaded_points[-1]["value"] == 2.16


def test_replace_macro_indicator_points_deletes_old_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    saved = macro_indicators.replace_macro_indicator_points(
        con, _series(), [{"date": "2021-02-01", "value": 3.00, "source": "test"}]
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert len(loaded) == 1


def test_merge_macro_indicator_points_preserves_existing_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    workbook_points = [
        {"date": "2021-01-06", "value": 2.20, "source": "workbook"},
        {"date": "2021-01-07", "value": 2.16, "source": "workbook"},
    ]
    fred_points = [
        {"date": "2023-10-01", "value": 6.10, "source": "fred"},
        {"date": "2023-10-02", "value": 6.08, "source": "fred"},
    ]

    macro_indicators.replace_macro_indicator_points(con, _series(), workbook_points)
    saved = macro_indicators.merge_macro_indicator_points(
        con,
        {**_series(), "source": "merged"},
        fred_points,
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")
    loaded_series = [
        row
        for row in macro_indicators.load_macro_indicator_series(con)
        if row["series_id"] == "bbb_corporate_yield"
    ][0]

    assert saved == {"series": 1, "points": 2}
    assert [row["date"] for row in loaded] == [
        "2021-01-06",
        "2021-01-07",
        "2023-10-01",
        "2023-10-02",
    ]
    assert loaded[-1]["value"] == 6.08
    assert loaded_series["source"] == "merged"


def test_merge_macro_indicator_points_replaces_matching_dates(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(
        con,
        _series(),
        [{"date": "2023-10-02", "value": 12.00, "source": "old"}],
    )
    saved = macro_indicators.merge_macro_indicator_points(
        con,
        {**_series(), "source": "merged"},
        [{"date": "2023-10-02", "value": 11.75, "source": "new"}],
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert loaded == [{"date": "2023-10-02", "value": 11.75, "source": "new"}]


def test_insert_macro_indicator_points_additive(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.insert_macro_indicator_points(con, _series(), _points())
    saved = macro_indicators.insert_macro_indicator_points(
        con,
        _series(),
        [{"date": "2021-02-01", "value": 3.00, "source": "test"}],
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert len(loaded) == 3


def test_load_latest_macro_indicator_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    latest = macro_indicators.load_latest_macro_indicator_points(con)

    assert len(latest) >= 1
    bbb = [r for r in latest if r["series_id"] == "bbb_corporate_yield"]
    assert bbb[0]["date"] == "2021-01-07"
    assert bbb[0]["value"] == 2.16


def test_load_macro_indicator_points_for_series(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    grouped = macro_indicators.load_macro_indicator_points_for_series(
        con, ["bbb_corporate_yield"]
    )

    assert "bbb_corporate_yield" in grouped
    assert len(grouped["bbb_corporate_yield"]) == 2


def test_normalize_series_id_rejects_empty():
    with pytest.raises(ValueError, match="series id is required"):
        macro_indicators._normalize_series_id("")


def test_replace_macro_indicator_points_batch(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points_batch(
        con,
        [
            {"series": _series(), "points": _points()},
            {
                "series": {
                    "series_id": "aaa_corporate_yield",
                    "title": "AAA Corporate Yield",
                    "units": "percent",
                    "source": "test",
                },
                "points": [{"date": "2021-01-06", "value": 1.50, "source": "test"}],
            },
        ],
    )
    loaded = macro_indicators.load_macro_indicator_series(con)
    assert len(loaded) == 2
