from app.tools import price_distribution


METHOD_VERSION = "oil_distribution_v2"
RETURN_DEFINITION = "arithmetic_close_to_close"
DISTRIBUTION_WINDOW = "2016-01-01_to_latest_available"
STANDARD_DEVIATION = "sample"
ISO_WEEK_DEFINITION = "iso_calendar_week_last_available_trading_day"
MINIMUM_SAMPLES = {"daily": 252, "weekly": 52}
DISTRIBUTION_START_DATE = "2016-01-01"


def daily_returns(observations):
    return price_distribution.daily_returns(observations, DISTRIBUTION_START_DATE)


def iso_weekly_returns(observations):
    return price_distribution.iso_weekly_returns(
        observations, DISTRIBUTION_START_DATE
    )


def classify_return(current_return, mean_return, sample_standard_deviation):
    return price_distribution.classify_return(
        current_return, mean_return, sample_standard_deviation
    )


def build_distribution(observations, frequency, minimum_samples=None):
    return price_distribution.build_distribution_from_observations(
        observations,
        frequency,
        method_version=METHOD_VERSION,
        distribution_window=DISTRIBUTION_WINDOW,
        start_date=DISTRIBUTION_START_DATE,
        minimum_samples=minimum_samples,
    )
