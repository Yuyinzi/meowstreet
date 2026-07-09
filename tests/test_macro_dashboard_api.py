from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_macro_dashboard_page_routes_are_served():
    response = client.get("/macro-dashboard.html")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_market_phase_api_returns_lightweight_market_overview(monkeypatch):
    from app import api

    def fake_connect():
        class FakeConnection:
            def close(self):
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
        class FakeConnection:
            def close(self):
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
        class FakeConnection:
            def close(self):
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


def test_gdp_relationship_overview_api_is_lightweight(monkeypatch):
    from app import api

    class FakeConnection:
        def close(self):
            pass

    def fake_connect():
        return FakeConnection()

    def fake_load_relationships(con):
        return [
            {
                "relationship_id": "us_sp500_gdp",
                "title": "S&P 500 vs US GDP",
                "region": "US",
                "economy": "US GDP",
                "index_name": "S&P 500",
                "primary_lag_months": 6,
                "correlation_window_years": 10,
                "source_workbook": "GDP_Correlations.xlsx",
                "source_sheet": "S&P500_USGDP Correlation",
            },
            {
                "relationship_id": "china_sse_gdp",
                "title": "SSE Composite vs China GDP",
                "region": "China",
                "economy": "China GDP",
                "index_name": "SSE Composite",
                "primary_lag_months": 6,
                "correlation_window_years": 10,
                "source_workbook": "GDP_Correlations.xlsx",
                "source_sheet": "China GDP Correlation",
            },
            {
                "relationship_id": "europe_stoxx_gdp",
                "title": "STOXX Europe vs Europe GDP",
                "region": "Europe",
                "economy": "Europe GDP",
                "index_name": "STOXX Europe",
                "primary_lag_months": 6,
                "correlation_window_years": 10,
                "source_workbook": "GDP_Correlations.xlsx",
                "source_sheet": "Europe GDP Correlation",
            },
        ]

    def fake_load_lag_rows(con, relationship_id):
        return [
            {
                "date": "2020-06-30",
                "lag_months": 6,
                "index_yoy": 0.29,
                "gdp_yoy": -0.09,
                "rolling_correlation": -0.09,
            }
        ]

    def fake_load_quad_rows(con, relationship_id):
        return [
            {
                "date": "2020-09-30",
                "period_label": "2020 Q3",
                "quad_case": "0,1",
                "index_direction": 0,
                "gdp_direction": 1,
            }
        ]

    monkeypatch.setattr(api.gdp_market_relationships, "connect", fake_connect)
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_relationships", fake_load_relationships
    )
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_lag_rows", fake_load_lag_rows
    )
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_quad_rows", fake_load_quad_rows
    )

    response = client.get("/api/macro-dashboard/gdp-relationships")

    assert response.status_code == 200
    payload = response.json()
    assert [r["relationship_id"] for r in payload["relationships"]] == ["us_sp500_gdp"]
    assert payload["relationships"][0]["relationship_id"] == "us_sp500_gdp"
    assert "lag_series" not in payload["relationships"][0]


def test_gdp_relationship_detail_api_returns_one_relationship(monkeypatch):
    from app import api

    class FakeConnection:
        def close(self):
            pass

    def fake_connect():
        return FakeConnection()

    def fake_load_relationships(con):
        return [
            {
                "relationship_id": "us_sp500_gdp",
                "title": "S&P 500 vs US GDP",
                "region": "US",
                "economy": "US GDP",
                "index_name": "S&P 500",
                "primary_lag_months": 6,
                "correlation_window_years": 10,
                "source_workbook": "GDP_Correlations.xlsx",
                "source_sheet": "S&P500_USGDP Correlation",
            }
        ]

    def fake_load_lag_rows(con, relationship_id):
        return [
            {
                "date": "2020-06-30",
                "lag_months": 6,
                "index_yoy": 0.29,
                "gdp_yoy": -0.09,
                "rolling_correlation": -0.09,
            }
        ]

    def fake_load_quad_rows(con, relationship_id):
        return [
            {
                "date": "2020-09-30",
                "period_label": "2020 Q3",
                "quad_case": "0,1",
                "index_direction": 0,
                "gdp_direction": 1,
            }
        ]

    monkeypatch.setattr(api.gdp_market_relationships, "connect", fake_connect)
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_relationships", fake_load_relationships
    )
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_lag_rows", fake_load_lag_rows
    )
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_quad_rows", fake_load_quad_rows
    )

    response = client.get("/api/macro-dashboard/gdp-relationships/us_sp500_gdp")

    assert response.status_code == 200
    payload = response.json()
    assert payload["relationship_id"] == "us_sp500_gdp"
    assert "lag_series" in payload


def test_gdp_relationship_detail_api_returns_400_for_unknown_relationship(monkeypatch):
    from app import api

    class FakeConnection:
        def close(self):
            pass

    monkeypatch.setattr(
        api.gdp_market_relationships, "connect", lambda: FakeConnection()
    )
    monkeypatch.setattr(
        api.gdp_market_relationships, "load_relationships", lambda con: []
    )

    response = client.get("/api/macro-dashboard/gdp-relationships/unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "relationship is unknown: unknown"


def test_us_rates_liquidity_api_returns_dashboard_payload(monkeypatch):
    from app import api

    class FakeConnection:
        def close(self):
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
        api.us_rates_liquidity_db,
        "load_latest_macro_indicator_points",
        fake_load_latest_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_rate_points_for_series",
        fake_load_rate_points_for_series,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
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

    class FakeConnection:
        def close(self):
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

    class FakeConnection:
        def close(self):
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
        lambda: type("C", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(api.us_rates_liquidity_db, "load_rate_series", lambda con: [])
    monkeypatch.setattr(
        api.us_rates_liquidity_db, "load_rate_points_for_series", lambda con, sids: {}
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
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

    class FakeCon:
        def close(self):
            pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    card = payload["headline"][0]
    assert card["id"] == "m2_money_supply"
    assert card["label"] == "M2 Money Supply"
    assert card["period"] == "2026-06-01"
    assert card["state"]["m2_money_stock"] == 112.0
    assert card["change"]["m2_3m_momentum"] is not None
    assert payload["missing"] is None


def test_growth_cycle_m2_detail_api_returns_chart_payload(monkeypatch):
    from app import api

    class FakeCon:
        def close(self):
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
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        fake_load,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_ai_interpretation",
        lambda con, scope, snapshot_hash: None,
    )

    response = client.get("/api/macro-dashboard/growth-cycle/m2_money_supply")

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail_id"] == "m2_money_supply"
    assert payload["title"] == "M2 Money Supply"
    assert len(payload["charts"]) == 3
    assert payload["charts"][0]["kind"] == "time_series"
    assert payload["m2_ai_interpretation"]["text_en"] is not None
    assert "generator" in payload["m2_ai_interpretation"]["text_en"]


def test_growth_cycle_detail_api_rejects_unknown_detail():
    response = client.get("/api/macro-dashboard/growth-cycle/unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "growth cycle detail is unknown: unknown"


def test_growth_cycle_m2_detail_api_attaches_stored_ai_interpretation(monkeypatch):
    from app import api

    class FakeCon:
        def close(self):
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
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        fake_load,
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


def test_growth_cycle_api_returns_missing_payload_when_m2_db_rows_are_missing(
    monkeypatch,
):
    from app import api

    class FakeCon:
        def close(self):
            pass

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        lambda con, series_id: [],
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    assert response.json() == {
        "headline": [],
        "missing": "No M2 money supply data found. Run scripts/import_m2_money_supply.py.",
    }


def test_growth_cycle_api_returns_inflation_context_card(monkeypatch):
    from app import api

    class FakeCon:
        def close(self):
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
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    payload = response.json()
    card_ids = [card["id"] for card in payload["headline"]]
    assert card_ids == ["m2_money_supply", "inflation_context", "gdp_expectations"]
    inflation = payload["headline"][1]
    assert inflation["label"] == "Inflation Context"
    assert inflation["status"] == "above_target"
    assert round(inflation["core_pce_yoy"], 4) == 0.0308
    assert round(inflation["gap"], 4) == 0.0108
    gdp_expectations = payload["headline"][2]
    assert gdp_expectations["label"] == "GDP Expectations"
    assert gdp_expectations["status"] == "pending_inputs"
    assert gdp_expectations["expected_direction"] is None


def test_growth_cycle_api_keeps_m2_when_inflation_context_is_missing(monkeypatch):
    from app import api

    class FakeCon:
        def close(self):
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
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )

    response = client.get("/api/macro-dashboard/growth-cycle")

    assert response.status_code == 200
    assert [card["id"] for card in response.json()["headline"]] == [
        "m2_money_supply",
        "gdp_expectations",
    ]


def test_growth_cycle_m2_detail_api_includes_core_pce_comparison(monkeypatch):
    from app import api

    class FakeCon:
        def close(self):
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
        raise AssertionError(series_id)

    monkeypatch.setattr(api.us_rates_liquidity_db, "connect", lambda: FakeCon())
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_macro_indicator_points",
        fake_load_macro_indicator_points,
    )
    monkeypatch.setattr(
        api.us_rates_liquidity_db,
        "load_ai_interpretation",
        lambda con, scope, snapshot_hash: None,
    )

    response = client.get("/api/macro-dashboard/growth-cycle/m2_money_supply")

    assert response.status_code == 200
    chart = response.json()["charts"][0]
    assert chart["title"] == "M2 YoY Growth vs Inflation Constraint"
    assert chart["keys"] == ["m2_yoy", "core_pce_yoy", "fed_target"]
