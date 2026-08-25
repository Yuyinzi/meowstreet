from types import SimpleNamespace

import pytest

from app.services import macro_refresh_commodities
from app.services.macro_refresh_registry import build_refresh_tasks
from app.services.macro_refresh_resources import ArtifactStore, SQLiteWriterGate


def _args(**overrides):
    values = {
        "skip_yahoo": True,
        "skip_rates": True,
        "skip_consumer_sentiment": True,
        "skip_m2": True,
        "skip_macro_indicators": True,
        "skip_building_permits": True,
        "skip_ism": True,
        "skip_gdp": True,
        "skip_fomc": True,
        "skip_nfib_sbo": True,
        "skip_nfib_sbo_regional": True,
        "skip_tracked_commodities": False,
        "skip_cyclical_commodities": False,
        "skip_oil": False,
        "skip_lumber": True,
        "skip_shfe_copper": False,
        "skip_dce_iron_ore_sina": False,
        "skip_economic_confirmation": False,
        "fomc_calendar_path": None,
        "verbose": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _providers():
    return {
        "tracked_commodities_fetch": lambda argv: 0,
        "tracked_commodities_import": lambda argv: 0,
        "cyclical_cot_fetch": lambda argv: 0,
        "cyclical_cot_import": lambda argv: 0,
        "cyclical_fred_fetch": lambda argv: 0,
        "cyclical_fred_import": lambda argv: 0,
        "oil_fetch": lambda argv: 0,
        "oil_import": lambda argv: 0,
        "shfe_copper_fetch": lambda argv: 0,
        "shfe_copper_import": lambda argv: 0,
        "dce_iron_ore_sina_fetch": lambda argv: 0,
        "dce_iron_ore_sina_import": lambda argv: 0,
        "dol_fetch": lambda argv: 0,
        "dol_import": lambda argv: 0,
        "bls_fetch": lambda argv: 0,
        "bls_import": lambda argv: 0,
        "federal_reserve_fetch": lambda argv: 0,
        "federal_reserve_import": lambda argv: 0,
    }


def test_registry_stages_commodity_and_confirmation_provider_lanes():
    tasks = build_refresh_tasks(
        _args(), _providers(), openai_config={}, artifact_store=ArtifactStore()
    )
    selected = {task["name"]: task for task in tasks}

    assert selected["tracked_commodities_fetch"]["lane"] == "tracked_commodities"
    assert selected["cyclical_cot_fetch"]["lane"] == "cftc"
    assert selected["cyclical_cot_import"]["resources"] == ["sqlite_writer"]
    assert selected["cyclical_fred_fetch"]["lane"] == "fred_macro"
    assert selected["cyclical_fred_fetch"]["resources"] == ["fred"]
    assert selected["oil_fetch"]["lane"] == "eia"
    assert selected["shfe_copper_fetch"]["lane"] == "shfe"
    assert selected["dce_iron_ore_sina_fetch"]["lane"] == "dce_sina"
    assert selected["dol_fetch"]["lane"] == "dol"
    assert selected["bls_fetch"]["lane"] == "bls"
    assert selected["federal_reserve_fetch"]["lane"] == "federal_reserve"
    assert selected["dol_import"]["resources"] == ["sqlite_writer"]


def test_cyclical_fred_fetch_and_cftc_fetch_are_separate_artifacts():
    artifacts = ArtifactStore()
    result = macro_refresh_commodities.fetch_cyclical_fred(
        artifacts, fetcher=lambda series_id: f"observation_date,{series_id}\n"
    )

    assert result["artifact_key"] == "commodities.cyclical_fred"
    assert "commodities.cyclical_fred" in artifacts._values


def test_persistence_does_not_call_network_fetcher(tmp_path):
    artifacts = ArtifactStore()
    artifacts.put(
        "commodities.oil",
        {
            "oil_wti_spot": {
                "series": {"series_id": "oil_wti_spot"},
                "observations": [],
            }
        },
    )
    called = []

    with pytest.raises(ValueError):
        macro_refresh_commodities.persist_oil(
            tmp_path / "market.sqlite", artifacts, fetcher=lambda: called.append(1)
        )
    assert called == []


def test_fetch_adapter_can_run_while_writer_gate_is_held(tmp_path):
    gate = SQLiteWriterGate()
    artifacts = ArtifactStore()
    with gate.acquire():
        result = macro_refresh_commodities.fetch_cyclical_fred(
            artifacts,
            fetcher=lambda series_id: f"observation_date,{series_id}\n2026-08-01,1\n",
        )

    assert result["series"]


def _shfe_row(trade_date):
    return {
        "trade_date": trade_date,
        "product": "CU",
        "contract": "CU2610",
        "open": 80500.0,
        "high": 80500.0,
        "low": 80500.0,
        "close": 80500.0,
        "previous_settlement": 80400.0,
        "settlement": 80500.0,
        "volume": 100.0,
        "open_interest": 220000.0,
        "open_interest_change": 100.0,
        "turnover": 10000.0,
        "source": "shfe",
        "source_class": "official_exchange",
        "access_adapter": "akshare",
        "access_adapter_version": "1.18.81",
        "source_identifier": "SHFE:CU",
        "source_url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
        "retrieved_at": "2026-07-31T00:00:00+00:00",
    }


def test_persist_shfe_commits_each_staged_date_before_later_failure(monkeypatch, tmp_path):
    artifacts = ArtifactStore()
    artifacts.put(
        "commodities.shfe",
        {
            "trade_dates": ["2026-07-28", "2026-07-29"],
            "rows": [_shfe_row("2026-07-28"), _shfe_row("2026-07-29")],
        },
    )
    from app.db import macro_indicators
    from app.services import shfe_copper_import

    real_import = shfe_copper_import.import_shfe_cu_dates
    calls = []

    def fail_second(con, trade_dates, **kwargs):
        calls.append(trade_dates)
        if len(calls) == 2:
            raise RuntimeError("second SHFE date failed")
        return real_import(con, trade_dates, **kwargs)

    monkeypatch.setattr(shfe_copper_import, "import_shfe_cu_dates", fail_second)

    with pytest.raises(RuntimeError, match="second SHFE date failed"):
        macro_refresh_commodities.persist_shfe_copper(tmp_path / "market.sqlite", artifacts)

    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        rows = macro_indicators.load_shfe_cu_contract_observations(con)
    finally:
        con.close()
    assert calls == [["2026-07-28"], ["2026-07-29"]]
    assert [row["trade_date"] for row in rows] == ["2026-07-28"]


def test_fetch_dce_uses_fourteen_day_overlap_after_latest_observation(tmp_path):
    from app.db import macro_indicators

    db_path = tmp_path / "market.sqlite"
    con = macro_indicators.connect(db_path)
    macro_indicators.merge_macro_indicator_observations(
        con,
        {
            "series_id": "iron_ore_dce",
            "title": "Sina I0",
            "units": "CNY/tonne",
            "source": "sina",
        },
        [{"date": "2026-08-10", "value": 700.0, "source": "sina"}],
    )
    con.close()

    calls = []

    def fetcher(start_date, end_date):
        calls.append((start_date, end_date))
        return {
            "series": {"series_id": "iron_ore_dce"},
            "observations": [{"date": "2026-08-20", "value": 701.0, "source": "sina"}],
        }

    macro_refresh_commodities.fetch_dce_iron_ore_sina(
        ArtifactStore(),
        db_path=db_path,
        today_date="2026-08-20",
        fetcher=fetcher,
    )

    assert calls == [("2026-07-27", "2026-08-21")]


def test_fetch_dce_initial_uses_full_history_window(tmp_path):
    calls = []

    def fetcher(start_date, end_date):
        calls.append((start_date, end_date))
        return {
            "series": {"series_id": "iron_ore_dce"},
            "observations": [{"date": "2013-10-18", "value": 700.0, "source": "sina"}],
        }

    macro_refresh_commodities.fetch_dce_iron_ore_sina(
        ArtifactStore(),
        db_path=tmp_path / "market.sqlite",
        today_date="2026-08-20",
        initial=True,
        fetcher=fetcher,
    )

    assert calls == [("2013-10-18", "2026-08-21")]
