import types

import pytest

from pathlib import Path

from app.data_sources import tracked_commodities
from app.data_sources.tracked_commodities import (
    ACTIVE_MARKET_SERIES,
    MARKET_SERIES,
)
from app.db import macro_indicators
from app.services import tracked_commodities_import
from app.services.tracked_commodities_import import (
    import_commodity_browser_rows,
    refresh_tracked_commodities,
)


def seed_observation(con, date, value):
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "iron_ore_62_cfr_china",
            "title": "Iron Ore 62% CFR China",
            "units": "USD/tonne",
            "source": "investing.com",
        },
        [{"date": date, "value": value, "source": "investing.com"}],
    )


def rendered_result(rows):
    return {
        "status": "ok",
        "payload": {
            "data": [
                {"rowDate": row_date, "last_close": price} for row_date, price in rows
            ]
        },
        "retrieved_at": "2026-08-01T12:00:00+00:00",
        "source_url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures",
    }


def stored_dates(con):
    return [
        point["date"]
        for point in macro_indicators.load_macro_indicator_points(
            con, "iron_ore_62_cfr_china"
        )
    ]


_FAKE_OBSERVATION = {
    "date": "2026-07-24",
    "value": 5.7,
    "source": "investing.com",
    "source_url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures",
    "source_identifier": "iron_ore_62_cfr_china",
    "source_class": "free_web",
    "retrieved_at": "2026-07-30T12:00:00",
}


def _fake_fetcher(start_date=None, end_date=None, markets=None):
    targets = [
        (sid, MARKET_SERIES[sid])
        for sid in (markets or ACTIVE_MARKET_SERIES)
    ]
    return {
        sid: {
            "series": {
                "series_id": sid,
                "title": meta["display_name"],
                "source": "investing.com",
                "source_class": "free_web",
                "units": "USD",
                "source_url": meta["price_page_url"],
                "exchange_label": meta["exchange_label"],
            },
            "observations": [{**_FAKE_OBSERVATION, "source_identifier": sid}],
        }
        for sid, meta in targets
    }


def test_refresh_rolls_back_when_a_market_requires_reauthentication(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    def failing_fetcher(start_date=None, end_date=None, markets=None):
        raise ValueError(
            "Investing session requires verification; "
            "run scripts/import_tracked_commodities.py --login"
        )

    with pytest.raises(ValueError, match="session requires verification"):
        refresh_tracked_commodities(con, fetcher=failing_fetcher)

    assert macro_indicators.load_macro_indicator_points(con, "copper_lme") == []


def test_refresh_merges_prices_and_preserves_source_metadata(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = refresh_tracked_commodities(con, fetcher=_fake_fetcher)
    assert result == {"series": 3, "observations": 3}

    points = macro_indicators.load_macro_indicator_points(
        con, "iron_ore_62_cfr_china"
    )
    assert len(points) == 1
    assert points[0]["source"] == "investing.com"


def test_refresh_rejects_archived_lumber(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    with pytest.raises(
        ValueError, match="archived commodity market: lumber"
    ):
        refresh_tracked_commodities(
            con, fetcher=_fake_fetcher, markets=["lumber"]
        )
    assert macro_indicators.load_macro_indicator_points(con, "lumber") == []


def test_refresh_preserves_source_class_and_retrieved_at_through_db_roundtrip(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    refresh_tracked_commodities(con, fetcher=_fake_fetcher)
    observations = macro_indicators.load_macro_indicator_observations(
        con, "iron_ore_62_cfr_china"
    )
    assert len(observations) == 1
    assert observations[0]["source_class"] == "free_web"
    assert observations[0]["retrieved_at"] == "2026-07-30T12:00:00"
    assert observations[0]["source_identifier"] == "iron_ore_62_cfr_china"


_CSV_TEXT = 'Date,Price,Open,High,Low,Vol.,Change %\n"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n"Jul 23, 2026",5.680,5.690,5.700,5.660,15.2K,-0.18%\n'


def test_cli_csv_rejects_empty_entry(tmp_path, capsys):
    from scripts import import_tracked_commodities

    exit_code = import_tracked_commodities.main(
        ["--csv", "--db-path", str(tmp_path / "test.db")]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "--csv requires at least one market_id=path.csv entry" in captured.err


def test_cli_csv_rejects_archived_lumber(tmp_path, capsys):
    from scripts import import_tracked_commodities

    csv_path = tmp_path / "lumber.csv"
    csv_path.write_text(
        "Date,Price,Open,High,Low,Vol.,Change %\n"
        '"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n',
        encoding="utf-8",
    )
    exit_code = import_tracked_commodities.main(
        [
            "--csv",
            f"lumber={csv_path}",
            "--db-path",
            str(tmp_path / "test.db"),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "archived commodity market cannot be imported: lumber" in (
        captured.err
    )


def test_cli_markets_rejects_archived_lumber():
    from scripts import import_tracked_commodities

    with pytest.raises(SystemExit, match="2"):
        import_tracked_commodities.main(["--markets", "lumber"])


def test_cli_reports_chrome_start_command_when_cdp_session_is_missing(
    monkeypatch, capsys
):
    from scripts import import_tracked_commodities

    def blocked_import(con, **kwargs):
        raise ValueError(
            "No Investing.com page found in the Chrome session at "
            "http://127.0.0.1:9222. "
            "Start the dedicated Chrome with scripts/start_investing_chrome.py, "
            "open and verify an Investing.com price page, and leave it open."
        )

    monkeypatch.setattr(
        import_tracked_commodities,
        "tracked_commodities_import",
        type(
            "fake_mod",
            (),
            {
                "import_commodity_browser_rows": staticmethod(blocked_import),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(
        ["--markets", "iron_ore_62_cfr_china", "--db-path", "/tmp/nonexistent.db"]
    )
    assert exit_code == 1
    assert "start_investing_chrome.py" in capsys.readouterr().err


def test_cli_dry_run_uses_rendered_history_range(monkeypatch, capsys):
    from scripts import import_tracked_commodities

    calls = []

    def fake_import(con, **kwargs):
        calls.append(kwargs)
        return {
            "series": 1,
            "observations": 42,
            "ranges": {
                "iron_ore_62_cfr_china": {
                    "start_date": "2026-07-30",
                    "end_date": "2026-07-31",
                }
            },
        }

    monkeypatch.setattr(
        import_tracked_commodities,
        "tracked_commodities_import",
        type(
            "fake_mod",
            (),
            {
                "import_commodity_browser_rows": staticmethod(fake_import),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(
        ["--dry-run", "--markets", "iron_ore_62_cfr_china"]
    )

    assert exit_code == 0
    assert calls == [
        {
            "markets": ["iron_ore_62_cfr_china"],
            "cdp_endpoint": "http://127.0.0.1:9222",
            "dry_run": True,
        }
    ]
    assert "2026-07-30 to 2026-07-31" in capsys.readouterr().out


def test_rendered_history_aborts_before_writes_when_an_archived_market_is_requested(
    tmp_path,
):
    con = macro_indicators.connect(tmp_path / "macro.db")

    def fetcher(market, **kwargs):
        return rendered_result([("Jul 31, 2026", "98.00")])

    with pytest.raises(
        ValueError, match="archived commodity market: lumber"
    ):
        import_commodity_browser_rows(
            con,
            markets=["iron_ore_62_cfr_china", "lumber"],
            fetcher=fetcher,
        )
    assert stored_dates(con) == []


def test_rendered_history_import_preserves_source_provenance(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-29", 98.27)

    def provenance_fetcher(market, **kwargs):
        return {
            "status": "ok",
            "payload": {
                "data": [
                    {"rowDate": "Jul 31, 2026", "last_close": "98.00"},
                    {"rowDate": "Jul 30, 2026", "last_close": "98.25"},
                ]
            },
            "retrieved_at": "2026-07-30T00:00:00+00:00",
            "source_url": market["price_page_url"],
        }

    result = import_commodity_browser_rows(
        con,
        markets=["iron_ore_62_cfr_china"],
        fetcher=provenance_fetcher,
    )
    assert result == {
        "series": 1,
        "observations": 2,
        "ranges": {
            "iron_ore_62_cfr_china": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            }
        },
        "no_new_data": [],
    }

    observations = macro_indicators.load_macro_indicator_observations(
        con, "iron_ore_62_cfr_china"
    )
    assert len(observations) == 3
    assert (
        observations[-1]["source_url"]
        == MARKET_SERIES["iron_ore_62_cfr_china"]["price_page_url"]
    )
    assert observations[-1]["retrieved_at"] == "2026-07-30T00:00:00+00:00"
    assert observations[-1]["source_identifier"] == "iron_ore_62_cfr_china"


def test_rendered_history_dry_run_returns_range_without_writing(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-29", 98.27)

    result = import_commodity_browser_rows(
        con,
        markets=["iron_ore_62_cfr_china"],
        fetcher=lambda market, **kwargs: rendered_result(
            [("Jul 31, 2026", "98.00"), ("Jul 30, 2026", "98.25")]
        ),
        dry_run=True,
    )

    assert result == {
        "series": 1,
        "observations": 2,
        "ranges": {
            "iron_ore_62_cfr_china": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            }
        },
        "no_new_data": [],
    }
    assert stored_dates(con) == ["2026-07-29"]


def test_default_cli_reports_missing_investing_tab(monkeypatch, capsys):
    from scripts import import_tracked_commodities

    def missing_tab_import(con, **kwargs):
        raise ValueError(
            "No Investing.com page found in the Chrome session; "
            "open and verify an Investing.com price page and leave it open"
        )

    monkeypatch.setattr(
        import_tracked_commodities,
        "tracked_commodities_import",
        type(
            "fake_mod",
            (),
            {
                "import_commodity_browser_rows": staticmethod(
                    missing_tab_import
                ),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(
        ["--markets", "iron_ore_62_cfr_china"]
    )
    assert exit_code == 1
    assert "leave it open" in capsys.readouterr().err


_CSV_TEXT = 'Date,Price,Open,High,Low,Vol.,Change %\n"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n"Jul 23, 2026",5.680,5.690,5.700,5.660,15.2K,-0.18%\n'


def test_csv_import_roundtrip_preserves_provenance(tmp_path):
    csv_path = tmp_path / "copper.csv"
    csv_path.write_text(_CSV_TEXT, encoding="utf-8")
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = tracked_commodities_import.import_commodity_csv_files(
        con, {"iron_ore_62_cfr_china": csv_path}
    )
    assert result == {"series": 1, "observations": 2}

    observations = macro_indicators.load_macro_indicator_observations(
        con, "iron_ore_62_cfr_china"
    )
    assert len(observations) == 2
    assert observations[0]["source"] == "investing.com"
    assert observations[0]["source_class"] == "free_web"
    assert observations[0]["source_identifier"] == "iron_ore_62_cfr_china"
    assert observations[0]["retrieved_at"] is not None


def test_refresh_honours_markets_parameter(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = refresh_tracked_commodities(
        con, fetcher=_fake_fetcher, markets=["iron_ore_62_cfr_china"]
    )
    assert result == {"series": 1, "observations": 1}


def test_refresh_accepts_reactivated_lme(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = refresh_tracked_commodities(
        con, fetcher=_fake_fetcher, markets=["copper_lme"]
    )
    assert result == {"series": 1, "observations": 1}
    points = macro_indicators.load_macro_indicator_points(con, "copper_lme")
    assert len(points) == 1


def test_free_web_series_includes_investing_copper_and_iron_ore():
    markets = tracked_commodities.free_web_series()

    assert list(markets) == [
        "copper_comex",
        "copper_lme",
        "iron_ore_62_cfr_china",
    ]
    assert (
        "copper_comex" not in tracked_commodities.ARCHIVED_MARKET_SERIES
    )
    assert "copper_lme" not in tracked_commodities.ARCHIVED_MARKET_SERIES


def test_macro_refresh_does_not_register_http_commodity_task_by_default():
    from jobs import refresh_macro_data

    args = types.SimpleNamespace(
        skip_yahoo=True,
        skip_rates=True,
        skip_consumer_sentiment=True,
        skip_m2=True,
        skip_building_permits=True,
        skip_ism=True,
        skip_gdp=True,
        skip_fomc=True,
        skip_nfib_sbo=True,
        skip_nfib_sbo_regional=True,
        skip_cyclical_commodities=True,
        skip_oil=True,
        skip_tracked_commodities=False,
        skip_lumber=True,
        skip_copper_comex=True,
        skip_lme_copper=True,
        fomc_calendar_path=None,
    )

    tasks = refresh_macro_data._planned_tasks(
        args,
        benchmark_main=lambda argv: 0,
        rates_main=lambda argv: 0,
        consumer_main=lambda argv: 0,
        m2_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        ism_reports_main=lambda argv: 0,
        gdp_main=lambda argv: 0,
        fomc_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        tracked_commodities_main=lambda argv: 0,
    )
    task_names = [task["name"] for task in tasks]
    assert "tracked_commodities" not in task_names


def test_cli_rejects_obsolete_browser_download_option():
    from scripts import import_tracked_commodities

    with pytest.raises(SystemExit, match="2"):
        import_tracked_commodities.main(["--browser-download"])


def test_rendered_history_merges_only_dates_later_than_baseline(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-29", 98.27)
    result = import_commodity_browser_rows(
        con,
        markets=["iron_ore_62_cfr_china"],
        fetcher=lambda market, **kwargs: rendered_result(
            [
                ("Jul 31, 2026", "98.00"),
                ("Jul 30, 2026", "98.25"),
                ("Jul 29, 2026", "98.27"),
            ]
        ),
    )
    assert result["observations"] == 2
    assert stored_dates(con) == ["2026-07-29", "2026-07-30", "2026-07-31"]


def test_rendered_history_requires_existing_baseline(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    with pytest.raises(ValueError, match="requires an existing baseline"):
        import_commodity_browser_rows(
            con,
            markets=["iron_ore_62_cfr_china"],
            fetcher=lambda market, **kwargs: rendered_result(
                [("Jul 31, 2026", "98.00")]
            ),
        )


def test_rendered_history_rejects_empty_payload(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-29", 98.27)

    with pytest.raises(ValueError, match="no parseable rows"):
        import_commodity_browser_rows(
            con,
            markets=["iron_ore_62_cfr_china"],
            fetcher=lambda market, **kwargs: {
                "status": "ok",
                "payload": {"data": []},
                "retrieved_at": "2026-07-30T00:00:00+00:00",
                "source_url": market["price_page_url"],
            },
        )
    assert stored_dates(con) == ["2026-07-29"]


def test_rendered_history_no_op_when_no_rendered_date_is_newer_than_baseline(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-31", 98.00)
    result = import_commodity_browser_rows(
        con,
        markets=["iron_ore_62_cfr_china"],
        fetcher=lambda market, **kwargs: rendered_result(
            [("Jul 31, 2026", "98.00"), ("Jul 30, 2026", "98.25")]
        ),
    )
    assert result == {
        "series": 0,
        "observations": 0,
        "ranges": {},
        "no_new_data": ["iron_ore_62_cfr_china"],
    }
    assert stored_dates(con) == ["2026-07-31"]


def test_rendered_history_mixed_markets_commit_new_and_record_noop(
    tmp_path, monkeypatch
):
    fake_meta = {
        "price_page_url": "https://www.investing.com/commodities/fake-historical-data",
        "display_name": "Fake Iron Ore",
        "exchange_label": "Fake",
        "instrument": "Fake index",
        "units": "USD/tonne",
    }
    monkeypatch.setitem(MARKET_SERIES, "fake_iron_ore", fake_meta)
    monkeypatch.setitem(ACTIVE_MARKET_SERIES, "fake_iron_ore", fake_meta)

    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-29", 98.27)
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "fake_iron_ore",
            "title": "Fake Iron Ore",
            "units": "USD/tonne",
            "source": "investing.com",
        },
        [{"date": "2026-07-31", "value": 1.0, "source": "investing.com"}],
    )

    def fetcher(market, **kwargs):
        if market["price_page_url"] == fake_meta["price_page_url"]:
            return rendered_result([("Jul 31, 2026", "1.00"), ("Jul 30, 2026", "1.01")])
        return rendered_result([("Jul 31, 2026", "98.00"), ("Jul 30, 2026", "98.25")])

    result = import_commodity_browser_rows(
        con,
        markets=["iron_ore_62_cfr_china", "fake_iron_ore"],
        fetcher=fetcher,
    )
    assert result == {
        "series": 1,
        "observations": 2,
        "ranges": {
            "iron_ore_62_cfr_china": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            }
        },
        "no_new_data": ["fake_iron_ore"],
    }
    assert stored_dates(con) == ["2026-07-29", "2026-07-30", "2026-07-31"]
    fake_dates = [
        point["date"]
        for point in macro_indicators.load_macro_indicator_points(
            con, "fake_iron_ore"
        )
    ]
    assert fake_dates == ["2026-07-31"]


def test_rendered_history_writes_nothing_when_adapter_fails(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    seed_observation(con, "2026-07-29", 98.27)

    def failing_fetcher(market, **kwargs):
        return {
            "status": "render_failed",
            "message": "historical data table missing",
        }

    with pytest.raises(ValueError, match="rendered history fetch failed"):
        import_commodity_browser_rows(
            con,
            markets=["iron_ore_62_cfr_china"],
            fetcher=failing_fetcher,
        )
    assert stored_dates(con) == ["2026-07-29"]


def test_default_cli_uses_rendered_history_importer(monkeypatch, tmp_path, capsys):
    from scripts import import_tracked_commodities

    calls = []
    monkeypatch.setattr(
        import_tracked_commodities.tracked_commodities_import,
        "import_commodity_browser_rows",
        lambda con, **kwargs: (
            calls.append(kwargs) or {"series": 1, "observations": 2, "ranges": {}}
        ),
    )
    assert (
        import_tracked_commodities.main(["--db-path", str(tmp_path / "macro.db")])
        == 0
    )
    assert calls[0]["markets"] == [
        "copper_comex",
        "copper_lme",
        "iron_ore_62_cfr_china",
    ]
    assert "observations: 2" in capsys.readouterr().out
