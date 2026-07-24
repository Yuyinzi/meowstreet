import sqlite3

from app.db import consumer_sentiment, macro_indicators, us_rates_liquidity
from app.tools import consumer_sentiment as consumer_sentiment_tool

_TREASURY_10Y_SERIES_ID = "treasury_10y"
_TIPS_10Y_SERIES_ID = "tips_10y"
_CPI_YOY_SERIES_ID = "cpi_yoy"


def load_overview(con):
    points = consumer_sentiment.load_overview_series(con)
    return consumer_sentiment_tool.build_summary(points)


def _normalize_rate_source(points):
    return [
        {
            "date": point["date"],
            "value": point["value"],
            "source": point.get("source")
            or point.get("source_workbook")
            or point.get("source_sheet"),
        }
        for point in points
    ]


def load_detail(con):
    points = consumer_sentiment.load_detail_series(con)
    detail = consumer_sentiment_tool.build_detail(points)

    treasury_10y = []
    tips_10y = []
    try:
        treasury_10y = _normalize_rate_source(
            us_rates_liquidity.load_rate_points(con, _TREASURY_10Y_SERIES_ID)
        )
        tips_10y = _normalize_rate_source(
            us_rates_liquidity.load_rate_points(con, _TIPS_10Y_SERIES_ID)
        )
    except sqlite3.OperationalError:
        pass

    cpi_yoy = []
    try:
        cpi_yoy = macro_indicators.load_macro_indicator_points(con, _CPI_YOY_SERIES_ID)
    except ValueError:
        pass

    real_rate = consumer_sentiment_tool.compute_real_rate(treasury_10y, cpi_yoy)

    fomc_tone = None
    try:
        fomc_tone = us_rates_liquidity.load_latest_combined_fomc_policy_read(
            con, detail["summary"].get("as_of") or "2099-12-31"
        )
    except sqlite3.OperationalError:
        pass

    detail["context"] = {
        "treasury_10y": treasury_10y,
        "tips_10y": tips_10y,
        "cpi_yoy": cpi_yoy,
        "real_rate": real_rate,
        "fomc_tone": fomc_tone,
    }
    return detail
