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


def test_replace_macro_indicator_points_batch_atomic_rollback_on_error(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")

    with pytest.raises(ValueError, match="series id is required"):
        macro_indicators.replace_macro_indicator_points_batch(
            con,
            [
                {"series": _series(), "points": _points()},
                {
                    "series": {
                        "series_id": "",
                        "title": "Bad Series",
                        "units": "percent",
                        "source": "test",
                    },
                    "points": [{"date": "2021-01-06", "value": 1.50, "source": "test"}],
                },
            ],
        )

    loaded = macro_indicators.load_macro_indicator_series(con)
    assert len(loaded) == 0


class TestMacroIndicatorObservationMetadata:
    def test_merge_macro_indicator_observations_replaces_a_revised_month(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        series = {
            "series_id": "building_permits_saar",
            "title": "Building Permits",
            "units": "thousands_saar",
            "source": "Census",
        }
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-05-01",
                    "value": 1413.0,
                    "source": "census.xlsx",
                    "release_date": "2026-06-16",
                    "revision_status": "initial",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "May 2026",
                }
            ],
        )
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-05-01",
                    "value": 1418.0,
                    "source": "census.xlsx",
                    "release_date": "2026-07-17",
                    "revision_status": "revised",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "June 2026 release",
                }
            ],
        )
        result = macro_indicators.load_macro_indicator_observations(
            con, "building_permits_saar"
        )
        assert result == [
            {
                "date": "2026-05-01",
                "value": 1418.0,
                "source": "census.xlsx",
                "release_date": "2026-07-17",
                "revision_status": "revised",
                "source_url": "https://www.census.gov/construction/nrc/index.html",
                "source_identifier": "June 2026 release",
                "source_hash": None,
            }
        ]

    def test_merge_macro_indicator_observations_preserves_metadata_on_value_update(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        series = {
            "series_id": "building_permits_saar",
            "title": "Building Permits",
            "units": "thousands_saar",
            "source": "Census",
        }
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-05-01",
                    "value": 1413.0,
                    "source": "census.xlsx",
                    "release_date": "2026-06-16",
                    "revision_status": "initial",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "May 2026",
                },
                {
                    "date": "2026-04-01",
                    "value": 1420.0,
                    "source": "census.xlsx",
                    "release_date": "2026-06-16",
                    "revision_status": "initial",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "May 2026",
                },
            ],
        )
        result = macro_indicators.load_macro_indicator_observations(
            con, "building_permits_saar"
        )
        assert len(result) == 2
        assert result[0]["date"] == "2026-04-01"
        assert result[1]["date"] == "2026-05-01"
        assert all(r["release_date"] == "2026-06-16" for r in result)
        assert all(r["revision_status"] == "initial" for r in result)

    def test_load_macro_indicator_observations_returns_empty_for_unknown_series(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        result = macro_indicators.load_macro_indicator_observations(
            con, "no_such_series"
        )
        assert result == []


_COT_ROW = {
    "commodity_id": "crude_oil_wti",
    "report_date": "2026-07-21",
    "manager_longs": 200000.0,
    "manager_shorts": 150000.0,
    "open_interest": 1000000.0,
    "publication_date": "2026-07-24",
    "report_type": "disaggregated_futures_only",
    "source_url": "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
    "source_hash": "abc123",
}


def test_merge_cot_observations_updates_same_commodity_and_report_date(tmp_path):
    con = macro_indicators.connect(tmp_path / ".sqlite")
    macro_indicators.merge_cot_observations(con, [_COT_ROW])
    macro_indicators.merge_cot_observations(
        con, [{**_COT_ROW, "manager_longs": 201000.0}]
    )

    assert macro_indicators.load_cot_observations(con) == [
        {**_COT_ROW, "manager_longs": 201000.0}
    ]
