from app.db import ism_surveys, us_rates_liquidity
from app.tools import ism_services, ism_services_industry

SERVICES_SERIES_IDS = list(ism_services.SERIES_TO_KEY)


def load_overview(con):
    points = us_rates_liquidity.load_macro_indicator_points_for_series(
        con, SERVICES_SERIES_IDS
    )
    signal = ism_services.build_signal(points)
    rankings = ism_surveys.load_industry_rankings(con, "services", limit_months=6)
    signal_period = (
        signal.get("period")
        if signal.get("state") not in ("pending_inputs", "stale_periods")
        else None
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


def load_detail(con):
    points = us_rates_liquidity.load_macro_indicator_points_for_series(
        con, SERVICES_SERIES_IDS
    )
    signal = ism_services.build_signal(points)
    rankings = ism_surveys.load_industry_rankings(con, "services", limit_months=6)
    signal_period = (
        signal.get("period")
        if signal.get("state") not in ("pending_inputs", "stale_periods")
        else None
    )
    comments = ism_surveys.load_industry_comments(
        con, "services", report_month=signal_period
    )
    if signal_period is None:
        industries = {"industries": []}
    else:
        period_rankings = [r for r in rankings if r["date"] == signal_period]
        industries = ism_services_industry.build_industry_payload(
            period_rankings, comments
        )
    industries["breadth"] = ism_services_industry.build_breadth(
        rankings, max_date=signal_period
    )
    return ism_services.build_detail(points, signal, industries)
