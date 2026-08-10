import sqlite3
import threading
from types import ModuleType

import pytest

from fastapi.testclient import TestClient

from app.api import app
from app.db import growth_cycle
from app.db import macro_indicators as macro_indicators_db
from app.db import market_assistant as market_assistant_db
from app.services import market_setup_current


@pytest.fixture
def client():
    return TestClient(app)


def test_current_state_reads_all_sources_from_one_connection(monkeypatch, tmp_path):
    seen = []

    def record_connection(con):
        seen.append(id(con))

    monkeypatch.setattr(
        market_setup_current, "_record_read_connection", record_connection
    )
    market_setup_current.read_current_setup_state(
        tmp_path / "market.sqlite", as_of_date="2026-08-10"
    )

    assert len(set(seen)) == 1


def test_dashboard_route_matches_extracted_service(client, monkeypatch):
    expected = {"version": "market_setup_v2", "macro_regime": {"code": "growth_stable"}}
    monkeypatch.setattr(
        market_setup_current, "read_current_setup_state", lambda *a, **k: expected
    )

    assert client.get("/api/macro-dashboard/market-setup").json() == expected


def test_service_module_has_no_ingestion_or_data_source_imports():
    for value in vars(market_setup_current).values():
        if isinstance(value, ModuleType):
            assert "data_sources" not in value.__name__
            assert not value.__name__.endswith("_import")


def test_current_resolution_never_calls_fetch_or_refresh(tmp_path, monkeypatch):
    from app.data_sources import census_nrc
    from app.tools import benchmark_market_data as benchmark_market_data_tool

    def raise_on_call(*args, **kwargs):
        raise RuntimeError("network or ingestion must not be called")

    monkeypatch.setattr(benchmark_market_data_tool, "refresh_benchmarks", raise_on_call)
    monkeypatch.setattr(census_nrc, "fetch_permits_workbook", raise_on_call)

    payload = market_setup_current.read_current_setup_state(
        tmp_path / "market.sqlite", as_of_date="2026-08-10"
    )

    assert isinstance(payload, dict)


def test_current_state_reads_one_pre_commit_view_during_uncommitted_write(tmp_path):
    db_path = tmp_path / "market.sqlite"
    market_setup_current.read_current_setup_state(db_path, as_of_date="2026-08-10")
    market_setup_current.read_current_setup_state(db_path, as_of_date="2026-08-10")
    seed_con = sqlite3.connect(db_path)
    seed_con.execute(
        "insert into gdp_relationships(relationship_id, title) values ('us_sp500_gdp', 'US S&P 500 / GDP')"
    )
    seed_con.commit()
    seed_con.close()
    baseline = market_setup_current.read_current_setup_state(
        db_path, as_of_date="2026-08-10"
    )
    assert (
        baseline["evidence_layers"]["final_confirmation"]["coverage_summary"][0]
        == "GDP: missing"
    )
    writer = sqlite3.connect(db_path)
    writer.execute("begin")
    writer.execute(
        "insert into gdp_quad_rows(relationship_id, date, period_label) values ('us_sp500_gdp', '2026-06-30', '2026 Q2')"
    )
    try:
        payload = market_setup_current.read_current_setup_state(
            db_path, as_of_date="2026-08-10"
        )
        assert (
            payload["evidence_layers"]["final_confirmation"]["coverage_summary"][0]
            == "GDP: missing"
        )
    finally:
        writer.commit()
        writer.close()
    after = market_setup_current.read_current_setup_state(
        db_path, as_of_date="2026-08-10"
    )
    assert (
        after["evidence_layers"]["final_confirmation"]["coverage_summary"][0]
        == "GDP: available"
    )


def test_init_schema_keeps_begin_transaction_open_on_seeded_db(tmp_path):
    db_path = tmp_path / "market.sqlite"
    market_setup_current.read_current_setup_state(db_path, as_of_date="2026-08-10")
    con = market_assistant_db.connect(db_path)
    try:
        con.execute("begin")
        assert con.in_transaction is True
        market_setup_current._init_schema(con)
        assert con.in_transaction is True
        macro_indicators_db.load_macro_indicator_points(con, "m2_money_stock")
        assert con.in_transaction is True
    finally:
        con.rollback()
        con.close()


def test_current_state_ignores_commit_landing_between_two_reads(tmp_path, monkeypatch):
    db_path = tmp_path / "market.sqlite"
    market_setup_current.read_current_setup_state(db_path, as_of_date="2026-08-10")
    seed_con = sqlite3.connect(db_path)
    seed_con.execute(
        "insert into gdp_relationships(relationship_id, title) values ('us_sp500_gdp', 'US S&P 500 / GDP')"
    )
    seed_con.commit()
    seed_con.close()
    baseline = market_setup_current.read_current_setup_state(
        db_path, as_of_date="2026-08-10"
    )
    assert (
        baseline["evidence_layers"]["final_confirmation"]["coverage_summary"][0]
        == "GDP: missing"
    )
    reader_at_loader = threading.Event()
    writer_committed = threading.Event()
    release_reader = threading.Event()
    original_loader = growth_cycle.load_latest_ism_at_a_glance_rows

    def blocking_loader(con):
        reader_at_loader.set()
        assert release_reader.wait(timeout=10)
        return original_loader(con)

    monkeypatch.setattr(
        growth_cycle, "load_latest_ism_at_a_glance_rows", blocking_loader
    )

    def writer_commit_mid_read():
        assert reader_at_loader.wait(timeout=10)
        writer_con = sqlite3.connect(db_path)
        writer_con.execute("begin")
        writer_con.execute(
            "insert into gdp_quad_rows(relationship_id, date, period_label) values ('us_sp500_gdp', '2026-06-30', '2026 Q2')"
        )
        writer_con.commit()
        writer_con.close()
        writer_committed.set()
        release_reader.set()

    writer = threading.Thread(target=writer_commit_mid_read)
    writer.start()
    try:
        payload = market_setup_current.read_current_setup_state(
            db_path, as_of_date="2026-08-10"
        )
    finally:
        release_reader.set()
        writer.join(timeout=10)
    assert writer_committed.is_set()
    assert (
        payload["evidence_layers"]["final_confirmation"]["coverage_summary"][0]
        == "GDP: missing"
    )


def test_resolve_current_explanation_builds_snapshot_envelope(tmp_path):
    db_path = tmp_path / "market.sqlite"
    payload = market_setup_current.resolve_current_explanation(
        db_path, previous_context_id=None, resolved_at="2026-08-10T01:00:00Z"
    )

    assert payload["resolution"]["mode"] == "current"
    assert payload["resolution"]["resolved_at"] == "2026-08-10T01:00:00Z"
    assert payload["resolution"]["previous_context_id"] is None
    assert payload["resolution"]["context_changed"] is True
    assert payload["resolution"]["current_context_id"]
    assert payload["delta"] == {"results_changed": True, "changes": []}
    assert (
        payload["snapshot"]["context_id"] == payload["resolution"]["current_context_id"]
    )
    assert (
        payload["snapshot"]["snapshot_schema_version"]
        == "market_setup_explanation_snapshot_v1"
    )


def test_resolve_current_explanation_reuses_snapshot_by_fingerprint(tmp_path):
    db_path = tmp_path / "market.sqlite"
    first = market_setup_current.resolve_current_explanation(
        db_path, previous_context_id=None, resolved_at="2026-08-10T01:00:00Z"
    )
    second = market_setup_current.resolve_current_explanation(
        db_path,
        previous_context_id=first["resolution"]["current_context_id"],
        resolved_at="2026-08-10T02:00:00Z",
    )

    assert (
        second["resolution"]["current_context_id"]
        == first["resolution"]["current_context_id"]
    )
    assert second["resolution"]["context_changed"] is False
    assert (
        second["snapshot"]["explanation_fingerprint"]
        == first["snapshot"]["explanation_fingerprint"]
    )
    assert second["delta"] == {"results_changed": False, "changes": []}
