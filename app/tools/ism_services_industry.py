SERVICES_COMPONENTS = (
    ("business_activity", "Business Activity"),
    ("new_orders", "New Orders"),
    ("employment", "Employment"),
    ("supplier_deliveries", "Supplier Deliveries"),
    ("inventories", "Inventories"),
    ("inventory_sentiment", "Inventory Sentiment"),
    ("prices", "Prices"),
    ("backlog", "Order Backlog"),
    ("new_export_orders", "New Export Orders"),
    ("imports", "Imports"),
)

SERVICES_DIRECTION_LABELS = {
    "growth": "Growth",
    "contraction": "Contraction",
    "higher": "Higher",
    "lower": "Lower",
    "increase": "Increase",
    "decrease": "Decrease",
    "slower": "Slower",
    "faster": "Faster",
    "too_low": "Too Low",
    "too_high": "Too High",
    "no_change": "No Change",
    "reduction": "Reduction",
}

_SERVICES_COMPONENT_LABELS = dict(SERVICES_COMPONENTS)
_SERVICES_COMPONENT_INDEX = {
    signal_type: index for index, (signal_type, label) in enumerate(SERVICES_COMPONENTS)
}

CANONICAL_INDUSTRIES = (
    "Accommodation & Food Services",
    "Agriculture, Forestry, Fishing & Hunting",
    "Arts, Entertainment & Recreation",
    "Construction",
    "Educational Services",
    "Finance & Insurance",
    "Health Care & Social Assistance",
    "Information",
    "Management of Companies & Support Services",
    "Mining",
    "Other Services",
    "Professional, Scientific & Technical Services",
    "Public Administration",
    "Real Estate, Rental & Leasing",
    "Retail Trade",
    "Transportation & Warehousing",
    "Utilities",
    "Wholesale Trade",
)

_CANONICAL_SET = frozenset(CANONICAL_INDUSTRIES)


def normalize_industry(name):
    if not name or not isinstance(name, str):
        raise ValueError("industry name is required")
    normalized = " ".join(name.split())
    if normalized in _CANONICAL_SET:
        return normalized
    raise ValueError(f"unknown services industry: {normalized}")


def _group_rankings(rankings):
    groups = {}
    for row in rankings:
        try:
            industry = normalize_industry(row["industry"])
        except ValueError:
            continue
        groups.setdefault(industry, []).append(row)
    for industry in groups:
        groups[industry].sort(key=lambda r: r["date"])
    return groups


def _direction_change(prev_direction, curr_direction):
    if prev_direction == curr_direction:
        return None
    return f"{prev_direction}_to_{curr_direction}"


def _month_diff(date1, date2):
    y1, m1, _ = date1.split("-")
    y2, m2, _ = date2.split("-")
    return (int(y1) * 12 + int(m1)) - (int(y2) * 12 + int(m2))


def _six_months_earlier(date_str):
    year, month, day = date_str.split("-")
    month_num = int(month) - 6
    year_num = int(year)
    if month_num <= 0:
        month_num += 12
        year_num -= 1
    return f"{year_num:04d}-{month_num:02d}-{day}"


def _positive_streak(rows):
    streak = 0
    prev_date = None
    for row in reversed(rows):
        if row["direction"] != "growth":
            break
        if prev_date is not None and _month_diff(prev_date, row["date"]) != 1:
            break
        prev_date = row["date"]
        streak += 1
    return streak


def _negative_streak(rows):
    streak = 0
    prev_date = None
    for row in reversed(rows):
        if row["direction"] != "contraction":
            break
        if prev_date is not None and _month_diff(prev_date, row["date"]) != 1:
            break
        prev_date = row["date"]
        streak += 1
    return streak


def _match_comments(industry, comments):
    matched = []
    for comment in comments:
        try:
            if normalize_industry(comment["industry"]) == industry:
                matched.append(comment["comment_text"])
        except ValueError:
            pass
    return matched


def _safe_normalize_industry(name):
    try:
        return normalize_industry(name)
    except ValueError:
        return None


def _same_direction_rank_change(rows):
    if len(rows) < 2 or rows[-2]["direction"] != rows[-1]["direction"]:
        return None
    return rows[-1]["rank"] - rows[-2]["rank"]


def _latest_direction_change(rows):
    if len(rows) < 2 or rows[-2]["direction"] == rows[-1]["direction"]:
        return None
    return f"{rows[-2]['direction']}_to_{rows[-1]['direction']}"


def _direction_streak(rows):
    if not rows:
        return {"direction": None, "months": 0}
    latest_direction = rows[-1]["direction"]
    months = 0
    previous_date = None
    for row in reversed(rows):
        if row["direction"] != latest_direction:
            break
        if previous_date is not None and _month_diff(previous_date, row["date"]) != 1:
            break
        previous_date = row["date"]
        months += 1
    return {"direction": latest_direction, "months": months}


def _coverage_by_key(coverage_rows):
    return {(row["signal_type"], row["direction"]): row for row in coverage_rows}


def _component_list_size(coverage, signal_type, direction):
    row = coverage.get((signal_type, direction))
    if not row or row.get("validation_status") != "complete":
        return None
    declared_count = row.get("declared_count")
    return declared_count if declared_count is not None else row.get("extracted_count")


def _component_coverage_info(coverage_rows):
    services_rows = [
        row for row in coverage_rows if row["signal_type"] in _SERVICES_COMPONENT_LABELS
    ]
    if not services_rows:
        return "unavailable", None
    all_absent = all(row.get("validation_status") == "absent" for row in services_rows)
    if all_absent:
        return "absent", 0
    known = {
        row["signal_type"]
        for row in services_rows
        if row.get("validation_status") == "complete" and row.get("list_present")
    }
    status = "available" if known else "unavailable"
    return status, len(known) if known else None


def _component_signals_for_industry(industry, signals, coverage):
    rows = []
    for signal in signals:
        signal_type = signal.get("signal_type")
        if signal_type not in _SERVICES_COMPONENT_LABELS:
            continue
        if _safe_normalize_industry(signal.get("industry")) != industry:
            continue
        direction = signal.get("direction")
        rows.append(
            {
                "signal_type": signal_type,
                "label": _SERVICES_COMPONENT_LABELS[signal_type],
                "direction": direction,
                "direction_label": SERVICES_DIRECTION_LABELS.get(
                    direction, str(direction or "").replace("_", " ").title()
                ),
                "rank": signal.get("rank"),
                "list_size": _component_list_size(coverage, signal_type, direction),
            }
        )
    rows.sort(
        key=lambda row: (
            _SERVICES_COMPONENT_INDEX[row["signal_type"]],
            row["rank"] if row["rank"] is not None else 10_000,
        )
    )
    return rows


def build_services_industry_analysis(
    rankings,
    component_signals,
    coverage_rows,
    comments,
    period,
    source_url,
):
    if period is None:
        return {
            "status": "unavailable",
            "reason": "Services report period is unavailable",
            "period": None,
            "source_url": source_url,
            "growing_industries": [],
            "contracting_industries": [],
            "industries": [],
        }
    grouped_rankings = _group_rankings(
        [row for row in rankings if row.get("date") <= period]
    )
    latest_rows = [
        rows[-1]
        for rows in grouped_rankings.values()
        if rows and rows[-1]["date"] == period
    ]
    if not latest_rows:
        return {
            "status": "unavailable",
            "reason": f"Services industry rankings are unavailable for {period}",
            "period": period,
            "source_url": source_url,
            "growing_industries": [],
            "contracting_industries": [],
            "industries": [],
        }
    coverage = _coverage_by_key(coverage_rows)
    coverage_status, available_components = _component_coverage_info(coverage_rows)
    cutoff = _six_months_earlier(period)
    industries = []
    for latest in latest_rows:
        industry = normalize_industry(latest["industry"])
        recent = [row for row in grouped_rankings[industry] if row["date"] >= cutoff]
        history_rows = recent[-6:]
        industry_components = _component_signals_for_industry(
            industry, component_signals, coverage
        )
        industries.append(
            {
                "industry": industry,
                "direction": latest["direction"],
                "rank": latest["rank"],
                "direction_change": _latest_direction_change(history_rows),
                "rank_change": _same_direction_rank_change(history_rows),
                "streak": _direction_streak(history_rows),
                "trend": [
                    {
                        "period": row["date"],
                        "direction": row["direction"],
                        "rank": row["rank"],
                    }
                    for row in history_rows
                ],
                "component_signals": industry_components,
                "component_coverage": {
                    "listed_components": len(
                        {row["signal_type"] for row in industry_components}
                    ),
                    "available_components": available_components,
                    "coverage_status": coverage_status,
                },
                "comments": _match_comments(industry, comments),
            }
        )
    growing = sorted(
        (
            {"industry": row["industry"], "rank": row["rank"]}
            for row in industries
            if row["direction"] == "growth"
        ),
        key=lambda row: row["rank"],
    )
    contracting = sorted(
        (
            {"industry": row["industry"], "rank": row["rank"]}
            for row in industries
            if row["direction"] == "contraction"
        ),
        key=lambda row: row["rank"],
    )
    industries.sort(
        key=lambda row: (
            0 if row["direction"] == "growth" else 1,
            row["rank"],
            row["industry"],
        )
    )
    return {
        "status": "available",
        "period": period,
        "source_url": source_url,
        "growing_industries": growing,
        "contracting_industries": contracting,
        "industries": industries,
    }


def _normalize_and_filter_signals(signals, industry, signal_type, alt_signal_type=None):
    result = []
    for sig in signals:
        try:
            sig_industry = normalize_industry(sig.get("industry", ""))
        except ValueError:
            continue
        if sig_industry != industry:
            continue
        if sig.get("signal_type") in (signal_type, alt_signal_type):
            result.append(sig)
    return result


def _signal_trend_list_size(coverage, signal_type, direction):
    for c in coverage:
        if c["signal_type"] == signal_type and c["direction"] == direction:
            count = c.get("declared_count") or c.get("extracted_count")
            return count
    return None


def _signal_trend_cell(signals, coverage, industry, signal_type, alt_signal_type=None):
    matching = _normalize_and_filter_signals(
        signals, industry, signal_type, alt_signal_type
    )
    if len(matching) == 1:
        sig = matching[0]
        direction = sig["direction"]
        list_size = _signal_trend_list_size(coverage, sig["signal_type"], direction)
        return {
            "status": "listed",
            "direction": direction,
            "direction_label": SERVICES_DIRECTION_LABELS.get(
                direction, str(direction or "").replace("_", " ").title()
            ),
            "rank": sig["rank"],
            "list_size": list_size,
        }
    if len(matching) > 1:
        return {
            "status": "conflicting",
            "direction": None,
            "direction_label": "Conflicting",
            "rank": None,
            "list_size": None,
        }
    signal_types_to_check = {signal_type}
    if alt_signal_type:
        signal_types_to_check.add(alt_signal_type)
    relevant = [c for c in coverage if c["signal_type"] in signal_types_to_check]
    if relevant and all(c.get("validation_status") == "complete" for c in relevant):
        return {
            "status": "not_listed",
            "direction": None,
            "direction_label": "Not listed",
            "rank": None,
            "list_size": None,
        }
    return {
        "status": "unavailable",
        "direction": None,
        "direction_label": "Unavailable",
        "rank": None,
        "list_size": None,
    }


def build_services_signal_trend(reports, industry_signals, signal_coverage, industry):
    signals_by_report = {}
    for sig in industry_signals:
        signals_by_report.setdefault(sig["report_id"], []).append(sig)
    coverage_by_report = {}
    for cov in signal_coverage:
        coverage_by_report.setdefault(cov["report_id"], []).append(cov)
    sorted_reports = sorted(reports, key=lambda r: r["report_month"])
    points = []
    for report in sorted_reports:
        rid = report["report_id"]
        sigs = signals_by_report.get(rid, [])
        covs = coverage_by_report.get(rid, [])
        components = {}
        for signal_type, label in SERVICES_COMPONENTS:
            components[signal_type] = _signal_trend_cell(
                sigs, covs, industry, signal_type
            )
        points.append(
            {
                "period": report["report_month"],
                "overall": _signal_trend_cell(
                    sigs, covs, industry, "overall_growth", "overall_contraction"
                ),
                "components": components,
            }
        )
    return points


def _direction_change_from_rows(rows):
    if len(rows) < 2:
        return None
    prev = rows[-2]
    curr = rows[-1]
    if prev["direction"] != curr["direction"]:
        return _direction_change(prev["direction"], curr["direction"])
    return None


def _rank_change_from_rows(rows):
    if len(rows) < 2:
        return None
    return rows[-1]["rank"] - rows[-2]["rank"]


def build_industry_payload(rankings, comments):
    groups = _group_rankings(rankings)
    industries = []
    for industry in sorted(groups):
        rows = groups[industry]
        latest = rows[-1]

        matched_comments = _match_comments(industry, comments)

        industries.append(
            {
                "industry": industry,
                "latest_date": latest["date"],
                "direction": latest["direction"],
                "rank": latest["rank"],
                "direction_change": _direction_change_from_rows(rows),
                "rank_change": _rank_change_from_rows(rows),
                "positive_streak": _positive_streak(rows),
                "negative_streak": _negative_streak(rows),
                "comments": matched_comments,
            }
        )
    return {"industries": industries}


def _latest_month_date(rankings):
    return max(row["date"] for row in rankings) if rankings else None


_UNSET = object()


def build_breadth(rankings, max_date=_UNSET):
    if max_date is _UNSET:
        latest = _latest_month_date(rankings)
    elif max_date is None:
        latest = None
    else:
        latest = max_date
    if latest is None or (
        max_date is not _UNSET
        and max_date is not None
        and not any(row["date"] == max_date for row in rankings)
    ):
        return {
            "growth_count": 0,
            "contraction_count": 0,
            "neutral_count": 0,
            "total_count": 0,
            "status": None,
        }

    growth_count = 0
    contraction_count = 0
    neutral_count = 0
    for row in rankings:
        if row["date"] != latest:
            continue
        try:
            normalize_industry(row["industry"])
        except ValueError:
            continue
        if row["direction"] == "growth":
            growth_count += 1
        elif row["direction"] == "contraction":
            contraction_count += 1
        else:
            neutral_count += 1

    total_count = growth_count + contraction_count + neutral_count

    if growth_count > contraction_count:
        status = "supportive"
    elif contraction_count > growth_count:
        status = "warning"
    else:
        status = "mixed"

    return {
        "growth_count": growth_count,
        "contraction_count": contraction_count,
        "neutral_count": neutral_count,
        "total_count": total_count,
        "status": status,
    }
