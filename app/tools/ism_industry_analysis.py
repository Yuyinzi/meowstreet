import re
from datetime import date

from app.tools.macro_growth_cycle import ism_at_a_glance_tone

CANONICAL_INDUSTRIES = (
    "Apparel, Leather & Allied Products",
    "Chemical Products",
    "Computer & Electronic Products",
    "Electrical Equipment, Appliances & Components",
    "Fabricated Metal Products",
    "Food, Beverage & Tobacco Products",
    "Furniture & Related Products",
    "Machinery",
    "Miscellaneous Manufacturing",
    "Nonmetallic Mineral Products",
    "Paper Products",
    "Petroleum & Coal Products",
    "Plastics & Rubber Products",
    "Primary Metals",
    "Printing & Related Support Activities",
    "Textile Mills",
    "Transportation Equipment",
    "Wood Products",
)

_CANONICAL_SET = set(CANONICAL_INDUSTRIES)

_KNOWN_ALIASES = {
    "Apparel, Leather and Allied Products": "Apparel, Leather & Allied Products",
    "Electrical Equipment, Appliances and Components": (
        "Electrical Equipment, Appliances & Components"
    ),
    "Fabricated Metal": "Fabricated Metal Products",
    "Food, Beverage and Tobacco Products": ("Food, Beverage & Tobacco Products"),
    "Furniture and Related Products": "Furniture & Related Products",
    "Miscellaneous": "Miscellaneous Manufacturing",
    "Nonmetallic Mineral": "Nonmetallic Mineral Products",
    "Paper": "Paper Products",
    "Petroleum and Coal Products": "Petroleum & Coal Products",
    "Plastics and Rubber Products": "Plastics & Rubber Products",
    "Printing and Related Support Activities": (
        "Printing & Related Support Activities"
    ),
    "Primary Metal": "Primary Metals",
    "Textile": "Textile Mills",
    "Transportation": "Transportation Equipment",
    "Wood": "Wood Products",
    "Computer and Electronic Products": "Computer & Electronic Products",
}

_ALIAS_MAP = dict(_KNOWN_ALIASES)


def normalize_industry(name):
    if not name or not isinstance(name, str):
        raise ValueError("industry name is required")
    normalized = " ".join(name.split())
    canonical = _ALIAS_MAP.get(normalized)
    if canonical:
        return canonical
    if normalized in _CANONICAL_SET:
        return normalized
    raise ValueError(f"unknown industry: {normalized}")


def validate_industry_name(name):
    try:
        normalize_industry(name)
        return True
    except ValueError:
        return False


CORE_SIGNAL_PAIRS = [
    ("new_orders", "growth", "decrease"),
    ("production", "growth", "decrease"),
    ("backlog", "higher", "lower"),
]

SECONDARY_SIGNAL_PAIRS = [
    ("employment", "growth", "decrease"),
    ("supplier_deliveries", "slower", "faster"),
    ("inventories", "higher", "lower"),
    ("customer_inventories", "too_low", "too_high"),
    ("prices", "increase", "decrease"),
    ("new_export_orders", "growth", "decrease"),
    ("imports", "higher", "lower"),
]

_OVERALL_POSITIVE = ("overall_growth", "growth")
_OVERALL_NEGATIVE = ("overall_contraction", "contraction")
_OVERALL_PAIRS = [_OVERALL_POSITIVE, _OVERALL_NEGATIVE]

SIGNAL_DIRECTION_NAMES = {
    ("new_orders", "growth"): "growth",
    ("new_orders", "decrease"): "decrease",
    ("production", "growth"): "growth",
    ("production", "decrease"): "decrease",
    ("backlog", "higher"): "higher",
    ("backlog", "lower"): "lower",
    ("employment", "growth"): "growth",
    ("employment", "decrease"): "decrease",
    ("supplier_deliveries", "slower"): "slower",
    ("supplier_deliveries", "faster"): "faster",
    ("inventories", "higher"): "higher",
    ("inventories", "lower"): "lower",
    ("customer_inventories", "too_low"): "too_low",
    ("customer_inventories", "too_high"): "too_high",
    ("prices", "increase"): "increase",
    ("prices", "decrease"): "decrease",
    ("new_export_orders", "growth"): "growth",
    ("new_export_orders", "decrease"): "decrease",
    ("imports", "higher"): "higher",
    ("imports", "lower"): "lower",
}

ISM_INDUSTRY_SIGNAL_SCORE_VERSION = "ism_industry_signal_v1"

ISM_INDUSTRY_SIGNAL_WEIGHTS = {
    "new_orders": 0.40,
    "production": 0.30,
    "backlog": 0.20,
    "overall": 0.10,
}

_SCORE_LABEL_THRESHOLDS = [
    (75.0, "strong"),
    (60.0, "improving"),
    (40.0, "mixed"),
    (25.0, "weakening"),
]


def _positive_score(rank, list_size):
    if rank < 1 or rank > list_size:
        raise ValueError(f"rank {rank} is out of range for list of size {list_size}")
    return 50.0 + 50.0 * (list_size - rank + 1) / list_size


def _negative_score(rank, list_size):
    if rank < 1 or rank > list_size:
        raise ValueError(f"rank {rank} is out of range for list of size {list_size}")
    return 50.0 - 50.0 * (list_size - rank + 1) / list_size


def _signal_component_score(signal_status):
    status = signal_status.get("status")
    if status == "not_reported":
        return 50.0
    if status == "positive":
        rank = signal_status.get("rank")
        list_size = signal_status.get("list_size")
        if rank is not None and list_size is not None:
            return _positive_score(rank, list_size)
        return None
    if status == "negative":
        rank = signal_status.get("rank")
        list_size = signal_status.get("list_size")
        if rank is not None and list_size is not None:
            return _negative_score(rank, list_size)
        return None
    return None


def _score_label(score):
    if score is None:
        return "unavailable"
    for threshold, label in _SCORE_LABEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "weak"


_SCORE_BEARING_SIGNALS = ["new_orders", "production", "backlog", "overall"]


def _build_industry_scores(overall_status, core_signals):
    component_scores = {}
    component_scores["new_orders"] = _signal_component_score(
        core_signals.get("new_orders", {})
    )
    component_scores["production"] = _signal_component_score(
        core_signals.get("production", {})
    )
    component_scores["backlog"] = _signal_component_score(
        core_signals.get("backlog", {})
    )
    component_scores["overall"] = _signal_component_score(overall_status)

    total_weight = 0.0
    weighted_sum = 0.0
    for signal_type, weight in ISM_INDUSTRY_SIGNAL_WEIGHTS.items():
        score = component_scores.get(signal_type)
        if score is not None:
            weighted_sum += score * weight
            total_weight += weight

    if total_weight == 0:
        return None, 0.0, "unavailable", component_scores

    score = weighted_sum / total_weight
    coverage = total_weight * 100
    label = _score_label(score)
    return score, coverage, label, component_scores


def _round_score(score):
    if score is None:
        return None
    return round(score, 1)


def _industry_sort_key(industry):
    score = industry.get("score")
    score_coverage = industry.get("score_coverage", 0)
    overall_signal = industry.get("overall_signal", {})
    overall_rank = overall_signal.get("rank")
    name = industry.get("industry", "").lower()
    score_sort = -score if score is not None else float("-inf")
    rank_sort = overall_rank if overall_rank is not None else float("inf")
    return (1 if score is None else 0, score_sort, -score_coverage, rank_sort, name)


def _group_signals_by_industry(signals):
    groups = {}
    for signal in signals:
        industry = normalize_industry(signal["industry"])
        groups.setdefault(industry, []).append(signal)
    return groups


def _group_coverage_by_key(coverage):
    return {(row["signal_type"], row["direction"]): row for row in coverage}


def _signal_list(signals, signal_type, direction):
    return [
        signal
        for signal in signals
        if signal["signal_type"] == signal_type and signal["direction"] == direction
    ]


def _first_signal(signals, signal_type, direction):
    matched = _signal_list(signals, signal_type, direction)
    return matched[0] if matched else None


def _derive_signal_status(industry, signals, coverage, signal_type, pos_dir, neg_dir):
    pos_key = (signal_type, pos_dir)
    neg_key = (signal_type, neg_dir)
    pos_coverage = coverage.get(pos_key)
    neg_coverage = coverage.get(neg_key)

    pos_signal = _first_signal(signals, signal_type, pos_dir)
    neg_signal = _first_signal(signals, signal_type, neg_dir)

    pos_complete = pos_coverage and pos_coverage["validation_status"] == "complete"
    neg_complete = neg_coverage and neg_coverage["validation_status"] == "complete"

    if pos_signal:
        if pos_complete:
            return {
                "status": "positive",
                "direction": SIGNAL_DIRECTION_NAMES[(signal_type, pos_dir)],
                "rank": pos_signal["rank"],
                "list_size": pos_coverage["declared_count"]
                or pos_coverage["extracted_count"],
                "evidence_text": pos_signal["evidence_text"],
            }
        return {
            "status": "positive",
            "direction": SIGNAL_DIRECTION_NAMES[(signal_type, pos_dir)],
            "rank": None,
            "list_size": None,
            "evidence_text": pos_signal["evidence_text"],
        }

    if neg_signal:
        if neg_complete:
            return {
                "status": "negative",
                "direction": SIGNAL_DIRECTION_NAMES[(signal_type, neg_dir)],
                "rank": neg_signal["rank"],
                "list_size": neg_coverage["declared_count"]
                or neg_coverage["extracted_count"],
                "evidence_text": neg_signal["evidence_text"],
            }
        return {
            "status": "negative",
            "direction": SIGNAL_DIRECTION_NAMES[(signal_type, neg_dir)],
            "rank": None,
            "list_size": None,
            "evidence_text": neg_signal["evidence_text"],
        }

    if pos_complete and neg_complete:
        return {
            "status": "not_reported",
            "direction": None,
            "rank": None,
            "list_size": None,
            "evidence_text": None,
        }

    return {
        "status": "unavailable",
        "direction": None,
        "rank": None,
        "list_size": None,
        "evidence_text": None,
    }


def _derive_overall_status(industry, signals, coverage):
    pos_signal = _first_signal(signals, "overall_growth", "growth")
    neg_signal = _first_signal(signals, "overall_contraction", "contraction")
    pos_coverage = coverage.get(("overall_growth", "growth"))
    neg_coverage = coverage.get(("overall_contraction", "contraction"))
    pos_complete = pos_coverage and pos_coverage["validation_status"] == "complete"
    neg_complete = neg_coverage and neg_coverage["validation_status"] == "complete"

    if pos_signal:
        if pos_complete:
            return {
                "status": "positive",
                "direction": "growth",
                "rank": pos_signal["rank"],
                "list_size": (
                    pos_coverage["declared_count"] or pos_coverage["extracted_count"]
                ),
            }
        return {
            "status": "positive",
            "direction": "growth",
            "rank": None,
            "list_size": None,
        }

    if neg_signal:
        if neg_complete:
            return {
                "status": "negative",
                "direction": "contraction",
                "rank": neg_signal["rank"],
                "list_size": (
                    neg_coverage["declared_count"] or neg_coverage["extracted_count"]
                ),
            }
        return {
            "status": "negative",
            "direction": "contraction",
            "rank": None,
            "list_size": None,
        }

    if pos_complete and neg_complete:
        return {
            "status": "not_reported",
            "direction": None,
            "rank": None,
            "list_size": None,
        }

    return {
        "status": "unavailable",
        "direction": None,
        "rank": None,
        "list_size": None,
    }


def _build_macro_context(at_a_glance_rows):
    series_map = {
        "ism_manufacturing_new_orders": "new_orders",
        "ism_manufacturing_production": "production",
        "ism_manufacturing_order_backlog": "backlog",
        "ism_manufacturing_inventories": "inventories",
        "ism_manufacturing_customer_inventories": "customer_inventories",
    }
    result = {}
    for row in at_a_glance_rows:
        key = series_map.get(row["series_id"])
        if key:
            result[key] = {
                "value": row["current_value"],
                "direction": row["direction"],
                "rate_of_change": row["rate_of_change"],
                "point_change": row.get("point_change"),
                "trend_months": row.get("trend_months"),
                "tone": ism_at_a_glance_tone(row),
            }
    return result


def _match_comments(industry, comments):
    matched = []
    for comment in comments:
        try:
            if normalize_industry(comment["industry"]) == industry:
                matched.append(comment["comment_text"])
        except ValueError:
            pass
    return matched


def _report_has_sufficient_coverage(coverage):
    core_keys = [
        ("new_orders", "growth"),
        ("new_orders", "decrease"),
        ("production", "growth"),
        ("production", "decrease"),
        ("backlog", "higher"),
        ("backlog", "lower"),
        ("overall_growth", "growth"),
        ("overall_contraction", "contraction"),
    ]
    for key in core_keys:
        cov = coverage.get(key)
        if not cov or cov["validation_status"] != "complete":
            return False
    return True


def _validate_signal_consistency(signals, coverage):
    groups = {}
    for signal in signals:
        key = (signal["signal_type"], signal["direction"])
        groups.setdefault(key, []).append(signal)
    coverage_by_key = {(c["signal_type"], c["direction"]): c for c in coverage}

    for cov in coverage:
        if cov["validation_status"] != "complete":
            continue
        if (
            cov["declared_count"] is not None
            and cov["extracted_count"] != cov["declared_count"]
        ):
            raise ValueError(
                f"{cov['signal_type']} {cov['direction']} coverage has "
                f"declared_count={cov['declared_count']} but "
                f"extracted_count={cov['extracted_count']}"
            )

    for key, group in groups.items():
        ranks = sorted(signal["rank"] for signal in group)
        expected = list(range(1, len(group) + 1))
        if ranks != expected:
            raise ValueError(
                f"industry signal ranks are incomplete for {key[0]} {key[1]}"
            )
        industries = [normalize_industry(signal["industry"]) for signal in group]
        if len(industries) != len(set(industries)):
            raise ValueError(f"industry signals are duplicated for {key[0]} {key[1]}")
        cov = coverage_by_key.get(key)
        if cov and cov["validation_status"] == "complete":
            expected_count = cov["declared_count"] or cov["extracted_count"]
            if expected_count is not None and len(group) != expected_count:
                raise ValueError(
                    f"{key[0]} {key[1]} has {len(group)} signal rows but "
                    f"coverage indicates {expected_count}"
                )

    for cov_key, cov in coverage_by_key.items():
        if cov["validation_status"] != "complete":
            continue
        expected_count = cov["declared_count"] or cov["extracted_count"]
        if expected_count is None or expected_count == 0:
            continue
        if cov_key not in groups:
            raise ValueError(
                f"{cov_key[0]} {cov_key[1]} has complete coverage with "
                f"{expected_count} industry(ies) but no signal rows exist"
            )


def build_ism_industry_analysis(
    report,
    industry_signals,
    signal_coverage,
    at_a_glance_rows,
    comments,
):
    if not report:
        return {
            "status": "unavailable",
            "reason": "latest ISM report is unavailable",
            "industries": [],
        }

    _validate_signal_consistency(industry_signals, signal_coverage)

    coverage = _group_coverage_by_key(signal_coverage)
    by_industry = _group_signals_by_industry(industry_signals)
    canonical_industries_set = set(by_industry.keys())

    status = "available" if _report_has_sufficient_coverage(coverage) else "partial"

    macro_context = _build_macro_context(at_a_glance_rows)

    industries = []
    for industry in canonical_industries_set:
        signals = by_industry[industry]

        overall = _derive_overall_status(industry, signals, coverage)
        core_signals = {}
        for signal_type, pos_dir, neg_dir in CORE_SIGNAL_PAIRS:
            core_signals[signal_type] = _derive_signal_status(
                industry, signals, coverage, signal_type, pos_dir, neg_dir
            )

        for signal_type in ["new_orders", "production", "backlog"]:
            cs = core_signals.get(signal_type, {})
            cs["component_score"] = _round_score(_signal_component_score(cs))

        overall["component_score"] = _round_score(_signal_component_score(overall))

        secondary_signals = {}
        for signal_type, pos_dir, neg_dir in SECONDARY_SIGNAL_PAIRS:
            secondary_signals[signal_type] = _derive_signal_status(
                industry, signals, coverage, signal_type, pos_dir, neg_dir
            )

        matched_comments = _match_comments(industry, comments)

        score, score_cov, score_label_val, _ = _build_industry_scores(
            overall, core_signals
        )

        summary_parts = []
        for signal_type, label in [
            ("new_orders", "New Orders"),
            ("production", "Production"),
            ("backlog", "Backlog"),
        ]:
            cs = core_signals.get(signal_type, {})
            if cs.get("status") == "positive":
                summary_parts.append(f"{label} is strong")
            elif cs.get("status") == "negative":
                summary_parts.append(f"{label} is weak")
            elif cs.get("status") == "not_reported":
                summary_parts.append(f"{label} was not reported")
        summary = "; ".join(summary_parts) if summary_parts else None

        industries.append(
            {
                "industry": industry,
                "overall_signal": {
                    "status": overall.get("status"),
                    "direction": overall.get("direction"),
                    "rank": overall.get("rank"),
                    "list_size": overall.get("list_size"),
                    "component_score": overall.get("component_score"),
                },
                "score": _round_score(score),
                "score_coverage": round(score_cov, 1),
                "score_label": score_label_val,
                "summary": summary,
                "core_signals": core_signals,
                "secondary_signals": secondary_signals,
                "comments": matched_comments,
            }
        )

    industries.sort(key=_industry_sort_key)

    missing_core = 0
    complete_components = 0
    unavailable_components = 0
    for industry in industries:
        for st in _SCORE_BEARING_SIGNALS:
            if st == "overall":
                sig_status = industry.get("overall_signal", {}).get("status")
            else:
                sig_status = industry["core_signals"].get(st, {}).get("status")
            if sig_status == "unavailable":
                unavailable_components += 1
                missing_core += 1
            else:
                complete_components += 1

    result = {
        "status": "partial" if missing_core > 0 else status,
        "score_version": ISM_INDUSTRY_SIGNAL_SCORE_VERSION,
        "score_weights": dict(ISM_INDUSTRY_SIGNAL_WEIGHTS),
        "coverage_summary": {
            "complete_components": complete_components,
            "unavailable_components": unavailable_components,
        },
        "report_id": report["report_id"],
        "period": report["report_month"],
        "source_url": report.get("source_url", ""),
        "macro_context": macro_context,
        "industries": industries,
    }
    return result


def _monthly_industry_point(
    industry_signals_for_month,
    coverage_for_month,
    industry,
):
    signals = [
        s
        for s in industry_signals_for_month
        if normalize_industry(s["industry"]) == industry
    ]
    coverage = _group_coverage_by_key(coverage_for_month)
    overall = _derive_overall_status(industry, signals, coverage)
    core_signals = {}
    for signal_type, pos_dir, neg_dir in CORE_SIGNAL_PAIRS:
        core_signals[signal_type] = _derive_signal_status(
            industry, signals, coverage, signal_type, pos_dir, neg_dir
        )

    for signal_type in ["new_orders", "production", "backlog"]:
        cs = core_signals.get(signal_type, {})
        cs["component_score"] = _round_score(_signal_component_score(cs))
    overall["component_score"] = _round_score(_signal_component_score(overall))

    sufficient = _report_has_sufficient_coverage(coverage)
    if sufficient:
        score, score_cov, _, _ = _build_industry_scores(overall, core_signals)
    else:
        _, score_cov, _, _ = _build_industry_scores(overall, core_signals)
        score = None

    confirmed = sum(
        1
        for st in ["new_orders", "production", "backlog"]
        if core_signals.get(st, {}).get("status") == "positive"
    )

    return {
        "score": _round_score(score),
        "score_coverage": round(score_cov, 1) if score_cov else 0.0,
        "overall_status": overall.get("status"),
        "overall_rank": overall.get("rank"),
        "overall_direction": overall.get("direction"),
        "positive_confirmation_count": confirmed,
        "new_orders": {
            "status": core_signals.get("new_orders", {}).get("status"),
            "rank": core_signals.get("new_orders", {}).get("rank"),
        },
        "production": {
            "status": core_signals.get("production", {}).get("status"),
            "rank": core_signals.get("production", {}).get("rank"),
        },
        "backlog": {
            "status": core_signals.get("backlog", {}).get("status"),
            "rank": core_signals.get("backlog", {}).get("rank"),
        },
    }


def _build_trend_summary(trend_points):
    if not trend_points:
        return {
            "latest_score_change": None,
            "positive_month_streak": 0,
            "negative_month_streak": 0,
            "broad_confirmation_streak": 0,
            "latest_positive_confirmation_count": 0,
            "eligible_month_count": 0,
            "requested_month_count": 0,
        }

    latest_score = trend_points[-1]["score"]
    prev_score = None
    for point in reversed(trend_points[:-1]):
        if point["score"] is not None:
            prev_score = point["score"]
            break

    latest_score_change = None
    if latest_score is not None and prev_score is not None:
        latest_score_change = round(latest_score - prev_score, 1)

    streak = 0
    later_period = None
    for point in reversed(trend_points):
        if point["overall_direction"] != "growth" or point.get("score") is None:
            break
        period = point.get("period")
        if later_period and not _report_months_are_adjacent(period, later_period):
            break
        streak += 1
        later_period = period

    neg_streak = 0
    later_period = None
    for point in reversed(trend_points):
        if (
            point["overall_direction"] not in ("contraction", "decrease", "lower")
            or point.get("score") is None
        ):
            break
        period = point.get("period")
        if later_period and not _report_months_are_adjacent(period, later_period):
            break
        neg_streak += 1
        later_period = period

    broad_confirmation_streak = 0
    later_period = None
    for point in reversed(trend_points):
        if point["positive_confirmation_count"] != 3:
            break
        period = point.get("period")
        if later_period and not _report_months_are_adjacent(period, later_period):
            break
        broad_confirmation_streak += 1
        later_period = period

    latest_confirmed = (
        trend_points[-1]["positive_confirmation_count"] if trend_points else 0
    )

    eligible = sum(1 for p in trend_points if p["score"] is not None)

    return {
        "latest_score_change": latest_score_change,
        "positive_month_streak": streak,
        "negative_month_streak": neg_streak,
        "broad_confirmation_streak": broad_confirmation_streak,
        "latest_positive_confirmation_count": latest_confirmed,
        "eligible_month_count": eligible,
        "requested_month_count": len(trend_points),
    }


def _report_months_are_adjacent(earlier, later):
    if not earlier or not later:
        return False
    earlier_date = date.fromisoformat(earlier)
    later_date = date.fromisoformat(later)
    return (
        later_date.year * 12
        + later_date.month
        - earlier_date.year * 12
        - earlier_date.month
        == 1
    )


def build_ism_industry_history(
    reports,
    industry_signals,
    signal_coverage,
    at_a_glance_rows,
):
    if not reports:
        return {}

    signals_by_report = {}
    for signal in industry_signals:
        signals_by_report.setdefault(signal["report_id"], []).append(signal)

    coverage_by_report = {}
    for cov in signal_coverage:
        coverage_by_report.setdefault(cov["report_id"], []).append(cov)

    report_months = {r["report_id"]: r["report_month"] for r in reports}

    latest_industries = set()
    latest_signals = signals_by_report.get(reports[-1]["report_id"], [])
    for signal in latest_signals:
        try:
            latest_industries.add(normalize_industry(signal["industry"]))
        except ValueError:
            pass

    industry_history = {}
    for industry in latest_industries:
        points = []
        for report in reports:
            rid = report["report_id"]
            sigs = signals_by_report.get(rid, [])
            covs = coverage_by_report.get(rid, [])
            point = _monthly_industry_point(sigs, covs, industry)
            point["period"] = report["report_month"]
            points.append(point)
        industry_history[industry] = {
            "trend": points,
            "trend_summary": _build_trend_summary(points),
        }

    return industry_history
