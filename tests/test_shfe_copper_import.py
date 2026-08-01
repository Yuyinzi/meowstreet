from datetime import date as date_type

import pytest

from app.db import macro_indicators
from app.services import shfe_copper_import


def _raw_row(trade_date, contract, close, open_interest, **overrides):
    return {
        "trade_date": trade_date,
        "product": "CU",
        "contract": contract,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "previous_settlement": close,
        "settlement": close,
        "volume": 100.0,
        "open_interest": open_interest,
        "open_interest_change": None,
        "turnover": 10000.0,
        "source": "shfe",
        "source_class": "official_exchange",
        "access_adapter": "akshare",
        "access_adapter_version": "1.18.81",
        "source_identifier": "SHFE:CU",
        "source_url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
        "retrieved_at": "2026-07-31T00:00:00+00:00",
        **overrides,
    }


def fake_fetcher(rows_by_range):
    def fetcher(start, end):
        normalized = rows_by_range.get((start, end), [])
        if not normalized:
            raise ValueError("akshare returned no valid SHFE CU contract observations")
        return normalized

    return fetcher


def test_import_shfe_cu_dates_writes_raw_and_derived_only_after_success(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    rows = [
        _raw_row("2026-07-28", "CU2609", 79000.0, 200000.0),
        _raw_row("2026-07-28", "CU2610", 80200.0, 150000.0),
        _raw_row("2026-07-29", "CU2609", 79500.0, 120000.0),
        _raw_row("2026-07-29", "CU2610", 80500.0, 220000.0),
    ]
    fetcher = fake_fetcher({("2026-07-01", "2026-07-31"): rows})

    result = shfe_copper_import.import_shfe_cu_dates(
        con, ["2026-07-28", "2026-07-29"], fetcher=fetcher
    )

    assert result["raw_observations"] == 4
    assert result["derived_observations"] == 2
    raw = macro_indicators.load_shfe_cu_contract_observations(con)
    main = macro_indicators.load_shfe_cu_main_observations(con)
    assert len(raw) == 4
    assert len(main) == 2
    assert main[0]["selected_contract"] == "CU2609"


def test_import_shfe_cu_dates_rolls_back_on_adapter_failure_in_second_month(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")

    def partially_failing_fetcher(start, end):
        if start == "2026-08-01":
            raise RuntimeError("upstream source changed schema")
        return [
            _raw_row("2026-07-28", "CU2609", 79000.0, 200000.0),
            _raw_row("2026-07-28", "CU2610", 80200.0, 150000.0),
        ]

    with pytest.raises(RuntimeError, match="upstream source changed schema"):
        shfe_copper_import.import_shfe_cu_dates(
            con,
            ["2026-07-28", "2026-08-03"],
            fetcher=partially_failing_fetcher,
        )

    assert macro_indicators.load_shfe_cu_contract_observations(con) == []
    assert macro_indicators.load_shfe_cu_main_observations(con) == []


def test_incremental_window_starts_from_latest_raw_date_minus_14_days(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_shfe_cu_contract_observations(
        con,
        [_raw_row("2026-07-20", "CU2609", 79000.0, 200000.0)],
    )
    window = shfe_copper_import.incremental_window(con)

    assert window[0] == "2026-07-06"
    assert window[1] == date_type.today().isoformat()


def test_refresh_shfe_cu_main_rebuilds_recent_switch_in_lookback(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    earlier = [
        _raw_row("2026-07-10", "CU2609", 79000.0, 200000.0),
        _raw_row("2026-07-13", "CU2609", 79500.0, 220000.0),
        _raw_row("2026-07-13", "CU2610", 80500.0, 120000.0),
    ]
    macro_indicators.merge_shfe_cu_contract_observations(con, earlier)
    rows_by_range = {
        ("2026-07-01", "2026-07-31"): earlier
        + [
            _raw_row("2026-07-14", "CU2609", 80000.0, 100000.0),
            _raw_row("2026-07-14", "CU2610", 81000.0, 220000.0),
        ]
    }
    fetcher = fake_fetcher(rows_by_range)

    result = shfe_copper_import.refresh_shfe_cu_main(
        con,
        start_date="2026-07-13",
        end_date="2026-07-14",
        fetcher=fetcher,
    )

    assert result["derived_observations"] == 2
    main = macro_indicators.load_shfe_cu_main_observations(con)
    assert [row["selected_contract"] for row in main] == ["CU2609", "CU2610"]
    assert main[1]["contract_roll"] is True


def test_refresh_rebuild_window_boundary_does_not_roll_backward(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    pre_window = [
        _raw_row("2026-07-09", "CU2609", 79000.0, 100000.0),
        _raw_row("2026-07-09", "CU2610", 80200.0, 200000.0),
    ]
    macro_indicators.merge_shfe_cu_contract_observations(con, pre_window)
    macro_indicators.replace_shfe_cu_main_observations(
        con,
        [
            {
                "date": "2026-07-09",
                "selected_contract": "CU2610",
                "close": 80200.0,
                "contract_roll": True,
                "roll_affected": True,
            }
        ],
    )
    window_rows = [
        _raw_row("2026-07-10", "CU2609", 79500.0, 250000.0),
        _raw_row("2026-07-10", "CU2610", 80500.0, 150000.0),
    ]
    fetcher = fake_fetcher({("2026-07-01", "2026-07-31"): window_rows})

    shfe_copper_import.refresh_shfe_cu_main(
        con,
        start_date="2026-07-10",
        end_date="2026-07-10",
        fetcher=fetcher,
    )

    main = macro_indicators.load_shfe_cu_main_observations(con)
    assert [row["selected_contract"] for row in main] == ["CU2610", "CU2610"]
    assert main[1]["contract_roll"] is False
    assert main[1]["previous_selected_contract"] == "CU2610"


def test_import_shfe_cu_dates_reports_month_with_no_rows_as_source_failure(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")

    def empty_fetcher(start, end):
        raise ValueError("akshare returned no valid SHFE CU contract observations")

    with pytest.raises(ValueError, match="no valid SHFE CU"):
        shfe_copper_import.import_shfe_cu_dates(
            con, ["2026-07-28"], fetcher=empty_fetcher
        )
    assert macro_indicators.load_shfe_cu_contract_observations(con) == []


def test_import_shfe_cu_dates_partitions_range_into_calendar_months(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    calls = []

    def recording_fetcher(start, end):
        calls.append((start, end))
        return [
            _raw_row("2026-07-28", "CU2609", 79000.0, 200000.0),
            _raw_row("2026-08-03", "CU2610", 80500.0, 220000.0),
        ]

    shfe_copper_import.import_shfe_cu_dates(
        con, ["2026-07-28", "2026-08-03"], fetcher=recording_fetcher
    )

    assert calls == [("2026-07-01", "2026-07-31"), ("2026-08-01", "2026-08-31")]


def test_import_shfe_cu_dates_does_not_issue_one_request_per_date(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    calls = []

    def recording_fetcher(start, end):
        calls.append((start, end))
        return [_raw_row("2026-07-28", "CU2609", 79000.0, 200000.0)]

    shfe_copper_import.import_shfe_cu_dates(
        con, ["2026-07-01", "2026-07-02", "2026-07-03"], fetcher=recording_fetcher
    )

    assert len(calls) == 1


from scripts import import_shfe_copper


def fake_refresh(
    con,
    start_date=None,
    end_date=None,
    fetcher=None,
    dry_run=False,
    progress_callback=None,
):
    return {
        "raw_dates_requested": 10,
        "raw_dates_published": 8,
        "raw_observations": 96,
        "derived_observations": 8,
        "rebuild_start_date": "2026-07-16",
        "rebuild_end_date": "2026-07-30",
    }


def test_cli_accepts_explicit_backfill_dates(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(shfe_copper_import, "refresh_shfe_cu_main", fake_refresh)
    assert (
        import_shfe_copper.main(
            [
                "--db-path",
                str(tmp_path / "market.sqlite"),
                "--start-date",
                "2016-01-01",
                "--end-date",
                "2016-12-31",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "derived_observations: 8" in out


def test_cli_prints_each_received_shfe_trading_day(monkeypatch, tmp_path, capsys):
    def refresh_with_progress(
        con, start_date=None, end_date=None, fetcher=None, dry_run=False, progress_callback=None
    ):
        progress_callback(
            {
                "date": "2016-01-04",
                "contracts_received": 160,
                "completed": 1,
                "total": 245,
            }
        )
        return fake_refresh(con, start_date, end_date, fetcher)

    monkeypatch.setattr(
        shfe_copper_import, "refresh_shfe_cu_main", refresh_with_progress
    )

    assert (
        import_shfe_copper.main(
            [
                "--db-path",
                str(tmp_path / "market.sqlite"),
                "--start-date",
                "2016-01-01",
                "--end-date",
                "2016-12-31",
            ]
        )
        == 0
    )

    assert "SHFE CU 2016-01-04: received 160 contracts (1/245)" in capsys.readouterr().out


def test_cli_invalid_range_returns_code_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(shfe_copper_import, "refresh_shfe_cu_main", fake_refresh)
    assert (
        import_shfe_copper.main(
            [
                "--db-path",
                str(tmp_path / "market.sqlite"),
                "--start-date",
                "2026-12-31",
                "--end-date",
                "2026-01-01",
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "start date" in err


def test_cli_future_date_returns_code_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(shfe_copper_import, "refresh_shfe_cu_main", fake_refresh)
    assert (
        import_shfe_copper.main(
            [
                "--db-path",
                str(tmp_path / "market.sqlite"),
                "--start-date",
                "2099-01-01",
                "--end-date",
                "2099-12-31",
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "future" in err


def test_cli_dry_run_writes_neither_table(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        shfe_copper_import,
        "_default_fetcher",
        lambda progress_callback=None: fake_fetcher(
            {
                ("2026-07-01", "2026-07-31"): [
                    _raw_row("2026-07-28", "CU2609", 79000.0, 200000.0)
                ]
            }
        ),
    )
    assert (
        import_shfe_copper.main(
            [
                "--db-path",
                str(tmp_path / "market.sqlite"),
                "--start-date",
                "2026-07-01",
                "--end-date",
                "2026-07-31",
                "--dry-run",
            ]
        )
        == 0
    )
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    assert macro_indicators.load_shfe_cu_contract_observations(con) == []
    assert macro_indicators.load_shfe_cu_main_observations(con) == []
    con.close()
