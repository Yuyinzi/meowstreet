from app.db import growth_cycle, ism_surveys, us_rates_liquidity
from app.tools import ism_services, ism_services_industry

SERVICES_SERIES_IDS = list(ism_services.SERIES_TO_KEY)


def load_overview(con):
    points = us_rates_liquidity.load_macro_indicator_points_for_series(
        con, SERVICES_SERIES_IDS
    )
    signal = ism_services.build_signal(points)
    signal_period = (
        signal.get("period")
        if signal.get("state") not in ("pending_inputs", "stale_periods")
        else None
    )
    rankings = ism_surveys.load_industry_rankings(
        con, "services", limit_months=6, max_date=signal_period
    )
    comments = ism_surveys.load_industry_comments(
        con, "services", report_month=signal_period
    )
    breadth = ism_services_industry.build_breadth(rankings, max_date=signal_period)
    return {
        "payload": ism_services.build_latest_payload(points),
        "signal": signal,
        "card": ism_services.build_card(signal, breadth),
        "industry_breadth": breadth,
    }


def _load_rich_evidence(con, signal_period):
    if signal_period is None:
        return None
    snapshot = ism_surveys.load_latest_report_snapshot(con, "services")
    if not snapshot or snapshot["report_month"] != signal_period:
        return None
    rid = snapshot["report_id"]
    glance = growth_cycle.load_ism_at_a_glance_rows(con, rid)
    signals = growth_cycle.load_ism_report_industry_signals(con, rid)
    commodities = growth_cycle.load_ism_report_commodities(con, rid)
    narrative = growth_cycle.load_ism_report_narrative_facts(con, rid)
    comments_rows = growth_cycle.load_ism_report_comments(con, rid)
    component_industries = [
        s
        for s in signals
        if s["signal_type"] not in ("overall_growth", "overall_contraction")
    ]
    return {
        "at_a_glance_rows": glance or [],
        "component_industries": component_industries,
        "respondent_comments": [dict(r) for r in comments_rows]
        if comments_rows
        else [],
        "commodities": commodities or [],
        "narrative_facts": narrative["facts_json"] if narrative else {},
        "source": {
            "source_url": snapshot["source_url"],
            "source_hash": snapshot["source_hash"],
        },
    }


def load_detail(con):
    points = us_rates_liquidity.load_macro_indicator_points_for_series(
        con, SERVICES_SERIES_IDS
    )
    signal = ism_services.build_signal(points)
    signal_period = (
        signal.get("period")
        if signal.get("state") not in ("pending_inputs", "stale_periods")
        else None
    )
    rankings = ism_surveys.load_industry_rankings(
        con, "services", limit_months=6, max_date=signal_period
    )
    comments = ism_surveys.load_industry_comments(
        con, "services", report_month=signal_period
    )
    if signal_period is not None:
        capped_rankings = [r for r in rankings if r["date"] <= signal_period]
        industries = ism_services_industry.build_industry_payload(
            capped_rankings, comments
        )
        industries["industries"] = [
            ind
            for ind in industries["industries"]
            if ind["latest_date"] == signal_period
        ]
    else:
        industries = {"industries": []}
    industries["breadth"] = ism_services_industry.build_breadth(
        rankings, max_date=signal_period
    )
    detail = ism_services.build_detail(points, signal, industries)
    detail["rich_evidence"] = _load_rich_evidence(con, signal_period)
    return detail
