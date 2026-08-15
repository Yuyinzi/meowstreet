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


class TestNormalizerExplanations:
    def test_policy_normalizer_preserves_approved_fomc_policy_read(self):
        fomc = {
            "period": "2026-07-28",
            "latest_tone": {
                "policy_action": "hold",
                "marker_tone": "hawkish",
                "guidance_bias": "neutral",
                "language_tone": "hawkish",
                "overall_bias": "mild_hawkish",
                "tone_change": "more_hawkish",
                "confidence": "high",
                "reason": "Hold decision with hawkish inflation language.",
            },
        }
        normalized = market_setup_current._normalize_policy_response(
            fomc,
            {"period": "2026-06-01", "status": "expanding"},
            {"period": "2026-06-01", "status": "above_target"},
            {"status": "available"},
            "rising",
        )
        fact = normalized["facts"]["macro_policy_response"]
        assert fact["relationship_to_growth_direction"] == "conflicts"
        assert fact["explanation"]["policy_read"]["policy_action"] == "hold"
        assert fact["explanation"]["policy_read"]["overall_bias"] == "mild_hawkish"

    def test_survey_normalizer_preserves_reasons_and_alignment(self):
        survey = {
            "version": "ism_survey_synthesis_v1",
            "status": "available",
            "period": "2026-06",
            "economic_direction": "aligned_expansion",
            "growth_momentum": "rising",
            "survey_alignment": "aligned",
            "demand_alignment": "aligned_rising",
            "leading_side": "manufacturing",
            "cross_sector_comparison": "both_expanding",
            "expected_gdp_direction": "rising",
            "bias_confirmation": "confirmed",
            "backlog_confirmation": "growing",
            "agreements": ["Manufacturing and Services are both expanding"],
            "conflicts": [],
            "missing_inputs": [],
            "reasons": ["Business surveys indicate broad expansion"],
        }
        normalized = market_setup_current._normalize_expected_growth(survey)
        fact = normalized["facts"]["survey_growth_direction"]
        assert fact["direction"] == "rising"
        assert fact["status"] == "available"
        assert fact["explanation"]["reasons"] == [
            "Business surveys indicate broad expansion"
        ]
        assert fact["explanation"]["survey_alignment"] == "aligned"
        assert fact["explanation"]["demand_alignment"] == "aligned_rising"
        assert fact["explanation"]["growth_momentum"] == "rising"
        assert fact["explanation"]["agreements"] == [
            "Manufacturing and Services are both expanding"
        ]

    def test_survey_normalizer_with_none_keeps_no_explanation(self):
        normalized = market_setup_current._normalize_expected_growth(None)
        assert normalized is None

    def test_financial_normalizer_preserves_state_reasons_and_details(self):
        rates = {
            "as_of": "2026-06-01",
            "derived": {
                "curve_status": "inverted",
                "credit_conditions_status": "stress",
                "vix": 30.0,
                "ten_year_real_rate": 1.2,
            },
        }
        normalized = market_setup_current._normalize_financial_conditions(
            rates, "rising"
        )
        fact = normalized["facts"]["macro_financial_conditions"]
        assert fact["relationship_to_growth_direction"] == "conflicts"
        assert fact["explanation"]["state"] == "confirms_contraction_risk"
        assert fact["explanation"]["growth_confirmation"] == "not_confirmed"
        assert fact["explanation"]["reasons"]
        assert fact["explanation"]["details"]["curve_status"] == "inverted"
        assert fact["explanation"]["details"]["credit_conditions_status"] == "stress"
        assert fact["explanation"]["details"]["vix"] == 30.0
        assert fact["explanation"]["details"]["ten_year_real_rate"] == 1.2

    def test_consumer_normalizer_preserves_state_reason_percentile_momentum(self):
        summary = {
            "method_version": 2,
            "data_status": "aligned_period",
            "aligned_month": "2026-06-01",
            "primary_signal": {
                "series_id": "umcsi_expectations",
                "percentile_zone": "elevated",
                "momentum": "improving",
            },
            "expectations": {
                "percentile_rank": 91.25,
                "percentile_label": "91st percentile",
            },
            "confirmation": {"state": "broadly_confirmed"},
        }
        normalized = market_setup_current._normalize_consumer_demand(summary, "rising")
        fact = normalized["facts"]["consumer_demand_outlook"]
        assert fact["relationship_to_growth_direction"] == "supports"
        assert fact["explanation"]["state"] == "confirms_expansion"
        assert fact["explanation"]["direction"] == "expansion"
        assert fact["explanation"]["reason"]
        assert fact["explanation"]["percentile_zone"] == "elevated"
        assert fact["explanation"]["momentum"] == "improving"
        assert fact["explanation"]["percentile_label"] == "91st percentile"
        assert fact["explanation"]["confirmation_state"] == "broadly_confirmed"

    def test_market_phase_normalizer_preserves_reason_and_starting_posture(self):
        payload = {
            "markets": [
                {
                    "benchmark_id": "us_sp500",
                    "title": "S&P 500",
                    "region": "US",
                    "data_through": "2026-06-01",
                    "latest": {"market_phase_status": "bull_market"},
                }
            ]
        }
        normalized = market_setup_current._normalize_market_environment(payload)
        fact = normalized["facts"]["sp500_market_phase"]
        assert fact["phase"] == "bull_market"
        assert fact["explanation"]["state"] == "bull_market"
        assert fact["explanation"]["starting_posture"] == "long"
        assert fact["explanation"]["reason"]

    def test_credit_vix_m2_normalizers_preserve_current_context(self):
        rates = {
            "as_of": "2026-06-01",
            "derived": {
                "curve_status": "inverted",
                "credit_conditions_status": "stress",
                "vix": 30.0,
                "ten_year_real_rate": 1.2,
            },
        }
        financial = market_setup_current._normalize_financial_conditions(
            rates, "rising"
        )
        credit = financial["facts"]["credit_conditions"]
        assert credit["status"] == "stress"
        assert credit["explanation"]["status"] == "stress"
        vix = financial["facts"]["vix_level"]
        assert vix["level"] == 30.0
        assert vix["explanation"]["level"] == 30.0

        fomc = {"period": "2026-07-28", "latest_tone": {"marker_tone": "hawkish"}}
        policy = market_setup_current._normalize_policy_response(
            fomc,
            {
                "period": "2026-06-01",
                "status": "expanding",
                "status_label": "Expanding",
            },
            {"period": "2026-06-01", "status": "near_target"},
            {"status": "available"},
            "rising",
        )
        m2 = policy["facts"]["m2_liquidity"]
        assert m2["status"] == "expanding"
        assert m2["explanation"]["status"] == "expanding"
        assert m2["explanation"]["status_label"] == "Expanding"
