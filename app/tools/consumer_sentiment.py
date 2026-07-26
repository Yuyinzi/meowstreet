SERIES_TO_KEY = {
    "umcsi_aggregate": "aggregate",
    "umcsi_expectations": "expectations",
    "umcsi_current_conditions": "current_conditions",
}

CAPACITY_SERIES_IDS = [
    "household_debt_to_gdp",
    "household_debt_service_ratio",
    "personal_saving_rate",
    "one_to_four_family_mortgage_liabilities",
]


def _previous_calendar_month(date_str):
    year_s, month_s, _ = date_str.split("-")
    year = int(year_s)
    month = int(month_s)
    if month == 1:
        return f"{year - 1:04d}-12-01"
    return f"{year:04d}-{month - 1:02d}-01"


def _latest_point(points):
    return points[-1] if points else None


def _prior_calendar_month_point(points):
    if len(points) < 2:
        return None
    current = points[-1]
    expected_prior = _previous_calendar_month(current["date"])
    for point in reversed(points[:-1]):
        if point["date"] == expected_prior:
            return point
    return None


def _point_change(points):
    current = _latest_point(points)
    prior = _prior_calendar_month_point(points)
    if current is None or prior is None:
        return None
    return round(current["value"] - prior["value"], 1)


def _capacity_completeness(points_by_id):
    present = 0
    for sid in CAPACITY_SERIES_IDS:
        if points_by_id.get(sid):
            present += 1
    if present == len(CAPACITY_SERIES_IDS):
        return "complete"
    if present > 0:
        return "partial"
    return "missing"


def _data_status(points_by_id):
    latest_dates = []
    for key in ("umcsi_aggregate", "umcsi_expectations", "umcsi_current_conditions"):
        pts = points_by_id.get(key)
        if not pts:
            return "missing"
        latest_dates.append(pts[-1]["date"])
    if len(set(latest_dates)) == 1:
        return "aligned_period"
    return "mixed_periods"


def _large_expectations_decline(expectations_points):
    change = _point_change(expectations_points)
    if change is None:
        return False
    return change < -10


def _direction(change):
    if change is None:
        return "unavailable"
    if change > 0:
        return "improving"
    if change < 0:
        return "weakening"
    return "unchanged"


def _month_number(date_str):
    year, month, _ = date_str.split("-")
    return int(year) * 12 + int(month) - 1


def _consecutive_months(points):
    return all(
        _month_number(current["date"]) - _month_number(previous["date"]) == 1
        for previous, current in zip(points, points[1:])
    )


def _rolling_percentile(points, observation_date):
    ordered = sorted(
        (point for point in points if point["date"] <= observation_date),
        key=lambda point: point["date"],
    )
    evaluated = next(
        (
            index
            for index in range(len(ordered) - 1, -1, -1)
            if ordered[index]["date"] == observation_date
        ),
        None,
    )
    if evaluated is None:
        return {
            "available": False,
            "rank": None,
            "window_start": None,
            "window_end": observation_date,
            "observation_count": 0,
        }
    start = max(0, evaluated - 239)
    window = ordered[start : evaluated + 1]
    if len(window) != 240 or not _consecutive_months(window):
        return {
            "available": False,
            "rank": None,
            "window_start": None,
            "window_end": observation_date,
            "observation_count": len(window),
        }
    current_value = window[-1]["value"]
    below = sum(point["value"] < current_value for point in window)
    equal = sum(point["value"] == current_value for point in window)
    rank = 100 * (below + 0.5 * equal) / len(window)
    return {
        "available": True,
        "rank": round(rank, 2),
        "unrounded_rank": rank,
        "window_start": window[0]["date"],
        "window_end": observation_date,
        "observation_count": len(window),
    }


def _percentile_zone(rank):
    if rank <= 15:
        return "depressed"
    if rank >= 85:
        return "elevated"
    return "typical"


def _ordinal_percentile(rank):
    display_rank = int(rank + 0.5)
    remainder_100 = display_rank % 100
    if 11 <= remainder_100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(display_rank % 10, "th")
    return f"{display_rank}{suffix} percentile"


def _sentiment_metric(points, role):
    latest = _latest_point(points)
    change = _point_change(points)
    momentum = _direction(change)
    percentile = (
        _rolling_percentile(points, latest["date"])
        if latest
        else {
            "available": False,
            "rank": None,
            "window_start": None,
            "window_end": None,
            "observation_count": 0,
        }
    )
    rank = percentile["rank"]
    zone = (
        _percentile_zone(percentile["unrounded_rank"])
        if percentile["available"]
        else "percentile_unavailable"
    )
    return {
        "value": latest["value"] if latest else None,
        "date": latest["date"] if latest else None,
        "point_change": change,
        "point_change_unit": "index_points",
        "momentum": momentum,
        "percentile_rank": rank,
        "percentile_label": (
            _ordinal_percentile(rank) if rank is not None else "Unavailable"
        ),
        "percentile_zone": zone,
        "role": role,
        "confirms_primary": None,
        "source": latest.get("source") if latest else None,
        "_percentile_window": {
            "start": percentile["window_start"],
            "end": percentile["window_end"],
            "observation_count": percentile["observation_count"],
        },
    }


def _confirmation(aggregate, expectations, current_conditions, periods_aligned):
    unavailable = (
        not periods_aligned
        or expectations["percentile_zone"] == "percentile_unavailable"
        or aggregate["percentile_zone"] == "percentile_unavailable"
        or current_conditions["percentile_zone"] == "percentile_unavailable"
    )
    if unavailable:
        return {
            "state": "unavailable",
            "aggregate_confirms": None,
            "current_conditions_confirms": None,
        }
    primary_zone = expectations["percentile_zone"]
    aggregate_confirms = aggregate["percentile_zone"] == primary_zone
    current_confirms = current_conditions["percentile_zone"] == primary_zone
    if aggregate_confirms and current_confirms:
        state = "broadly_confirmed"
    elif aggregate_confirms:
        state = "aggregate_confirms"
    elif current_confirms:
        state = "current_conditions_confirms"
    else:
        state = "divergent"
    return {
        "state": state,
        "aggregate_confirms": aggregate_confirms,
        "current_conditions_confirms": current_confirms,
    }


def _primary_signal(expectations):
    if expectations["percentile_zone"] == "percentile_unavailable":
        return {
            "series_id": "umcsi_expectations",
            "percentile_zone": "percentile_unavailable",
            "momentum": expectations["momentum"],
            "headline": "Primary sentiment percentile is unavailable.",
        }
    zone = expectations["percentile_zone"].replace("_", " ").title()
    momentum = expectations["momentum"].replace("_", " ").title()
    return {
        "series_id": "umcsi_expectations",
        "percentile_zone": expectations["percentile_zone"],
        "momentum": expectations["momentum"],
        "headline": f"{zone} \u00b7 {momentum}",
    }


def _public_sentiment_metric(metric):
    return {key: value for key, value in metric.items() if key != "_percentile_window"}


def _interpretation_by_id(interpretations, series_id):
    return next(
        (
            interpretation
            for interpretation in interpretations
            if interpretation["series_id"] == series_id
        ),
        None,
    )


def _financing_input_state(interpretation):
    if (
        not interpretation
        or not interpretation.get("available")
        or interpretation["direction"] == "unavailable"
    ):
        return "unavailable"
    if interpretation["direction"] == "falling":
        return "easing"
    if interpretation["direction"] == "rising":
        return "tightening"
    return "unchanged"


def _ability_direction(interpretation):
    if (
        not interpretation
        or not interpretation.get("available")
        or interpretation["direction"] == "unavailable"
    ):
        return "unavailable"
    return interpretation["direction"]


def _ability_read(interpretations):
    debt_service = _financing_input_state(
        _interpretation_by_id(interpretations, "household_debt_service_ratio")
    )
    real_rate = _financing_input_state(
        _interpretation_by_id(interpretations, "real_10y_rate")
    )
    if "unavailable" in {debt_service, real_rate}:
        financing = "unavailable"
    elif debt_service == real_rate:
        financing = debt_service
    else:
        financing = "mixed"
    leverage = _ability_direction(
        _interpretation_by_id(interpretations, "household_debt_to_gdp")
    )
    saving = _ability_direction(
        _interpretation_by_id(interpretations, "personal_saving_rate")
    )
    return {
        "financing": {"label": "Financing", "state": financing},
        "leverage": {"label": "Leverage", "state": leverage},
        "saving": {"label": "Saving", "state": saving},
    }


def _percentile_window(points):
    latest = _latest_point(points)
    if not latest:
        return {
            "start": None,
            "end": None,
            "observation_count": 0,
        }
    percentile = _rolling_percentile(points, latest["date"])
    return {
        "start": percentile["window_start"],
        "end": percentile["window_end"],
        "observation_count": percentile["observation_count"],
    }


def _capacity_interpretations(points_by_id, real_rate_points):
    interpretations = []
    for sid in CAPACITY_SERIES_IDS:
        pts = points_by_id.get(sid, [])
        if not pts:
            interpretations.append(
                {
                    "series_id": sid,
                    "label": _capacity_series_label(sid),
                    "available": False,
                    "direction": "unavailable",
                    "interpretation": _single_capacity_interpretation(sid, None),
                }
            )
            continue
        current = pts[-1]
        prior = pts[-2] if len(pts) > 1 else None
        prior_val = prior["value"] if prior else None
        change = (
            round(current["value"] - prior_val, 2) if prior_val is not None else None
        )
        interpretation = _single_capacity_interpretation(sid, change)
        interpretations.append(
            {
                "series_id": sid,
                "label": _capacity_series_label(sid),
                "available": True,
                "latest_value": current["value"],
                "latest_date": current["date"],
                "direction": "rising"
                if change and change > 0
                else "falling"
                if change and change < 0
                else "unchanged"
                if change == 0
                else "unavailable",
                "interpretation": interpretation,
            }
        )
    real_rate_entry = {
        "series_id": "real_10y_rate",
        "label": _capacity_series_label("real_10y_rate"),
        "available": False,
        "has_direction": False,
        "direction": "unavailable",
        "interpretation": "Real rate data unavailable for direction assessment.",
    }
    if len(real_rate_points) == 1:
        real_rate_entry["available"] = True
        real_rate_entry["interpretation"] = (
            "Single real rate observation — direction cannot be determined."
        )
    elif len(real_rate_points) > 1:
        real_rate_change = round(
            real_rate_points[-1]["value"] - real_rate_points[-2]["value"], 2
        )
        real_rate_direction = (
            "falling"
            if real_rate_change and real_rate_change < 0
            else "rising"
            if real_rate_change and real_rate_change > 0
            else "unchanged"
            if real_rate_change == 0
            else "unavailable"
        )
        real_rate_entry["available"] = True
        real_rate_entry["has_direction"] = real_rate_direction != "unavailable"
        real_rate_entry["direction"] = real_rate_direction
        real_rate_entry["interpretation"] = _real_rate_interpretation(
            real_rate_direction
        )
    interpretations.append(real_rate_entry)
    mortgage = next(
        (
            interpretation
            for interpretation in interpretations
            if interpretation["series_id"] == "one_to_four_family_mortgage_liabilities"
        ),
        None,
    )
    debt_service_ratio = next(
        (
            interpretation
            for interpretation in interpretations
            if interpretation["series_id"] == "household_debt_service_ratio"
        ),
        None,
    )
    if mortgage:
        mortgage["context_interpretation"] = (
            f"Debt Service Ratio: {_capacity_context_state(debt_service_ratio)}. "
            f"Real 10Y Rate: {_capacity_context_state(real_rate_entry)}."
        )
    return interpretations


def _capacity_context_state(interpretation):
    if not interpretation or not interpretation.get("available"):
        return "data unavailable"
    if interpretation.get("direction") == "unavailable":
        return "direction unavailable"
    return interpretation["direction"]


def _single_capacity_interpretation(series_id, change):
    if series_id == "household_debt_to_gdp":
        if change is None:
            return "Insufficient data to determine leverage trend."
        if change < 0:
            return "Declining leverage: household debt-to-GDP ratio is falling."
        if change == 0:
            return "Household debt-to-GDP ratio is unchanged."
        return "Increasing leverage: household debt-to-GDP ratio is rising."
    if series_id == "household_debt_service_ratio":
        if change is None:
            return "Insufficient data to determine cash-flow burden trend."
        if change < 0:
            return "Easing household cash-flow burden: debt-service ratio is falling."
        if change == 0:
            return "Household debt-service ratio is unchanged."
        return "Increasing household cash-flow burden: debt-service ratio is rising."
    if series_id == "personal_saving_rate":
        if change is None:
            return "Insufficient data to determine thrift trend."
        if change < 0:
            return "Less thrift: near-term spending support but a smaller financial buffer."
        if change == 0:
            return "Personal saving rate is unchanged."
        return (
            "Greater thrift: near-term spending caution but a larger financial buffer."
        )
    if series_id == "one_to_four_family_mortgage_liabilities":
        if change is None:
            return "Mortgage direction unavailable. Scale context only — absolute dollar amount does not indicate capacity leverage."
        if change > 0:
            return "Rising mortgage liabilities. Scale context only — absolute dollar amount does not indicate capacity leverage."
        if change < 0:
            return "Declining mortgage liabilities. Scale context only — absolute dollar amount does not indicate capacity leverage."
        return "Mortgage liabilities unchanged. Scale context only — absolute dollar amount does not indicate capacity leverage."
    return ""


def _real_rate_interpretation(direction):
    if direction == "falling":
        return "Real financing conditions are easing."
    if direction == "rising":
        return "Real financing conditions are tightening."
    if direction == "unchanged":
        return "Real financing conditions are unchanged."
    return "Real rate data unavailable for direction assessment."


def _household_debt_gdp_quarter_note(points):
    if not points:
        return None
    latest = points[-1]
    date_str = latest["date"]
    year, month, _ = date_str.split("-")
    quarter = (int(month) - 1) // 3 + 1
    return f"Latest official: Q{quarter} {year} · IMF/FRED reporting lag — lagged balance-sheet evidence, does not represent the current quarter."


def _capacity_clause(interpretation):
    series_id = interpretation["series_id"]
    direction = interpretation["direction"]
    clauses = {
        ("household_debt_to_gdp", "rising"): "household leverage rose",
        ("household_debt_to_gdp", "falling"): "household leverage fell",
        ("household_debt_to_gdp", "unchanged"): "household leverage was unchanged",
        ("household_debt_service_ratio", "rising"): ("debt-service burden increased"),
        ("household_debt_service_ratio", "falling"): ("debt-service burden eased"),
        ("household_debt_service_ratio", "unchanged"): (
            "debt-service burden was unchanged"
        ),
        ("personal_saving_rate", "rising"): (
            "greater saving indicates near-term spending caution with a larger "
            "financial buffer"
        ),
        ("personal_saving_rate", "falling"): (
            "lower saving indicates near-term spending support with a smaller "
            "financial buffer"
        ),
        ("personal_saving_rate", "unchanged"): "saving was unchanged",
        ("real_10y_rate", "rising"): "real financing conditions tightened",
        ("real_10y_rate", "falling"): "real financing conditions eased",
        ("real_10y_rate", "unchanged"): ("real financing conditions were unchanged"),
    }
    if series_id == "real_10y_rate" and direction == "unavailable":
        return interpretation["interpretation"].rstrip(".")
    return clauses.get((series_id, direction))


def _join_capacity_clauses(clauses):
    approved_example = {
        "debt-service burden eased",
        "real financing conditions eased",
        "household leverage rose",
        "saving was unchanged",
    }
    if set(clauses) == approved_example:
        return (
            "Debt-service burden and real financing conditions eased, while "
            "household leverage rose; saving was unchanged."
        )
    return "; ".join(clauses).capitalize() + "."


def _capacity_evidence_read(interpretations, completeness):
    available = [
        interpretation
        for interpretation in interpretations
        if interpretation.get("available")
        and interpretation["series_id"] != "one_to_four_family_mortgage_liabilities"
    ]
    clauses = [
        clause
        for interpretation in available
        if (clause := _capacity_clause(interpretation))
    ]
    if not clauses:
        return {
            "headline": (
                "Ability to spend cannot be assessed from the available capacity data."
            ),
            "explanation": "",
        }
    directions = {
        interpretation["direction"]
        for interpretation in available
        if interpretation["direction"] in {"rising", "falling"}
    }
    if completeness != "complete":
        headline = "Capacity evidence is incomplete."
    elif len(directions) > 1:
        headline = "Capacity evidence points in different directions."
    else:
        headline = "Available capacity evidence does not define a combined state."
    explanation = _join_capacity_clauses(clauses)
    if completeness != "complete":
        explanation += " Some capacity inputs are unavailable."
    return {"headline": headline, "explanation": explanation}


def _capacity_series_label(series_id):
    labels = {
        "household_debt_to_gdp": "Household Debt/GDP",
        "household_debt_service_ratio": "Debt Service Ratio",
        "personal_saving_rate": "Personal Saving Rate",
        "one_to_four_family_mortgage_liabilities": "Mortgage Liabilities",
        "real_10y_rate": "Real 10Y Rate",
    }
    return labels.get(series_id, series_id)


def compute_real_rate(treasury_10y_points, cpi_yoy_points):
    cpi_by_month = {}
    for p in cpi_yoy_points:
        month = p["date"][:7]
        cpi_by_month.setdefault(month, []).append(p)
    cpi_latest_by_month = {
        month: pts[-1]["value"] for month, pts in cpi_by_month.items()
    }
    result = []
    for p in treasury_10y_points:
        month = p["date"][:7]
        cpi_val = cpi_latest_by_month.get(month)
        if cpi_val is not None:
            result.append(
                {
                    "date": p["date"],
                    "value": round(p["value"] - cpi_val, 2),
                    "treasury_10y": p["value"],
                    "cpi_yoy": cpi_val,
                }
            )
    return result


def build_summary(points_by_id, policy_context=None, real_rate_points=None):
    aggregate_points = points_by_id.get("umcsi_aggregate", [])
    expectations_points = points_by_id.get("umcsi_expectations", [])
    current_points = points_by_id.get("umcsi_current_conditions", [])

    aggregate = _sentiment_metric(aggregate_points, "confirmation")
    expectations = _sentiment_metric(expectations_points, "primary")
    current_conditions = _sentiment_metric(current_points, "confirmation")

    periods_aligned = (
        aggregate["date"] is not None
        and aggregate["date"] == expectations["date"]
        and expectations["date"] == current_conditions["date"]
    )
    confirmation = _confirmation(
        aggregate, expectations, current_conditions, periods_aligned
    )
    aggregate["confirms_primary"] = confirmation["aggregate_confirms"]
    current_conditions["confirms_primary"] = confirmation["current_conditions_confirms"]

    ds = _data_status(points_by_id)

    as_of = None
    for sid in ("umcsi_aggregate", "umcsi_expectations", "umcsi_current_conditions"):
        pts = points_by_id.get(sid)
        if pts:
            if as_of is None or pts[-1]["date"] > as_of:
                as_of = pts[-1]["date"]

    aligned_month = None
    if ds == "aligned_period":
        aligned_month = aggregate["date"] if aggregate["date"] else None

    large_decline = _large_expectations_decline(expectations_points)

    reasons = []
    if ds == "missing":
        reasons.append("sentiment data is missing")
    if ds == "mixed_periods":
        reasons.append("component observation months differ")
    if large_decline:
        reasons.append("large expectations decline")

    capacity_interpretations = _capacity_interpretations(
        points_by_id, real_rate_points or []
    )
    capacity_completeness = _capacity_completeness(points_by_id)
    if capacity_completeness == "partial":
        reasons.append("consumer capacity data is incomplete")
    if capacity_completeness == "missing":
        reasons.append("consumer capacity data is missing")

    capacity_read = _capacity_evidence_read(
        capacity_interpretations, capacity_completeness
    )

    result = {
        "method_version": 2,
        "as_of": as_of,
        "data_status": ds,
        "aligned_month": aligned_month,
        "percentile_method": {
            "version": 2,
            "window_months": 240,
            "lower_boundary": 15,
            "upper_boundary": 85,
            "rank_method": "midrank",
        },
        "primary_signal": _primary_signal(expectations),
        "confirmation": confirmation,
        "aggregate": _public_sentiment_metric(aggregate),
        "expectations": _public_sentiment_metric(expectations),
        "current_conditions": _public_sentiment_metric(current_conditions),
        "large_expectations_decline": large_decline,
        "capacity_completeness": capacity_completeness,
        "capacity_as_of": {
            sid: pts[-1]["date"] if pts else None for sid in CAPACITY_SERIES_IDS
        },
        "capacity_evidence": {
            **capacity_read,
            "drivers": capacity_interpretations,
        },
        "ability_read": _ability_read(capacity_interpretations),
        "reasons": reasons,
        "source_latest_final_month": as_of,
    }
    return result


def build_detail(points_by_id, policy_context=None, real_rate_points=None):
    summary = build_summary(points_by_id, policy_context, real_rate_points)
    history = {}
    for series_key in (
        "umcsi_aggregate",
        "umcsi_expectations",
        "umcsi_current_conditions",
    ):
        pts = points_by_id.get(series_key, [])
        history[series_key] = [
            {"date": p["date"], "value": p["value"], "source": p["source"]} for p in pts
        ]
    point_changes = {}
    for series_key in (
        "umcsi_aggregate",
        "umcsi_expectations",
        "umcsi_current_conditions",
    ):
        pts = points_by_id.get(series_key, [])
        changes = []
        for i, pt in enumerate(pts):
            if i == 0:
                continue
            expected_prior = _previous_calendar_month(pt["date"])
            prior_match = next(
                (p for p in reversed(pts[:i]) if p["date"] == expected_prior),
                None,
            )
            if prior_match:
                change = round(pt["value"] - prior_match["value"], 1)
                changes.append({"date": pt["date"], "point_change": change})
        point_changes[series_key] = changes
    capacity = {}
    for sid in CAPACITY_SERIES_IDS:
        pts = points_by_id.get(sid, [])
        capacity[sid] = [
            {"date": p["date"], "value": p["value"], "source": p["source"]} for p in pts
        ]
    capacity_interpretations = _capacity_interpretations(
        points_by_id, real_rate_points or []
    )
    household_gdp_note = _household_debt_gdp_quarter_note(
        points_by_id.get("household_debt_to_gdp", [])
    )
    detail = {
        "detail_id": "consumer_sentiment",
        "summary": summary,
        "history": history,
        "point_changes": point_changes,
        "capacity": capacity,
        "capacity_interpretations": capacity_interpretations,
        "household_debt_gdp_quarter_note": household_gdp_note,
        "percentile_windows": {
            "aggregate": _percentile_window(points_by_id.get("umcsi_aggregate", [])),
            "expectations": _percentile_window(
                points_by_id.get("umcsi_expectations", [])
            ),
            "current_conditions": _percentile_window(
                points_by_id.get("umcsi_current_conditions", [])
            ),
        },
    }
    return detail
