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


def _load_industry_analysis(con, signal_period, rankings, comments):
    snapshot = (
        ism_surveys.load_latest_report_snapshot(con, "services")
        if signal_period is not None
        else None
    )
    if not snapshot or snapshot["report_month"] != signal_period:
        return ism_services_industry.build_services_industry_analysis(
            rankings,
            [],
            [],
            comments,
            period=signal_period,
            source_url=None,
        )
    report_id = snapshot["report_id"]
    component_signals = [
        row
        for row in growth_cycle.load_ism_report_industry_signals(con, report_id)
        if row["signal_type"] not in ("overall_growth", "overall_contraction")
    ]
    coverage_rows = [
        row
        for row in growth_cycle.load_ism_report_industry_signal_coverage(con, report_id)
        if row["signal_type"] not in ("overall_growth", "overall_contraction")
    ]
    return ism_services_industry.build_services_industry_analysis(
        rankings,
        component_signals,
        coverage_rows,
        comments,
        period=signal_period,
        source_url=snapshot["source_url"],
    )


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
            "report_id": snapshot["report_id"],
            "report_month": snapshot["report_month"],
            "title": snapshot["title"],
            "source_url": snapshot["source_url"],
            "source_hash": snapshot["source_hash"],
        },
    }


def _format_point_change(value):
    if value is None:
        return "change unavailable"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.1f} points"


def _format_at_a_glance_change(row):
    return (
        f"{row['label']}: {row['current_value']:.1f}, "
        f"{_format_point_change(row.get('point_change'))}; "
        f"{row.get('direction') or 'Direction unavailable'} / "
        f"{row.get('rate_of_change') or 'rate unavailable'}."
    )


def _build_official_report_summary(rich_evidence):
    if not rich_evidence:
        return None
    rows = rich_evidence.get("at_a_glance_rows") or []
    source = rich_evidence.get("source") or {}
    pmi = next(
        (row for row in rows if row.get("series_id") == "ism_services_pmi"),
        None,
    )
    headline = ""
    if pmi:
        headline = (
            f"Services PMI {pmi['current_value']:.1f}, "
            f"{_format_point_change(pmi.get('point_change'))} from prior month; "
            f"{pmi.get('direction') or 'Direction unavailable'} / "
            f"{pmi.get('rate_of_change') or 'rate unavailable'}."
        )
    changed_rows = sorted(
        (row for row in rows if row is not pmi),
        key=lambda row: abs(row.get("point_change") or 0),
        reverse=True,
    )
    return {
        "source_type": "report_extracted",
        "report_id": source.get("report_id"),
        "period": source.get("report_month"),
        "title": source.get("title"),
        "source_url": source.get("source_url"),
        "headline": headline,
        "major_changes": [_format_at_a_glance_change(row) for row in changed_rows[:5]],
        "respondent_comments": rich_evidence.get("respondent_comments") or [],
        "comment_preview_count": 3,
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
    rich_evidence = _load_rich_evidence(con, signal_period)
    detail["official_report_summary"] = _build_official_report_summary(rich_evidence)
    detail["rich_evidence"] = rich_evidence
    if rich_evidence:
        report_month = (rich_evidence.get("source") or {}).get("report_month")
        if report_month == signal_period:
            presentation = ism_services.build_latest_presentation(
                rich_evidence["at_a_glance_rows"]
            )
            detail["latest"].update(presentation["latest"])
            detail["latest_metadata"] = presentation["latest_metadata"]
            detail["detail_groups"] = presentation["detail_groups"]
    detail["industry_analysis"] = _load_industry_analysis(
        con, signal_period, rankings, comments
    )
    return detail
