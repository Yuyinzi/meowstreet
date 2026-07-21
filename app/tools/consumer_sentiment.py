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


def _aggregate_zone(value):
    if value is None:
        return "ambiguous"
    if value > 80:
        return "bullish"
    if 70 < value <= 80:
        return "benign"
    if 55 <= value < 70:
        return "bearish"
    return "ambiguous"


def _expectations_zone(value):
    if value is None:
        return "ambiguous"
    if 95 <= value <= 110:
        return "peak"
    if 70 < value <= 90:
        return "steady_growth"
    if 55 <= value < 70:
        return "trough"
    return "ambiguous"


def _evidence_state(aggregate_zone, expectations_zone):
    if aggregate_zone == "ambiguous" or expectations_zone == "ambiguous":
        return "ambiguous"
    aggregate_positive = aggregate_zone in ("bullish", "benign")
    aggregate_bearish = aggregate_zone == "bearish"
    expectations_positive = expectations_zone in ("peak", "steady_growth")
    expectations_trough = expectations_zone == "trough"
    if aggregate_positive and expectations_positive:
        return "supportive"
    if aggregate_bearish and expectations_trough:
        return "adverse"
    return "conflicting"


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
        return "current"
    return "mixed_periods"


def _large_expectations_decline(expectations_points):
    change = _point_change(expectations_points)
    if change is None:
        return False
    return change < -10


def build_summary(points_by_id, policy_context=None):
    aggregate_points = points_by_id.get("umcsi_aggregate", [])
    expectations_points = points_by_id.get("umcsi_expectations", [])
    current_points = points_by_id.get("umcsi_current_conditions", [])

    aggregate_latest = _latest_point(aggregate_points)
    expectations_latest = _latest_point(expectations_points)
    current_latest = _latest_point(current_points)

    agg_value = aggregate_latest["value"] if aggregate_latest else None
    exp_value = expectations_latest["value"] if expectations_latest else None
    cur_value = current_latest["value"] if current_latest else None

    agg_zone = _aggregate_zone(agg_value)
    exp_zone = _expectations_zone(exp_value)

    ds = _data_status(points_by_id)
    aggregate_missing = not aggregate_points
    expectations_missing = not expectations_points

    if aggregate_missing or expectations_missing or ds == "mixed_periods":
        evidence = "insufficient_data"
    else:
        evidence = _evidence_state(agg_zone, exp_zone)

    capacity_completeness = _capacity_completeness(points_by_id)

    latest_months = []
    for sid in ("umcsi_aggregate", "umcsi_expectations", "umcsi_current_conditions"):
        pts = points_by_id.get(sid)
        if pts:
            latest_months.append(pts[-1]["date"])
    common_month = (
        max(latest_months, key=lambda d: (latest_months.count(d), d))
        if latest_months
        else None
    )

    reasons = []
    if evidence == "insufficient_data":
        if aggregate_missing:
            reasons.append("aggregate sentiment is missing")
        if expectations_missing:
            reasons.append("expectations are missing")
        if ds == "mixed_periods":
            reasons.append("umcsi observation months differ")
    if ds == "mixed_periods":
        reasons.append("component periods are mixed")
    if evidence == "ambiguous":
        reasons.append("sentiment zone is ambiguous")
    if evidence == "conflicting":
        reasons.append("aggregate and expectations zones conflict")
    if evidence == "adverse":
        reasons.append("aggregate and expectations both indicate adversity")
    if capacity_completeness == "partial":
        reasons.append("consumer capacity data is incomplete")
    if capacity_completeness == "missing":
        reasons.append("consumer capacity data is missing")

    large_decline = _large_expectations_decline(expectations_points)
    if large_decline:
        reasons.append("large expectations decline")

    result = {
        "version": 1,
        "as_of": common_month,
        "data_status": ds,
        "evidence_state": evidence,
        "aggregate": {
            "value": agg_value,
            "date": aggregate_latest["date"] if aggregate_latest else None,
            "point_change": _point_change(aggregate_points),
            "zone": agg_zone,
            "source": "University of Michigan Table 1" if aggregate_latest else None,
        },
        "expectations": {
            "value": exp_value,
            "date": expectations_latest["date"] if expectations_latest else None,
            "point_change": _point_change(expectations_points),
            "zone": exp_zone,
            "source": "University of Michigan Table 5" if expectations_latest else None,
        },
        "current_conditions": {
            "value": cur_value,
            "date": current_latest["date"] if current_latest else None,
            "source": "University of Michigan Table 5" if current_latest else None,
        },
        "large_expectations_decline": large_decline,
        "capacity_completeness": capacity_completeness,
        "capacity_as_of": {
            sid: pts[-1]["date"] if pts else None for sid in CAPACITY_SERIES_IDS
        },
        "reasons": reasons,
        "source_latest_final_month": common_month,
    }
    return result


def build_detail(points_by_id, policy_context=None):
    summary = build_summary(points_by_id, policy_context)
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
    detail = {
        "detail_id": "consumer_sentiment",
        "summary": summary,
        "history": history,
        "point_changes": point_changes,
        "capacity": capacity,
    }
    return detail
