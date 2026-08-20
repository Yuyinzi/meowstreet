import datetime

import pytest

from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dashboard_cache():
    from app.routers import macro_dashboard as macro_dashboard_router

    macro_dashboard_router._DASHBOARD_CACHE.clear()
    yield
    macro_dashboard_router._DASHBOARD_CACHE.clear()


def _market_setup_payload():
    payload = client.get("/api/macro-dashboard/market-setup").json()
    payload.pop("generated_at", None)
    return payload


def _decision_snapshot(payload):
    return {
        "macro_regime.code": payload["macro_regime"]["code"],
        "market_confirmation.code": payload["market_confirmation"]["code"],
        "market_confirmation.confirmation_test_count": payload["market_confirmation"][
            "confirmation_test_count"
        ],
        "market_setup.code": payload["market_setup"]["code"],
        "market_setup.agreement": payload["market_setup"]["agreement"],
        "portfolio_posture.code": payload["portfolio_posture"]["code"],
        "missing_inputs": payload["missing_inputs"],
        "next_triggers": payload["next_triggers"],
    }


def _present_display_only_inputs(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        lambda con, params, as_of: {
            "claims_confirmation": {
                "initial_claims": {
                    "classification": "stable",
                    "observation_period": "2026-07-25",
                    "latest_4w_mean": 240000.0,
                },
                "continuing_claims": {
                    "classification": "stable",
                    "observation_period": "2026-07-25",
                    "latest_4w_mean": 1900000.0,
                },
                "claims_direction": "stable",
                "confirmation_status": "not_confirming",
            },
            "labor_context": {
                "role": "context_only",
                "method_status": "pending_approval",
                "data_status": "available",
                "metrics": {},
            },
        },
    )
    monkeypatch.setattr(
        macro_dashboard_router.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        macro_dashboard_router.tool,
        "build_cyclical_commodities_payload",
        lambda *args, **kwargs: {"cot": {}},
    )
    monkeypatch.setattr(
        macro_dashboard_router.nfib_sbo,
        "build_nfib_sbo_signal",
        lambda observations, survey_synthesis, as_of: {"status": "ok"},
    )


def _absent_display_only_inputs(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    def raise_on_call(*args, **kwargs):
        raise RuntimeError("display-only input absent")

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        raise_on_call,
    )
    monkeypatch.setattr(
        macro_dashboard_router.macro_indicators_db,
        "load_cot_observations",
        raise_on_call,
    )
    monkeypatch.setattr(
        macro_dashboard_router.nfib_sbo,
        "build_nfib_sbo_signal",
        lambda observations, survey_synthesis, as_of: None,
    )


def test_market_setup_payload_declares_loaded_display_only_evidence_as_excluded(
    monkeypatch,
):
    _present_display_only_inputs(monkeypatch)

    payload = client.get("/api/macro-dashboard/market-setup").json()

    excluded = set(payload["excluded_inputs"])
    assert {
        "economic_confirmation",
        "cyclical_commodities",
        "nfib_regional_evidence",
    } <= excluded


def test_market_setup_payload_includes_equity_breadth_and_jobless_claims_watch_items(
    monkeypatch,
):
    _present_display_only_inputs(monkeypatch)

    payload = client.get("/api/macro-dashboard/market-setup").json()

    watch_ids = {item["id"] for item in payload["watch_items"]}
    assert "equity_breadth" in watch_ids
    assert "jobless_claims" in watch_ids
    for item in payload["watch_items"]:
        if item["id"] in ("equity_breadth", "jobless_claims"):
            assert item["decision_effect"] == "none"
            assert "condition_ref" not in item


def test_display_only_inputs_do_not_change_decision_outputs(monkeypatch):
    _present_display_only_inputs(monkeypatch)
    with_payload = client.get("/api/macro-dashboard/market-setup").json()
    _absent_display_only_inputs(monkeypatch)
    without_payload = client.get("/api/macro-dashboard/market-setup").json()

    assert _decision_snapshot(with_payload) == _decision_snapshot(without_payload)


class _FakeCursor:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeConStubs:
    def close(self):
        pass

    def executescript(self, script):
        pass

    def execute(self, sql, params=None):
        return _FakeCursor()

    def commit(self):
        pass


def test_macro_dashboard_page_routes_are_served():
    response = client.get("/macro-dashboard.html")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_cyclical_commodities_script_is_served():
    response = client.get("/cyclical-commodities-ui.js")

    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]


def test_commodity_ids_keep_the_dce_iron_ore_id():
    from app import api

    assert "iron_ore_dce" in api.method_COMMODITY_SERIES_IDS


def test_commodity_ids_use_investing_copper():
    from app import api

    assert "copper_comex" in api.method_COMMODITY_SERIES_IDS
    assert "copper_lme" in api.method_COMMODITY_SERIES_IDS
    assert "copper_comex_hg_yahoo_v1" not in api.method_COMMODITY_SERIES_IDS
    assert "copper_lme_sina_cad_v1" not in api.method_COMMODITY_SERIES_IDS


def test_growth_cycle_ism_industry_breadth_prefers_latest_official_report(monkeypatch):
    from app import api

    con = object()
    report = {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "source_url": "https://example.com/june",
    }
    html = """
    <h1>June 2026 ISM Manufacturing PMI Report</h1>
    <p>The 14 manufacturing industries reporting growth in June — listed in order — are:
    Printing & Related Support Activities; Electrical Equipment, Appliances & Components;
    and Food, Beverage & Tobacco Products. The three industries in contraction are:
    Paper Products; Furniture & Related Products; and Wood Products.</p>
    """

    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda db: report,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_source_snapshot",
        lambda db, source_url: {
            "source_name": "ismworld",
            "raw_html": html,
        },
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda db: [
            {
                "date": "2020-12-01",
                "industry": "Apparel, Leather & Allied Products",
                "direction": "growth",
                "rank": 16,
                "source": "ISM_Manufacturing_Index.xlsx",
            }
        ],
    )

    summary = api._load_latest_ism_industry_breadth(con)

    assert summary["date"] == "2026-06-01"
    assert summary["growth_count"] == 3
    assert summary["contraction_count"] == 3
    assert summary["top_growth"][0] == {
        "industry": "Printing & Related Support Activities",
        "rank": 3,
    }


def test_growth_cycle_ism_industry_breadth_falls_back_to_workbook(monkeypatch):
    from app import api

    con = object()
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda db: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda db: [
            {
                "date": "2020-12-01",
                "industry": "Apparel, Leather & Allied Products",
                "direction": "growth",
                "rank": 16,
                "source": "ISM_Manufacturing_Index.xlsx",
            }
        ],
    )

    summary = api._load_latest_ism_industry_breadth(con)

    assert summary["date"] == "2020-12-01"
    assert summary["top_growth"] == [
        {"industry": "Apparel, Leather & Allied Products", "rank": 16}
    ]


def test_market_phase_api_returns_lightweight_market_overview(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection(_FakeConStubs):
            pass

        return FakeConnection()

    def fake_load_price_rows(con, benchmark_id):
        assert con is not None
        if benchmark_id != "us_sp500":
            return []
        return [
            {
                "date": "2020-01-01",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            },
            {
                "date": "2020-01-02",
                "open": 79.0,
                "high": 79.0,
                "low": 79.0,
                "close": 79.0,
            },
        ]

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", fake_load_price_rows
    )

    response = client.get("/api/macro-dashboard/market-phase")

    assert response.status_code == 200
    payload = response.json()
    assert payload["markets"][0]["benchmark_id"] == "us_sp500"
    assert payload["markets"][0]["latest"]["market_phase_status"] == "bear_market"
    assert "series" not in payload["markets"][0]


def test_market_phase_detail_api_returns_one_chart_series(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection(_FakeConStubs):
            pass

        return FakeConnection()

    def fake_load_price_rows(con, benchmark_id):
        assert con is not None
        assert benchmark_id == "us_sp500"
        return [
            {
                "date": "2020-01-01",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            },
            {
                "date": "2020-01-02",
                "open": 79.0,
                "high": 79.0,
                "low": 79.0,
                "close": 79.0,
            },
        ]

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", fake_load_price_rows
    )

    response = client.get("/api/macro-dashboard/market-phase/us_sp500")

    assert response.status_code == 200
    payload = response.json()
    assert payload["benchmark_id"] == "us_sp500"
    assert payload["latest"]["market_phase_status"] == "bear_market"
    assert len(payload["series"]) == 2


def test_market_phase_detail_api_returns_400_for_unknown_benchmark(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection(_FakeConStubs):
            pass

        return FakeConnection()

    def fake_load_price_rows(con, benchmark_id):
        return []

    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_connect)
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", fake_load_price_rows
    )

    response = client.get("/api/macro-dashboard/market-phase/unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "benchmark is unknown: unknown"


def test_market_phase_refresh_api_refreshes_one_benchmark(monkeypatch):
    from app import api

    calls = []

    def fake_refresh_benchmarks(benchmark_ids):
        calls.append(benchmark_ids)
        return [
            {
                "benchmark_id": "us_sp500",
                "symbol": "^GSPC",
                "rows_upserted": 2,
                "latest_date": "2026-07-01",
                "source": "yahoo_finance:^GSPC",
            }
        ]

    monkeypatch.setattr(
        api.benchmark_market_data_tool, "refresh_benchmarks", fake_refresh_benchmarks
    )

    response = client.post("/api/macro-dashboard/market-phase/us_sp500/refresh")

    assert response.status_code == 200
    assert response.json() == {
        "benchmark_id": "us_sp500",
        "symbol": "^GSPC",
        "rows_upserted": 2,
        "latest_date": "2026-07-01",
        "source": "yahoo_finance:^GSPC",
    }
    assert calls == [["us_sp500"]]


def test_market_phase_refresh_api_returns_400_for_refresh_errors(monkeypatch):
    from app import api

    def fake_refresh_benchmarks(benchmark_ids):
        raise ValueError("benchmark refresh is unknown: unknown")

    monkeypatch.setattr(
        api.benchmark_market_data_tool, "refresh_benchmarks", fake_refresh_benchmarks
    )

    response = client.post("/api/macro-dashboard/market-phase/unknown/refresh")

    assert response.status_code == 400
    assert response.json() == {"detail": "benchmark refresh is unknown: unknown"}


def test_us_rates_liquidity_api_returns_dashboard_payload(monkeypatch):
    from app import api

    class FakeConnection(_FakeConStubs):
        pass

    def fake_connect():
        return FakeConnection()

    def fake_load_rate_series(con):
        return [
            {
                "series_id": "treasury_10y",
                "title": "10-Year Treasury",
                "instrument_type": "nominal_treasury",
                "maturity_months": 120,
                "units": "percent",
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
            {
                "series_id": "treasury_2y",
                "title": "2-Year Treasury",
                "instrument_type": "nominal_treasury",
                "maturity_months": 24,
                "units": "percent",
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
        ]

    def fake_load_latest_points(con):
        return [
            {
                "series_id": "treasury_10y",
                "date": "2021-01-03",
                "value": 0.93,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
            {
                "series_id": "treasury_2y",
                "date": "2021-01-03",
                "value": 0.12,
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            },
        ]

    def fake_load_latest_macro_indicator_points(con):
        return [
            {
                "series_id": "cpi_yoy",
                "date": "2021-01-03",
                "value": 1.40,
                "source": "US_P4_Macro_Indicators.csv",
            }
        ]

    def fake_load_rate_points_for_series(con, series_ids):
        return {}

    def fake_load_macro_indicator_points_for_series(con, series_ids):
        if series_ids == [
            "aaa_corporate_yield",
            "bbb_corporate_yield",
            "ccc_corporate_yield",
        ]:
            return {
                series_id: [
                    {
                        "date": "2021-01-07",
                        "value": 2.00,
                        "source": "Corporate_Bond_Indices.xlsm",
                    },
                    {
                        "date": "2023-07-10",
                        "value": 6.00,
                        "source": "BAMLC0A4CBBBEY.csv",
                    },
                ]
                for series_id in series_ids
            }
        return {}

    def fake_load_ai_interpretation(con, scope, snapshot_hash):
        assert scope == "us_credit_conditions"
        return {
            "scope": scope,
            "snapshot_hash": snapshot_hash,
            "as_of": "2026-07-06",
            "prompt_version": "credit-cat-v1",
            "model": "gpt-4.1-mini",
            "tone": "trader_cat",
            "status": "risk_rising",
            "text_en": "Credit risk is rising. BBB is calm, but CCC-BBB is hissing.",
            "text_zh": "信用风险正在上升。BBB还平静，但CCC-BBB已经在发出警告。",
            "metrics_json": "{}",
            "generated_at": "2026-07-08T10:30:00Z",
        }

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", fake_connect)
    monkeypatch.setattr(
        api.us_rates_liquidity_db, "load_rate_series", fake_load_rate_series
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db, "load_latest_points", fake_load_latest_points
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_latest_macro_indicator_points",
        fake_load_latest_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_rate_points_for_series",
        fake_load_rate_points_for_series,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points_for_series",
        fake_load_macro_indicator_points_for_series,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_ai_interpretation",
        fake_load_ai_interpretation,
    )

    response = client.get("/api/macro-dashboard/us-rates-liquidity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of"] == "2021-01-03"
    assert payload["derived"]["tens_twos_spread"] == 0.81
    assert payload["derived"]["cpi_based_real_rate"] == -0.47
    assert payload["credit_coverage"]["has_gap"] is True
    assert payload["credit_coverage"]["gap_start"] == "2021-01-08"
    assert payload["credit_coverage"]["gap_end"] == "2023-07-09"
    assert payload["credit_ai_interpretation"]["tone"] == "trader_cat"
    assert "BBB is calm" in payload["credit_ai_interpretation"]["text_en"]


def test_us_rates_liquidity_detail_api_returns_two_charts(monkeypatch):
    from app import api

    class FakeConnection(_FakeConStubs):
        pass

    def fake_connect():
        return FakeConnection()

    def fake_load_rate_series(con):
        return [
            {
                "series_id": "treasury_10y",
                "title": "10-Year Treasury",
                "instrument_type": "nominal_treasury",
                "maturity_months": 120,
                "units": "percent",
                "source_workbook": "Benchmark_Yields_US.xlsm",
                "source_sheet": "Data",
            }
        ]

    def fake_load_rate_points_for_series(con, series_ids):
        assert series_ids == ["treasury_10y"]
        return {
            "treasury_10y": [
                {
                    "date": "2021-01-03",
                    "value": 0.93,
                    "source_workbook": "Benchmark_Yields_US.xlsm",
                    "source_sheet": "Data",
                }
            ]
        }

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", fake_connect)
    monkeypatch.setattr(
        api.us_rates_liquidity_db, "load_rate_series", fake_load_rate_series
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_rate_points_for_series",
        fake_load_rate_points_for_series,
    )

    response = client.get("/api/macro-dashboard/us-rates-liquidity/treasury_10y")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail_id"] == "treasury_10y"
    assert len(payload["charts"]) == 2


def test_us_rates_liquidity_detail_api_returns_400_for_unknown_detail():
    response = client.get("/api/macro-dashboard/us-rates-liquidity/unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "us rates detail is unknown: unknown"


def test_us_rates_liquidity_curve_detail_api_passes_selected_dates(monkeypatch):
    from app import api

    class FakeConnection(_FakeConStubs):
        pass

    captured = {}

    def fake_connect():
        return FakeConnection()

    def fake_detail_series_ids(detail_id):
        assert detail_id == "yield_curve_shape"
        return ["treasury_10y"]

    def fake_build_detail_payload(detail_id, series_rows, points_by_id, options=None):
        captured["options"] = options
        return {
            "detail_id": detail_id,
            "title": "Yield Curve Shape",
            "source": "Benchmark_Yields_US.xlsm",
            "charts": [],
        }

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", fake_connect)
    monkeypatch.setattr(api.us_rates_liquidity_db, "load_rate_series", lambda con: [])
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_rate_points_for_series",
        lambda con, series_ids: {},
    )
    monkeypatch.setattr(
        api.us_rates_liquidity, "detail_series_ids", fake_detail_series_ids
    )
    monkeypatch.setattr(
        api.us_rates_liquidity, "build_detail_payload", fake_build_detail_payload
    )

    response = client.get(
        "/api/macro-dashboard/us-rates-liquidity/yield_curve_shape"
        "?nominalCurrentDate=2021-01-03&nominalComparisonDate=2020-08-16&realCurrentDate=2021-01-03&realComparisonDate=2020-08-16"
    )

    assert response.status_code == 200
    assert captured["options"] == {
        "nominal_current_date": "2021-01-03",
        "nominal_comparison_date": "2020-08-16",
        "real_current_date": "2021-01-03",
        "real_comparison_date": "2020-08-16",
    }


def test_credit_detail_endpoints_return_active_credit_charts(monkeypatch):
    from app import api

    def fake_detail_series_ids(detail_id):
        return {
            "bbb_credit_spread": ["treasury_10y", "bbb_corporate_yield"],
            "ccc_credit_spread": ["treasury_10y", "ccc_corporate_yield"],
            "ccc_bbb_quality_spread": ["bbb_corporate_yield", "ccc_corporate_yield"],
            "credit_conditions_diagnostics": [
                "treasury_10y",
                "bbb_corporate_yield",
                "ccc_corporate_yield",
            ],
            "credit_risk_regime": [
                "treasury_10y",
                "bbb_corporate_yield",
                "ccc_corporate_yield",
            ],
        }[detail_id]

    def fake_build_detail_payload(detail_id, series_rows, points_by_id, options=None):
        if detail_id in ("credit_conditions_diagnostics", "credit_risk_regime"):
            return {
                "detail_id": detail_id,
                "title": "Credit Conditions",
                "charts": [
                    {
                        "kind": "credit_diagnostics",
                        "title": "Credit Conditions",
                        "status": "weak_credit_warning",
                        "metrics": {},
                        "series": [],
                    }
                ],
            }
        return {
            "detail_id": detail_id,
            "title": detail_id,
            "charts": [
                {
                    "kind": "time_series",
                    "title": detail_id,
                    "keys": [detail_id],
                    "labels": {detail_id: detail_id},
                    "series": [{"date": "2021-01-07", detail_id: 1.23}],
                }
            ],
        }

    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )
    monkeypatch.setattr(api.us_rates_liquidity_db, "load_rate_series", lambda con: [])
    monkeypatch.setattr(
        api.us_rates_liquidity_db, "load_rate_points_for_series", lambda con, sids: {}
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points_for_series",
        lambda con, sids: {},
    )
    monkeypatch.setattr(
        api.us_rates_liquidity, "detail_series_ids", fake_detail_series_ids
    )
    monkeypatch.setattr(
        api.us_rates_liquidity, "build_detail_payload", fake_build_detail_payload
    )

    for detail_id in [
        "bbb_credit_spread",
        "ccc_credit_spread",
        "ccc_bbb_quality_spread",
        "credit_conditions_diagnostics",
        "credit_risk_regime",
    ]:
        response = client.get(f"/api/macro-dashboard/us-rates-liquidity/{detail_id}")
        assert response.status_code == 200, f"Failed for {detail_id}"
        payload = response.json()
        assert payload["charts"][0]["kind"] in {"time_series", "credit_diagnostics"}


def test_growth_cycle_api_returns_m2_money_supply_payload(monkeypatch):
    from app import api

    def fake_load_macro_indicator_points(con, series_id):
        assert hasattr(con, "close")
        if series_id == "core_pce_price_index":
            return []
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return []
        if series_id.startswith("ism_manufacturing_"):
            return []
        if series_id.startswith("ism_services_"):
            return []
        assert series_id == "m2_money_stock"
        return [
            {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
            {"date": "2025-07-01", "value": 101, "source": "m2.xlsx"},
            {"date": "2025-08-01", "value": 102, "source": "m2.xlsx"},
            {"date": "2025-09-01", "value": 103, "source": "m2.xlsx"},
            {"date": "2025-10-01", "value": 104, "source": "m2.xlsx"},
            {"date": "2025-11-01", "value": 105, "source": "m2.xlsx"},
            {"date": "2025-12-01", "value": 106, "source": "m2.xlsx"},
            {"date": "2026-01-01", "value": 107, "source": "m2.xlsx"},
            {"date": "2026-02-01", "value": 108, "source": "m2.xlsx"},
            {"date": "2026-03-01", "value": 109, "source": "m2.xlsx"},
            {"date": "2026-04-01", "value": 110, "source": "m2.xlsx"},
            {"date": "2026-05-01", "value": 111, "source": "m2.xlsx"},
            {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
        ]

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    m2_card = next(
        card for card in payload["headline"] if card["id"] == "m2_money_supply"
    )
    assert m2_card["label"] == "M2 Money Supply"
    assert m2_card["period"] == "2026-06-01"
    assert m2_card["state"]["m2_money_stock"] == 112.0
    assert m2_card["change"]["m2_3m_momentum"] is not None
    assert payload["missing"] is None
    assert "ism_pmi" not in payload["growth_cycle"]


def test_growth_cycle_api_includes_ism_manufacturing_values(monkeypatch):
    from app import api

    ISM_PMI_POINTS = [
        {"date": "2026-05-01", "value": 50.0, "source": "ISM.xlsx"},
        {"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"},
    ]

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "core_pce_price_index":
            return []
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return []
        if series_id == "m2_money_stock":
            return [
                {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2025-07-01", "value": 101, "source": "m2.xlsx"},
                {"date": "2025-08-01", "value": 102, "source": "m2.xlsx"},
                {"date": "2025-09-01", "value": 103, "source": "m2.xlsx"},
                {"date": "2025-10-01", "value": 104, "source": "m2.xlsx"},
                {"date": "2025-11-01", "value": 105, "source": "m2.xlsx"},
                {"date": "2025-12-01", "value": 106, "source": "m2.xlsx"},
                {"date": "2026-01-01", "value": 107, "source": "m2.xlsx"},
                {"date": "2026-02-01", "value": 108, "source": "m2.xlsx"},
                {"date": "2026-03-01", "value": 109, "source": "m2.xlsx"},
                {"date": "2026-04-01", "value": 110, "source": "m2.xlsx"},
                {"date": "2026-05-01", "value": 111, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
            ]
        if series_id == "ism_manufacturing_pmi":
            return ISM_PMI_POINTS
        if series_id == "ism_manufacturing_new_orders":
            return [{"date": "2026-06-01", "value": 52.0, "source": "ISM.xlsx"}]
        if series_id == "ism_manufacturing_customer_inventories":
            return [{"date": "2026-06-01", "value": 47.5, "source": "ISM.xlsx"}]
        if series_id.startswith("ism_manufacturing_"):
            return [{"date": "2026-06-01", "value": 50.0, "source": "ISM.xlsx"}]
        if series_id.startswith("ism_services_"):
            return []
        raise AssertionError(series_id)

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    import app.db.macro_indicators as _macro_indicators

    monkeypatch.setattr(
        _macro_indicators,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    gc = payload["growth_cycle"]
    assert gc["ism_pmi"] == 51.2
    assert gc["ism_new_orders"] == 52.0
    assert gc["ism_customer_inventories"] == 47.5
    assert gc["ism_imports"] == 50.0
    assert gc["ism_period"] == "2026-06-01"
    assert payload["headline"][0]["id"] == "ism_manufacturing"


def test_growth_cycle_api_returns_grouped_sections(monkeypatch):
    from app import api

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2025-07-01", "value": 101, "source": "m2.xlsx"},
                {"date": "2025-08-01", "value": 102, "source": "m2.xlsx"},
                {"date": "2025-09-01", "value": 103, "source": "m2.xlsx"},
                {"date": "2025-10-01", "value": 104, "source": "m2.xlsx"},
                {"date": "2025-11-01", "value": 105, "source": "m2.xlsx"},
                {"date": "2025-12-01", "value": 106, "source": "m2.xlsx"},
                {"date": "2026-01-01", "value": 107, "source": "m2.xlsx"},
                {"date": "2026-02-01", "value": 108, "source": "m2.xlsx"},
                {"date": "2026-03-01", "value": 109, "source": "m2.xlsx"},
                {"date": "2026-04-01", "value": 110, "source": "m2.xlsx"},
                {"date": "2026-05-01", "value": 111, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
            ]
        if series_id == "core_pce_price_index":
            return []
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return []
        if series_id.startswith("ism_manufacturing_"):
            return [{"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"}]
        if series_id.startswith("ism_services_"):
            return []
        raise AssertionError(series_id)

    class FakeCon(_FakeConStubs):
        pass

    import app.db.macro_indicators as _macro_indicators

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        _macro_indicators,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    sections = response.json()["sections"]
    assert [section["id"] for section in sections] == [
        "ism_manufacturing",
        "ism_services",
        "m2_liquidity",
        "cyclical_commodities_usd",
        "inflation_context",
        "fomc_context",
        "housing_credit",
        "small_business",
    ]
    assert sections[0]["title"] == "ISM Manufacturing"
    assert sections[0]["status"] == "available"
    assert sections[2]["cards"] == ["m2_money_supply"]


def test_growth_cycle_m2_detail_api_returns_chart_payload(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    rows = [
        {"date": "2025-01-01", "value": 100.0, "source": "m2.xlsx"},
        {"date": "2025-02-01", "value": 101.0, "source": "m2.xlsx"},
        {"date": "2025-03-01", "value": 102.0, "source": "m2.xlsx"},
        {"date": "2025-04-01", "value": 103.0, "source": "m2.xlsx"},
        {"date": "2025-05-01", "value": 104.0, "source": "m2.xlsx"},
        {"date": "2025-06-01", "value": 105.0, "source": "m2.xlsx"},
        {"date": "2025-07-01", "value": 106.0, "source": "m2.xlsx"},
        {"date": "2025-08-01", "value": 107.0, "source": "m2.xlsx"},
        {"date": "2025-09-01", "value": 108.0, "source": "m2.xlsx"},
        {"date": "2025-10-01", "value": 109.0, "source": "m2.xlsx"},
        {"date": "2025-11-01", "value": 110.0, "source": "m2.xlsx"},
        {"date": "2025-12-01", "value": 111.0, "source": "m2.xlsx"},
        {"date": "2026-01-01", "value": 125.0, "source": "m2.xlsx"},
    ]

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())

    def fake_load(con, series_id):
        if series_id == "core_pce_price_index":
            return []
        return rows

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_ai_interpretation",
        lambda con, scope, snapshot_hash: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_events_with_latest_tone",
        lambda con, event_type: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle/m2_money_supply")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail_id"] == "m2_money_supply"
    assert payload["title"] == "M2 Money Supply"
    assert len(payload["charts"]) == 5
    assert payload["charts"][0]["kind"] == "time_series"
    assert payload["m2_ai_interpretation"]["text_en"] is not None
    assert "generator" in payload["m2_ai_interpretation"]["text_en"]


def test_growth_cycle_detail_api_rejects_unknown_detail():
    response = client.get("/api/macro-dashboard/growth-cycle/unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "growth cycle detail is unknown: unknown"


def test_growth_cycle_sections_include_small_business_with_nfib_card(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_points(con, series_id):
        if series_id == "m2_money_stock":
            return [{"date": "2026-06-01", "value": 100, "source": "m2.xlsx"}]
        if series_id.startswith("ism_manufacturing_"):
            return [{"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"}]
        return []

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda *a: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda *a: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    sections = response.json()["sections"]
    sb = next((s for s in sections if s["id"] == "small_business"), None)
    assert sb is not None, "small_business section missing"
    assert "nfib_sbo" in sb.get("cards", []), (
        f"nfib_sbo card not in small_business section: {sb}"
    )


def test_growth_cycle_nfib_card_appears_in_headline(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [{"date": "2026-06-01", "value": 100, "source": "m2.xlsx"}]
        return []

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    nfib_card = next(
        item for item in response.json()["headline"] if item["id"] == "nfib_sbo"
    )
    assert nfib_card is not None
    assert nfib_card["status"] == "unavailable"


def test_growth_cycle_nfib_detail_includes_regional_evidence(monkeypatch):
    from app import api

    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {sid: [] for sid in series_ids},
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_all_nfib_regional_observations",
        lambda con: [
            {
                "region_id": "pacific",
                "indicator_id": "nfib_sbo_optimism",
                "date": "2026-06-30",
                "value": 95.0,
                "availability": "available",
                "units": "index",
                "title": "Small Business Optimism Index",
                "display_label": "Pacific",
                "api_label": "Pacific",
                "states": "AK, CA, HI, OR, WA",
                "source_url": "https://api.nfib-sbet.org/rest/sbetdb/_proc/getTotals2",
                "procedure_name": "getTotals2",
            },
            {
                "region_id": "pacific",
                "indicator_id": "nfib_sbo_employment_plans",
                "date": "2026-06-30",
                "value": 10.0,
                "availability": "available",
                "units": "net_pct",
                "title": "Plans to Increase Employment",
                "display_label": "Pacific",
                "api_label": "Pacific",
                "states": "AK, CA, HI, OR, WA",
                "source_url": "https://api.nfib-sbet.org/rest/sbetdb/_proc/getTotals2",
                "procedure_name": "getTotals2",
            },
        ],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db, "connect", lambda: type("C", (_FakeConStubs,), {})()
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda *a: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda *a: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = TestClient(api.app).get("/api/macro-dashboard/growth-cycle/nfib_sbo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail_id"] == "nfib_sbo"
    assert "regional_evidence" in payload
    assert payload["regional_evidence"]["regions"][0]["id"] == "pacific"


def test_growth_cycle_nfib_detail_returns_200(monkeypatch):
    from app import api

    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda *a: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda *a: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = TestClient(api.app).get("/api/macro-dashboard/growth-cycle/nfib_sbo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail_id"] == "nfib_sbo"


def test_growth_cycle_m2_detail_api_attaches_stored_ai_interpretation(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    rows = [
        {"date": "2020-01-01", "value": 100.0, "source": "m2.xlsx"},
        {"date": "2020-02-01", "value": 101.0, "source": "m2.xlsx"},
        {"date": "2020-03-01", "value": 102.0, "source": "m2.xlsx"},
        {"date": "2020-04-01", "value": 103.0, "source": "m2.xlsx"},
        {"date": "2020-05-01", "value": 104.0, "source": "m2.xlsx"},
        {"date": "2020-06-01", "value": 105.0, "source": "m2.xlsx"},
        {"date": "2020-07-01", "value": 106.0, "source": "m2.xlsx"},
        {"date": "2020-08-01", "value": 107.0, "source": "m2.xlsx"},
        {"date": "2020-09-01", "value": 108.0, "source": "m2.xlsx"},
        {"date": "2020-10-01", "value": 109.0, "source": "m2.xlsx"},
        {"date": "2020-11-01", "value": 110.0, "source": "m2.xlsx"},
        {"date": "2020-12-01", "value": 111.0, "source": "m2.xlsx"},
        {"date": "2021-01-01", "value": 125.0, "source": "m2.xlsx"},
    ]
    calls = []

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())

    def fake_load(con, series_id):
        if series_id == "core_pce_price_index":
            return []
        return rows

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load,
    )

    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_events_with_latest_tone",
        lambda con, event_type: [],
    )

    def fake_load_ai_interpretation(con, scope, snapshot_hash):
        calls.append((scope, snapshot_hash))
        return {
            "scope": scope,
            "snapshot_hash": snapshot_hash,
            "text_en": "M2 is expanding quickly, so liquidity is a confirmation tailwind.",
            "text_zh": "M2快速扩张，因此流动性是确认性的顺风。",
            "tone": "trader_cat",
            "prompt_version": "m2-cat-v1",
            "model": "gpt-4.1-mini",
            "as_of": "2021-01-01",
        }

    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_ai_interpretation",
        fake_load_ai_interpretation,
    )

    response = client.get("/api/macro-dashboard/growth-cycle/m2_money_supply")

    assert response.status_code == 200
    payload = response.json()
    assert payload["m2_ai_interpretation"]["tone"] == "trader_cat"
    assert (
        "liquidity is a confirmation tailwind"
        in payload["m2_ai_interpretation"]["text_en"]
    )
    assert calls[0][0] == "m2_money_supply"
    assert len(calls[0][1]) == 64


def test_growth_cycle_api_includes_next_fomc_meeting(monkeypatch):
    from app import api

    class FakeConnection(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeConnection())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: (
            [
                {"date": "2025-01-01", "value": 100.0, "source": "m2.csv"},
                {"date": "2025-02-01", "value": 101.0, "source": "m2.csv"},
                {"date": "2025-03-01", "value": 102.0, "source": "m2.csv"},
                {"date": "2025-04-01", "value": 103.0, "source": "m2.csv"},
                {"date": "2025-05-01", "value": 104.0, "source": "m2.csv"},
                {"date": "2025-06-01", "value": 105.0, "source": "m2.csv"},
                {"date": "2025-07-01", "value": 106.0, "source": "m2.csv"},
                {"date": "2025-08-01", "value": 107.0, "source": "m2.csv"},
                {"date": "2025-09-01", "value": 108.0, "source": "m2.csv"},
                {"date": "2025-10-01", "value": 109.0, "source": "m2.csv"},
                {"date": "2025-11-01", "value": 110.0, "source": "m2.csv"},
                {"date": "2025-12-01", "value": 111.0, "source": "m2.csv"},
                {"date": "2026-01-01", "value": 120.0, "source": "m2.csv"},
            ]
            if series_id == "m2_money_stock"
            else []
        ),
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: {
            "event_id": "fomc_2026_07_28",
            "event_type": "fomc_meeting",
            "start_date": "2026-07-28",
            "end_date": "2026-07-29",
            "display_month": "2026-07-01",
            "title": "FOMC Meeting",
            "source": "Federal Reserve",
            "policy_tone": "unknown",
            "has_sep": 0,
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        },
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    card = next(
        item for item in response.json()["headline"] if item["id"] == "fomc_calendar"
    )
    assert card["period"] == "2026-07-28"


def test_growth_cycle_api_returns_dashboard_without_m2_data(
    monkeypatch,
):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["headline"] is not None
    assert payload["growth_cycle"] is not None
    assert payload["missing"] is None


def test_growth_cycle_api_includes_ism_macro_signal_in_gdp(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2026-05-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 101, "source": "m2.xlsx"},
            ]
        if series_id.startswith("ism_manufacturing_"):
            return [{"date": "2026-06-01", "value": 52.0, "source": "ISM.xlsx"}]
        return []

    reports = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "source_url": "https://example.com/june",
            "source_hash": "abc123",
        }
    ]
    at_a_glance = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 52.0,
            "previous_value": 51.5,
            "point_change": 0.5,
        },
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_new_orders",
            "label": "New Orders",
            "current_value": 53.0,
            "previous_value": 52.0,
            "point_change": 1.0,
        },
    ]

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: reports[0],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6: reports,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_at_a_glance_rows_for_reports",
        lambda con, report_ids: at_a_glance,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    survey_card = next(
        card for card in payload["headline"] if card["id"] == "survey_synthesis"
    )
    assert survey_card["status"] == "partial"
    assert survey_card["economic_direction"] is None
    assert survey_card["expected_gdp_direction"] is None
    assert survey_card["survey_portfolio_implication"] is None
    assert survey_card["growth_momentum"] is None
    assert survey_card["components"]["manufacturing"]["status"] == "available"
    assert survey_card["components"]["manufacturing"]["period"] == "2026-06-01"
    ism_card = next(
        card for card in payload["headline"] if card["id"] == "ism_manufacturing"
    )
    assert ism_card["policy_context"]["growth_pressure"] == "less_easing_pressure"
    assert not any(card["id"] == "fomc_tone" for card in payload["headline"])


def test_growth_cycle_api_propagates_source_url_and_hash(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2026-05-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 101, "source": "m2.xlsx"},
            ]
        if series_id.startswith("ism_manufacturing_"):
            return [{"date": "2026-06-01", "value": 52.0, "source": "ISM.xlsx"}]
        return []

    reports = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "source_url": "https://example.com/june",
            "source_hash": "abc123",
        }
    ]
    at_a_glance = [
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_pmi",
            "label": "Manufacturing PMI",
            "current_value": 52.0,
            "previous_value": 51.5,
            "point_change": 0.5,
        },
        {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
            "series_id": "ism_manufacturing_new_orders",
            "label": "New Orders",
            "current_value": 53.0,
            "previous_value": 52.0,
            "point_change": 1.0,
        },
    ]

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: reports[0],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6: reports,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_at_a_glance_rows_for_reports",
        lambda con, report_ids: at_a_glance,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    survey_card = next(
        card for card in payload["headline"] if card["id"] == "survey_synthesis"
    )
    assert survey_card["components"]["manufacturing"]["period"] == "2026-06-01"
    assert (
        payload["growth_cycle"]["survey_synthesis"]["version"]
        == "ism_survey_synthesis_v1"
    )


def test_growth_cycle_api_handles_no_ism_reports_gracefully(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2026-05-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 101, "source": "m2.xlsx"},
            ]
        return []

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    survey_card = next(
        card for card in payload["headline"] if card["id"] == "survey_synthesis"
    )
    assert survey_card["status"] == "partial"
    assert survey_card["components"]["manufacturing"]["status"] == "unavailable"
    assert survey_card["components"]["services"]["status"] == "unavailable"


def test_growth_cycle_api_returns_inflation_context_card(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2025-07-01", "value": 101, "source": "m2.xlsx"},
                {"date": "2025-08-01", "value": 102, "source": "m2.xlsx"},
                {"date": "2025-09-01", "value": 103, "source": "m2.xlsx"},
                {"date": "2025-10-01", "value": 104, "source": "m2.xlsx"},
                {"date": "2025-11-01", "value": 105, "source": "m2.xlsx"},
                {"date": "2025-12-01", "value": 106, "source": "m2.xlsx"},
                {"date": "2026-01-01", "value": 107, "source": "m2.xlsx"},
                {"date": "2026-02-01", "value": 108, "source": "m2.xlsx"},
                {"date": "2026-03-01", "value": 109, "source": "m2.xlsx"},
                {"date": "2026-04-01", "value": 110, "source": "m2.xlsx"},
                {"date": "2026-05-01", "value": 111, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
            ]
        if series_id == "core_pce_price_index":
            return [
                {"date": "2025-06-01", "value": 130.0, "source": "FRED monthly"},
                {"date": "2025-07-01", "value": 130.2, "source": "FRED monthly"},
                {"date": "2025-08-01", "value": 130.4, "source": "FRED monthly"},
                {"date": "2025-09-01", "value": 130.6, "source": "FRED monthly"},
                {"date": "2025-10-01", "value": 130.8, "source": "FRED monthly"},
                {"date": "2025-11-01", "value": 131.0, "source": "FRED monthly"},
                {"date": "2025-12-01", "value": 131.2, "source": "FRED monthly"},
                {"date": "2026-01-01", "value": 131.4, "source": "FRED monthly"},
                {"date": "2026-02-01", "value": 131.6, "source": "FRED monthly"},
                {"date": "2026-03-01", "value": 131.8, "source": "FRED monthly"},
                {"date": "2026-04-01", "value": 132.0, "source": "FRED monthly"},
                {"date": "2026-05-01", "value": 132.2, "source": "FRED monthly"},
                {"date": "2026-06-01", "value": 134.0, "source": "FRED monthly"},
            ]
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return [
                {
                    "date": f"2026-{index + 1:02d}-01",
                    "value": 6000000.0 + index * 1000,
                    "source": "FRED weekly",
                }
                for index in range(53)
            ]
        if series_id.startswith("ism_manufacturing_"):
            return []
        if series_id.startswith("ism_services_"):
            return []
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    card_ids = [card["id"] for card in payload["headline"]]
    assert card_ids == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_supply",
        "inflation_context",
        "fed_balance_sheet",
        "survey_synthesis",
        "housing_permits",
        "nfib_sbo",
        "cyclical_commodities",
    ]
    inflation = payload["headline"][3]
    assert inflation["label"] == "Inflation Context"
    assert inflation["status"] == "above_target"
    assert round(inflation["core_pce_yoy"], 4) == 0.0308
    assert round(inflation["gap"], 4) == 0.0108
    fed_card = next(
        card for card in payload["headline"] if card["id"] == "fed_balance_sheet"
    )
    assert fed_card["label"] == "Fed Balance Sheet"
    assert fed_card["status"] == "context"
    survey_card = next(
        card for card in payload["headline"] if card["id"] == "survey_synthesis"
    )
    assert survey_card["label"] == "Survey Synthesis"
    assert survey_card["status"] == "partial"
    assert survey_card["expected_gdp_direction"] is None


def test_growth_cycle_api_keeps_m2_when_inflation_context_is_missing(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2025-07-01", "value": 101, "source": "m2.xlsx"},
                {"date": "2025-08-01", "value": 102, "source": "m2.xlsx"},
                {"date": "2025-09-01", "value": 103, "source": "m2.xlsx"},
                {"date": "2025-10-01", "value": 104, "source": "m2.xlsx"},
                {"date": "2025-11-01", "value": 105, "source": "m2.xlsx"},
                {"date": "2025-12-01", "value": 106, "source": "m2.xlsx"},
                {"date": "2026-01-01", "value": 107, "source": "m2.xlsx"},
                {"date": "2026-02-01", "value": 108, "source": "m2.xlsx"},
                {"date": "2026-03-01", "value": 109, "source": "m2.xlsx"},
                {"date": "2026-04-01", "value": 110, "source": "m2.xlsx"},
                {"date": "2026-05-01", "value": 111, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
            ]
        if series_id == "core_pce_price_index":
            return []
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return []
        if series_id.startswith("ism_manufacturing_"):
            return []
        if series_id.startswith("ism_services_"):
            return []
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    assert [card["id"] for card in response.json()["headline"]] == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_supply",
        "survey_synthesis",
        "housing_permits",
        "nfib_sbo",
        "cyclical_commodities",
    ]


def test_growth_cycle_api_returns_fed_balance_sheet_card(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def rows(start_value, count=53):
        return [
            {
                "date": f"2026-{index + 1:02d}-01",
                "value": start_value + index * 1000,
                "source": "FRED weekly",
            }
            for index in range(count)
        ]

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return rows(100, 13)
        if series_id == "core_pce_price_index":
            return []
        if series_id == "fed_total_assets":
            return rows(6000000, 53)
        if series_id == "fed_treasury_holdings":
            return rows(4200000, 53)
        if series_id == "fed_mbs_holdings":
            return rows(2200000, 53)
        if series_id.startswith("ism_manufacturing_"):
            return []
        if series_id.startswith("ism_services_"):
            return []
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date, *a: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    cards = response.json()["headline"]
    assert [card["id"] for card in cards] == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_supply",
        "fed_balance_sheet",
        "survey_synthesis",
        "housing_permits",
        "nfib_sbo",
        "cyclical_commodities",
    ]
    fed_card = next(card for card in cards if card["id"] == "fed_balance_sheet")
    assert fed_card["status"] == "context"
    assert fed_card["total_assets"] == 6052000


def test_growth_cycle_m2_detail_api_includes_core_pce_comparison(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def rows(start_value):
        return [
            {"date": "2025-01-01", "value": start_value + 0, "source": "FRED"},
            {"date": "2025-02-01", "value": start_value + 1, "source": "FRED"},
            {"date": "2025-03-01", "value": start_value + 2, "source": "FRED"},
            {"date": "2025-04-01", "value": start_value + 3, "source": "FRED"},
            {"date": "2025-05-01", "value": start_value + 4, "source": "FRED"},
            {"date": "2025-06-01", "value": start_value + 5, "source": "FRED"},
            {"date": "2025-07-01", "value": start_value + 6, "source": "FRED"},
            {"date": "2025-08-01", "value": start_value + 7, "source": "FRED"},
            {"date": "2025-09-01", "value": start_value + 8, "source": "FRED"},
            {"date": "2025-10-01", "value": start_value + 9, "source": "FRED"},
            {"date": "2025-11-01", "value": start_value + 10, "source": "FRED"},
            {"date": "2025-12-01", "value": start_value + 11, "source": "FRED"},
            {"date": "2026-01-01", "value": start_value + 25, "source": "FRED"},
        ]

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return rows(100)
        if series_id == "core_pce_price_index":
            return rows(130)
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return rows(100)
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_ai_interpretation",
        lambda con, scope, snapshot_hash: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_events_with_latest_tone",
        lambda con, event_type: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle/m2_money_supply")

    assert response.status_code == 200
    chart = response.json()["charts"][0]
    assert chart["title"] == "M2 YoY Growth vs Inflation Constraint"
    assert chart["keys"] == [
        "m2_yoy",
        "core_pce_yoy",
        "fed_target",
    ]
    fed_chart = response.json()["charts"][1]
    assert fed_chart["title"] == "Fed Total Assets YoY"
    assert fed_chart["keys"] == ["fed_total_assets_yoy"]


def test_growth_cycle_api_includes_fomc_tone_card(monkeypatch):
    from app import api

    class FakeConnection(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeConnection())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: (
            [
                {"date": "2025-01-01", "value": 100.0, "source": "m2.csv"},
                {"date": "2025-02-01", "value": 101.0, "source": "m2.csv"},
                {"date": "2025-03-01", "value": 102.0, "source": "m2.csv"},
                {"date": "2025-04-01", "value": 103.0, "source": "m2.csv"},
                {"date": "2025-05-01", "value": 104.0, "source": "m2.csv"},
                {"date": "2025-06-01", "value": 105.0, "source": "m2.csv"},
                {"date": "2025-07-01", "value": 106.0, "source": "m2.csv"},
                {"date": "2025-08-01", "value": 107.0, "source": "m2.csv"},
                {"date": "2025-09-01", "value": 108.0, "source": "m2.csv"},
                {"date": "2025-10-01", "value": 109.0, "source": "m2.csv"},
                {"date": "2025-11-01", "value": 110.0, "source": "m2.csv"},
                {"date": "2025-12-01", "value": 111.0, "source": "m2.csv"},
                {"date": "2026-01-01", "value": 120.0, "source": "m2.csv"},
            ]
            if series_id == "m2_money_stock"
            else []
        ),
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: {
            "event_id": "fomc_2026_06_16",
            "start_date": "2026-06-16",
            "end_date": "2026-06-17",
            "source_hash": "abc123",
            "marker_tone": "hawkish",
            "policy_action": "hold",
            "guidance_bias": "neutral",
            "language_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "tone_change": "more_hawkish",
            "confidence": "high",
            "reason": "Inflation language became firmer.",
        },
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    tone_card = next(
        item for item in response.json()["headline"] if item["id"] == "fomc_tone"
    )
    assert tone_card["label"] == "FOMC Policy Read"
    assert tone_card["latest_tone"]["marker_tone"] == "hawkish"
    assert tone_card["latest_tone"]["policy_action"] == "hold"
    assert tone_card["latest_tone"]["overall_bias"] == "mild_hawkish"
    assert tone_card["latest_tone"]["tone_change"] == "more_hawkish"


def test_growth_cycle_api_returns_ism_overview_cards_in_ism_section(monkeypatch):
    from app import api

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
            ]
        if series_id == "core_pce_price_index":
            return []
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return []
        values = {
            "ism_manufacturing_pmi": 51.2,
            "ism_manufacturing_new_orders": 52.0,
            "ism_manufacturing_production": 50.4,
            "ism_manufacturing_employment": 49.8,
            "ism_manufacturing_supplier_deliveries": 50.1,
            "ism_manufacturing_inventories": 48.6,
            "ism_manufacturing_customer_inventories": 47.5,
            "ism_manufacturing_prices": 55.3,
            "ism_manufacturing_order_backlog": 49.0,
            "ism_manufacturing_exports": 51.8,
            "ism_manufacturing_imports": 50.2,
        }
        if series_id in values:
            return [
                {"date": "2026-06-01", "value": values[series_id], "source": "ISM.xlsx"}
            ]
        if series_id.startswith("ism_services_"):
            return []
        raise AssertionError(series_id)

    class FakeCon(_FakeConStubs):
        pass

    import app.db.macro_indicators as _macro_indicators

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        _macro_indicators,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    cards = {card["id"]: card for card in payload["headline"]}
    sections = {section["id"]: section for section in payload["sections"]}
    assert sections["ism_manufacturing"]["cards"] == ["ism_manufacturing"]
    assert cards["ism_manufacturing"]["pmi"] == 51.2
    assert (
        cards["ism_manufacturing"]["segments"]["growth_drivers"]["above_50_count"] == 4
    )
    assert cards["ism_manufacturing"]["segments"]["inflation_supply"]["prices"] == 55.3
    assert (
        cards["ism_manufacturing"]["segments"]["industry_breadth"]["status"]
        == "pending_inputs"
    )


def test_growth_cycle_api_returns_ism_manufacturing_detail(monkeypatch):
    from app import api

    calls = []

    def fake_connect():
        class FakeConnection(_FakeConStubs):
            def close(self):
                calls.append(("close",))

        return FakeConnection()

    def fake_gdp_connect():
        class FakeConnection(_FakeConStubs):
            def close(self):
                calls.append(("gdp_close",))

        return FakeConnection()

    def fake_benchmark_connect():
        class FakeConnection(_FakeConStubs):
            def close(self):
                calls.append(("benchmark_close",))

        return FakeConnection()

    def fake_load_macro_indicator_points_for_series(con, series_ids):
        calls.append(("series", tuple(series_ids)))
        return {
            "ism_manufacturing_pmi": [
                {"date": "2025-10-01", "value": 48.0, "source": "workbook"},
                {"date": "2025-11-01", "value": 48.5, "source": "workbook"},
                {"date": "2025-12-01", "value": 49.0, "source": "workbook"},
                {"date": "2026-01-01", "value": 50.0, "source": "workbook"},
                {"date": "2026-02-01", "value": 51.0, "source": "workbook"},
                {"date": "2026-03-01", "value": 52.0, "source": "workbook"},
                {"date": "2026-05-01", "value": 51.4, "source": "workbook"},
            ],
            "ism_manufacturing_new_orders": [
                {"date": "2026-05-01", "value": 53.2, "source": "workbook"}
            ],
            "ism_manufacturing_production": [
                {"date": "2026-05-01", "value": 52.0, "source": "workbook"}
            ],
            "ism_manufacturing_employment": [
                {"date": "2026-05-01", "value": 48.8, "source": "workbook"}
            ],
            "ism_manufacturing_order_backlog": [
                {"date": "2026-05-01", "value": 47.9, "source": "workbook"}
            ],
            "ism_manufacturing_exports": [
                {"date": "2026-05-01", "value": 51.1, "source": "workbook"}
            ],
            "ism_manufacturing_imports": [
                {"date": "2026-05-01", "value": 49.5, "source": "workbook"}
            ],
            "ism_manufacturing_prices": [
                {"date": "2026-05-01", "value": 56.4, "source": "workbook"}
            ],
            "ism_manufacturing_supplier_deliveries": [
                {"date": "2026-05-01", "value": 50.6, "source": "workbook"}
            ],
            "ism_manufacturing_inventories": [
                {"date": "2026-05-01", "value": 46.8, "source": "workbook"}
            ],
            "ism_manufacturing_customer_inventories": [
                {"date": "2026-05-01", "value": 44.9, "source": "workbook"}
            ],
        }

    def fake_load_quad_rows(con, relationship_id):
        calls.append(("gdp_level_rows", relationship_id))
        return [
            {"date": "2025-09-30", "gdp_level": 100.0, "index_level": 5000.0},
            {"date": "2025-12-31", "gdp_level": 99.0, "index_level": 5100.0},
            {"date": "2026-03-31", "gdp_level": 95.0, "index_level": 5200.0},
        ]

    def fake_load_price_rows(con, benchmark_id):
        calls.append(("benchmark_prices", benchmark_id))
        return [
            {"date": "2026-01-31", "close": 5000.0},
            {"date": "2026-02-28", "close": 5100.0},
            {"date": "2026-03-31", "close": 5300.0},
        ]

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", fake_connect)
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points_for_series",
        fake_load_macro_indicator_points_for_series,
    )
    monkeypatch.setattr(api.gdp_market_relationships, "connect", fake_gdp_connect)
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "load_quad_rows",
        fake_load_quad_rows,
    )
    monkeypatch.setattr(api.benchmark_market_data, "connect", fake_benchmark_connect)
    monkeypatch.setattr(
        api.benchmark_market_data,
        "load_price_rows",
        fake_load_price_rows,
    )

    def fake_latest_rankings(con):
        return [
            {
                "date": "2026-05-01",
                "industry": "Computer & Electronic Products",
                "direction": "growth",
                "rank": 16,
                "source": "ISM_Manufacturing_Index.xlsx",
            },
            {
                "date": "2026-05-01",
                "industry": "Machinery",
                "direction": "contraction",
                "rank": -1,
                "source": "ISM_Manufacturing_Index.xlsx",
            },
        ]

    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        fake_latest_rankings,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    response = client.get("/api/macro-dashboard/growth-cycle/ism_manufacturing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail_id"] == "ism_manufacturing"
    assert [chart["id"] for chart in payload["charts"]] == [
        "ism_manufacturing_heat_map",
        "ism_macro_context",
    ]
    assert payload["charts"][1]["kind"] == "small_multiples"
    assert len(payload["charts"][0]["keys"]) == 11
    assert "pmi" in payload["latest"]
    assert "new_orders" in payload["latest"]
    assert payload["latest"]["pmi"] == 51.4
    assert len(payload["detail_groups"]) == 4
    assert payload["detail_groups"][3]["label"] == "Industry Breadth"
    assert payload["detail_groups"][3]["industry_breadth"]["growth_count"] == 1
    assert payload["detail_groups"][3]["industry_breadth"]["contraction_count"] == 1
    assert calls[0] == ("series", tuple(api.ISM_MANUFACTURING_SERIES_IDS))
    assert ("gdp_level_rows", "us_sp500_gdp") in calls
    assert ("benchmark_prices", "us_sp500") in calls
    assert ("gdp_close",) in calls
    assert ("benchmark_close",) in calls
    assert calls[-1] == ("close",)


def test_growth_cycle_api_ism_detail_includes_industry_analysis(monkeypatch):
    from app import api

    def fake_connect():
        return _FakeConStubs()

    def fake_load_macro_indicator_points_for_series(con, series_ids):
        return {
            "ism_manufacturing_pmi": [
                {"date": "2026-06-01", "value": 52.6, "source": "test"}
            ],
        }

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", fake_connect)
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points_for_series",
        fake_load_macro_indicator_points_for_series,
    )
    monkeypatch.setattr(
        api.gdp_market_relationships, "connect", lambda: _FakeConStubs()
    )
    monkeypatch.setattr(api.benchmark_market_data, "connect", lambda: _FakeConStubs())
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_quad_rows", lambda con, rid: []
    )
    monkeypatch.setattr(
        api.benchmark_market_data, "load_price_rows", lambda con, bid: []
    )
    monkeypatch.setattr(
        api.growth_cycle, "load_latest_ism_industry_rankings", lambda con: []
    )
    monkeypatch.setattr(
        api.growth_cycle, "load_latest_ism_at_a_glance_rows", lambda con: []
    )

    report = {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 Report",
        "source_url": "https://example.com/june-2026",
        "source_name": "ismworld",
    }

    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: report,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_source_snapshot",
        lambda con, url: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signals",
        lambda con, rid: _default_signals(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signal_coverage",
        lambda con, rid: _default_coverage(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_at_a_glance_rows",
        lambda con, rid: _default_at_a_glance(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_comments",
        lambda con, rid: _default_comments(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6: [report],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signals_for_reports",
        lambda con, rids: _default_signals(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signal_coverage_for_reports",
        lambda con, rids: [
            {**c, "report_id": rids[0], "report_month": "2026-06-01"}
            for c in _default_coverage()
        ],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_at_a_glance_rows_for_reports",
        lambda con, rids: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle/ism_manufacturing")

    assert response.status_code == 200
    payload = response.json()
    assert "industry_analysis" in payload
    ia = payload["industry_analysis"]
    assert ia["status"] == "available"
    assert ia["report_id"] == "ism_manufacturing_2026_06"
    assert len(ia["industries"]) > 0
    printing = next(
        i
        for i in ia["industries"]
        if i["industry"] == "Printing & Related Support Activities"
    )
    assert printing["overall_signal"]["rank"] == 1
    assert printing["core_signals"]["new_orders"]["rank"] == 3
    assert printing["core_signals"]["production"]["rank"] == 1
    assert printing["core_signals"]["backlog"]["status"] == "not_reported"
    assert printing["comments"] == []
    assert "trend" in printing
    assert "trend_summary" in printing
    assert len(printing["trend"]) == 1
    assert printing["trend"][0]["period"] == "2026-06-01"


def test_services_detail_returns_signal_trend(monkeypatch):
    from app import api
    from app.db import ism_surveys
    from app.services import ism_services_dashboard
    from tests.test_macro_dashboard_api import client

    report = {
        "report_id": "ism_services_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Services PMI Report",
        "source_url": "https://example.com/services/june",
        "source_hash": "abc123",
    }
    monkeypatch.setattr(
        ism_services_dashboard.ism_surveys,
        "load_latest_report_snapshot",
        lambda con, survey_type: report,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signals",
        lambda con, report_id: [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Construction",
                "rank": 1,
                "source_excerpt": "growth excerpt",
            }
        ],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signal_coverage",
        lambda con, report_id: [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "list_present": True,
                "declared_count": 12,
                "extracted_count": 12,
                "validation_status": "complete",
                "evidence_text": "",
                "source_url": "",
                "source_hash": "",
            }
        ],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6, survey_type="manufacturing": [report],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signals_for_reports",
        lambda con, report_ids: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_ism_report_industry_signal_coverage_for_reports",
        lambda con, report_ids: [],
    )

    resp = client.get("/api/macro-dashboard/growth-cycle/ism_services")
    assert resp.status_code == 200
    data = resp.json()
    analysis = data.get("industry_analysis", {})
    if analysis.get("industries"):
        ind = analysis["industries"][0]
        assert "signal_trend" in ind


def _default_signals():
    from app.tools.ism_industry_analysis import CANONICAL_INDUSTRIES

    growth_industries = [
        "Printing & Related Support Activities",
        "Machinery",
        "Chemical Products",
        "Computer & Electronic Products",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
        "Fabricated Metal Products",
        "Primary Metals",
        "Paper Products",
        "Miscellaneous Manufacturing",
        "Furniture & Related Products",
        "Transportation Equipment",
        "Plastics & Rubber Products",
        "Wood Products",
    ]
    signals = []
    for rank, ind in enumerate(growth_industries, start=1):
        signals.append(
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The 14 manufacturing industries reporting growth in June.",
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/june-2026",
                "source_hash": "abc",
            }
        )
    for ind in [
        "Nonmetallic Mineral Products",
        "Apparel, Leather & Allied Products",
        "Petroleum & Coal Products",
    ]:
        r = [
            "Nonmetallic Mineral Products",
            "Apparel, Leather & Allied Products",
            "Petroleum & Coal Products",
        ].index(ind) + 1
        signals.append(
            {
                "signal_type": "overall_contraction",
                "direction": "contraction",
                "industry": ind,
                "rank": r,
                "evidence_text": "The three industries reporting contraction in June.",
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/june-2026",
                "source_hash": "abc",
            }
        )
    no_list = [
        "Chemical Products",
        "Computer & Electronic Products",
        "Printing & Related Support Activities",
        "Machinery",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
        "Fabricated Metal Products",
        "Primary Metals",
        "Paper Products",
        "Miscellaneous Manufacturing",
        "Furniture & Related Products",
    ]
    for rank, ind in enumerate(no_list, start=1):
        signals.append(
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The 11 industries reporting growth in new orders.",
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/june-2026",
                "source_hash": "abc",
            }
        )
    prod_list = [
        "Printing & Related Support Activities",
        "Chemical Products",
        "Computer & Electronic Products",
        "Machinery",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
        "Fabricated Metal Products",
        "Paper Products",
    ]
    for rank, ind in enumerate(prod_list, start=1):
        signals.append(
            {
                "signal_type": "production",
                "direction": "growth",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The eight industries reporting production growth.",
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/june-2026",
                "source_hash": "abc",
            }
        )
    bh_list = [
        "Machinery",
        "Computer & Electronic Products",
        "Chemical Products",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
    ]
    for rank, ind in enumerate(bh_list, start=1):
        signals.append(
            {
                "signal_type": "backlog",
                "direction": "higher",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The five industries reporting higher order backlogs.",
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "source_url": "https://example.com/june-2026",
                "source_hash": "abc",
            }
        )
    return signals


def _default_coverage():
    return [
        {
            "signal_type": "overall_growth",
            "direction": "growth",
            "list_present": True,
            "declared_count": 14,
            "extracted_count": 14,
            "validation_status": "complete",
            "evidence_text": "The 14 manufacturing industries reporting growth in June.",
        },
        {
            "signal_type": "overall_contraction",
            "direction": "contraction",
            "list_present": True,
            "declared_count": 3,
            "extracted_count": 3,
            "validation_status": "complete",
            "evidence_text": "The three industries reporting contraction in June.",
        },
        {
            "signal_type": "new_orders",
            "direction": "growth",
            "list_present": True,
            "declared_count": 11,
            "extracted_count": 11,
            "validation_status": "complete",
            "evidence_text": "The 11 industries reporting growth in new orders.",
        },
        {
            "signal_type": "new_orders",
            "direction": "decrease",
            "list_present": True,
            "declared_count": 0,
            "extracted_count": 0,
            "validation_status": "complete",
            "evidence_text": "No industries reported a decrease in new orders in June.",
        },
        {
            "signal_type": "production",
            "direction": "growth",
            "list_present": True,
            "declared_count": 8,
            "extracted_count": 8,
            "validation_status": "complete",
            "evidence_text": "The eight industries reporting production growth.",
        },
        {
            "signal_type": "production",
            "direction": "decrease",
            "list_present": True,
            "declared_count": 0,
            "extracted_count": 0,
            "validation_status": "complete",
            "evidence_text": "No industries reported a decrease in production in June.",
        },
        {
            "signal_type": "backlog",
            "direction": "higher",
            "list_present": True,
            "declared_count": 5,
            "extracted_count": 5,
            "validation_status": "complete",
            "evidence_text": "The five industries reporting higher order backlogs.",
        },
        {
            "signal_type": "backlog",
            "direction": "lower",
            "list_present": True,
            "declared_count": 0,
            "extracted_count": 0,
            "validation_status": "complete",
            "evidence_text": "No industries reported lower order backlogs in June.",
        },
    ]


def _default_at_a_glance():
    return [
        {
            "series_id": "ism_manufacturing_new_orders",
            "current_value": 56.0,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "label": "New Orders",
            "report_id": "ism_manufacturing_2026_06",
        },
        {
            "series_id": "ism_manufacturing_production",
            "current_value": 52.2,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "label": "Production",
            "report_id": "ism_manufacturing_2026_06",
        },
    ]


def _default_comments():
    return [
        {
            "industry": "Chemical Products",
            "comment_text": "Input costs remain elevated.",
            "report_id": "ism_manufacturing_2026_06",
            "comment_index": 0,
        }
    ]


def test_growth_cycle_api_returns_ism_industry_breadth(monkeypatch):
    from app import api

    def fake_load_macro_indicator_points(con, series_id):
        if series_id == "m2_money_stock":
            return [
                {"date": "2025-06-01", "value": 100, "source": "m2.xlsx"},
                {"date": "2025-07-01", "value": 101, "source": "m2.xlsx"},
                {"date": "2025-08-01", "value": 102, "source": "m2.xlsx"},
                {"date": "2025-09-01", "value": 103, "source": "m2.xlsx"},
                {"date": "2025-10-01", "value": 104, "source": "m2.xlsx"},
                {"date": "2025-11-01", "value": 105, "source": "m2.xlsx"},
                {"date": "2025-12-01", "value": 106, "source": "m2.xlsx"},
                {"date": "2026-01-01", "value": 107, "source": "m2.xlsx"},
                {"date": "2026-02-01", "value": 108, "source": "m2.xlsx"},
                {"date": "2026-03-01", "value": 109, "source": "m2.xlsx"},
                {"date": "2026-04-01", "value": 110, "source": "m2.xlsx"},
                {"date": "2026-05-01", "value": 111, "source": "m2.xlsx"},
                {"date": "2026-06-01", "value": 112, "source": "m2.xlsx"},
            ]
        if series_id == "core_pce_price_index":
            return []
        if series_id in (
            "fed_total_assets",
            "fed_treasury_holdings",
            "fed_mbs_holdings",
        ):
            return []
        return []

    def fake_load_macro_indicator_points_for_series(con, series_ids):
        return {
            "ism_manufacturing_pmi": [
                {"date": "2026-06-01", "value": 51.2, "source": "ISM.xlsx"}
            ]
        }

    def fake_latest_rankings(con):
        return [
            {
                "date": "2026-06-01",
                "industry": "Computer & Electronic Products",
                "direction": "growth",
                "rank": 16,
                "source": "ISM_Manufacturing_Index.xlsx",
            },
            {
                "date": "2026-06-01",
                "industry": "Machinery",
                "direction": "contraction",
                "rank": -1,
                "source": "ISM_Manufacturing_Index.xlsx",
            },
        ]

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        fake_latest_rankings,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points_for_series",
        fake_load_macro_indicator_points_for_series,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    card = next(
        card for card in payload["headline"] if card["id"] == "ism_manufacturing"
    )
    assert card["segments"]["industry_breadth"]["status"] == "available"
    assert card["segments"]["industry_breadth"]["growth_count"] == 1
    assert card["segments"]["industry_breadth"]["contraction_count"] == 1


def test_growth_cycle_api_ism_detail_includes_at_a_glance_metadata(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    def fake_load_macro_indicator_points_for_series(con, series_ids):
        assert hasattr(con, "close")
        return {
            "ism_manufacturing_pmi": [
                {"date": "2026-06-01", "value": 51.2, "source": "workbook"},
            ],
            "ism_manufacturing_new_orders": [
                {"date": "2026-06-01", "value": 52.0, "source": "workbook"},
            ],
        }

    def fake_load_quad_rows(con, relationship_id):
        return []

    def fake_load_price_rows(con, benchmark_id):
        return []

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.growth_cycle, "load_latest_ism_industry_rankings", lambda con: []
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [
            {
                "report_id": "ism_manufacturing_2026_06",
                "report_month": "2026-06-01",
                "series_id": "ism_manufacturing_pmi",
                "label": "Manufacturing PMI",
                "current_value": 53.3,
                "previous_value": 54.0,
                "point_change": -0.7,
                "direction": "Growing",
                "rate_of_change": "Slower",
                "trend_months": 6,
                "source_url": "https://example.com",
                "source_hash": "abc123",
            },
        ],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points_for_series",
        fake_load_macro_indicator_points_for_series,
    )
    monkeypatch.setattr(api.gdp_market_relationships, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "load_quad_rows",
        fake_load_quad_rows,
    )
    monkeypatch.setattr(api.benchmark_market_data, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.benchmark_market_data,
        "load_price_rows",
        fake_load_price_rows,
    )

    response = client.get("/api/macro-dashboard/growth-cycle/ism_manufacturing")

    assert response.status_code == 200
    payload = response.json()
    assert "latest_metadata" in payload
    assert payload["latest_metadata"]["pmi"]["point_change"] == -0.7
    assert payload["latest_metadata"]["pmi"]["tone"] == "amber"


def test_growth_cycle_api_returns_survey_synthesis(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    assert "survey_synthesis" in payload["growth_cycle"]
    synthesis = payload["growth_cycle"]["survey_synthesis"]
    assert synthesis["version"] == "ism_survey_synthesis_v1"
    assert synthesis["status"] == "partial"
    assert synthesis["economic_direction"] is None


def test_consumer_sentiment_page_routes_are_served():
    response = client.get("/consumer-sentiment.js")
    assert response.status_code == 200

    response = client.get("/consumer-sentiment.css")
    assert response.status_code == 200


def test_consumer_sentiment_api_returns_summary(monkeypatch):
    from app import api

    def fake_connect():
        return _FakeConStubs()

    monkeypatch.setattr(api.consumer_sentiment, "connect", fake_connect)

    response = client.get("/api/macro-dashboard/consumer-sentiment")

    assert response.status_code == 200
    payload = response.json()
    assert payload["method_version"] == 2
    assert payload["primary_signal"]["percentile_zone"] == ("percentile_unavailable")
    assert payload["confirmation"]["state"] == "unavailable"
    assert "evidence_state" not in payload


def test_consumer_sentiment_detail_api_returns_detail(monkeypatch):
    from app import api

    def fake_connect():
        return _FakeConStubs()

    monkeypatch.setattr(api.consumer_sentiment, "connect", fake_connect)

    response = client.get("/api/macro-dashboard/consumer-sentiment/detail")

    assert response.status_code == 200
    payload = response.json()
    assert "detail_id" in payload
    assert payload["summary"]["method_version"] == 2
    assert "percentile_windows" in payload


def _consumer_sentiment_summary(zone="elevated", momentum="improving"):
    return {
        "method_version": 2,
        "data_status": "aligned_period",
        "aligned_month": "2026-06-01",
        "primary_signal": {
            "series_id": "umcsi_expectations",
            "percentile_zone": zone,
            "momentum": momentum,
        },
        "expectations": {
            "percentile_rank": 91.25,
            "percentile_label": "91st percentile",
        },
        "confirmation": {"state": "broadly_confirmed"},
    }


def test_market_setup_api_passes_consumer_demand_to_v2_builder(monkeypatch):
    from app import api

    captured = {}

    monkeypatch.setattr(
        api.consumer_sentiment_dashboard,
        "load_overview",
        lambda con: _consumer_sentiment_summary(zone="depressed", momentum="weakening"),
    )
    monkeypatch.setattr(
        api.market_setup_v2,
        "build_market_setup_v2",
        lambda **kwargs: captured.setdefault("payload", kwargs) or {},
    )

    api.macro_dashboard_market_setup()

    consumer_facts = captured["payload"]["consumer_demand"]["facts"][
        "consumer_demand_outlook"
    ]
    assert "relationship_to_growth_direction" in consumer_facts


def test_market_setup_api_exposes_decision_path_without_expanding_decision_authority():
    payload = client.get("/api/macro-dashboard/market-setup").json()

    assert payload["version"] == "market_setup_v2"
    assert payload["evidence_layers"]["decision_path"]["steps"]
    assert payload["evidence_layers"]["economic_reality"]["role"] == "supplementary"
    assert payload["evidence_layers"]["final_confirmation"]["role"] == "review_only"
    assert "economic_confirmation" not in payload["method_versions"]


def test_market_setup_api_keeps_v2_insufficient_when_consumer_data_is_unavailable(
    monkeypatch,
):
    from app import api

    monkeypatch.setattr(
        api.consumer_sentiment_dashboard,
        "load_overview",
        lambda con: {"method_version": 2, "data_status": "missing"},
    )

    response = TestClient(api.app).get("/api/macro-dashboard/market-setup")

    assert response.status_code == 200
    assert response.json()["version"] == "market_setup_v2"
    assert "consumer_demand" not in response.json()["macro_regime"]
    assert "Consumer Sentiment" not in response.json()["missing_inputs"]


def test_growth_cycle_endpoint_returns_housing_card_with_visible_unavailable_state(
    monkeypatch,
):
    from app import api

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )

    response = TestClient(api.app).get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    card = next(
        card for card in response.json()["headline"] if card["id"] == "housing_permits"
    )
    assert card["status"] == "unavailable"
    assert card["reason"]


def test_market_setup_display_only_regional_nfib_keeps_decision_outputs(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    _present_display_only_inputs(monkeypatch)
    with_payload = client.get("/api/macro-dashboard/market-setup").json()
    monkeypatch.setattr(
        macro_dashboard_router.nfib_sbo,
        "build_nfib_sbo_signal",
        lambda observations, survey_synthesis, as_of: None,
    )
    without_payload = client.get("/api/macro-dashboard/market-setup").json()

    assert _decision_snapshot(with_payload) == _decision_snapshot(without_payload)


def test_housing_detail_endpoint_returns_level_and_smoothed_yoy_charts(monkeypatch):
    from app import api

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/housing_permits"
    )

    assert response.status_code == 200
    charts = response.json()["charts"]
    assert charts[0]["title"] == "Building Permits SAAR"
    assert charts[1]["title"] == "Building Permits YoY and 12M Average"


def test_growth_cycle_api_returns_partial_card_when_only_official_usd_is_available(
    monkeypatch,
):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: [
                {"date": "2026-07-21", "value": 120.0, "source_identifier": "DTWEXBGS"}
            ]
            for sid in series_ids
        },
    )

    response = TestClient(api.app).get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    cards = [
        card
        for card in response.json()["headline"]
        if card.get("id") == "cyclical_commodities"
    ]
    assert len(cards) > 0
    card = cards[0]
    assert card["status"] == "partial_official_evidence"
    section = next(
        section
        for section in response.json()["sections"]
        if section["id"] == "cyclical_commodities_usd"
    )
    assert section["cards"] == ["cyclical_commodities"]


def test_detail_endpoint_returns_explicit_unavailable_attribution(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    assert response.json()["commodity_attribution"]["status"] == "unavailable"


def test_detail_endpoint_exposes_process_read_and_corroboration(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: [
                {"date": "2026-07-20", "value": 120.0, "source_identifier": "DTWEXBGS"},
                {"date": "2026-07-21", "value": 120.5, "source_identifier": "DTWEXBGS"},
            ]
            for sid in series_ids
            if not sid.startswith("oil")
        },
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    assert (
        response.json()["process_read"]["status"]
        == "insufficient_for_commodity_narrative"
    )
    assert response.json()["corroboration"]["usd"]["available_series_count"] == 3


def test_detail_loads_active_investing_lme(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: rows
            for sid, rows in {
                "copper_lme": [
                    {
                        "date": "2026-07-30",
                        "value": 13745.72,
                        "source_identifier": "copper_lme",
                    },
                    {
                        "date": "2026-07-31",
                        "value": 13803.0,
                        "source_identifier": "copper_lme",
                    },
                ],
            }.items()
            if sid in series_ids
        },
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    lme = body["non_oil_observation"]["copper_lme"]
    assert lme["status"] == "available"
    assert lme["latest_date"] == "2026-07-31"
    assert lme["latest_value"] == 13803.0
    assert lme["display_name"] == "Copper (LME)"
    assert lme["source_label"] == "Investing.com"
    assert "copper_lme_sina_cad_v1" not in body["non_oil_observation"]
    assert "source_cutover_date" not in lme
    assert "return_transition_blocked" not in lme


def _usd_weekday_rows():
    rows = []
    day = datetime.date(2016, 1, 4)
    while len(rows) < 265:
        if day.weekday() < 5:
            rows.append(
                {
                    "date": day.isoformat(),
                    "value": 100.0 * (1.0005 ** len(rows)),
                }
            )
        day += datetime.timedelta(days=1)
    return rows


def test_usd_detail_propagates_distribution_and_review_state(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: list(_usd_weekday_rows()) for sid in series_ids
        },
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    usd_step = next(
        step
        for step in response.json()["steps"]
        if step["title"] == "Trade-Weighted USD"
    )
    usd_series = {series["series_id"]: series for series in usd_step["series"]}
    assert set(usd_series) == {"usd_broad", "usd_afe", "usd_eme"}
    for series in usd_series.values():
        assert (
            series["daily_distribution"]["method_version"]
            == "usd_price_distribution_v1"
        )
        assert (
            series["weekly_distribution"]["method_version"]
            == "usd_price_distribution_v1"
        )
        assert series["review_status"] in {
            "observation_available",
            "review_required",
            "unavailable",
        }


def _cot_identity_rows(count=300, net_fn=None, start="2021-01-05"):
    rows = []
    day = datetime.date.fromisoformat(start)
    for index in range(count):
        net = net_fn(index) if net_fn else 200000 - index
        shorts = 20000
        longs = shorts + net
        rows.append(
            {
                "commodity_id": "crude_oil_wti",
                "report_date": day.isoformat(),
                "cftc_contract_market_code": "067411",
                "report_type": "disaggregated_futures_only",
                "position_category": "managed_money",
                "manager_longs": longs,
                "manager_shorts": shorts,
                "open_interest": longs + shorts,
            }
        )
        day += datetime.timedelta(days=7)
    return rows


def _cot_allowlist():
    return {
        "version": "cot_historical_extreme_allowlist_v1",
        "report_type": "disaggregated_futures_only",
        "position_category": "managed_money",
        "entries": [
            {
                "commodity_id": "crude_oil_wti",
                "market_name": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
                "contract_code": "067411",
                "active": True,
            }
        ],
    }


def _stub_detail_route(monkeypatch, cot_rows, allowlist):
    from app import api
    from app.routers import macro_dashboard as macro_dashboard_module

    class FakeCon(_FakeConStubs):
        pass

    class FakeDate:
        @classmethod
        def today(cls):
            return datetime.date(2026, 8, 3)

    monkeypatch.setattr(macro_dashboard_module, "date", FakeDate)
    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: cot_rows,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {},
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_shfe_cu_main_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_refresh_status",
        lambda con: [],
    )
    monkeypatch.setattr(
        api,
        "_load_non_oil_attribution_source_audit",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_attribution_catalog",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_cot_historical_extreme_allowlist",
        lambda: allowlist,
    )


def test_cot_detail_propagates_all_four_extreme_statuses(monkeypatch):
    cases = [
        (_cot_identity_rows(net_fn=lambda i: 100000 + i), "historical_high", None),
        (_cot_identity_rows(net_fn=lambda i: 100000 - i), "historical_low", None),
        (
            _cot_identity_rows(net_fn=lambda i: 100000 + (i % 40)),
            "not_extreme",
            None,
        ),
        (
            _cot_identity_rows(count=10, start="2026-05-26"),
            "unavailable",
            "insufficient_history",
        ),
    ]
    for rows, expected_status, expected_reason in cases:
        _stub_detail_route(monkeypatch, rows, _cot_allowlist())
        response = TestClient(app).get(
            "/api/macro-dashboard/growth-cycle/cyclical_commodities"
        )
        assert response.status_code == 200
        cot_step = next(
            step
            for step in response.json()["steps"]
            if step["title"] == "CFTC COT Positioning"
        )
        wti = next(
            commodity
            for commodity in cot_step["commodities"]
            if commodity["commodity_id"] == "crude_oil_wti"
        )
        extreme = wti["review_evidence"]["cot_historical_extreme"]
        assert extreme["status"] == expected_status
        assert extreme["reason_code"] == expected_reason
        assert extreme["method_version"] == "cot_historical_extremes_v1"
        assert extreme["cftc_contract_market_code"] == "067411"
        assert extreme["report_type"] == "disaggregated_futures_only"
        assert extreme["position_category"] == "managed_money"
        assert "latest_report_date" in extreme
        assert "latest_net_position" in extreme
        assert "history_start_date" in extreme
        assert "history_end_date" in extreme
        assert "valid_observation_count" in extreme
        assert "history_has_gaps" in extreme


def test_market_setup_is_identical_across_cot_extreme_statuses(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    statuses = [
        _cot_identity_rows(net_fn=lambda i: 100000 + i),
        _cot_identity_rows(net_fn=lambda i: 100000 - i),
        _cot_identity_rows(net_fn=lambda i: 100000 + (i % 40)),
        _cot_identity_rows(count=10),
    ]
    responses = []
    for rows in statuses:
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_cot_observations",
            lambda con, rows=rows: rows,
        )
        responses.append(_market_setup_payload())

    assert all(response == responses[0] for response in responses)


def test_cot_historical_extreme_never_reaches_ticker_workflow(monkeypatch):
    import json

    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "cot_historical_extreme" not in json.dumps(payload)
    assert "review_evidence" not in json.dumps(payload)


def _oil_spread_rows(wti_value=68.0, brent_value=71.0):
    return {
        "oil_wti_spot": [
            {"date": "2026-07-24", "value": wti_value, "source_identifier": "RWTC"},
        ],
        "oil_brent_spot": [
            {"date": "2026-07-24", "value": brent_value, "source_identifier": "RBRTE"},
        ],
    }


def _lme_comex_copper_rows(lme_rows=None, comex_rows=None):
    return {
        "copper_lme": (
            lme_rows
            if lme_rows is not None
            else [{"date": "2026-07-24", "value": 9500.0}]
        ),
        "copper_comex": (
            comex_rows
            if comex_rows is not None
            else [{"date": "2026-07-24", "value": 4.5}]
        ),
    }


def _stub_detail_route_with_oil(monkeypatch, oil_rows):
    from app import api
    from app.routers import macro_dashboard as macro_dashboard_module

    class FakeCon(_FakeConStubs):
        pass

    class FakeDate:
        @classmethod
        def today(cls):
            return datetime.date(2026, 8, 3)

    monkeypatch.setattr(macro_dashboard_module, "date", FakeDate)
    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: list(oil_rows.get(sid, [])) for sid in series_ids
        },
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_shfe_cu_main_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_refresh_status",
        lambda con: [],
    )
    monkeypatch.setattr(
        api,
        "_load_non_oil_attribution_source_audit",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_attribution_catalog",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_cot_historical_extreme_allowlist",
        lambda: None,
    )


def _stub_detail_route_with_copper(monkeypatch, copper_rows):
    from app import api
    from app.routers import macro_dashboard as macro_dashboard_module

    class FakeCon(_FakeConStubs):
        pass

    class FakeDate:
        @classmethod
        def today(cls):
            return datetime.date(2026, 8, 3)

    monkeypatch.setattr(macro_dashboard_module, "date", FakeDate)
    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: list(copper_rows.get(sid, [])) for sid in series_ids
        },
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_shfe_cu_main_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_refresh_status",
        lambda con: [],
    )
    monkeypatch.setattr(
        api,
        "_load_non_oil_attribution_source_audit",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_attribution_catalog",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_cot_historical_extreme_allowlist",
        lambda: None,
    )


def test_detail_propagates_available_cross_market_spread(monkeypatch):
    from app import api

    _stub_detail_route_with_oil(monkeypatch, _oil_spread_rows())

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    spreads = body["review_evidence"]["cross_market_spreads"]
    brent_wti = next(
        entry for entry in spreads["spreads"] if entry["spread_id"] == "brent_wti_spot"
    )
    assert brent_wti["status"] == "available"
    assert brent_wti["value"] == 3.0
    assert brent_wti["common_observation_date"] == "2026-07-24"
    assert brent_wti["unit"] == "USD/BBL"
    assert brent_wti["expression"] == "brent_price - wti_price"
    assert brent_wti["legs"]["brent"]["source_identifier"] == "RBRTE"
    assert brent_wti["legs"]["wti"]["source_identifier"] == "RWTC"


def test_detail_propagates_negative_cross_market_spread(monkeypatch):
    from app import api

    _stub_detail_route_with_oil(
        monkeypatch, _oil_spread_rows(wti_value=75.0, brent_value=70.0)
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    body = response.json()
    spreads = body["review_evidence"]["cross_market_spreads"]
    brent_wti = next(
        entry for entry in spreads["spreads"] if entry["spread_id"] == "brent_wti_spot"
    )
    assert brent_wti["status"] == "available"
    assert brent_wti["value"] == -5.0


def test_detail_propagates_unavailable_cross_market_spread_states(monkeypatch):
    from app import api

    cases = [
        (_oil_spread_rows(wti_value=68.0), "available", None),
        (_oil_spread_rows(wti_value=68.0, brent_value=71.0), "available", None),
        ({"oil_wti_spot": [], "oil_brent_spot": []}, "unavailable", None),
        (
            {
                "oil_wti_spot": [
                    {"date": "2026-07-24", "value": 68.0, "source_identifier": "RWTC"}
                ],
                "oil_brent_spot": [
                    {
                        "date": "2026-07-23",
                        "value": 71.0,
                        "source_identifier": "RBRTE",
                    }
                ],
            },
            "unavailable",
            "no_common_observation_date",
        ),
    ]
    for oil_rows, expected_status, expected_reason in cases:
        _stub_detail_route_with_oil(monkeypatch, oil_rows)
        response = TestClient(api.app).get(
            "/api/macro-dashboard/growth-cycle/cyclical_commodities"
        )
        assert response.status_code == 200
        spreads = response.json()["review_evidence"]["cross_market_spreads"]
        brent_wti = next(
            entry
            for entry in spreads["spreads"]
            if entry["spread_id"] == "brent_wti_spot"
        )
        assert brent_wti["status"] == expected_status
        if expected_reason:
            assert brent_wti["reason"] == expected_reason


def test_detail_cross_market_spread_has_no_recommendation_fields(monkeypatch):
    from app import api

    _stub_detail_route_with_oil(monkeypatch, _oil_spread_rows())

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    body = response.json()
    spreads = body["review_evidence"]["cross_market_spreads"]
    for entry in spreads["spreads"]:
        for field in (
            "bullish",
            "bearish",
            "recommendation",
            "normal",
            "abnormal",
            "arbitrage",
        ):
            assert field not in entry
            assert field not in str(entry.get("label", "").lower())


def test_cross_market_spreads_never_reach_ticker_workflow(monkeypatch):
    import json

    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={
            "symbol": "XYZ",
            "observations": {
                "cross_market_spreads": {
                    "method_version": "cross_market_spreads_v1",
                    "spreads": [
                        {
                            "spread_id": "brent_wti_spot",
                            "status": "available",
                            "value": 3.0,
                        }
                    ],
                }
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "cross_market_spreads" not in json.dumps(payload)
    assert "brent_wti_spot" not in json.dumps(payload)
    assert "review_evidence" not in json.dumps(payload)


def test_ticker_classification_is_identical_across_cross_market_spread_observations(
    monkeypatch,
):
    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    observations = [
        {"symbol": "XYZ", "observations": {"oil_wti_spot": 68.0}},
        {"symbol": "XYZ", "observations": {"oil_wti_spot": 90.0}},
        {"symbol": "XYZ", "observations": {"cross_market_spreads": {"value": 3.0}}},
        {"symbol": "XYZ", "observations": {}},
    ]
    responses = []
    for body in observations:
        response = client.post("/api/ticker-workflow/evaluate", json=body)
        assert response.status_code == 200
        responses.append(response.json())

    assert all(response == responses[0] for response in responses)


def test_market_setup_is_identical_across_cross_market_spread_states(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    states = [
        _oil_spread_rows(wti_value=68.0, brent_value=71.0),
        _oil_spread_rows(wti_value=75.0, brent_value=70.0),
        {"oil_wti_spot": [], "oil_brent_spot": []},
    ]
    responses = []
    for rows in states:
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids, rows=rows: {
                sid: list(rows.get(sid, [])) for sid in series_ids
            },
        )
        responses.append(_market_setup_payload())

    assert all(response == responses[0] for response in responses)


def test_detail_propagates_lme_comex_differential_limited_contract(monkeypatch):
    from app import api

    _stub_detail_route_with_copper(monkeypatch, _lme_comex_copper_rows())

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    spreads = response.json()["review_evidence"]["cross_market_spreads"]
    entry = next(
        entry
        for entry in spreads["spreads"]
        if entry["spread_id"] == "lme_comex_copper"
    )
    assert entry["status"] == "available"
    assert entry["comparability"] == "limited"
    assert entry["evidence_type"] == "date_aligned_continuous_price_differential"
    assert entry["method_version"] == "copper_lme_comex_differential_v1"
    assert entry["common_observation_date"] == "2026-07-24"
    assert entry["value"] == pytest.approx(-420.8018)
    assert entry["legs"]["lme"]["value"] == 9500.0
    assert entry["legs"]["comex"]["source_value"] == 4.5
    assert entry["legs"]["comex"]["normalized_value"] == pytest.approx(9920.8018)
    assert entry["legs"]["comex"]["normalized_unit"] == "USD/tonne"
    assert entry["legs"]["comex"]["conversion_factor"] == 2204.62262185
    assert entry["limitations"] == [
        "contract_tenor_not_confirmed_comparable",
        "close_timing_not_synchronized",
        "continuous_roll_rules_undocumented",
    ]
    by_id = {entry["spread_id"]: entry for entry in spreads["spreads"]}
    assert by_id["shfe_lme_copper"]["reason"] == "fx_source_not_approved"
    assert by_id["shfe_comex_copper"]["reason"] == "fx_source_not_approved"


def test_detail_propagates_unavailable_lme_comex_differential_states(monkeypatch):
    from app import api

    cases = [
        (
            {
                "copper_lme": [],
                "copper_comex": [{"date": "2026-07-24", "value": 4.5}],
            },
            "missing_lme_price",
        ),
        (
            {
                "copper_lme": [{"date": "2026-07-24", "value": 9500.0}],
                "copper_comex": [],
            },
            "missing_comex_price",
        ),
    ]
    for copper_rows, expected_reason in cases:
        _stub_detail_route_with_copper(monkeypatch, copper_rows)
        response = TestClient(api.app).get(
            "/api/macro-dashboard/growth-cycle/cyclical_commodities"
        )
        assert response.status_code == 200
        spreads = response.json()["review_evidence"]["cross_market_spreads"]
        entry = next(
            entry
            for entry in spreads["spreads"]
            if entry["spread_id"] == "lme_comex_copper"
        )
        assert entry["status"] == "unavailable"
        assert entry["reason"] == expected_reason


def test_market_setup_is_identical_across_lme_comex_differential_states(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    states = [
        {},
        _lme_comex_copper_rows(),
        {
            "copper_lme": [],
            "copper_comex": _lme_comex_copper_rows()["copper_comex"],
        },
    ]
    responses = []
    for rows in states:
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids, rows=rows: {
                sid: list(rows.get(sid, [])) for sid in series_ids
            },
        )
        responses.append(_market_setup_payload())

    assert all(response == responses[0] for response in responses)


def test_lme_comex_differential_never_reaches_ticker_workflow(monkeypatch):
    import json

    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={
            "symbol": "XYZ",
            "observations": {
                "cross_market_spreads": {
                    "method_version": "cross_market_spreads_v1",
                    "spreads": [
                        {
                            "spread_id": "lme_comex_copper",
                            "status": "available",
                            "comparability": "limited",
                            "value": -420.8018,
                        }
                    ],
                }
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "cross_market_spreads" not in json.dumps(payload)
    assert "lme_comex_copper" not in json.dumps(payload)
    assert "review_evidence" not in json.dumps(payload)


def test_ticker_classification_is_identical_across_lme_comex_differential_observations(
    monkeypatch,
):
    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    observations = [
        {"symbol": "XYZ", "observations": {}},
        {
            "symbol": "XYZ",
            "observations": {
                "cross_market_spreads": {
                    "method_version": "cross_market_spreads_v1",
                    "spreads": [
                        {
                            "spread_id": "lme_comex_copper",
                            "status": "available",
                            "value": -420.8018,
                        }
                    ],
                }
            },
        },
        {
            "symbol": "XYZ",
            "observations": {
                "cross_market_spreads": {
                    "method_version": "cross_market_spreads_v1",
                    "spreads": [
                        {
                            "spread_id": "lme_comex_copper",
                            "status": "unavailable",
                            "reason": "missing_lme_price",
                        }
                    ],
                }
            },
        },
    ]
    responses = []
    for body in observations:
        response = client.post("/api/ticker-workflow/evaluate", json=body)
        assert response.status_code == 200
        responses.append(response.json())

    assert all(response == responses[0] for response in responses)


def _inflation_monthly_rows(
    values=None, start="2016-01-01", source_identifier="CPIAUCSL"
):
    if values is None:
        values = [100.0 * (1.002**index) for index in range(120)]
    rows = []
    year, month = int(start[:4]), int(start[5:7])
    for value in values:
        rows.append(
            {
                "date": f"{year:04d}-{month:02d}-01",
                "value": value,
                "source_identifier": source_identifier,
            }
        )
        month += 1
        if month == 13:
            month = 1
            year += 1
    return rows


def _stub_detail_route_with_inflation(monkeypatch, rows_by_series):
    from app import api
    from app.routers import macro_dashboard as macro_dashboard_module

    class FakeCon(_FakeConStubs):
        pass

    class FakeDate:
        @classmethod
        def today(cls):
            return datetime.date(2026, 8, 3)

    monkeypatch.setattr(macro_dashboard_module, "date", FakeDate)
    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: list(rows_by_series.get(sid, [])) for sid in series_ids
        },
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_shfe_cu_main_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_refresh_status",
        lambda con: [],
    )
    monkeypatch.setattr(
        api,
        "_load_non_oil_attribution_source_audit",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_attribution_catalog",
        lambda: None,
    )
    monkeypatch.setattr(
        api,
        "_load_cot_historical_extreme_allowlist",
        lambda: None,
    )


def test_inflation_detail_propagates_monthly_distribution_and_review_state(
    monkeypatch,
):
    rows = _inflation_monthly_rows()
    _stub_detail_route_with_inflation(monkeypatch, {"cpi_all_items": rows})

    response = TestClient(app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    inflation_step = next(
        step
        for step in response.json()["steps"]
        if step["title"] == "CPI/PPI Confirmation"
    )
    series = {s["series_id"]: s for s in inflation_step["series"]}
    assert "cpi_all_items" in series
    monthly = series["cpi_all_items"]["monthly_distribution"]
    assert monthly["method_version"] == "inflation_price_distribution_v1"
    assert monthly["classification"] == "normal"
    assert series["cpi_all_items"]["review_status"] == "observation_available"
    assert series["cpi_all_items"]["review_label"] is None


def test_inflation_detail_propagates_each_abnormal_boundary(monkeypatch):
    cases = [
        ("cpi_all_items", "abnormal_1sigma"),
        ("core_cpi", "abnormal_2sigma"),
        ("ppi_all_commodities", "abnormal_3sigma"),
    ]
    for series_id, expected_classification in cases:
        rows = _inflation_monthly_rows(
            values=[100.0 * (1.002**index) for index in range(119)] + [150.0]
        )
        _stub_detail_route_with_inflation(monkeypatch, {series_id: rows})
        response = TestClient(app).get(
            "/api/macro-dashboard/growth-cycle/cyclical_commodities"
        )
        assert response.status_code == 200
        inflation_step = next(
            step
            for step in response.json()["steps"]
            if step["title"] == "CPI/PPI Confirmation"
        )
        series = {s["series_id"]: s for s in inflation_step["series"]}
        monthly = series[series_id]["monthly_distribution"]
        assert monthly["classification"].startswith("abnormal_")
        assert monthly["method_version"] == "inflation_price_distribution_v1"
        assert series[series_id]["review_status"] == "review_required"
        assert series[series_id]["review_label"] is not None
        assert "no macro attribution" in series[series_id]["review_label"].lower()


def test_inflation_detail_exposes_unavailable_state_with_exact_reason(monkeypatch):
    rows = [
        {"date": "2026-06-01", "value": 100.0, "source_identifier": "CPIAUCSL"},
        {"date": "2026-07-01", "value": 102.0, "source_identifier": "CPIAUCSL"},
    ]
    _stub_detail_route_with_inflation(monkeypatch, {"cpi_all_items": rows})

    response = TestClient(app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    inflation_step = next(
        step
        for step in response.json()["steps"]
        if step["title"] == "CPI/PPI Confirmation"
    )
    series = {s["series_id"]: s for s in inflation_step["series"]}
    monthly = series["cpi_all_items"]["monthly_distribution"]
    assert monthly["classification"] == "unavailable"
    assert monthly["reason"] == "at least 36 monthly returns are required"
    assert series["cpi_all_items"]["review_status"] == "unavailable"
    assert (
        series["cpi_all_items"]["review_label"]
        == "at least 36 monthly returns are required"
    )


def test_inflation_detail_no_look_ahead_uses_as_of_date(monkeypatch):
    rows = _inflation_monthly_rows(
        values=[100.0 * (1.002**index) for index in range(120)]
    )
    future = [{"date": "2026-09-01", "value": 160.0, "source_identifier": "CPIAUCSL"}]
    _stub_detail_route_with_inflation(
        monkeypatch, {"cpi_all_items": rows + future}
    )

    response = TestClient(app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    inflation_step = next(
        step
        for step in response.json()["steps"]
        if step["title"] == "CPI/PPI Confirmation"
    )
    series = {s["series_id"]: s for s in inflation_step["series"]}
    inflation = series["cpi_all_items"]
    monthly = inflation["monthly_distribution"]
    assert monthly["sample_end_date"] == "2025-12-01"
    assert monthly["current_return"] is not None
    assert monthly["current_return"] != pytest.approx(160.0 / 100.0 - 1)
    assert inflation["latest_date"] == "2025-12-01"
    assert inflation["latest_date"] != "2026-09-01"
    assert inflation["latest_value"] != 160.0
    assert inflation["mom_pct"] is not None
    assert inflation["yoy_pct"] is not None


def test_inflation_detail_has_no_recommendation_fields(monkeypatch):
    rows = _inflation_monthly_rows(
        values=[100.0 * (1.002**index) for index in range(119)] + [150.0]
    )
    _stub_detail_route_with_inflation(monkeypatch, {"cpi_all_items": rows})

    response = TestClient(app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    inflation_step = next(
        step
        for step in response.json()["steps"]
        if step["title"] == "CPI/PPI Confirmation"
    )
    series = {s["series_id"]: s for s in inflation_step["series"]}
    for key in ("buy", "sell", "recommendation", "target_price"):
        assert key not in series["cpi_all_items"]


def test_market_setup_is_identical_across_inflation_distribution_states(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader, **kwargs: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    states = [
        _inflation_monthly_rows(),
        _inflation_monthly_rows(
            values=[100.0 * (1.002**index) for index in range(119)] + [150.0]
        ),
        [
            {"date": "2026-06-01", "value": 100.0},
            {"date": "2026-07-01", "value": 102.0},
        ],
    ]
    responses = []
    for rows in states:
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids, rows=rows: {
                sid: list(rows)
                for sid in series_ids
                if sid in api._OBSERVATION_SERIES_IDS
            },
        )
        responses.append(_market_setup_payload())

    assert all(response == responses[0] for response in responses)


def test_ticker_classification_is_identical_across_cot_extreme_observations(
    monkeypatch,
):
    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    statuses = [
        _cot_identity_rows(net_fn=lambda i: 100000 + i),
        _cot_identity_rows(net_fn=lambda i: 100000 - i),
        _cot_identity_rows(count=10),
    ]
    responses = []
    for rows in statuses:
        response = client.post(
            "/api/ticker-workflow/evaluate",
            json={"symbol": "XYZ", "observations": {"cot": rows}},
        )
        assert response.status_code == 200
        responses.append(response.json())

    assert all(response == responses[0] for response in responses)


def test_market_setup_is_identical_when_usd_final_value_changes(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    def _market_setup_response(rows):
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids: {sid: list(rows) for sid in series_ids},
        )
        return _market_setup_payload()

    normal_rows = _usd_weekday_rows()
    abnormal_rows = list(normal_rows)
    abnormal_rows[-1] = {
        "date": abnormal_rows[-1]["date"],
        "value": abnormal_rows[-2]["value"] * 1.5,
    }

    assert _market_setup_response(normal_rows) == _market_setup_response(abnormal_rows)


def test_usd_distribution_never_reaches_ticker_workflow(monkeypatch):
    import json

    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    assert "usd" not in json.dumps(response.json())


def test_inflation_distribution_never_reaches_ticker_workflow(monkeypatch):
    import json

    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    assert "cpi" not in json.dumps(response.json())
    assert "inflation" not in json.dumps(response.json())


def test_ticker_classification_is_identical_across_inflation_states(monkeypatch):
    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    states = [
        _inflation_monthly_rows(),
        _inflation_monthly_rows(
            values=[100.0 * (1.002**index) for index in range(119)] + [150.0]
        ),
        [
            {"date": "2026-06-01", "value": 100.0},
            {"date": "2026-07-01", "value": 102.0},
        ],
    ]
    responses = []
    for rows in states:
        response = client.post(
            "/api/ticker-workflow/evaluate",
            json={"symbol": "XYZ", "observations": {"inflation": rows}},
        )
        assert response.status_code == 200
        responses.append(response.json())

    assert all(response == responses[0] for response in responses)


def test_market_setup_is_identical_when_data_changes(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    first = _market_setup_payload()
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [{"commodity_id": "crude_oil_wti", "report_date": "2026-07-21"}],
    )
    second = _market_setup_payload()

    assert _decision_snapshot(second) == _decision_snapshot(first)


def _stub_eia_observations(monkeypatch):
    from app import api

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: (
            {
                sid: [
                    {"date": "2026-07-24", "value": 64.89, "source_identifier": "RWTC"}
                ]
                for sid in series_ids
                if sid in api._OIL_SERIES_IDS
            }
            if any(sid in api._OIL_SERIES_IDS for sid in series_ids)
            else {
                sid: [
                    {
                        "date": "2026-07-20",
                        "value": 120.0,
                        "source_identifier": "DTWEXBGS",
                    },
                    {
                        "date": "2026-07-21",
                        "value": 120.5,
                        "source_identifier": "DTWEXBGS",
                    },
                ]
                for sid in series_ids
            }
        ),
    )


def test_detail_returns_oil_observation_and_pending_attribution(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    _stub_eia_observations(monkeypatch)

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["oil_observation"]["status"] == "available"
    assert body["commodity_attribution"]["status"] == "attribution_pending_review"
    summary = body["oil_price_distribution_summary"]
    assert summary["status"] in {"normal", "abnormal", "incomplete"}
    assert "trade" not in summary["label"].lower()
    assert "physical-market attribution remains required" in summary["detail"]
    if summary["status"] == "abnormal":
        assert body["process_read"]["status"] == "review_required"
        assert body["oil_attribution_review"]["status"] == "review_required"
    elif summary["status"] == "normal":
        assert body["process_read"]["status"] == "observation_available"
        assert body["oil_attribution_review"] is None
    else:
        assert body["process_read"]["status"] == "insufficient_for_commodity_narrative"
        assert body["oil_attribution_review"] is None


def test_market_setup_is_identical_when_oil_data_changes(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    def _market_setup_response(oil_value):
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids: {
                sid: [
                    {
                        "date": "2026-07-24",
                        "value": oil_value,
                        "source_identifier": "RWTC",
                    }
                ]
                for sid in series_ids
            },
        )
        return _market_setup_payload()

    assert _market_setup_response(60.0) == _market_setup_response(90.0)


def test_oil_review_states_do_not_change_market_setup(monkeypatch):
    from app import api

    from fastapi.testclient import TestClient

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )

    def _response(oil_value):
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids: {
                sid: [
                    {
                        "date": "2026-07-24",
                        "value": oil_value,
                        "source_identifier": "RWTC",
                    }
                ]
                for sid in series_ids
            },
        )
        return _market_setup_payload()

    assert _response(60.0) == _response(90.0)


def test_oil_full_history_injects_distributions_and_market_setup_unchanged(
    monkeypatch,
):
    from app import api
    from fastapi.testclient import TestClient
    import datetime

    class FakeCon(_FakeConStubs):
        pass

    daily_rows = []
    for i in range(253):
        d = datetime.date(2025, 1, 2) + datetime.timedelta(days=i)
        daily_rows.append({"date": d.isoformat(), "value": 100.0 + i * 0.1})

    weekly_rows = []
    d = datetime.date(2025, 1, 6)
    for i in range(53):
        friday = d + datetime.timedelta(days=4)
        weekly_rows.append({"date": friday.isoformat(), "value": 100.0 + i * 0.5})
        d += datetime.timedelta(days=7)

    oil_benchmark_rows = daily_rows + weekly_rows

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (
                oil_benchmark_rows
                if sid in api._OIL_SERIES_IDS[:2]
                else [{"date": "2026-07-24", "value": 64.89, "source_identifier": sid}]
                if sid in api._OIL_SERIES_IDS
                else [
                    {"date": "2026-07-20", "value": 120.0},
                    {"date": "2026-07-21", "value": 120.5},
                ]
            )
            for sid in series_ids
        },
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    benchmarks = body["oil_observation"]["benchmarks"]
    for bid in ("oil_wti_spot", "oil_brent_spot"):
        assert "daily_distribution" in benchmarks[bid]
        assert "weekly_distribution" in benchmarks[bid]
        assert (
            benchmarks[bid]["daily_distribution"]["method_version"]
            == "oil_distribution_v2"
        )
        assert (
            benchmarks[bid]["weekly_distribution"]["method_version"]
            == "oil_distribution_v2"
        )
        assert "classification" in benchmarks[bid]["daily_distribution"]

    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )

    def _market_setup_response(oil_value):
        monkeypatch.setattr(
            api.macro_indicators_db,
            "load_macro_indicator_observations_for_series",
            lambda con, series_ids: {
                sid: (
                    [{"date": "2026-07-24", "value": oil_value}]
                    if sid in api._OIL_SERIES_IDS
                    else [
                        {"date": "2026-07-20", "value": 120.0},
                        {"date": "2026-07-21", "value": 120.5},
                    ]
                )
                for sid in series_ids
            },
        )
        return _market_setup_payload()

    assert _market_setup_response(60.0) == _market_setup_response(90.0)


def test_market_setup_is_identical_when_active_lbr_data_changes(monkeypatch):
    from app import api
    from fastapi.testclient import TestClient

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    original_loader = (
        api.macro_indicators_db.load_macro_indicator_observations_for_series
    )

    def changed_lbr_loader(con, series_ids):
        result = original_loader(con, series_ids)
        result["lumber_cme_lbr_yahoo_v1"] = [
            {"date": "2026-07-24", "value": 999.0, "source_identifier": "LBR=F"}
        ]
        return result

    baseline = _market_setup_payload()
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        changed_lbr_loader,
    )
    assert _market_setup_payload() == baseline


def _non_oil_weekday_rows(start, count, value_at):
    rows = []
    day = start
    while len(rows) < count:
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "value": value_at(len(rows))})
        day += datetime.timedelta(days=1)
    return rows


def _copper_comex_normal_rows():
    return _non_oil_weekday_rows(
        datetime.date(2016, 1, 4), 265, lambda i: 100.0 * (1.0005**i)
    )


def _copper_comex_abnormal_rows():
    def value_at(i):
        if i == 264:
            return 100.0 * (1.0005**263) * 1.5
        return 100.0 * (1.0005**i)

    return _non_oil_weekday_rows(datetime.date(2016, 1, 4), 265, value_at)


def _iron_ore_abnormal_rows():
    def value_at(i):
        if i == 264:
            return 100.0 * (1.0005**263) * 1.5
        return 100.0 * (1.0005**i)

    return _non_oil_weekday_rows(datetime.date(2016, 1, 4), 265, value_at)


def _non_oil_global_fact():
    return {
        "commodity_id": "copper",
        "source_name": "International Wrought Copper Council",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "factor_category": "supply",
        "metric_name": "Semis production",
        "geography": "Global",
        "observation_date": "2024-12-31",
        "publication_date": None,
        "value": 12345678.0,
        "units": "t",
        "status": "available",
        "method_version": "non_oil_attribution_evidence_v1",
    }


def _non_oil_attribution_audit_payload():
    def audit_row(
        commodity_id,
        source_name,
        source_url,
        audit_status,
        factor_categories,
        access_method,
        geography,
        frequency,
        units,
        audit_basis,
    ):
        return {
            "commodity_id": commodity_id,
            "source_name": source_name,
            "source_url": source_url,
            "source_type": "official_data",
            "source_coverage": [],
            "audit_status": audit_status,
            "access_method": access_method,
            "factor_categories": factor_categories,
            "geography": geography,
            "frequency": frequency,
            "unit_status": "published",
            "units": units,
            "publication_date_status": "published",
            "stability": "manual",
            "audit_basis": audit_basis,
            "audited_at": "2026-08-02",
            "source_ref": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        }

    return {
        "version": "non_oil_attribution_source_audit_v1",
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_catalog_version": "commodity_attribution_evidence_catalog_v1",
        "source_catalog": "app/resources/attribution_catalog.v1.json",
        "audits": [
            audit_row(
                "copper",
                "International Wrought Copper Council",
                "http://www.coppercouncil.org/iwcc-statistics-and-data",
                "structured_recurring_candidate",
                ["supply", "demand"],
                "xlsx_download",
                "Global (107 countries by region)",
                "annual",
                "t",
                "Page exposes direct public XLSX downloads for global semis production and demand.",
            ),
            audit_row(
                "lumber",
                "Food and Agriculture Organization of the United Nations",
                "https://www.fao.org/faostat/en/#data/FO",
                "structured_recurring_candidate",
                ["supply", "trade"],
                "api",
                "Global by country",
                "annual",
                "t, m3, USD",
                "FAOSTAT Forestry Production and Trade bulk-download dataset (FO).",
            ),
            audit_row(
                "iron_ore",
                "US Geological Survey",
                "https://www.usgs.gov/centers/nmic/iron-ore-statistics-and-information",
                "manual_review_only",
                ["supply", "demand"],
                "xlsx_download",
                "US and world",
                "monthly",
                "t",
                "Public MIS posting is paused pending a ScienceBase transition.",
            ),
            audit_row(
                "iron_ore",
                "Government of Western Australia",
                "https://www.dmp.wa.gov.au/About-Us-Careers/Latest-Statistics-Release-4081.aspx",
                "manual_review_only",
                ["supply", "trade", "price"],
                "xlsx_download",
                "Western Australia",
                "annual",
                "kt, AUD m",
                "Method URL redirects to the WA Resources industry data page.",
            ),
            audit_row(
                "iron_ore",
                "Government of Western Australia",
                "https://www.dmp.wa.gov.au/About-Us-Careers/Statistics-Digest-3962.aspx",
                "manual_review_only",
                ["supply", "trade", "price"],
                "manual_report_download",
                "Western Australia",
                "annual",
                "kt, AUD m",
                "Method URL redirects to the WA Mineral and Petroleum statistics digest page.",
            ),
            audit_row(
                "iron_ore",
                "World Bank Commodity Markets",
                "https://www.worldbank.org/en/research/commodity-markets",
                "structured_recurring_candidate",
                ["price"],
                "xlsx_download",
                "Global",
                "monthly",
                "USD",
                "Monthly Pink Sheet commodity prices.",
            ),
        ],
    }


def test_non_oil_detail_propagates_distribution_review_evidence(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    comex_rows = _copper_comex_abnormal_rows()

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (comex_rows if sid == "copper_comex" else []) for sid in series_ids
        },
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    series = body["non_oil_observation"]["copper_comex"]
    assert (
        series["daily_distribution"]["method_version"]
        == "non_oil_price_distribution_v1"
    )
    assert (
        series["weekly_distribution"]["method_version"]
        == "non_oil_price_distribution_v1"
    )
    assert series["daily_distribution"]["classification"] == "abnormal_3sigma"
    assert series["review_status"] in {"review_required", "observation_available"}
    assert series["review_status"] == "review_required"
    assert body["commodity_returns"]["review_required_series_ids"] == [
        "copper_comex"
    ]


def _catalog_with_copper():
    return {
        "version": "commodity_attribution_evidence_catalog_v1",
        "generated_at": "2026-08-02T00:00:00+00:00",
        "source_document": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
        "resources": [
            {
                "commodity_id": "copper",
                "source_name": "International Copper Study Group",
                "source_url": "https://www.icsg.org/",
                "source_type": "industry_body",
                "coverage": ["production", "usage", "stocks", "forecasts"],
                "source_ref": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
                "status": "cataloged",
            },
            {
                "commodity_id": "oil",
                "source_name": "Energy Information Administration",
                "source_url": "https://www.eia.gov/petroleum/",
                "source_type": "official_data",
                "coverage": ["prices"],
                "source_ref": "data/source_material/Video 12/Cyclical_Commodities_Demand_Supply_Factors.pdf",
                "status": "cataloged",
            },
        ],
    }


def test_non_oil_detail_exposes_review_resources_from_catalog(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    comex_rows = _copper_comex_abnormal_rows()

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (comex_rows if sid == "copper_comex" else []) for sid in series_ids
        },
    )
    monkeypatch.setattr(
        api,
        "_load_attribution_catalog",
        lambda: _catalog_with_copper(),
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    resources = body["attribution_review_resources"]
    assert [r["source_name"] for r in resources] == ["International Copper Study Group"]
    assert all(r["commodity_id"] == "copper" for r in resources)
    assert all(r["status"] == "cataloged" for r in resources)


def test_non_oil_detail_exposes_empty_review_resources_without_catalog(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    comex_rows = _copper_comex_abnormal_rows()

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (comex_rows if sid == "copper_comex" else []) for sid in series_ids
        },
    )
    monkeypatch.setattr(api, "_load_attribution_catalog", lambda: None)

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attribution_review_resources"] == []
    assert (
        body["non_oil_observation"]["copper_comex"]["review_status"]
        == "review_required"
    )


def test_non_oil_detail_composes_attribution_evidence_from_facts_and_audit(
    monkeypatch,
):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    comex_rows = _copper_comex_abnormal_rows()
    iron_rows = _iron_ore_abnormal_rows()

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (
                comex_rows
                if sid == "copper_comex"
                else iron_rows
                if sid == "iron_ore_62_cfr_china"
                else []
            )
            for sid in series_ids
        },
    )
    monkeypatch.setattr(api, "_load_attribution_catalog", lambda: None)
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [_non_oil_global_fact()],
    )
    monkeypatch.setattr(
        api,
        "_load_non_oil_attribution_source_audit",
        lambda: _non_oil_attribution_audit_payload(),
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    evidence = body["non_oil_attribution_evidence"]
    assert evidence["copper"]["status"] == "available"
    assert evidence["copper"]["facts"][0]["geography"] == "Global"
    assert evidence["iron_ore"]["status"] == "unavailable"
    assert "USGS" in evidence["iron_ore"]["reason"]
    assert {
        row["source_name"] for row in evidence["iron_ore"]["manual_review_resources"]
    } == {"Government of Western Australia"}


def test_growth_cycle_dashboard_scrubs_non_oil_attribution_internals(monkeypatch):
    import json

    from app import api

    class FakeCon(_FakeConStubs):
        pass

    comex_rows = _copper_comex_abnormal_rows()
    iron_rows = _iron_ore_abnormal_rows()

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (
                comex_rows
                if sid == "copper_comex"
                else iron_rows
                if sid == "iron_ore_62_cfr_china"
                else []
            )
            for sid in series_ids
        },
    )
    monkeypatch.setattr(api, "_load_attribution_catalog", lambda: None)

    def db_shaped_non_oil_fact():
        fact = _non_oil_global_fact()
        fact["source_hash"] = (
            "f0e4c2f76c58916ec258f246851bea091d14d4247a2fc3e18694461b1816e13b"
        )
        fact["retrieved_at"] = "2026-08-02T00:00:00+00:00"
        return fact

    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [db_shaped_non_oil_fact()],
    )
    monkeypatch.setattr(
        api,
        "_load_non_oil_attribution_source_audit",
        lambda: _non_oil_attribution_audit_payload(),
    )

    response = TestClient(api.app).get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    body = response.json()
    payload = body["growth_cycle"]["cyclical_commodities_payload"]
    assert "non_oil_attribution_facts" not in payload
    assert "non_oil_attribution_source_audit" not in payload
    assert "source_hash" not in json.dumps(payload)
    assert "retrieved_at" not in json.dumps(payload)
    evidence = payload["non_oil_attribution_evidence"]
    assert evidence["copper"]["status"] == "available"
    assert evidence["copper"]["facts"][0]["geography"] == "Global"
    assert "source_hash" not in evidence["copper"]["facts"][0]
    assert "retrieved_at" not in evidence["copper"]["facts"][0]
    assert evidence["iron_ore"]["status"] == "unavailable"


def test_non_oil_detail_marks_facts_unavailable_when_refresh_failed(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    comex_rows = _copper_comex_abnormal_rows()

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_cot_observations",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_next_macro_event",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_approved_macro_event_tone",
        lambda con, event_type, as_of_date: None,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_latest_combined_fomc_policy_read",
        lambda con, as_of_date: None,
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: {
            sid: (comex_rows if sid == "copper_comex" else []) for sid in series_ids
        },
    )
    monkeypatch.setattr(api, "_load_attribution_catalog", lambda: None)
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_facts",
        lambda con: [_non_oil_global_fact()],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_non_oil_attribution_refresh_status",
        lambda con: [
            {
                "commodity_id": "copper",
                "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
                "status": "unavailable",
                "error_message": "faostat fetch failed",
                "refreshed_at": "2026-08-02T00:00:00+00:00",
            }
        ],
    )

    response = TestClient(api.app).get(
        "/api/macro-dashboard/growth-cycle/cyclical_commodities"
    )

    assert response.status_code == 200
    body = response.json()
    copper = body["non_oil_attribution_evidence"]["copper"]
    assert copper["status"] == "unavailable"
    assert "faostat fetch failed" in copper["reason"]
    assert copper["next_action"]
    assert copper["facts"] == []


def test_non_oil_market_setup_is_identical_when_returns_change(monkeypatch):
    from app import api

    class FakeCon(_FakeConStubs):
        pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations",
        lambda con, sid: [],
    )
    monkeypatch.setattr(
        api.market_phase,
        "build_dashboard_payload",
        lambda loader: None,
    )
    monkeypatch.setattr(
        api.benchmark_market_data,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.gdp_market_relationships,
        "connect",
        lambda: FakeCon(),
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_industry_rankings",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_at_a_glance_rows",
        lambda con: [],
    )
    monkeypatch.setattr(
        api.growth_cycle,
        "load_latest_ism_report_snapshot",
        lambda con: None,
    )

    original_loader = (
        api.macro_indicators_db.load_macro_indicator_observations_for_series
    )

    def changed_loader(con, series_ids, copper_rows):
        result = original_loader(con, series_ids)
        result["copper_comex"] = copper_rows
        return result

    baseline = _market_setup_payload()
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: changed_loader(
            con, series_ids, _copper_comex_normal_rows()
        ),
    )
    normal = _market_setup_payload()
    monkeypatch.setattr(
        api.macro_indicators_db,
        "load_macro_indicator_observations_for_series",
        lambda con, series_ids: changed_loader(
            con, series_ids, _copper_comex_abnormal_rows()
        ),
    )
    abnormal = _market_setup_payload()

    assert normal == baseline
    assert abnormal == baseline


def test_non_oil_ticker_workflow_output_has_no_field(monkeypatch):
    import json

    from app import api

    monkeypatch.setattr(
        api.tool_runner,
        "apply_tools",
        lambda method, observation_payload: observation_payload.get("observations", {}),
    )

    response = client.post(
        "/api/ticker-workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "" not in json.dumps(payload)


def _economic_confirmation_payload(as_of_timestamp):
    return {
        "as_of": as_of_timestamp,
        "method_version": "economic_confirmation_v1.0",
        "vintage_policy": "latest_official_vintage",
        "claims_confirmation": {
            "confirmation_status": "partial",
            "method_version": "claims_confirmation_v1.0",
        },
        "labor_context": {"role": "context_only", "data_status": "missing"},
        "real_activity": {
            "data_status": "missing",
            "method_status": "pending_approval",
            "confirmation_status": "unavailable",
            "unavailable_reason": "method_not_approved",
        },
        "event_risk": {"direction": "unknown", "next_event": None},
        "economic_confirmation": {
            "status": "limited_coverage",
            "based_on": ["claims_confirmation_v1.0"],
            "excluded_modules": [
                {"module": "esr_labor_context", "reason": "method_not_approved"},
                {"module": "real_activity", "reason": "method_not_approved"},
            ],
            "coverage": "claims_only",
            "approved_directional_modules": 1,
            "context_only_modules": 2,
        },
    }


def test_economic_confirmation_api_returns_limited_coverage_payload(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )
    captured = {}

    def fake_load_overview(con, macro_growth_context, as_of_timestamp):
        captured["macro_growth_context"] = macro_growth_context
        return _economic_confirmation_payload(as_of_timestamp)

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        fake_load_overview,
    )
    monkeypatch.setattr(
        macro_dashboard_router,
        "_survey_synthesis_direction",
        lambda con: {"status": "available", "expected_gdp_direction": "slowing"},
    )

    response = client.get("/api/macro-dashboard/economic-confirmation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["economic_confirmation"]["status"] == "limited_coverage"
    assert payload["real_activity"]["confirmation_status"] == "unavailable"
    assert captured["macro_growth_context"] == {"expected_gdp_direction": "slowing"}


def test_economic_confirmation_api_ignores_query_param_direction(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )
    captured = {}

    def fake_load_overview(con, macro_growth_context, as_of_timestamp):
        captured["macro_growth_context"] = macro_growth_context
        return _economic_confirmation_payload(as_of_timestamp)

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        fake_load_overview,
    )
    monkeypatch.setattr(
        macro_dashboard_router,
        "_survey_synthesis_direction",
        lambda con: {"status": "available", "expected_gdp_direction": "falling"},
    )

    response = client.get(
        "/api/macro-dashboard/economic-confirmation?expected_gdp_direction=growth_accelerating"
    )

    assert response.status_code == 200
    assert captured["macro_growth_context"] == {"expected_gdp_direction": "falling"}


def test_economic_confirmation_api_returns_400_for_value_error(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )

    def raising_load_overview(con, macro_growth_context, as_of_timestamp):
        raise ValueError("claims confirmation is unavailable")

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        raising_load_overview,
    )

    response = client.get("/api/macro-dashboard/economic-confirmation")

    assert response.status_code == 400
    assert response.json()["detail"] == "claims confirmation is unavailable"


def test_economic_confirmation_detail_api_returns_payload(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )
    captured = {}

    def fake_load_detail(con, macro_growth_context, as_of_timestamp):
        captured["macro_growth_context"] = macro_growth_context
        payload = _economic_confirmation_payload(as_of_timestamp)
        payload["vintage_policy"] = "point_in_time"
        return payload

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_detail",
        fake_load_detail,
    )
    monkeypatch.setattr(
        macro_dashboard_router,
        "_survey_synthesis_direction",
        lambda con: {"status": "available", "expected_gdp_direction": "improving"},
    )

    response = client.get("/api/macro-dashboard/economic-confirmation/detail")

    assert response.status_code == 200
    assert response.json()["economic_confirmation"]["status"] == "limited_coverage"
    assert captured["macro_growth_context"] == {"expected_gdp_direction": "improving"}
    assert "T" in response.json()["as_of"]
    assert response.json()["as_of"].endswith("+00:00")
    assert response.json()["vintage_policy"] == "point_in_time"


def test_economic_confirmation_detail_api_returns_400_for_value_error(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )

    def raising_load_detail(con, macro_growth_context, as_of_timestamp):
        raise ValueError("claims confirmation is unavailable")

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_detail",
        raising_load_detail,
    )

    response = client.get("/api/macro-dashboard/economic-confirmation/detail")

    assert response.status_code == 400
    assert response.json()["detail"] == "claims confirmation is unavailable"


def _labor_snapshot(series_id, value, source_url):
    return {
        "series_id": series_id,
        "reference_period": "2026-06",
        "value": value,
        "value_at_release": value,
        "latest_revised_value": None,
        "revision_number": 0,
        "release_date": "2026-07-02",
        "source_url": source_url,
    }


def _economic_confirmation_payload_with_labor(as_of_timestamp, vintage_policy):
    payload = _economic_confirmation_payload(as_of_timestamp)
    payload["vintage_policy"] = vintage_policy
    payload["labor_context"] = {
        "role": "context_only",
        "method_status": "pending_approval",
        "confirmation_status": "unavailable",
        "unavailable_reason": "method_not_approved",
        "data_status": "available",
        "metrics": {
            "nonfarm_payrolls_change": _labor_snapshot(
                "nonfarm_payrolls_change",
                57.0,
                "https://www.bls.gov/news.release/empsit.b.htm",
            ),
            "payrolls_3m_average_change": _labor_snapshot(
                "payrolls_3m_average_change",
                111.0,
                "https://www.bls.gov/news.release/empsit.b.htm",
            ),
            "unemployment_rate": _labor_snapshot(
                "unemployment_rate",
                4.2,
                "https://www.bls.gov/news.release/empsit.a.htm",
            ),
            "average_weekly_hours": _labor_snapshot(
                "average_weekly_hours",
                34.3,
                "https://www.bls.gov/news.release/empsit.b.htm",
            ),
            "average_hourly_earnings": _labor_snapshot(
                "average_hourly_earnings",
                37.64,
                "https://www.bls.gov/news.release/empsit.b.htm",
            ),
        },
    }
    return payload


def test_economic_confirmation_routes_serve_html_labor_snapshots(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )

    def fake_load_overview(con, macro_growth_context, as_of_timestamp):
        return _economic_confirmation_payload_with_labor(
            as_of_timestamp, "latest_official_vintage"
        )

    def fake_load_detail(con, macro_growth_context, as_of_timestamp):
        return _economic_confirmation_payload_with_labor(
            as_of_timestamp, "point_in_time"
        )

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        fake_load_overview,
    )
    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_detail",
        fake_load_detail,
    )
    monkeypatch.setattr(
        macro_dashboard_router,
        "_survey_synthesis_direction",
        lambda con: {"status": "available", "expected_gdp_direction": "slowing"},
    )

    overview = client.get("/api/macro-dashboard/economic-confirmation")
    detail = client.get("/api/macro-dashboard/economic-confirmation/detail")

    assert overview.status_code == 200
    assert detail.status_code == 200
    assert overview.json()["vintage_policy"] == "latest_official_vintage"
    assert detail.json()["vintage_policy"] == "point_in_time"
    detail_labor = detail.json()["labor_context"]
    assert detail_labor["data_status"] == "available"
    assert detail_labor["confirmation_status"] == "unavailable"
    assert detail_labor["metrics"]["nonfarm_payrolls_change"]["value"] == 57.0
    assert detail_labor["metrics"]["payrolls_3m_average_change"]["value"] == 111.0
    assert detail_labor["metrics"]["unemployment_rate"]["value"] == 4.2
    assert detail_labor["metrics"]["average_weekly_hours"]["value"] == 34.3
    assert detail_labor["metrics"]["average_hourly_earnings"]["release_date"] == (
        "2026-07-02"
    )
    assert detail.json()["economic_confirmation"]["coverage"] == "claims_only"


def test_market_setup_api_returns_the_v2_layered_contract(monkeypatch):
    from app import api
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.market_setup_v2,
        "build_market_setup_v2",
        lambda **kwargs: {
            "version": "market_setup_v2",
            "macro_regime": {"code": "growth_decelerating"},
            "market_confirmation": {"code": "not_confirming_downside"},
            "market_setup": {"code": "macro_weakening_price_not_confirming"},
            "portfolio_posture": {"code": "neutral_selective"},
        },
    )
    response = TestClient(api.app).get("/api/macro-dashboard/market-setup")
    assert response.status_code == 200
    assert response.json()["version"] == "market_setup_v2"
    assert "setup_type" not in response.json()
    assert "market_conclusion" not in response.json()


def test_macro_growth_context_uses_lightweight_survey_synthesis(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    calls = []

    monkeypatch.setattr(
        macro_dashboard_router,
        "macro_dashboard_growth_cycle",
        lambda: calls.append("growth_cycle") or {
            "headline": [{"id": "survey_synthesis", "expected_gdp_direction": "rising"}]
        },
    )
    monkeypatch.setattr(
        macro_dashboard_router,
        "_survey_synthesis_direction",
        lambda con: calls.append("survey_synthesis_direction") or {
            "status": "available",
            "expected_gdp_direction": "falling",
        },
    )

    result = macro_dashboard_router._macro_growth_context(type("C", (), {})())
    assert result == {"expected_gdp_direction": "falling"}
    assert "survey_synthesis_direction" in calls
    assert "growth_cycle" not in calls


def test_economic_confirmation_endpoint_caches_overview(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation,
        "connect",
        lambda: type("C", (_FakeConStubs,), {})(),
    )
    calls = []

    def fake_load_overview(con, macro_growth_context, as_of_timestamp):
        calls.append(as_of_timestamp)
        return _economic_confirmation_payload(as_of_timestamp)

    monkeypatch.setattr(
        macro_dashboard_router.economic_confirmation_dashboard,
        "load_overview",
        fake_load_overview,
    )
    monkeypatch.setattr(
        macro_dashboard_router,
        "_survey_synthesis_direction",
        lambda con: {"status": "available", "expected_gdp_direction": "slowing"},
    )

    r1 = client.get("/api/macro-dashboard/economic-confirmation")
    r2 = client.get("/api/macro-dashboard/economic-confirmation")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert len(calls) == 1


def test_market_phase_refresh_invalidates_cache(monkeypatch):
    from app.routers import macro_dashboard as macro_dashboard_router

    build_calls = []

    def fake_build_dashboard_payload(loader, benchmark_ids):
        build_calls.append("build")
        return {"price_load_count": len(build_calls)}

    monkeypatch.setattr(
        macro_dashboard_router.market_phase,
        "build_dashboard_payload",
        fake_build_dashboard_payload,
    )
    monkeypatch.setattr(
        macro_dashboard_router.benchmark_market_data_tool,
        "refresh_benchmarks",
        lambda ids: [{"benchmark_id": ids[0], "status": "ok"}],
    )

    r1 = client.get("/api/macro-dashboard/market-phase")
    r2 = client.get("/api/macro-dashboard/market-phase")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert len(build_calls) == 1

    refresh = client.post("/api/macro-dashboard/market-phase/us_sp500/refresh")
    assert refresh.status_code == 200

    r3 = client.get("/api/macro-dashboard/market-phase")
    assert r3.status_code == 200
    assert r3.json()["price_load_count"] == 2
