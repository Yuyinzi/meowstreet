from datetime import date


NFIB_SBO_SIGNAL_VERSION = "nfib_sbo_signal_v1"

_COMPONENT_SERIES = [
    "nfib_sbo_employment_plans",
    "nfib_sbo_expansion_outlook",
    "nfib_sbo_inventory_plans",
    "nfib_sbo_economic_expectations",
    "nfib_sbo_real_sales_expectations",
]

_CONTEXT_SERIES = [
    "nfib_sbo_capital_outlay_plans",
    "nfib_sbo_current_inventory_low",
    "nfib_sbo_job_openings",
    "nfib_sbo_credit_conditions_expectations",
    "nfib_sbo_earnings_trends",
]

_CONTEXT_SERIES_TITLES = {
    "nfib_sbo_capital_outlay_plans": "Capital Expenditure Plans",
    "nfib_sbo_current_inventory_low": "Current Inventory Too Low",
    "nfib_sbo_job_openings": "Current Job Openings",
    "nfib_sbo_credit_conditions_expectations": "Credit Conditions Expectation",
    "nfib_sbo_earnings_trends": "Earnings Trends",
}

_ALL_SERIES = _COMPONENT_SERIES + _CONTEXT_SERIES + ["nfib_sbo_optimism"]

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


def _cross_check_status(
    nfib_trend, survey_direction, survey_synthesis, one_month_change, change_4m
):
    if nfib_trend in ("unavailable", "awaiting_confirmation"):
        return "awaiting_confirmation"

    if not survey_synthesis or not survey_direction:
        return "awaiting_confirmation"

    if change_4m is not None and one_month_change is not None:
        if (change_4m > 0 and one_month_change < 0) or (
            change_4m < 0 and one_month_change > 0
        ):
            return "awaiting_confirmation"

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
    status = _cross_check_status(
        trend,
        survey_direction,
        survey_synthesis,
        current_one_month_change,
        latest_4m_change,
    )

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

    previous_leading_index = None
    if current_one_month_change is not None:
        previous_leading_index = latest_index - current_one_month_change

    reasons = _build_reason(
        status,
        trend,
        latest_index,
        previous_leading_index,
        current_one_month_change,
        survey_direction,
    )
    latest = {
        "leading_index": round(latest_index, 1),
        "leading_index_4m_average": round(latest_4m_avg, 2)
        if latest_4m_avg is not None
        else None,
        "leading_index_4m_change": round(latest_4m_change, 2)
        if latest_4m_change is not None
        else None,
        "leading_index_1m_change": round(current_one_month_change, 2)
        if current_one_month_change is not None
        else None,
        "previous_leading_index": round(previous_leading_index, 1)
        if previous_leading_index is not None
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


def _build_reason(
    status,
    trend,
    leading_index,
    previous_leading_index,
    one_month_change,
    survey_direction,
):
    if status == "supports_growth_path":
        return f"nfib evidence supports the {survey_direction or 'current'} growth path"
    if status == "challenges_growth_path":
        return (
            f"nfib evidence challenges the {survey_direction or 'current'} growth path"
        )
    if (
        trend == "weakening"
        and one_month_change is not None
        and one_month_change > 0
        and previous_leading_index is not None
    ):
        return (
            "nfib's 4-month trend is weakening, but the latest leading index rose "
            f"from {previous_leading_index:.1f} to {leading_index:.1f}, so it has not "
            f"yet confirmed the ism-implied {survey_direction or 'current'} growth path"
        )
    if (
        trend == "improving"
        and one_month_change is not None
        and one_month_change < 0
        and previous_leading_index is not None
    ):
        return (
            "nfib's 4-month trend is improving, but the latest leading index fell "
            f"from {previous_leading_index:.1f} to {leading_index:.1f}, so it has not "
            f"yet confirmed the ism-implied {survey_direction or 'current'} growth path"
        )
    return "nfib evidence is awaiting confirmation"


def _latest_provenance(observations_by_series):
    sources = []
    for series_obs in observations_by_series.values():
        if series_obs:
            sources.append(series_obs[-1])
    if not sources:
        return {}
    latest = max(sources, key=lambda o: o.get("date", ""))
    return {
        "source_url": latest.get("source_url", ""),
        "release_date": latest.get("release_date", ""),
        "source_hash": latest.get("source_hash", ""),
    }


def _build_component_detail(series_id, series_obs, values_by_month, sorted_months_list):
    if not series_obs:
        return None
    latest_val = series_obs[-1]["value"]
    period = series_obs[-1]["date"][:7]
    previous_val = None
    if len(series_obs) >= 2:
        previous_val = series_obs[-2]["value"]
    change = latest_val - previous_val if previous_val is not None else None
    return {
        "latest": latest_val,
        "previous": previous_val,
        "change": change,
        "period": period,
        "observations": [
            {"date": obs["date"], "value": obs["value"]} for obs in series_obs
        ],
    }


def _build_optimism_detail(series_id, series_obs):
    if not series_obs:
        return None
    return {
        "latest": series_obs[-1]["value"],
        "period": series_obs[-1]["date"][:7],
        "observations": [
            {"date": obs["date"], "value": obs["value"]} for obs in series_obs
        ],
        "basis": "1986=100",
        "role": "overall_context",
    }


def build_nfib_sbo_detail_payload(observations_by_series, signal):
    values_by_month = _series_values_by_month(observations_by_series)
    sorted_months = _sorted_months(values_by_month)

    leading_components = {}
    for series_id in _COMPONENT_SERIES:
        series_obs = observations_by_series.get(series_id, [])
        leading_components[series_id] = _build_component_detail(
            series_id, series_obs, values_by_month, sorted_months
        )

    context_components = {}
    for series_id in _CONTEXT_SERIES:
        series_obs = observations_by_series.get(series_id, [])
        detail = _build_component_detail(
            series_id, series_obs, values_by_month, sorted_months
        )
        if detail:
            detail["title"] = _CONTEXT_SERIES_TITLES.get(series_id, series_id)
            detail["units"] = "net_pct"
            detail["role"] = "context_only"
            context_components[series_id] = detail
        else:
            context_components[series_id] = None

    optimism_obs = observations_by_series.get("nfib_sbo_optimism", [])
    optimism = _build_optimism_detail("nfib_sbo_optimism", optimism_obs)

    provenance = _latest_provenance(observations_by_series)

    return {
        "detail_id": "nfib_sbo",
        "signal_version": NFIB_SBO_SIGNAL_VERSION,
        "status": signal.get("status"),
        "reason": signal.get("reason"),
        "latest_signal": signal.get("latest"),
        "leading_components": leading_components,
        "context_components": context_components,
        "optimism": optimism,
        "detail_series": signal.get("detail_series", []),
        "source_url": provenance.get("source_url", ""),
        "release_date": provenance.get("release_date", ""),
        "source_hash": provenance.get("source_hash", ""),
    }
