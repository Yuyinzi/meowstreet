from app.tools import price_distribution

METHOD_VERSION = "usd_price_distribution_v1"
DISTRIBUTION_WINDOW = "2016-01-01_to_latest_available"
DISTRIBUTION_START_DATE = "2016-01-01"


def iso_weekly_returns(observations):
    return price_distribution.iso_weekly_returns(
        observations, DISTRIBUTION_START_DATE
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
