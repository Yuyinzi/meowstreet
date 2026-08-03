import logging
from datetime import date

from fastapi import APIRouter, HTTPException

from app import api
from app.db import benchmark_market_data, consumer_sentiment, gdp_market_relationships
from app.db import economic_confirmation
from app.db import growth_cycle
from app.db import macro_indicators as macro_indicators_db
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.services import consumer_sentiment_dashboard, ism_services_dashboard
from app.services import economic_confirmation as economic_confirmation_dashboard
from app.tools import (
    housing_permits,
    ism_industry_analysis,
    ism_macro_signal,
    ism_official_report,
    ism_survey_synthesis,
    macro_growth_cycle,
    market_phase,
    market_setup,
    nfib_sbo,
    cyclical_commodities as tool,
    us_rates_liquidity,
)
from app.tools import benchmark_market_data as benchmark_market_data_tool

router = APIRouter(prefix="/api/macro-dashboard", tags=["macro-dashboard"])


@router.get("/consumer-sentiment")
def macro_dashboard_consumer_sentiment():
    con = consumer_sentiment.connect()
    try:
        return consumer_sentiment_dashboard.load_overview(con)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


@router.get("/consumer-sentiment/detail")
def macro_dashboard_consumer_sentiment_detail():
    con = consumer_sentiment.connect()
    try:
        return consumer_sentiment_dashboard.load_detail(con)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


def _macro_growth_context():
    growth_cycle_payload = macro_dashboard_growth_cycle()
    survey_synthesis = next(
        (
            card
            for card in growth_cycle_payload.get("headline", [])
            if card.get("id") == "survey_synthesis"
        ),
        {},
    )
    return {"expected_gdp_direction": survey_synthesis.get("expected_gdp_direction")}


@router.get("/economic-confirmation")
def macro_dashboard_economic_confirmation():
    con = economic_confirmation.connect()
    try:
        return economic_confirmation_dashboard.load_overview(
            con,
            _macro_growth_context(),
            date.today().isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


@router.get("/economic-confirmation/detail")
def macro_dashboard_economic_confirmation_detail():
    con = economic_confirmation.connect()
    try:
        return economic_confirmation_dashboard.load_detail(
            con,
            _macro_growth_context(),
            date.today().isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


@router.get("/market-phase")
def macro_dashboard_market_phase():
    con = benchmark_market_data.connect()
    try:
        return market_phase.build_dashboard_payload(
            lambda benchmark_id: benchmark_market_data.load_price_rows(
                con, benchmark_id
            ),
            benchmark_ids=api.US_BENCHMARK_IDS,
        )
    finally:
        con.close()


@router.get("/market-phase/{benchmark_id}")
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


@router.post("/market-phase/{benchmark_id}/refresh")
def macro_dashboard_market_phase_refresh(benchmark_id):
    try:
        results = benchmark_market_data_tool.refresh_benchmarks([benchmark_id])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return results[0]


@router.get("/growth-cycle")
def macro_dashboard_growth_cycle():
    con = us_rates_liquidity_db.connect()
    growth_cycle.init_db(con)
    try:
        rows = macro_indicators_db.load_macro_indicator_points(con, "m2_money_stock")
        core_pce_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "core_pce_price_index",
        )
        fed_total_assets_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "fed_total_assets",
        )
        fed_treasury_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "fed_treasury_holdings",
        )
        fed_mbs_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "fed_mbs_holdings",
        )
        m2_money_stock = (
            {"series": [{"date": row["date"], "value": row["value"]} for row in rows]}
            if rows
            else None
        )
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
        ism_points = macro_indicators_db.load_macro_indicator_points_for_series(
            con,
            api.ISM_MANUFACTURING_SERIES_IDS,
        )
        ism_manufacturing = (
            macro_growth_cycle.build_ism_manufacturing_payload_from_latest_points(
                ism_points,
            )
            if any(ism_points.values())
            else None
        )
        ism_services_data = ism_services_dashboard.load_overview(con)
        cot_rows = macro_indicators_db.load_cot_observations(con)
        usd_observations = (
            macro_indicators_db.load_macro_indicator_observations_for_series(
                con,
                api._OBSERVATION_SERIES_IDS,
            )
        )
        oil_observations = (
            macro_indicators_db.load_macro_indicator_observations_for_series(
                con,
                api._OIL_SERIES_IDS,
            )
        )
        oil_series_metadata = (
            macro_indicators_db.load_macro_indicator_series_for_ids(
                con,
                api._OIL_SERIES_IDS,
            )
        )
        method_observations = (
            macro_indicators_db.load_macro_indicator_observations_for_series(
                con,
                api.method_COMMODITY_SERIES_IDS,
            )
        )
        shfe_main_observations = macro_indicators_db.load_shfe_cu_main_observations(
            con
        )
        non_oil_attribution_facts = (
            macro_indicators_db.load_non_oil_attribution_facts(con)
        )
        non_oil_attribution_audit = api._load_non_oil_attribution_source_audit()
        non_oil_attribution_refresh_status = (
            macro_indicators_db.load_non_oil_attribution_refresh_status(con)
        )
        dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
            ism_manufacturing=ism_manufacturing,
            ism_services=ism_services_data["payload"],
            m2_money_stock=m2_money_stock,
            core_pce_price_index=core_pce_price_index if core_pce_rows else None,
            fed_total_assets=fed_total_assets if fed_total_assets_rows else None,
            fed_treasury_holdings=fed_treasury_holdings if fed_treasury_rows else None,
            fed_mbs_holdings=fed_mbs_holdings if fed_mbs_rows else None,
            building_permits={
                "observations": macro_indicators_db.load_macro_indicator_observations(
                    con, "building_permits_saar"
                ),
                "as_of_date": date.today().isoformat(),
            },
            cyclical_commodities={
                "cot_rows": cot_rows,
                "usd_observations_by_series": usd_observations,
                "oil_observations_by_series": oil_observations,
                "oil_series_metadata_by_id": oil_series_metadata,
                "commodity_observations": method_observations,
                "shfe_cu_main_observations": shfe_main_observations,
                "attribution_review_catalog": api._load_attribution_catalog(),
                "non_oil_attribution_facts": non_oil_attribution_facts,
                "non_oil_attribution_source_audit": non_oil_attribution_audit,
                "non_oil_attribution_refresh_status": non_oil_attribution_refresh_status,
                "cot_historical_extreme_allowlist": api._load_cot_historical_extreme_allowlist(),
                "as_of_date": date.today().isoformat(),
            },
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
        ism_industry_breadth = api._load_latest_ism_industry_breadth(con)
        ism_at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
        ism_reports = growth_cycle.load_recent_ism_report_snapshots(con, limit=6)
        ism_macro_signal_result = None
        if ism_reports:
            report_ids = [r["report_id"] for r in ism_reports]
            report_at_a_glance = growth_cycle.load_ism_at_a_glance_rows_for_reports(
                con, report_ids
            )
            try:
                ism_macro_signal_result = ism_macro_signal.build_ism_macro_signal(
                    ism_reports,
                    report_at_a_glance,
                    industry_breadth=ism_industry_breadth,
                )
            except ValueError:
                logging.warning("ism macro signal build failed", exc_info=True)
                ism_macro_signal_result = {
                    "version": ism_macro_signal.ISM_MACRO_SIGNAL_VERSION,
                    "status": "invalid_data",
                    "report_id": None,
                    "period": None,
                    "source_url": None,
                    "source_hash": None,
                    "phase": "unavailable",
                    "momentum": "unavailable",
                    "cycle_state": "unavailable",
                    "growth_impulse": "unavailable",
                    "confidence": "unavailable",
                    "continuity": {
                        "months_loaded": 0,
                        "adjacent_months": 0,
                        "has_gap": False,
                        "latest_momentum_streak": 0,
                    },
                    "trend": [],
                    "metrics": {},
                    "confirmations": {},
                    "policy_context": {
                        "growth_pressure": "unavailable",
                        "inflation_pressure": "unavailable",
                        "supply_pressure": "unavailable",
                        "combined_pressure": "unavailable",
                    },
                    "coverage": {
                        "required_metrics": ["pmi", "new_orders"],
                        "available_required_metrics": [],
                        "optional_metrics": [
                            "production",
                            "inventories",
                            "prices",
                            "supplier_deliveries",
                        ],
                        "available_optional_metrics": [],
                        "missing_metrics": [],
                    },
                    "evidence": [],
                }
        nfib_sbo_observations = (
            macro_indicators_db.load_macro_indicator_observations_for_series(
                con,
                api.NFIB_SERIES_IDS,
            )
        )
        survey_synthesis_result = ism_survey_synthesis.build_survey_synthesis(
            ism_macro_signal_result,
            ism_services_data["signal"],
        )
        nfib_sbo_signal_result = nfib_sbo.build_nfib_sbo_signal(
            nfib_sbo_observations,
            survey_synthesis_result,
            date.today().isoformat(),
        )
        growth_cycle_payload = macro_growth_cycle.build_growth_cycle_dashboard_payload(
            dashboard,
            next_fomc_meeting=next_fomc_meeting,
            fomc_latest_tone=fomc_latest_tone,
            ism_industry_breadth=ism_industry_breadth,
            ism_at_a_glance=ism_at_a_glance,
            ism_macro_signal=ism_macro_signal_result,
            ism_services_card=ism_services_data["card"],
            survey_synthesis=survey_synthesis_result,
            nfib_sbo_signal=nfib_sbo_signal_result,
        )
        return growth_cycle_payload
    finally:
        con.close()


@router.get("/market-setup")
def macro_dashboard_market_setup():
    con = us_rates_liquidity_db.connect()
    growth_cycle.init_db(con)
    try:
        rows = macro_indicators_db.load_macro_indicator_points(con, "m2_money_stock")
        core_pce_rows = macro_indicators_db.load_macro_indicator_points(
            con, "core_pce_price_index"
        )
        fed_total_assets_rows = macro_indicators_db.load_macro_indicator_points(
            con, "fed_total_assets"
        )
        fed_treasury_rows = macro_indicators_db.load_macro_indicator_points(
            con, "fed_treasury_holdings"
        )
        fed_mbs_rows = macro_indicators_db.load_macro_indicator_points(
            con, "fed_mbs_holdings"
        )
        m2_money_stock = (
            {"series": [{"date": row["date"], "value": row["value"]} for row in rows]}
            if rows
            else None
        )
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
        ism_points = macro_indicators_db.load_macro_indicator_points_for_series(
            con, api.ISM_MANUFACTURING_SERIES_IDS
        )
        ism_manufacturing = (
            macro_growth_cycle.build_ism_manufacturing_payload_from_latest_points(
                ism_points
            )
            if any(ism_points.values())
            else None
        )
        dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
            ism_manufacturing=ism_manufacturing,
            m2_money_stock=m2_money_stock,
            core_pce_price_index=core_pce_price_index if core_pce_rows else None,
            fed_total_assets=fed_total_assets if fed_total_assets_rows else None,
            fed_treasury_holdings=fed_treasury_holdings if fed_treasury_rows else None,
            fed_mbs_holdings=fed_mbs_holdings if fed_mbs_rows else None,
        )
        as_of_date = date.today().isoformat()
        fomc_latest_tone = us_rates_liquidity_db.load_latest_combined_fomc_policy_read(
            con, as_of_date
        )
        if not fomc_latest_tone:
            fomc_latest_tone = (
                us_rates_liquidity_db.load_latest_approved_macro_event_tone(
                    con, "fomc_meeting", as_of_date
                )
            )
        ism_industry_breadth = api._load_latest_ism_industry_breadth(con)
        ism_at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
        ism_reports = growth_cycle.load_recent_ism_report_snapshots(con, limit=6)
        ism_macro_signal_result = None
        if ism_reports:
            report_ids = [r["report_id"] for r in ism_reports]
            report_at_a_glance = growth_cycle.load_ism_at_a_glance_rows_for_reports(
                con, report_ids
            )
            try:
                ism_macro_signal_result = ism_macro_signal.build_ism_macro_signal(
                    ism_reports,
                    report_at_a_glance,
                    industry_breadth=ism_industry_breadth,
                )
            except ValueError:
                logging.warning(
                    "ism macro signal build failed for market setup", exc_info=True
                )
        growth_cycle_data = dashboard.get("macro", {}).get("growth_cycle", {})
        ism_services_data = ism_services_dashboard.load_overview(con)
        survey_synthesis_result = ism_survey_synthesis.build_survey_synthesis(
            ism_macro_signal_result,
            ism_services_data["signal"],
        )
        fomc_tone_headline = macro_growth_cycle.build_fomc_tone_headline(
            fomc_latest_tone
        )
        m2_headline = macro_growth_cycle.build_m2_money_supply_headline(
            growth_cycle_data
        )
        inflation_context = macro_growth_cycle.build_inflation_context_headline(
            growth_cycle_data
        )
        fed_balance_sheet = macro_growth_cycle.build_fed_balance_sheet_headline(
            growth_cycle_data
        )
        market_phase_payload = api._load_market_phase_for_setup()
        rates_liquidity_payload = api._load_rates_liquidity_for_setup(con)
        if ism_reports and ism_macro_signal_result is None:
            ism_macro_signal_result = {
                "version": ism_macro_signal.ISM_MACRO_SIGNAL_VERSION,
                "status": "invalid_data",
            }
        consumer_sentiment_summary = None
        try:
            consumer_sentiment_summary = consumer_sentiment_dashboard.load_overview(con)
        except (ValueError, TypeError, RuntimeError):
            logging.warning(
                "consumer sentiment load failed for market setup", exc_info=True
            )
        housing_permits_signal = None
        try:
            observations = macro_indicators_db.load_macro_indicator_observations(
                con, "building_permits_saar"
            )
            housing_permits_signal = housing_permits.build_housing_permits_signal(
                observations,
                survey_synthesis_result,
                date.today().isoformat(),
            )
        except (ValueError, TypeError, RuntimeError):
            logging.warning(
                "housing permits load failed for market setup", exc_info=True
            )
        nfib_sbo_observations = (
            macro_indicators_db.load_macro_indicator_observations_for_series(
                con,
                api.NFIB_SERIES_IDS,
            )
        )
        nfib_sbo_signal_result = nfib_sbo.build_nfib_sbo_signal(
            nfib_sbo_observations,
            survey_synthesis_result,
            date.today().isoformat(),
        )
        payload = market_setup.build_market_setup(
            market_phase_payload=market_phase_payload,
            survey_synthesis=survey_synthesis_result,
            rates_liquidity_payload=rates_liquidity_payload,
            fomc_tone=fomc_tone_headline,
            m2_headline=m2_headline,
            inflation_context=inflation_context,
            fed_balance_sheet=fed_balance_sheet,
            consumer_sentiment_summary=consumer_sentiment_summary,
            housing_permits_signal=housing_permits_signal,
            nfib_sbo_signal=nfib_sbo_signal_result,
        )
        return {
            k: v
            for k, v in payload.items()
            if k not in ("idea_generation", "limitations")
        }
    finally:
        con.close()


@router.get("/growth-cycle/{detail_id}")
def macro_dashboard_growth_cycle_detail(detail_id):
    if detail_id not in {
        "m2_money_supply",
        "ism_manufacturing",
        "ism_services",
        "housing_permits",
        "nfib_sbo",
        "cyclical_commodities",
    }:
        raise HTTPException(
            status_code=400,
            detail=f"growth cycle detail is unknown: {detail_id}",
        )
    con = us_rates_liquidity_db.connect()
    growth_cycle.init_db(con)
    try:
        if detail_id == "housing_permits":
            observations = macro_indicators_db.load_macro_indicator_observations(
                con, "building_permits_saar"
            )
            growth_cycle_payload = macro_dashboard_growth_cycle()
            survey_synthesis = next(
                (
                    card
                    for card in growth_cycle_payload.get("headline", [])
                    if card.get("id") == "survey_synthesis"
                ),
                {},
            )
            signal = housing_permits.build_housing_permits_signal(
                observations, survey_synthesis, date.today().isoformat()
            )
            return housing_permits.build_housing_permits_detail_payload(
                observations, signal
            )
        if detail_id == "nfib_sbo":
            nfib_sbo_observations = (
                macro_indicators_db.load_macro_indicator_observations_for_series(
                    con,
                    api.NFIB_SERIES_IDS,
                )
            )
            growth_cycle_payload = macro_dashboard_growth_cycle()
            survey_synthesis = next(
                (
                    card
                    for card in growth_cycle_payload.get("headline", [])
                    if card.get("id") == "survey_synthesis"
                ),
                {},
            )
            signal = nfib_sbo.build_nfib_sbo_signal(
                nfib_sbo_observations,
                survey_synthesis,
                date.today().isoformat(),
            )
            detail = nfib_sbo.build_nfib_sbo_detail_payload(
                nfib_sbo_observations, signal
            )
            regional_rows = macro_indicators_db.load_all_nfib_regional_observations(con)
            regional_by_region = {}
            national_quarterly_by_series = {}
            for row in regional_rows or []:
                rid = row["region_id"]
                iid = row["indicator_id"]
                if rid == "national":
                    national_quarterly_by_series.setdefault(iid, []).append(row)
                else:
                    regional_by_region.setdefault(rid, {}).setdefault(iid, []).append(
                        row
                    )
            regional_evidence = nfib_sbo.build_nfib_sbo_regional_payload(
                regional_by_region,
                nfib_sbo_observations,
                national_quarterly_observations=national_quarterly_by_series,
            )
            detail["regional_evidence"] = regional_evidence
            return detail
        if detail_id == "cyclical_commodities":
            cot_rows = macro_indicators_db.load_cot_observations(con)
            usd_observations = (
                macro_indicators_db.load_macro_indicator_observations_for_series(
                    con,
                    api._OBSERVATION_SERIES_IDS,
                )
            )
            oil_observations = (
                macro_indicators_db.load_macro_indicator_observations_for_series(
                    con,
                    api._OIL_SERIES_IDS,
                )
            )
            oil_series_metadata = (
                macro_indicators_db.load_macro_indicator_series_for_ids(
                    con,
                    api._OIL_SERIES_IDS,
                )
            )
            method_observations = (
                macro_indicators_db.load_macro_indicator_observations_for_series(
                    con,
                    api.method_COMMODITY_SERIES_IDS,
                )
            )
            shfe_main_observations = (
                macro_indicators_db.load_shfe_cu_main_observations(con)
            )
            non_oil_attribution_facts = (
                macro_indicators_db.load_non_oil_attribution_facts(con)
            )
            non_oil_attribution_audit = (
                api._load_non_oil_attribution_source_audit()
            )
            non_oil_attribution_refresh_status = (
                macro_indicators_db.load_non_oil_attribution_refresh_status(con)
            )
            attribution_catalog = api._load_attribution_catalog()
            payload = tool.build_cyclical_commodities_payload(
                cot_rows,
                usd_observations,
                oil_observations,
                date.today().isoformat(),
                oil_series_metadata_by_id=oil_series_metadata,
                commodity_observations=method_observations,
                shfe_cu_main_observations=shfe_main_observations,
                attribution_review_catalog=attribution_catalog,
                non_oil_attribution_facts=non_oil_attribution_facts,
                non_oil_attribution_source_audit=non_oil_attribution_audit,
                non_oil_attribution_refresh_status=non_oil_attribution_refresh_status,
                cot_historical_extreme_allowlist=api._load_cot_historical_extreme_allowlist(),
            )
            return tool.build_cyclical_commodities_detail(payload)
        if detail_id == "ism_services":
            return ism_services_dashboard.load_detail(con)
        if detail_id == "ism_manufacturing":
            ism_points = macro_indicators_db.load_macro_indicator_points_for_series(
                con,
                api.ISM_MANUFACTURING_SERIES_IDS,
            )
            gdp_con = gdp_market_relationships.connect()
            benchmark_con = benchmark_market_data.connect()
            try:
                gdp_level_rows = gdp_market_relationships.load_quad_rows(
                    gdp_con,
                    "us_sp500_gdp",
                )
                sp500_price_rows = benchmark_market_data.load_price_rows(
                    benchmark_con,
                    "us_sp500",
                )
            finally:
                gdp_con.close()
                benchmark_con.close()
            ism_at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
            latest_ism_report = growth_cycle.load_latest_ism_report_snapshot(con)
            ism_industry_breadth = api._load_latest_ism_industry_breadth(
                con,
                latest_ism_report,
            )
            ism_comments = (
                growth_cycle.load_ism_report_comments(
                    con,
                    latest_ism_report["report_id"],
                )
                if latest_ism_report
                else []
            )
            ism_official_summary = macro_growth_cycle.build_ism_official_report_summary(
                latest_ism_report,
                ism_at_a_glance,
                ism_comments,
            )
            ism_industry_analysis_payload = None
            if latest_ism_report:
                report_id = latest_ism_report["report_id"]
                signals = growth_cycle.load_ism_report_industry_signals(con, report_id)
                coverage = growth_cycle.load_ism_report_industry_signal_coverage(
                    con, report_id
                )
                at_a_glance = growth_cycle.load_ism_at_a_glance_rows(con, report_id)
                ism_industry_analysis_payload = (
                    ism_industry_analysis.build_ism_industry_analysis(
                        latest_ism_report,
                        signals,
                        coverage,
                        at_a_glance,
                        ism_comments,
                    )
                )
                if ism_industry_analysis_payload.get("industries"):
                    recent_reports = growth_cycle.load_recent_ism_report_snapshots(
                        con, limit=6
                    )
                    report_ids = [r["report_id"] for r in recent_reports]
                    hist_signals = (
                        growth_cycle.load_ism_report_industry_signals_for_reports(
                            con, report_ids
                        )
                    )
                    hist_coverage = growth_cycle.load_ism_report_industry_signal_coverage_for_reports(
                        con, report_ids
                    )
                    history = ism_industry_analysis.build_ism_industry_history(
                        recent_reports,
                        hist_signals,
                        hist_coverage,
                        [],
                    )
                    for ind in ism_industry_analysis_payload["industries"]:
                        ind_history = history.get(ind["industry"], {})
                        ind["trend"] = ind_history.get("trend", [])
                        ind["trend_summary"] = ind_history.get(
                            "trend_summary",
                            {
                                "latest_score_change": None,
                                "positive_month_streak": 0,
                                "broad_confirmation_streak": 0,
                                "latest_positive_confirmation_count": 0,
                                "eligible_month_count": 0,
                                "requested_month_count": 0,
                            },
                        )
            return macro_growth_cycle.build_ism_manufacturing_detail_payload(
                ism_points,
                gdp_level_rows=gdp_level_rows,
                sp500_price_rows=sp500_price_rows,
                ism_industry_breadth=ism_industry_breadth,
                ism_at_a_glance=ism_at_a_glance,
                ism_official_summary=ism_official_summary,
                ism_industry_analysis=ism_industry_analysis_payload,
            )

        rows = macro_indicators_db.load_macro_indicator_points(con, "m2_money_stock")
        core_pce_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "core_pce_price_index",
        )
        fed_total_assets_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "fed_total_assets",
        )
        fed_treasury_rows = macro_indicators_db.load_macro_indicator_points(
            con,
            "fed_treasury_holdings",
        )
        fed_mbs_rows = macro_indicators_db.load_macro_indicator_points(
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


@router.get("/us-rates-liquidity")
def macro_dashboard_us_rates_liquidity():
    con = us_rates_liquidity_db.connect()
    try:
        latest_points = us_rates_liquidity_db.load_latest_points(con)
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


@router.get("/us-rates-liquidity/{detail_id}")
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
            macro_indicators_db.load_macro_indicator_points_for_series(
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
