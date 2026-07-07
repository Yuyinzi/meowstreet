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
        return {}

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

    response = client.get("/api/macro-dashboard/us-rates-liquidity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of"] == "2021-01-03"
    assert payload["derived"]["tens_twos_spread"] == 0.81
    assert payload["derived"]["cpi_based_real_rate"] == -0.47


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
