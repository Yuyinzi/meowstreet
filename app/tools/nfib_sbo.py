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


def _regional_latest_by_indicator(by_indicator):
    latest = {}
    for indicator_id, obs_list in by_indicator.items():
        if not obs_list:
            continue
        latest_obs = obs_list[-1]
        prev_obs = obs_list[-2] if len(obs_list) >= 2 else None
        detail = {
            "latest": latest_obs["value"],
            "previous": prev_obs["value"] if prev_obs else None,
            "period": latest_obs["date"],
            "availability": latest_obs.get("availability", "available"),
            "units": latest_obs.get("units", ""),
            "title": latest_obs.get("title", ""),
        }
        if (
            prev_obs is not None
            and prev_obs["value"] is not None
            and latest_obs["value"] is not None
        ):
            detail["qoq_change"] = latest_obs["value"] - prev_obs["value"]
        else:
            detail["qoq_change"] = None
        latest[indicator_id] = detail
    return latest


def _find_national_for_period(national_observations, indicator_id, period):
    obs_list = national_observations.get(indicator_id, [])
    for obs in obs_list:
        if obs["date"] == period:
            return obs.get("value")
    return None


def _find_national_quarterly_for_period(
    national_quarterly_observations, indicator_id, period
):
    if not national_quarterly_observations:
        return None
    obs_list = national_quarterly_observations.get(indicator_id, [])
    for obs in obs_list:
        if obs["date"] == period:
            return obs.get("value")
    return None


def _compute_national_diff(
    regional_detail,
    national_observations,
    indicator_id,
    national_quarterly_observations=None,
):
    period = regional_detail.get("period")
    regional_value = regional_detail.get("latest")
    if period is None or regional_value is None:
        return None
    national_value = _find_national_quarterly_for_period(
        national_quarterly_observations, indicator_id, period
    )
    if national_value is None:
        return None
    return {
        "national_value": national_value,
        "difference": round(regional_value - national_value, 2),
    }


def _build_regional_research_read(optimism_detail):
    if not optimism_detail or optimism_detail.get("latest") is None:
        return None

    english_parts = []
    chinese_parts = []
    national_diff = optimism_detail.get("national_diff")
    if national_diff is not None:
        difference = national_diff["difference"]
        relation = "above" if difference > 0 else "below" if difference < 0 else "at"
        chinese_relation = (
            "高" if difference > 0 else "低" if difference < 0 else "持平"
        )
        if relation == "at":
            english_parts.append("Optimism is at the national quarterly reading")
            chinese_parts.append("乐观指数与全国季度读数持平")
        else:
            english_parts.append(
                f"Optimism is {abs(difference):.1f} points {relation} the national quarterly reading"
            )
            chinese_parts.append(
                f"乐观指数较全国季度读数{chinese_relation}{abs(difference):.1f}点"
            )

    qoq_change = optimism_detail.get("qoq_change")
    if qoq_change is not None:
        direction = (
            "rose" if qoq_change > 0 else "fell" if qoq_change < 0 else "was unchanged"
        )
        chinese_direction = (
            "上升" if qoq_change > 0 else "下降" if qoq_change < 0 else "持平"
        )
        if qoq_change == 0:
            english_parts.append("was unchanged from the prior quarter")
            chinese_parts.append("较上季度持平")
        else:
            point_label = "point" if abs(qoq_change) == 1 else "points"
            english_parts.append(
                f"{direction} {abs(qoq_change):.1f} {point_label} from the prior quarter"
            )
            chinese_parts.append(f"较上季度{chinese_direction}{abs(qoq_change):.1f}点")

    if not english_parts:
        return None
    english = " and ".join(english_parts)
    if english.startswith("Optimism"):
        english = f"{english}."
    else:
        english = f"Optimism {english}."
    return {"en": english, "zh": "，".join(chinese_parts) + "。"}


def _unavailable_region(region_id):
    return {
        "id": region_id,
        "display_label": region_id.replace("_", " ").title(),
        "api_label": "",
        "states": "",
        "availability": "unavailable",
        "optimism": None,
        "leading_components": {},
        "context_components": {},
        "provenance": {},
        "regional_read": None,
        "research_next_action": "Official regional data was not published or was suppressed. Assess ticker exposure to this region through other sources.",
    }


def _build_regional_optimism_history_chart(
    regional_observations, national_quarterly_observations
):
    region_ids = ["pacific", "west_gulf", "north_atlantic"]
    values_by_region = {
        region_id: {
            obs["date"]: obs["value"]
            for obs in regional_observations.get(region_id, {}).get(
                "nfib_sbo_optimism", []
            )
            if obs.get("availability", "available") == "available"
            and obs.get("value") is not None
        }
        for region_id in region_ids
    }
    values_by_region["national"] = {
        obs["date"]: obs["value"]
        for obs in (national_quarterly_observations or {}).get("nfib_sbo_optimism", [])
        if obs.get("availability", "available") == "available"
        and obs.get("value") is not None
    }
    dates = sorted(
        {date_key for values in values_by_region.values() for date_key in values}
    )
    return {
        "title": "Regional Optimism vs National",
        "unit": "raw",
        "keys": ["pacific", "west_gulf", "north_atlantic", "national"],
        "labels": {
            "pacific": "Pacific",
            "west_gulf": "West Gulf",
            "north_atlantic": "North Atlantic",
            "national": "National",
        },
        "series": [
            {
                "date": date_key,
                **{
                    key: values_by_region[key].get(date_key) for key in values_by_region
                },
            }
            for date_key in dates
        ],
    }


def build_nfib_sbo_regional_payload(
    regional_observations, national_observations, national_quarterly_observations=None
):
    _REGION_ORDER = ["pacific", "west_gulf", "north_atlantic"]

    chart = _build_regional_optimism_history_chart(
        regional_observations, national_quarterly_observations
    )

    if not regional_observations:
        return {
            "regions": [_unavailable_region(r) for r in _REGION_ORDER],
            "optimism_history_chart": chart,
        }

    region_ids = [r for r in _REGION_ORDER if r in regional_observations] + [
        r for r in sorted(regional_observations.keys()) if r not in _REGION_ORDER
    ]
    regions = []
    for region_id in region_ids:
        by_indicator = regional_observations[region_id]
        if not by_indicator:
            regions.append(_unavailable_region(region_id))
            continue

        indicator_details = _regional_latest_by_indicator(by_indicator)

        first_obs = next(
            (obs for obs_list in by_indicator.values() for obs in obs_list if obs), {}
        )
        display_label = first_obs.get(
            "display_label", region_id.replace("_", " ").title()
        )
        api_label = first_obs.get("api_label", "")
        states = first_obs.get("states", "")

        optimism_detail = indicator_details.get("nfib_sbo_optimism")
        if optimism_detail:
            optimism_detail["national_diff"] = _compute_national_diff(
                optimism_detail,
                national_observations,
                "nfib_sbo_optimism",
                national_quarterly_observations,
            )
        availability = (
            optimism_detail["availability"] if optimism_detail else "unavailable"
        )

        leading_components = {}
        for cid in _COMPONENT_SERIES:
            detail = indicator_details.get(cid)
            if detail:
                detail["national_diff"] = _compute_national_diff(
                    detail,
                    national_observations,
                    cid,
                    national_quarterly_observations,
                )
            leading_components[cid] = detail

        context_components = {}
        for cid in _CONTEXT_SERIES:
            detail = indicator_details.get(cid)
            if detail:
                detail["national_diff"] = _compute_national_diff(
                    detail,
                    national_observations,
                    cid,
                    national_quarterly_observations,
                )
            context_components[cid] = detail

        _ALL_SIGNS = (
            list(_COMPONENT_SERIES) + list(_CONTEXT_SERIES) + ["nfib_sbo_optimism"]
        )
        provenance = {}
        for sid in _ALL_SIGNS:
            obs_list = by_indicator.get(sid, [])
            if obs_list and obs_list[-1].get("source_url"):
                last_obs = obs_list[-1]
                provenance = {
                    "source_url": last_obs.get("source_url", ""),
                    "retrieval_time": last_obs.get("retrieval_time", ""),
                    "procedure": last_obs.get("procedure_name", "getTotals2"),
                }
                break

        has_data = any(
            indicator_details.get(sid, {}).get("latest") is not None
            for sid in _ALL_SIGNS
        )

        if has_data:
            research_action = "Regional small-business data is available. Check whether the ticker has documented exposure to this region."
        else:
            research_action = "Official regional data was not published or was suppressed. Assess ticker exposure to this region through other sources."

        regions.append(
            {
                "id": region_id,
                "display_label": display_label,
                "api_label": api_label,
                "states": states,
                "availability": availability,
                "optimism": optimism_detail,
                "leading_components": leading_components,
                "context_components": context_components,
                "provenance": provenance,
                "regional_read": _build_regional_research_read(optimism_detail),
                "research_next_action": research_action,
            }
        )

    return {"regions": regions, "optimism_history_chart": chart}
