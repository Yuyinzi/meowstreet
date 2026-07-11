import json
from datetime import date
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import tool_runner, workflow_engine
from app.db import benchmark_market_data, gdp_market_relationships
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.tools import benchmark_market_data as benchmark_market_data_tool
from app.tools import (
    gdp_market_relationship,
    macro_growth_cycle,
    market_phase,
    us_rates_liquidity,
)

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
METHOD_PATH = ROOT / "data" / "local_system" / "synthesis" / "method.v1.json"

app = FastAPI(title="Meowstreet")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _us_gdp_relationships(relationships):
    return [
        relationship
        for relationship in relationships
        if str(relationship.get("region", "")).lower() == "us"
    ]


def load_workflow_method():
    if not METHOD_PATH.exists():
        raise HTTPException(
            status_code=500, detail=f"missing method artifact: {METHOD_PATH}"
        )
    return json.loads(METHOD_PATH.read_text(encoding="utf-8"))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "method-system.html")


@app.get("/method-system.html")
def local_system_html():
    return FileResponse(STATIC_DIR / "method-system.html")


@app.get("/method-system.css")
def local_system_css():
    return FileResponse(STATIC_DIR / "method-system.css", media_type="text/css")


@app.get("/method-system.js")
def local_system_js():
    return FileResponse(
        STATIC_DIR / "method-system.js", media_type="application/javascript"
    )


@app.get("/api/method-system/method")
def method():
    return load_workflow_method()


@app.post("/api/method-system/workflow/evaluate")
def workflow_evaluate(body: dict = Body(default={})):
    try:
        return workflow_engine.evaluate_workflow_method(
            load_workflow_method(),
            body,
            tool_runner=tool_runner.apply_tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/macro-dashboard.html")
def macro_dashboard_html():
    return FileResponse(STATIC_DIR / "macro-dashboard.html")


@app.get("/macro-dashboard.css")
def macro_dashboard_css():
    return FileResponse(STATIC_DIR / "macro-dashboard.css", media_type="text/css")


@app.get("/macro-dashboard.js")
def macro_dashboard_js():
    return FileResponse(
        STATIC_DIR / "macro-dashboard.js", media_type="application/javascript"
    )


@app.get("/api/macro-dashboard/market-phase")
def macro_dashboard_market_phase():
    con = benchmark_market_data.connect()
    try:
        return market_phase.build_dashboard_payload(
            lambda benchmark_id: benchmark_market_data.load_price_rows(
                con, benchmark_id
            )
        )
    finally:
        con.close()


@app.get("/api/macro-dashboard/market-phase/{benchmark_id}")
def macro_dashboard_market_phase_detail(benchmark_id):
    con = benchmark_market_data.connect()
    try:
        return market_phase.build_market_phase_payload(
            benchmark_id,
            benchmark_market_data.load_price_rows(con, benchmark_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


@app.post("/api/macro-dashboard/market-phase/{benchmark_id}/refresh")
def macro_dashboard_market_phase_refresh(benchmark_id):
    try:
        results = benchmark_market_data_tool.refresh_benchmarks([benchmark_id])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return results[0]


@app.get("/api/macro-dashboard/gdp-relationships")
def macro_dashboard_gdp_relationships():
    con = gdp_market_relationships.connect()
    try:
        relationships = gdp_market_relationships.load_relationships(con)
        return gdp_market_relationship.build_overview_payload(
            _us_gdp_relationships(relationships),
            lambda relationship_id: gdp_market_relationships.load_lag_rows(
                con, relationship_id
            ),
            lambda relationship_id: gdp_market_relationships.load_quad_rows(
                con, relationship_id
            ),
        )
    finally:
        con.close()


@app.get("/api/macro-dashboard/gdp-relationships/{relationship_id}")
def macro_dashboard_gdp_relationship_detail(relationship_id):
    con = gdp_market_relationships.connect()
    try:
        relationships = gdp_market_relationships.load_relationships(con)
        relationship = next(
            (
                item
                for item in relationships
                if item["relationship_id"] == relationship_id
            ),
            None,
        )
        if not relationship:
            raise ValueError(f"relationship is unknown: {relationship_id}")
        return gdp_market_relationship.build_detail_payload(
            relationship,
            gdp_market_relationships.load_lag_rows(con, relationship_id),
            gdp_market_relationships.load_quad_rows(con, relationship_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


@app.get("/api/macro-dashboard/growth-cycle")
def macro_dashboard_growth_cycle():
    con = us_rates_liquidity_db.connect()
    try:
        rows = us_rates_liquidity_db.load_macro_indicator_points(con, "m2_money_stock")
        if not rows:
            return {
                "headline": [],
                "missing": "No M2 money supply data found. Run scripts/import_m2_money_supply.py.",
            }
        core_pce_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "core_pce_price_index",
        )
        fed_total_assets_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "fed_total_assets",
        )
        fed_treasury_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "fed_treasury_holdings",
        )
        fed_mbs_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "fed_mbs_holdings",
        )
        m2_money_stock = {
            "series": [{"date": row["date"], "value": row["value"]} for row in rows]
        }
        core_pce_price_index = {
            "series": [
                {"date": row["date"], "value": row["value"]} for row in core_pce_rows
            ]
        }
        fed_total_assets = {
            "series": [
                {"date": row["date"], "value": row["value"]}
                for row in fed_total_assets_rows
            ]
        }
        fed_treasury_holdings = {
            "series": [
                {"date": row["date"], "value": row["value"]}
                for row in fed_treasury_rows
            ]
        }
        fed_mbs_holdings = {
            "series": [
                {"date": row["date"], "value": row["value"]} for row in fed_mbs_rows
            ]
        }
        dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
            m2_money_stock=m2_money_stock,
            core_pce_price_index=core_pce_price_index if core_pce_rows else None,
            fed_total_assets=fed_total_assets if fed_total_assets_rows else None,
            fed_treasury_holdings=fed_treasury_holdings if fed_treasury_rows else None,
            fed_mbs_holdings=fed_mbs_holdings if fed_mbs_rows else None,
        )
        next_fomc_meeting = us_rates_liquidity_db.load_next_macro_event(
            con,
            "fomc_meeting",
            date.today().isoformat(),
        )
        as_of_date = date.today().isoformat()
        fomc_latest_tone = us_rates_liquidity_db.load_latest_combined_fomc_policy_read(
            con,
            as_of_date,
        )
        if not fomc_latest_tone:
            fomc_latest_tone = (
                us_rates_liquidity_db.load_latest_approved_macro_event_tone(
                    con,
                    "fomc_meeting",
                    as_of_date,
                )
            )
        return macro_growth_cycle.build_growth_cycle_dashboard_payload(
            dashboard,
            next_fomc_meeting=next_fomc_meeting,
            fomc_latest_tone=fomc_latest_tone,
        )
    finally:
        con.close()


@app.get("/api/macro-dashboard/growth-cycle/{detail_id}")
def macro_dashboard_growth_cycle_detail(detail_id):
    if detail_id != "m2_money_supply":
        raise HTTPException(
            status_code=400,
            detail=f"growth cycle detail is unknown: {detail_id}",
        )
    con = us_rates_liquidity_db.connect()
    try:
        rows = us_rates_liquidity_db.load_macro_indicator_points(con, "m2_money_stock")
        core_pce_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "core_pce_price_index",
        )
        fed_total_assets_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "fed_total_assets",
        )
        fed_treasury_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "fed_treasury_holdings",
        )
        fed_mbs_rows = us_rates_liquidity_db.load_macro_indicator_points(
            con,
            "fed_mbs_holdings",
        )
        fomc_events = us_rates_liquidity_db.load_macro_events_with_latest_tone(
            con, "fomc_meeting"
        )
        detail_payload = macro_growth_cycle.build_m2_money_supply_detail_payload(
            rows,
            core_pce_rows=core_pce_rows,
            fed_total_assets_rows=fed_total_assets_rows,
            fed_treasury_rows=fed_treasury_rows,
            fed_mbs_rows=fed_mbs_rows,
            fomc_events=fomc_events,
        )
        dashboard_payload = macro_growth_cycle.build_growth_cycle_dashboard(
            m2_money_stock={"series": rows}
        )
        headline = dashboard_payload["macro"]["growth_cycle"]
        m2_headline = macro_growth_cycle.build_m2_money_supply_headline(headline)
        snapshot = macro_growth_cycle.m2_interpretation_snapshot(
            m2_headline, detail_payload
        )
        detail_payload["m2_interpretation_snapshot"] = snapshot
        detail_payload["m2_ai_interpretation"] = (
            us_rates_liquidity_db.load_ai_interpretation(
                con,
                snapshot["scope"],
                snapshot["hash"],
            )
            or macro_growth_cycle.m2_fallback_interpretation(m2_headline)
        )
        return detail_payload
    finally:
        con.close()


@app.get("/api/macro-dashboard/us-rates-liquidity")
def macro_dashboard_us_rates_liquidity():
    con = us_rates_liquidity_db.connect()
    try:
        latest_points = us_rates_liquidity_db.load_latest_points(con)
        latest_macro = us_rates_liquidity_db.load_latest_macro_indicator_points(con)
        credit_rate_points = us_rates_liquidity_db.load_rate_points_for_series(
            con, ["treasury_10y"]
        )
        credit_macro_points = (
            us_rates_liquidity_db.load_macro_indicator_points_for_series(
                con,
                ["aaa_corporate_yield", "bbb_corporate_yield", "ccc_corporate_yield"],
            )
        )
        payload = us_rates_liquidity.build_dashboard_payload(
            us_rates_liquidity_db.load_rate_series(con),
            latest_points,
            latest_macro,
            credit_rate_points=credit_rate_points,
            credit_macro_points=credit_macro_points,
            credit_macro_series_points=credit_macro_points,
        )
        snapshot = payload.get("credit_interpretation_snapshot", {})
        payload["credit_ai_interpretation"] = (
            us_rates_liquidity_db.load_ai_interpretation(
                con,
                snapshot.get("scope"),
                snapshot.get("hash"),
            )
            if snapshot.get("scope") and snapshot.get("hash")
            else None
        )
        return payload
    finally:
        con.close()


@app.get("/api/macro-dashboard/us-rates-liquidity/{detail_id}")
def macro_dashboard_us_rates_liquidity_detail(
    detail_id,
    nominalCurrentDate=None,
    nominalComparisonDate=None,
    realCurrentDate=None,
    realComparisonDate=None,
):
    con = us_rates_liquidity_db.connect()
    try:
        series_ids = us_rates_liquidity.detail_series_ids(detail_id)
        rate_series_ids = [
            series_id
            for series_id in series_ids
            if not series_id.startswith(("cpi_", "vix", "aaa_", "bbb_", "ccc_"))
        ]
        macro_series_ids = [
            series_id
            for series_id in series_ids
            if series_id.startswith(("cpi_", "vix", "aaa_", "bbb_", "ccc_"))
        ]
        points_by_id = us_rates_liquidity_db.load_rate_points_for_series(
            con,
            rate_series_ids,
        )
        points_by_id.update(
            us_rates_liquidity_db.load_macro_indicator_points_for_series(
                con,
                macro_series_ids,
            )
        )
        return us_rates_liquidity.build_detail_payload(
            detail_id,
            us_rates_liquidity_db.load_rate_series(con),
            points_by_id,
            {
                "nominal_current_date": nominalCurrentDate,
                "nominal_comparison_date": nominalComparisonDate,
                "real_current_date": realCurrentDate,
                "real_comparison_date": realComparisonDate,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()
