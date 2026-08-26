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
    market_assistant as market_assistant_router,
    pair_analysis as pair_analysis_router,
    portfolio_analysis as portfolio_analysis_router,
    quant_screen as quant_screen_router,
    static_files as static_files_router,
    ticker_context as ticker_context_router,
    ticker_quant as ticker_quant_router,
    ticker_workflow as ticker_workflow_router,
)
from app.services import consumer_sentiment_dashboard
from app.services import commodity_attribution_catalog
from app.services import cot_historical_extremes_catalog
from app.services import non_oil_attribution_source_audit
from app.tools import benchmark_market_data as benchmark_market_data_tool
from app.tools import (
    ism_industry_analysis,
    ism_official_report,
    macro_growth_cycle,
    market_phase,
    market_setup,
    market_setup_v2,
    us_rates_liquidity,
)
from app.routers.macro_dashboard import macro_dashboard_market_setup
from app.resources import resource_path

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
METHOD_PATH = resource_path("workflow_method")
ATTRIBUTION_CATALOG_PATH = resource_path("commodity_attribution_catalog")
NON_OIL_ATTRIBUTION_SOURCE_AUDIT_PATH = (
    resource_path("attribution_source_audit")
)
COT_HISTORICAL_EXTREME_ALLOWLIST_PATH = (
    resource_path("cot_extreme_allowlist")
)

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

OBSERVATION_SERIES_IDS = [
    "usd_broad",
    "usd_afe",
    "usd_eme",
    "cpi_all_items",
    "core_cpi",
    "ppi_all_commodities",
]

OIL_SERIES_IDS = [
    "oil_wti_spot",
    "oil_brent_spot",
    "oil_commercial_crude_stocks",
    "oil_commercial_crude_imports",
    "oil_crude_production",
    "oil_refinery_crude_input",
    "oil_petroleum_products_supplied",
]

COMMODITY_SERIES_IDS = [
    "copper_comex",
    "copper_lme",
    "copper_shanghai",
    "iron_ore_62_cfr_china",
    "iron_ore_dce",
    "lumber_cme_lbr_yahoo_v1",
]


def _load_attribution_catalog():
    try:
        return commodity_attribution_catalog.load_commodity_attribution_catalog(
            ATTRIBUTION_CATALOG_PATH
        )
    except (ValueError, TypeError, RuntimeError, OSError):
        logging.warning("commodities attribution catalog load failed", exc_info=True)
        return None


def _load_non_oil_attribution_source_audit():
    try:
        return non_oil_attribution_source_audit.load_non_oil_attribution_source_audit(
            NON_OIL_ATTRIBUTION_SOURCE_AUDIT_PATH, ATTRIBUTION_CATALOG_PATH
        )
    except (ValueError, TypeError, RuntimeError, OSError):
        logging.warning(
            "commodities non-oil attribution source audit load failed", exc_info=True
        )
        return None


def _load_cot_historical_extreme_allowlist():
    try:
        return cot_historical_extremes_catalog.load_cot_historical_extreme_allowlist(
            COT_HISTORICAL_EXTREME_ALLOWLIST_PATH
        )
    except (ValueError, TypeError, RuntimeError, OSError):
        logging.warning(
            "commodities cot historical extreme allowlist load failed", exc_info=True
        )
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
app.include_router(market_assistant_router.router)
app.include_router(ticker_context_router.router)
app.include_router(pair_analysis_router.router)
app.include_router(portfolio_analysis_router.router)
app.include_router(quant_screen_router.router)
app.include_router(ticker_quant_router.router)
