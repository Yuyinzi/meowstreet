import json
import logging
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app import tool_runner
from app.db import benchmark_market_data, consumer_sentiment, gdp_market_relationships
from app.db import growth_cycle
from app.db import macro_indicators as macro_indicators_db
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.routers import (
    macro_dashboard as macro_dashboard_router,
    static_files as static_files_router,
    ticker_workflow as ticker_workflow_router,
)
from app.services import consumer_sentiment_dashboard
from app.tools import benchmark_market_data as benchmark_market_data_tool
from app.tools import (
    ism_industry_analysis,
    ism_official_report,
    macro_growth_cycle,
    market_phase,
    market_setup,
    us_rates_liquidity,
)
from app.routers.macro_dashboard import macro_dashboard_market_setup

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
METHOD_PATH = ROOT / "data" / "local_system" / "synthesis" / "method.v1.json"

US_BENCHMARK_IDS = ["us_sp500", "us_nasdaq_100", "us_nasdaq_composite", "us_djia"]

ISM_MANUFACTURING_SERIES_IDS = [
    "ism_manufacturing_pmi",
    "ism_manufacturing_new_orders",
    "ism_manufacturing_production",
    "ism_manufacturing_employment",
    "ism_manufacturing_supplier_deliveries",
    "ism_manufacturing_inventories",
    "ism_manufacturing_customer_inventories",
    "ism_manufacturing_prices",
    "ism_manufacturing_order_backlog",
    "ism_manufacturing_exports",
    "ism_manufacturing_imports",
]

NFIB_SERIES_IDS = [
    "nfib_sbo_optimism",
    "nfib_sbo_employment_plans",
    "nfib_sbo_expansion_outlook",
    "nfib_sbo_inventory_plans",
    "nfib_sbo_economic_expectations",
    "nfib_sbo_real_sales_expectations",
    "nfib_sbo_capital_outlay_plans",
    "nfib_sbo_current_inventory_low",
    "nfib_sbo_job_openings",
    "nfib_sbo_credit_conditions_expectations",
    "nfib_sbo_earnings_trends",
]

_OBSERVATION_SERIES_IDS = [
    "usd_broad",
    "usd_afe",
    "usd_eme",
    "cpi_all_items",
    "core_cpi",
    "ppi_all_commodities",
]

_OIL_SERIES_IDS = [
    "oil_wti_spot",
    "oil_brent_spot",
    "oil_commercial_crude_stocks",
    "oil_commercial_crude_imports",
    "oil_crude_production",
    "oil_refinery_crude_input",
    "oil_petroleum_products_supplied",
]

method_COMMODITY_SERIES_IDS = [
    "copper_comex",
    "copper_lme",
    "copper_shanghai",
    "iron_ore_62_cfr_china",
    "iron_ore_dce",
    "lumber_cme_lbr_yahoo_v1",
]


def _load_market_phase_for_setup():
    try:
        con = benchmark_market_data.connect()
    except (ValueError, TypeError, RuntimeError):
        logging.warning(
            "benchmark market data connect failed for market setup", exc_info=True
        )
        return None
    try:
        return market_phase.build_dashboard_payload(
            lambda benchmark_id: benchmark_market_data.load_price_rows(
                con, benchmark_id
            ),
            benchmark_ids=US_BENCHMARK_IDS,
        )
    except (ValueError, TypeError, RuntimeError):
        logging.warning("market phase load failed for market setup", exc_info=True)
        return None
    finally:
        con.close()


def _load_rates_liquidity_for_setup(con):
    try:
        latest_points = us_rates_liquidity_db.load_latest_points(con)
        if not latest_points:
            return None
        latest_macro = macro_indicators_db.load_latest_macro_indicator_points(con)
        credit_rate_points = us_rates_liquidity_db.load_rate_points_for_series(
            con, ["treasury_10y"]
        )
        credit_macro_points = (
            macro_indicators_db.load_macro_indicator_points_for_series(
                con,
                ["aaa_corporate_yield", "bbb_corporate_yield", "ccc_corporate_yield"],
            )
        )
        return us_rates_liquidity.build_dashboard_payload(
            us_rates_liquidity_db.load_rate_series(con),
            latest_points,
            latest_macro,
            credit_rate_points=credit_rate_points,
            credit_macro_points=credit_macro_points,
            credit_macro_series_points=credit_macro_points,
        )
    except (ValueError, TypeError, RuntimeError):
        logging.warning("rates liquidity load failed for market setup", exc_info=True)
        return None


def _load_ism_industry_analysis_for_setup(con, latest_ism_report, ism_at_a_glance):
    if not latest_ism_report:
        return None
    report_id = latest_ism_report["report_id"]
    try:
        signals = growth_cycle.load_ism_report_industry_signals(con, report_id)
        coverage = growth_cycle.load_ism_report_industry_signal_coverage(con, report_id)
        payload = ism_industry_analysis.build_ism_industry_analysis(
            latest_ism_report, signals, coverage, ism_at_a_glance, []
        )
        if payload.get("industries"):
            recent_reports = growth_cycle.load_recent_ism_report_snapshots(con, limit=6)
            report_ids = [r["report_id"] for r in recent_reports]
            hist_signals = growth_cycle.load_ism_report_industry_signals_for_reports(
                con, report_ids
            )
            hist_coverage = (
                growth_cycle.load_ism_report_industry_signal_coverage_for_reports(
                    con, report_ids
                )
            )
            history = ism_industry_analysis.build_ism_industry_history(
                recent_reports, hist_signals, hist_coverage, []
            )
            for ind in payload["industries"]:
                ind_history = history.get(ind["industry"], {})
                ind["trend"] = ind_history.get("trend", [])
                ind["trend_summary"] = ind_history.get(
                    "trend_summary",
                    {
                        "latest_score_change": None,
                        "positive_month_streak": 0,
                        "negative_month_streak": 0,
                        "broad_confirmation_streak": 0,
                        "eligible_month_count": 0,
                        "requested_month_count": 0,
                    },
                )
        return payload
    except (ValueError, TypeError, RuntimeError):
        return None


def _load_latest_ism_industry_breadth(con, latest_ism_report=None):
    try:
        report = latest_ism_report or growth_cycle.load_latest_ism_report_snapshot(con)
    except AttributeError:
        report = None
    if report:
        snapshot = growth_cycle.load_ism_report_source_snapshot(
            con,
            report["source_url"],
        )
        if snapshot:
            try:
                report_text = ism_official_report.extract_report_text(
                    snapshot["raw_html"],
                    snapshot["source_name"],
                )
                rankings = ism_official_report.parse_rankings(
                    ism_official_report.normalize_text(report_text),
                    report["report_month"],
                )
                return macro_growth_cycle.build_ism_industry_breadth_summary(rankings)
            except ValueError:
                pass
    return macro_growth_cycle.build_ism_industry_breadth_summary(
        growth_cycle.load_latest_ism_industry_rankings(con)
    )


def load_workflow_method():
    if not METHOD_PATH.exists():
        raise HTTPException(
            status_code=500, detail=f"missing method artifact: {METHOD_PATH}"
        )
    return json.loads(METHOD_PATH.read_text(encoding="utf-8"))


app = FastAPI(title="Meowstreet")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(static_files_router.router)
app.include_router(ticker_workflow_router.router)
app.include_router(macro_dashboard_router.router)
