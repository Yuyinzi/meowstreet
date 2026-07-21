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
    return round(treasury_points[-1]["value"] - cpi_points[-1]["value"], 2)


def _load_fomc_tone(con):
    try:
        return us_rates_liquidity.load_latest_combined_fomc_policy_read(
            con, date.today().isoformat()
        )
    except Exception:
        return None


def load_detail(con):
    points = consumer_sentiment.load_detail_series(con)
    treasury_points = us_rates_liquidity.load_rate_points(con, "treasury_10y")
    cpi_points = macro_indicators.load_macro_indicator_points(con, "cpi_yoy")
    tips_points = us_rates_liquidity.load_rate_points(con, "tips_10y")
    fomc_tone = _load_fomc_tone(con)
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
