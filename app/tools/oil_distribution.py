from datetime import date, timedelta
from statistics import StatisticsError, stdev


METHOD_VERSION = "oil_distribution_v2"
RETURN_DEFINITION = "arithmetic_close_to_close"
DISTRIBUTION_WINDOW = "2016-01-01_to_latest_available"
STANDARD_DEVIATION = "sample"
ISO_WEEK_DEFINITION = "iso_calendar_week_last_available_trading_day"
MINIMUM_SAMPLES = {"daily": 252, "weekly": 52}
DISTRIBUTION_START_DATE = "2016-01-01"


def _arithmetic_return(current, prior):
    if prior == 0:
        return None
    return round((current / prior) - 1, 12)


def _sorted_valid_observations(observations):
    return sorted(
        [
            row
            for row in observations
            if (
                row.get("date")
                and row["date"] >= DISTRIBUTION_START_DATE
                and row.get("value") is not None
            )
        ],
        key=lambda row: row["date"],
    )


def daily_returns(observations):
    rows = _sorted_valid_observations(observations)
    return [
        {"date": current["date"], "value": change}
        for prior, current in zip(rows, rows[1:])
        if (change := _arithmetic_return(current["value"], prior["value"])) is not None
    ]


def iso_weekly_returns(observations):
    weekly_closes = {}
    for row in _sorted_valid_observations(observations):
        iso_year, iso_week, _ = date.fromisoformat(row["date"]).isocalendar()
        weekly_closes[(iso_year, iso_week)] = row
    result = []
    for key, current in sorted(weekly_closes.items()):
        prior_key_date = date.fromisocalendar(key[0], key[1], 1) - timedelta(days=7)
        prior_key = prior_key_date.isocalendar()[:2]
        prior = weekly_closes.get(prior_key)
        if prior is None:
            continue
        change = _arithmetic_return(current["value"], prior["value"])
        if change is not None:
            result.append({"date": current["date"], "value": change})
    return result


def classify_return(current_return, mean_return, sample_standard_deviation):
    if current_return is None:
        return "unavailable"
    if sample_standard_deviation == 0:
        return "normal" if current_return == mean_return else "abnormal_3sigma"
    distance = abs(current_return - mean_return)
    if distance >= 3 * sample_standard_deviation:
        return "abnormal_3sigma"
    if distance >= 2 * sample_standard_deviation:
        return "abnormal_2sigma"
    if distance > sample_standard_deviation:
        return "abnormal_1sigma"
    return "normal"


def build_distribution(observations, frequency, minimum_samples=None):
    if frequency not in ("daily", "weekly"):
        raise ValueError(f"distribution frequency is invalid: {frequency}")

    if minimum_samples is None:
        minimum_samples = MINIMUM_SAMPLES[frequency]

    if frequency == "weekly":
        returns = iso_weekly_returns(observations)
        week_definition = ISO_WEEK_DEFINITION
    else:
        returns = daily_returns(observations)
        week_definition = None

    sample_count = len(returns)
    if sample_count < minimum_samples:
        return {
            "method_version": METHOD_VERSION,
            "return_definition": RETURN_DEFINITION,
            "distribution_window": DISTRIBUTION_WINDOW,
            "standard_deviation": STANDARD_DEVIATION,
            "frequency": frequency,
            "week_definition": week_definition,
            "minimum_samples": minimum_samples,
            "sample_count": sample_count,
            "sample_mean": None,
            "sample_standard_deviation": None,
            "current_return": None,
            "sample_start_date": None,
            "sample_end_date": None,
            "classification": "unavailable",
            "reason": f"at least {minimum_samples} {frequency} returns are required",
        }

    values = [r["value"] for r in returns]
    sample_mean = sum(values) / len(values)
    sample_standard_deviation = stdev(values)
    current_return = returns[-1]["value"]

    classification = classify_return(
        current_return, sample_mean, sample_standard_deviation
    )

    return {
        "method_version": METHOD_VERSION,
        "return_definition": RETURN_DEFINITION,
        "distribution_window": DISTRIBUTION_WINDOW,
        "standard_deviation": STANDARD_DEVIATION,
        "frequency": frequency,
        "week_definition": week_definition,
        "minimum_samples": minimum_samples,
        "sample_count": sample_count,
        "sample_mean": sample_mean,
        "sample_standard_deviation": sample_standard_deviation,
        "current_return": current_return,
        "sample_start_date": returns[0]["date"],
        "sample_end_date": returns[-1]["date"],
        "classification": classification,
        "reason": None,
    }
