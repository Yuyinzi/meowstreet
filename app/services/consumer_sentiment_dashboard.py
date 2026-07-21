from datetime import date

from app.db import consumer_sentiment, macro_indicators, us_rates_liquidity
from app.tools import consumer_sentiment as consumer_sentiment_tool


def load_overview(con):
    points = consumer_sentiment.load_overview_series(con)
    summary = consumer_sentiment_tool.build_summary(points)
    return summary


def _real_rate(treasury_points, cpi_points):
    if not treasury_points or not cpi_points:
        return None
    treasury_latest = treasury_points[-1]
    cpi_latest = cpi_points[-1]
    return round(treasury_latest["value"] - cpi_latest["value"], 2)


def load_detail(con):
    points = consumer_sentiment.load_detail_series(con)
    treasury_points = macro_indicators.load_macro_indicator_points(con, "treasury_10y")
    cpi_points = macro_indicators.load_macro_indicator_points(con, "cpi_yoy")
    tips_points = macro_indicators.load_macro_indicator_points(con, "tips_10y")
    as_of_date = date.today().isoformat()
    fomc_tone = us_rates_liquidity.load_latest_combined_fomc_policy_read(
        con, as_of_date
    )
    context = {
        "treasury_10y": treasury_points,
        "cpi_yoy": cpi_points,
        "tips_10y": tips_points,
        "real_rate": _real_rate(treasury_points, cpi_points),
        "fomc_tone": fomc_tone,
    }
    detail = consumer_sentiment_tool.build_detail(points)
    detail["context"] = context
    return detail
