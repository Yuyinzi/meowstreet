import types

import pytest

from pathlib import Path

from app.data_sources.tracked_commodities import (
    ACTIVE_MARKET_SERIES,
    MARKET_SERIES,
)
from app.db import macro_indicators
from app.services import tracked_commodities_import
from app.services.tracked_commodities_import import (
    import_commodity_browser_downloads,
    refresh_tracked_commodities,
)


_FAKE_OBSERVATION = {
    "date": "2026-07-24",
    "value": 5.7,
    "source": "investing.com",
    "source_url": "https://www.investing.com/commodities/copper-historical-data?cid=959211",
    "source_identifier": "copper_lme",
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


def test_refresh_merges_method_prices_and_preserves_source_metadata(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = refresh_tracked_commodities(con, fetcher=_fake_fetcher)
    assert result == {"series": 2, "observations": 2}

    points = macro_indicators.load_macro_indicator_points(con, "copper_lme")
    assert len(points) == 1
    assert points[0]["source"] == "investing.com"


def test_refresh_rejects_archived_lumber(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    with pytest.raises(
        ValueError, match="archived method commodity market: lumber"
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
        con, "copper_lme"
    )
    assert len(observations) == 1
    assert observations[0]["source_class"] == "free_web"
    assert observations[0]["retrieved_at"] == "2026-07-30T12:00:00"
    assert observations[0]["source_identifier"] == "copper_lme"


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
    assert "archived method commodity market cannot be imported: lumber" in (
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
            "open and verify an Investing.com method page, and leave it open."
        )

    monkeypatch.setattr(
        import_tracked_commodities,
        "tracked_commodities_import",
        type(
            "fake_mod",
            (),
            {
                "import_commodity_browser_downloads": staticmethod(
                    blocked_import
                ),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(
        ["--markets", "copper_lme", "--db-path", "/tmp/nonexistent.db"]
    )
    assert exit_code == 1
    assert "start_investing_chrome.py" in capsys.readouterr().err


def test_cli_dry_run_uses_browser_download_range(monkeypatch, capsys):
    from scripts import import_tracked_commodities

    calls = []

    def fake_import(con, **kwargs):
        calls.append(kwargs)
        return {
            "series": 1,
            "observations": 42,
            "ranges": {
                "copper_lme": {
                    "start_date": "2016-01-01",
                    "end_date": "2026-07-30",
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
                "import_commodity_browser_downloads": staticmethod(fake_import),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(
        ["--dry-run", "--markets", "copper_lme"]
    )

    assert exit_code == 0
    assert calls == [
        {
            "markets": ["copper_lme"],
            "cdp_endpoint": "http://127.0.0.1:9222",
            "dry_run": True,
        }
    ]
    assert "2016-01-01 to 2026-07-30" in capsys.readouterr().out


def test_cli_defaults_to_browser_download_batch(monkeypatch, capsys, tmp_path):
    from scripts import import_tracked_commodities

    calls = []

    def successful_import(con, **kwargs):
        calls.append(kwargs)
        return {"series": 1, "observations": 5}

    monkeypatch.setattr(
        import_tracked_commodities,
        "tracked_commodities_import",
        type(
            "fake_mod",
            (),
            {
                "import_commodity_browser_downloads": staticmethod(
                    successful_import
                ),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(
        ["--markets", "copper_lme", "--db-path", str(tmp_path / "test.db")]
    )

    assert exit_code == 0
    assert calls == [
        {
            "markets": ["copper_lme"],
            "cdp_endpoint": "http://127.0.0.1:9222",
        }
    ]
    assert "observations: 5" in capsys.readouterr().out


_CSV_TEXT = 'Date,Price,Open,High,Low,Vol.,Change %\n"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n"Jul 23, 2026",5.680,5.690,5.700,5.660,15.2K,-0.18%\n'


def test_csv_import_roundtrip_preserves_provenance(tmp_path):
    csv_path = tmp_path / "copper.csv"
    csv_path.write_text(_CSV_TEXT, encoding="utf-8")
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = tracked_commodities_import.import_commodity_csv_files(
        con, {"copper_lme": csv_path}
    )
    assert result == {"series": 1, "observations": 2}

    observations = macro_indicators.load_macro_indicator_observations(
        con, "copper_lme"
    )
    assert len(observations) == 2
    assert observations[0]["source"] == "investing.com"
    assert observations[0]["source_class"] == "free_web"
    assert observations[0]["source_identifier"] == "copper_lme"
    assert observations[0]["retrieved_at"] is not None


def test_refresh_honours_markets_parameter(tmp_path):
    db_path = tmp_path / "test.db"
    con = macro_indicators.connect(db_path)

    result = refresh_tracked_commodities(
        con, fetcher=_fake_fetcher, markets=["copper_lme"]
    )
    assert result == {"series": 1, "observations": 1}


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
        fomc_calendar_path=None,
    )

    tasks = refresh_macro_data._planned_tasks(
        args,
        benchmark_main=lambda argv: 0,
        rates_main=lambda argv: 0,
        consumer_main=lambda argv: 0,
        m2_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        ism_main=lambda argv: 0,
        ism_services_main=lambda argv: 0,
        ism_reports_main=lambda argv: 0,
        gdp_main=lambda argv: 0,
        fomc_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        tracked_commodities_main=lambda argv: 0,
    )
    task_names = [t[0] for t in tasks]
    assert "tracked_commodities" not in task_names


def test_browser_download_batch_writes_nothing_when_one_market_download_fails(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")

    def failing_downloader(market, **kwargs):
        if "lumber" in market.get("price_page_url", ""):
            return {"status": "download_failed", "message": "unavailable"}
        csv_path = tmp_path / "ok.csv"
        csv_path.write_text(
            "Date,Price,Open,High,Low,Vol.,Change %\n"
            '"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n',
            encoding="utf-8",
        )
        return {
            "status": "ok",
            "csv_path": csv_path,
            "source_url": market["price_page_url"],
            "retrieved_at": "2026-07-30T00:00:00+00:00",
        }

    with pytest.raises(ValueError, match="lumber"):
        import_commodity_browser_downloads(
            con,
            markets=["copper_lme", "lumber"],
            downloader=failing_downloader,
        )
    assert macro_indicators.load_macro_indicator_points(con, "copper_lme") == []


def test_browser_download_import_uses_price_page_url_and_download_retrieval_time(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")

    csv_path = tmp_path / "ok.csv"
    csv_path.write_text(
        "Date,Price,Open,High,Low,Vol.,Change %\n"
        '"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n',
        encoding="utf-8",
    )

    def completed_downloader(market, **kwargs):
        return {
            "status": "ok",
            "csv_path": csv_path,
            "source_url": market["price_page_url"],
            "retrieved_at": "2026-07-30T00:00:00+00:00",
        }

    result = import_commodity_browser_downloads(
        con,
        markets=["copper_lme"],
        downloader=completed_downloader,
    )
    assert result == {"series": 1, "observations": 1}

    observations = macro_indicators.load_macro_indicator_observations(
        con, "copper_lme"
    )
    assert len(observations) == 1
    assert (
        observations[0]["source_url"]
        == MARKET_SERIES["copper_lme"]["price_page_url"]
    )
    assert observations[0]["retrieved_at"] == "2026-07-30T00:00:00+00:00"


def test_browser_download_dry_run_returns_range_without_writing_observations(tmp_path):
    con = macro_indicators.connect(tmp_path / "macro.db")
    csv_path = tmp_path / "ok.csv"
    csv_path.write_text(
        "Date,Price,Open,High,Low,Vol.,Change %\n"
        '"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n',
        encoding="utf-8",
    )

    def completed_downloader(market, **kwargs):
        return {
            "status": "ok",
            "csv_path": csv_path,
            "source_url": market["price_page_url"],
            "retrieved_at": "2026-07-30T00:00:00+00:00",
            "start_date": "2016-01-01",
            "end_date": "2026-07-30",
        }

    result = import_commodity_browser_downloads(
        con,
        markets=["copper_lme"],
        downloader=completed_downloader,
        dry_run=True,
    )

    assert result == {
        "series": 1,
        "observations": 1,
        "ranges": {
            "copper_lme": {
                "start_date": "2016-01-01",
                "end_date": "2026-07-30",
            }
        },
    }
    assert macro_indicators.load_macro_indicator_points(con, "copper_lme") == []


def test_default_browser_download_reports_missing_investing_tab(monkeypatch, capsys):
    from scripts import import_tracked_commodities

    def missing_tab_import(con, **kwargs):
        raise ValueError(
            "No Investing.com page found in the Chrome session; "
            "open and verify an Investing.com method page and leave it open"
        )

    monkeypatch.setattr(
        import_tracked_commodities,
        "tracked_commodities_import",
        type(
            "fake_mod",
            (),
            {
                "import_commodity_browser_downloads": staticmethod(
                    missing_tab_import
                ),
            },
        )(),
    )

    exit_code = import_tracked_commodities.main(["--markets", "copper_lme"])
    assert exit_code == 1
    assert "leave it open" in capsys.readouterr().err


def test_cli_rejects_obsolete_browser_download_option():
    from scripts import import_tracked_commodities

    with pytest.raises(SystemExit, match="2"):
        import_tracked_commodities.main(["--browser-download"])
