from datetime import date, timedelta
from statistics import stdev


_DEFAULT_START_DATE = "2016-01-01"
_ISO_WEEK_DEFINITION = "iso_calendar_week_last_available_trading_day"
_MINIMUM_SAMPLES = {"daily": 252, "weekly": 52}
_RETURN_DEFINITION = "arithmetic_close_to_close"
_STANDARD_DEVIATION = "sample"


def _arithmetic_return(current, prior):
    if prior == 0:
        return None
    return round((current / prior) - 1, 12)


def _sorted_valid_observations(observations, start_date):
    return sorted(
        [
            row
            for row in observations
            if (
                row.get("date")
                and row["date"] >= start_date
                and row.get("value") is not None
            )
        ],
        key=lambda row: row["date"],
    )


def daily_returns(observations, start_date="2016-01-01"):
    rows = _sorted_valid_observations(observations, start_date)
    return [
        {"date": current["date"], "value": change}
        for prior, current in zip(rows, rows[1:])
        if (change := _arithmetic_return(current["value"], prior["value"])) is not None
    ]


def iso_weekly_returns(observations, start_date="2016-01-01"):
    weekly_closes = {}
    for row in _sorted_valid_observations(observations, start_date):
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


def build_distribution_from_returns(
    returns,
    frequency,
    *,
    method_version,
    distribution_window,
    return_definition,
    minimum_samples=None,
):
    if frequency not in ("daily", "weekly"):
        raise ValueError(f"distribution frequency is invalid: {frequency}")

    if minimum_samples is None:
        minimum_samples = _MINIMUM_SAMPLES[frequency]

    if frequency == "weekly":
        week_definition = _ISO_WEEK_DEFINITION
    else:
        week_definition = None

    rows = sorted(returns, key=lambda row: row["date"])

    sample_count = len(rows)
    if sample_count < minimum_samples:
        return {
            "method_version": method_version,
            "return_definition": return_definition,
            "distribution_window": distribution_window,
            "standard_deviation": _STANDARD_DEVIATION,
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

    values = [r["value"] for r in rows]
    sample_mean = sum(values) / len(values)
    sample_standard_deviation = stdev(values)
    current_return = rows[-1]["value"]

    classification = classify_return(
        current_return, sample_mean, sample_standard_deviation
    )

    return {
        "method_version": method_version,
        "return_definition": return_definition,
        "distribution_window": distribution_window,
        "standard_deviation": _STANDARD_DEVIATION,
        "frequency": frequency,
        "week_definition": week_definition,
        "minimum_samples": minimum_samples,
        "sample_count": sample_count,
        "sample_mean": sample_mean,
        "sample_standard_deviation": sample_standard_deviation,
        "current_return": current_return,
        "sample_start_date": rows[0]["date"],
        "sample_end_date": rows[-1]["date"],
        "classification": classification,
        "reason": None,
    }


def build_distribution_from_observations(
    observations,
    frequency,
    *,
    method_version,
    distribution_window,
    start_date="2016-01-01",
    minimum_samples=None,
):
    if frequency == "weekly":
        returns = iso_weekly_returns(observations, start_date)
    else:
        returns = daily_returns(observations, start_date)
    return build_distribution_from_returns(
        returns,
        frequency,
        method_version=method_version,
        distribution_window=distribution_window,
        return_definition=_RETURN_DEFINITION,
        minimum_samples=minimum_samples,
    )
