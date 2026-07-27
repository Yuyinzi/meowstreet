from datetime import date


NFIB_SBO_SIGNAL_VERSION = "nfib_sbo_signal_v1"

_COMPONENT_SERIES = [
    "nfib_sbo_employment_plans",
    "nfib_sbo_expansion_outlook",
    "nfib_sbo_inventory_plans",
    "nfib_sbo_economic_expectations",
    "nfib_sbo_real_sales_expectations",
]

_ALL_SERIES = _COMPONENT_SERIES + ["nfib_sbo_optimism"]

_REPORT_STALE_DAYS = 45


def _observations_by_month(observations):
    by_month = {}
    for obs in observations:
        month = obs["date"][:7]
        by_month.setdefault(month, []).append(obs)
    return by_month


def _series_values_by_month(observations_by_series):
    months = {}
    for series_id, series_obs in observations_by_series.items():
        for obs in series_obs:
            month = obs["date"][:7]
            months.setdefault(month, {})[series_id] = obs["value"]
    return months


def _latest_report_month(observations_by_series):
    latest = None
    for sid in _COMPONENT_SERIES:
        series_obs = observations_by_series.get(sid, [])
        for obs in series_obs:
            m = obs["date"][:7]
            if latest is None or m > latest:
                latest = m
    return latest


def _sorted_months(values_by_month):
    return sorted(values_by_month.keys())


def _compute_leading_indices(values_by_month, sorted_months_list):
    indices = {}
    for month in sorted_months_list:
        vals = values_by_month.get(month, {})
        components = [vals.get(sid) for sid in _COMPONENT_SERIES]
        if None in components:
            continue
        indices[month] = sum(components) / 5
    return indices


def _compute_4m_average(leading_indices, sorted_months_list, current_month):
    try:
        idx = sorted_months_list.index(current_month)
    except ValueError:
        return None
    if idx < 3:
        return None
    window = sorted_months_list[idx - 3 : idx + 1]
    vals = [leading_indices[m] for m in window if m in leading_indices]
    if len(vals) < 4:
        return None
    return sum(vals) / len(vals)


def _compute_4m_change(leading_indices, sorted_months_list, current_month):
    try:
        idx = sorted_months_list.index(current_month)
    except ValueError:
        return None
    if idx < 4:
        return None
    current_4m = _compute_4m_average(leading_indices, sorted_months_list, current_month)
    prev_month = sorted_months_list[idx - 1]
    prev_4m = _compute_4m_average(leading_indices, sorted_months_list, prev_month)
    if current_4m is None or prev_4m is None:
        return None
    return current_4m - prev_4m


def _one_month_change(leading_indices, sorted_months_list, current_month):
    try:
        idx = sorted_months_list.index(current_month)
    except ValueError:
        return None
    if idx < 1:
        return None
    current = leading_indices.get(current_month)
    prev = leading_indices.get(sorted_months_list[idx - 1])
    if current is None or prev is None:
        return None
    return current - prev


def _is_stale(as_of_date, latest_report_month):
    if not latest_report_month:
        return True
    try:
        as_of = date.fromisoformat(as_of_date)
    except (ValueError, TypeError):
        return True
    report_end = f"{latest_report_month}-30"
    try:
        report_date = date.fromisoformat(report_end)
    except ValueError:
        report_date = date.fromisoformat(f"{latest_report_month}-01")
    return (as_of - report_date).days > _REPORT_STALE_DAYS


def _trend_direction(change_4m):
    if change_4m is None:
        return "unavailable"
    if change_4m > 0:
        return "improving"
    if change_4m < 0:
        return "weakening"
    return "awaiting_confirmation"


def _survey_growth_direction(survey_synthesis):
    if not survey_synthesis:
        return None
    return survey_synthesis.get("expected_gdp_direction")


def _cross_check_status(nfib_trend, survey_direction, survey_synthesis):
    if nfib_trend in ("unavailable", "awaiting_confirmation"):
        return "awaiting_confirmation"

    if not survey_synthesis or not survey_direction:
        if nfib_trend == "improving":
            return "supports_growth_path"
        if nfib_trend == "weakening":
            return "challenges_growth_path"
        return "unavailable"

    supports = {
        "improving": {"rising", "rebound_risk"},
        "weakening": {"slowing", "falling"},
    }

    if survey_direction in supports.get(nfib_trend, set()):
        return "supports_growth_path"

    if nfib_trend == "improving" and survey_direction in {"slowing", "falling"}:
        return "challenges_growth_path"
    if nfib_trend == "weakening" and survey_direction in {"rising", "rebound_risk"}:
        return "challenges_growth_path"

    return "awaiting_confirmation"


def _build_detail_series(leading_indices, sorted_months_list):
    series = []
    for month in sorted_months_list:
        idx = sorted_months_list.index(month)
        entry = {"date": f"{month}-01"}
        li = leading_indices.get(month)
        if li is not None:
            entry["leading_index"] = round(li, 2)
            if idx >= 3:
                avg = _compute_4m_average(leading_indices, sorted_months_list, month)
                entry["leading_index_4m_average"] = (
                    round(avg, 2) if avg is not None else None
                )
        series.append(entry)
    return series


def build_nfib_sbo_signal(observations_by_series, survey_synthesis, as_of_date):
    values_by_month = _series_values_by_month(observations_by_series)
    sorted_months = _sorted_months(values_by_month)
    leading_indices = _compute_leading_indices(values_by_month, sorted_months)

    latest_month = _latest_report_month(observations_by_series)
    if not latest_month or latest_month not in leading_indices:
        return {
            "version": NFIB_SBO_SIGNAL_VERSION,
            "status": "unavailable",
            "reason": "nfib report is unavailable or has no complete component data",
            "latest": None,
            "detail_series": [],
        }

    is_stale = _is_stale(as_of_date, latest_month)
    latest_index = leading_indices[latest_month]
    latest_4m_avg = _compute_4m_average(leading_indices, sorted_months, latest_month)
    latest_4m_change = _compute_4m_change(leading_indices, sorted_months, latest_month)
    current_one_month_change = _one_month_change(
        leading_indices, sorted_months, latest_month
    )
    trend = _trend_direction(latest_4m_change)
    survey_direction = _survey_growth_direction(survey_synthesis)
    status = _cross_check_status(trend, survey_direction, survey_synthesis)

    if is_stale:
        status = "unavailable"

    if status == "unavailable":
        return {
            "version": NFIB_SBO_SIGNAL_VERSION,
            "status": "unavailable",
            "reason": "nfib report is stale or has no complete component data",
            "latest": None,
            "detail_series": [],
        }

    reasons = _build_reason(status, trend, latest_4m_change, survey_direction)
    latest = {
        "leading_index": round(latest_index, 1),
        "leading_index_4m_average": round(latest_4m_avg, 2)
        if latest_4m_avg is not None
        else None,
        "leading_index_4m_change": round(latest_4m_change, 2)
        if latest_4m_change is not None
        else None,
        "period": latest_month,
    }

    return {
        "version": NFIB_SBO_SIGNAL_VERSION,
        "status": status,
        "trend": trend,
        "latest": latest,
        "reason": reasons,
        "detail_series": _build_detail_series(leading_indices, sorted_months),
    }


def _build_reason(status, trend, change, survey_direction):
    if status == "supports_growth_path":
        return f"nfib evidence supports the {survey_direction or 'current'} growth path"
    if status == "challenges_growth_path":
        return (
            f"nfib evidence challenges the {survey_direction or 'current'} growth path"
        )
    return "nfib evidence is awaiting confirmation"


def build_nfib_sbo_detail_payload(observations_by_series, signal):
    values_by_month = _series_values_by_month(observations_by_series)
    sorted_months = _sorted_months(values_by_month)

    components = {}
    for series_id in _COMPONENT_SERIES:
        series_obs = observations_by_series.get(series_id, [])
        if series_obs:
            components[series_id] = {
                "latest": series_obs[-1]["value"],
                "period": series_obs[-1]["date"][:7],
                "observations": [
                    {"date": obs["date"], "value": obs["value"]} for obs in series_obs
                ],
            }
        else:
            components[series_id] = None

    optimism_obs = observations_by_series.get("nfib_sbo_optimism", [])
    optimism = None
    if optimism_obs:
        optimism = {
            "latest": optimism_obs[-1]["value"],
            "period": optimism_obs[-1]["date"][:7],
            "observations": [
                {"date": obs["date"], "value": obs["value"]} for obs in optimism_obs
            ],
        }

    return {
        "detail_id": "nfib_sbo",
        "signal_version": NFIB_SBO_SIGNAL_VERSION,
        "latest_signal": signal.get("latest"),
        "components": components,
        "optimism": optimism,
        "detail_series": signal.get("detail_series", []),
    }
