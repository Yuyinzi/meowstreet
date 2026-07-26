from datetime import date, datetime


HOUSING_PERMITS_SIGNAL_VERSION = "housing_permits_signal_v1"

_IMPROVING_DIRECTIONS = {"rising", "rebound_risk"}
_WEAKENING_DIRECTIONS = {"slowing", "falling"}


def _pct_change(latest, previous):
    if previous == 0:
        return None
    return (latest - previous) / previous


def _validate_observations(observations):
    if observations is None or len(observations) == 0:
        raise ValueError("building permits observations are missing")
    return [
        {
            "date": obs["date"],
            "value": float(obs["value"]),
        }
        for obs in observations
    ]


def _is_stale(latest_date, as_of_date):
    if not latest_date or not as_of_date:
        return True
    latest = datetime.strptime(latest_date[:10], "%Y-%m-%d")
    as_of = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    if as_of.day >= 20:
        allowed_lag_months = 1
    else:
        allowed_lag_months = 2
    latest_year_month = latest.year * 12 + latest.month
    as_of_year_month = as_of.year * 12 + as_of.month
    return (as_of_year_month - latest_year_month) > allowed_lag_months


def _latest_metrics(observations):
    latest = observations[-1]
    value = latest["value"]
    mom = None
    yoy = None
    if len(observations) >= 2:
        mom = _pct_change(observations[-1]["value"], observations[-2]["value"])
    if len(observations) >= 13:
        yoy = _pct_change(observations[-1]["value"], observations[-13]["value"])
    return {
        "permits_saar": value,
        "permits_mom_pct": mom,
        "permits_yoy_pct": yoy,
    }


def _yoy_series(observations):
    result = []
    for i in range(12, len(observations)):
        yoy = _pct_change(observations[i]["value"], observations[i - 12]["value"])
        if yoy is not None:
            result.append({"date": observations[i]["date"], "value": yoy})
    return result


def _calculate_yoy_12m_average(yoy_series):
    if len(yoy_series) < 12:
        return None
    recent = yoy_series[-12:]
    return sum(item["value"] for item in recent) / len(recent)


def _yoy_12m_average_series(yoy_series):
    if len(yoy_series) < 12:
        return []
    return [
        {
            "date": yoy_series[index - 1]["date"],
            "value": sum(item["value"] for item in yoy_series[index - 12 : index])
            / 12,
        }
        for index in range(12, len(yoy_series) + 1)
    ]


def _primary_trend(yoy_12m_average_series):
    if len(yoy_12m_average_series) < 2:
        return None
    previous = yoy_12m_average_series[-2]["value"]
    latest = yoy_12m_average_series[-1]["value"]
    if latest > 0 and latest > previous:
        return "improving"
    if latest < 0 and latest < previous:
        return "weakening"
    return "mixed"


def _survey_direction(survey_synthesis):
    if survey_synthesis is None:
        return None
    status = survey_synthesis.get("status")
    if status not in ("available",):
        return None
    direction = survey_synthesis.get("expected_gdp_direction")
    if direction in _IMPROVING_DIRECTIONS:
        return "improving"
    if direction in _WEAKENING_DIRECTIONS:
        return "weakening"
    return None


def _determine_status(latest, yoy_average, trend, survey_dir, observations):
    if latest is None:
        return "unavailable", "building permit data is missing"
    mom = latest.get("permits_mom_pct")
    yoy = latest.get("permits_yoy_pct")
    if yoy is None:
        return "unavailable", "insufficient observation history for yoy calculation"
    if mom is not None and abs(mom) >= 0.20:
        return "awaiting_confirmation", (
            "monthly permit change exceeds 20%, awaiting confirmation of sustained direction"
        )
    if mom is not None and abs(mom) < 1e-10:
        return "awaiting_confirmation", (
            "monthly permit change is effectively zero, awaiting confirmation of sustained direction"
        )
    if trend is None:
        return "awaiting_confirmation", (
            "insufficient permit history for primary trend"
        )
    if yoy_average is not None and mom is not None:
        yoy_positive = yoy_average > 0
        mom_positive = mom > 0
        if yoy_positive != mom_positive:
            return "awaiting_confirmation", (
                "current monthly change conflicts with the 12-month yoy average"
            )
    if trend not in ("improving", "weakening"):
        return "awaiting_confirmation", (
            "smoothed permit trend is internally mixed, awaiting confirmation of sustained direction"
        )
    if survey_dir is None:
        return "awaiting_confirmation", (
            "survey synthesis is unavailable or partial; cannot evaluate housing alignment"
        )
    if trend == survey_dir:
        return (
            "supports_growth_path",
            f"housing permit evidence supports the {survey_dir} growth path",
        )
    return (
        "challenges_growth_path",
        f"housing permit evidence challenges the current growth path",
    )


def build_housing_permits_signal(observations, survey_synthesis, as_of_date):
    try:
        obs = _validate_observations(observations)
    except ValueError as exc:
        return {
            "version": HOUSING_PERMITS_SIGNAL_VERSION,
            "status": "unavailable",
            "reason": str(exc),
            "observation_period": None,
            "latest": {
                "permits_saar": None,
                "permits_mom_pct": None,
                "permits_yoy_pct": None,
                "permits_yoy_12m_average": None,
            },
        }
    if not obs:
        return {
            "version": HOUSING_PERMITS_SIGNAL_VERSION,
            "status": "unavailable",
            "reason": "no building permits observations available",
            "observation_period": None,
            "latest": {
                "permits_saar": None,
                "permits_mom_pct": None,
                "permits_yoy_pct": None,
                "permits_yoy_12m_average": None,
            },
        }
    latest_date = obs[-1]["date"]
    if _is_stale(latest_date, as_of_date):
        metrics = _latest_metrics(obs)
        return {
            "version": HOUSING_PERMITS_SIGNAL_VERSION,
            "status": "unavailable",
            "reason": f"latest permit observation {latest_date} is stale relative to {as_of_date}",
            "observation_period": latest_date,
            "latest": {
                "permits_saar": metrics.get("permits_saar"),
                "permits_mom_pct": metrics.get("permits_mom_pct"),
                "permits_yoy_pct": metrics.get("permits_yoy_pct"),
                "permits_yoy_12m_average": None,
            },
        }
    yoy_vals = _yoy_series(obs)
    yoy_12m_averages = _yoy_12m_average_series(yoy_vals)
    yoy_average = yoy_12m_averages[-1]["value"] if yoy_12m_averages else None
    previous_yoy_average = (
        yoy_12m_averages[-2]["value"] if len(yoy_12m_averages) >= 2 else None
    )
    trend = _primary_trend(yoy_12m_averages)
    latest = _latest_metrics(obs)
    survey_dir = _survey_direction(survey_synthesis)
    status, reason = _determine_status(latest, yoy_average, trend, survey_dir, obs)
    underlying_alignment = (
        "aligned"
        if trend in ("improving", "weakening") and trend == survey_dir
        else "conflicting"
        if trend in ("improving", "weakening") and survey_dir is not None
        else "unavailable"
    )
    return {
        "version": HOUSING_PERMITS_SIGNAL_VERSION,
        "status": status,
        "reason": reason,
        "observation_period": latest_date,
        "latest": {
            "permits_saar": latest["permits_saar"],
            "permits_mom_pct": latest["permits_mom_pct"],
            "permits_yoy_pct": latest["permits_yoy_pct"],
            "permits_yoy_12m_average": yoy_average,
        },
        "cross_validation": {
            "survey_synthesis": {
                "status": survey_synthesis.get("status") if survey_synthesis else None,
                "period": survey_synthesis.get("period") if survey_synthesis else None,
                "expected_gdp_direction": (
                    survey_synthesis.get("expected_gdp_direction")
                    if survey_synthesis
                    else None
                ),
                "direction": survey_dir,
                "underlying_alignment": underlying_alignment,
            },
            "permits": {
                "primary_trend": trend,
                "yoy_12m_average": yoy_average,
                "previous_yoy_12m_average": previous_yoy_average,
                "yoy_12m_average_change": (
                    yoy_average - previous_yoy_average
                    if yoy_average is not None and previous_yoy_average is not None
                    else None
                ),
                "latest_yoy": latest["permits_yoy_pct"],
                "latest_mom": latest["permits_mom_pct"],
            },
        },
    }


def build_housing_permits_card(signal):
    status = signal.get("status", "unavailable")
    reason = signal.get("reason", "no observations loaded")
    latest = signal.get("latest", {})
    return {
        "id": "housing_permits",
        "title": "Building Permits",
        "status": status,
        "reason": reason,
        "observation_period": signal.get("observation_period"),
        "latest": {
            "permits_saar": latest.get("permits_saar"),
            "permits_mom_pct": latest.get("permits_mom_pct"),
            "permits_yoy_pct": latest.get("permits_yoy_pct"),
            "permits_yoy_12m_average": latest.get("permits_yoy_12m_average"),
        },
    }


def build_housing_permits_detail_payload(observations, signal):
    obs = [{"date": o["date"], "value": float(o["value"])} for o in observations]
    yoy_vals = _yoy_series(obs)
    yoy_keys = {"yoy_pct"}
    yoy_labels = {"yoy_pct": "YoY % Change"}

    def _date_index(series, date_str):
        for idx, item in enumerate(series):
            if item["date"] == date_str:
                return idx
        return -1

    yoy_average_by_date = {
        item["date"]: item["value"] for item in _yoy_12m_average_series(yoy_vals)
    }
    if yoy_average_by_date:
        yoy_keys.add("yoy_12m_avg")
        yoy_labels["yoy_12m_avg"] = "12M Average YoY"

    yoy_multi = []
    for item in yoy_vals:
        row = {"date": item["date"], "yoy_pct": item["value"] * 100}
        avg_val = yoy_average_by_date.get(item["date"])
        row["yoy_12m_avg"] = avg_val * 100 if avg_val is not None else None
        yoy_multi.append(row)

    return {
        "detail_id": "housing_permits",
        "series_id": "building_permits_saar",
        "status": signal.get("status"),
        "reason": signal.get("reason"),
        "observation_period": signal.get("observation_period"),
        "latest": signal.get("latest", {}),
        "cross_validation": signal.get("cross_validation", {}),
        "charts": [
            {
                "title": "Building Permits SAAR",
                "series": [
                    {"date": o["date"], "value": float(o["value"])}
                    for o in observations
                ],
                "keys": ["value"],
                "labels": {"value": "Building Permits SAAR"},
            },
            {
                "title": "Building Permits YoY and 12M Average",
                "series": yoy_multi,
                "keys": sorted(yoy_keys),
                "labels": yoy_labels,
            },
        ],
    }
