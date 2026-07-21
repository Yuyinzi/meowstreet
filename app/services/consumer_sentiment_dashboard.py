from app.db import consumer_sentiment
from app.tools import consumer_sentiment as consumer_sentiment_tool


def load_overview(con):
    points = consumer_sentiment.load_overview_series(con)
    summary = consumer_sentiment_tool.build_summary(points)
    return summary


def load_detail(con):
    points = consumer_sentiment.load_detail_series(con)
    detail = consumer_sentiment_tool.build_detail(points)
    return detail
