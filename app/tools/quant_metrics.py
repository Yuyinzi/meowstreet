from datetime import UTC, datetime, timedelta
from statistics import mean


_DIVIDEND_REVIEW_QUESTIONS = [
    "Is the company paying a dividend?",
    "How much?",
    "What is the likelihood of a cut?",
]

_FIXED_MISSING_INPUTS = [
    "interest_coverage",
    "working_capital_to_total_assets",
    "ev_to_ebit",
]


def pe_differential(forward_pe, peer_forward_pe):
    if forward_pe is None or peer_forward_pe is None:
        return None
    if peer_forward_pe == 0:
        return None
    return forward_pe / peer_forward_pe


def days_to_cover(shares_short, volumes):
    if shares_short is None:
        return {"value": None, "status": "insufficient_data", "sample_days": 0}
    n = len(volumes)
    if n < 30:
        return {"value": None, "status": "insufficient_data", "sample_days": n}
    avg_volume = mean(volumes)
    if avg_volume == 0:
        return {"value": None, "status": "insufficient_data", "sample_days": n}
    value = shares_short / avg_volume
    if value > 30:
        status = "officially_dangerous"
    elif value > 15:
        status = "dangerous"
    else:
        status = "within"
    return {"value": value, "status": status, "sample_days": n}


def short_check_payload(fundamentals, volumes):
    shares_short = fundamentals.get("shares_short") if fundamentals else None
    return {
        "short_percent_of_float": fundamentals.get("short_percent_of_float") if fundamentals else None,
        "days_to_cover": days_to_cover(shares_short, volumes),
        "dividend": {
            "yield": fundamentals.get("dividend_yield") if fundamentals else None,
            "review_questions": _DIVIDEND_REVIEW_QUESTIONS,
        },
    }


def _ratio_item(key, value, status, note=None):
    item = {"key": key, "value": value, "status": status}
    if note is not None:
        item["note"] = note
    return item


def backward_ratios_payload(fundamentals):
    ratios = []
    missing_inputs = list(_FIXED_MISSING_INPUTS)
    if fundamentals is None:
        fundamentals = {}

    debt_to_equity = fundamentals.get("debt_to_equity")
    if debt_to_equity is not None:
        ratio = debt_to_equity / 100
        status = "dangerous" if ratio > 2 else "within"
        ratios.append(
            _ratio_item(
                "debt_to_equity",
                ratio,
                status,
                note="yahoo reports percent; converted to ratio",
            )
        )
    else:
        ratios.append(_ratio_item("debt_to_equity", None, "info"))

    current_ratio = fundamentals.get("current_ratio")
    if current_ratio is not None:
        status = "warning" if current_ratio < 1 else "within"
        ratios.append(_ratio_item("current_ratio", current_ratio, status))
    else:
        ratios.append(_ratio_item("current_ratio", None, "info"))

    for key in ("quick_ratio", "return_on_equity", "return_on_assets", "book_value"):
        ratios.append(_ratio_item(key, fundamentals.get(key), "info"))

    market_cap = fundamentals.get("market_cap")
    free_cashflow = fundamentals.get("free_cashflow")
    if market_cap is not None and free_cashflow is not None:
        fcf_yield = free_cashflow / market_cap if market_cap != 0 else None
        if free_cashflow > 0:
            price_to_fcf = market_cap / free_cashflow
            note = None
        else:
            price_to_fcf = None
            note = "free cash flow is zero or negative; price to fcf unavailable"
        ratios.append(_ratio_item("fcf_yield", fcf_yield, "info"))
        ratios.append(_ratio_item("price_to_fcf", price_to_fcf, "info", note=note))
    else:
        ratios.append(_ratio_item("fcf_yield", None, "info"))
        ratios.append(_ratio_item("price_to_fcf", None, "info"))

    enterprise_value = fundamentals.get("enterprise_value")
    ebitda = fundamentals.get("ebitda")
    if enterprise_value is not None and ebitda is not None:
        if ebitda > 0:
            ev_to_ebitda = enterprise_value / ebitda
            note = None
        else:
            ev_to_ebitda = None
            note = "ebitda is zero or negative; ev/ebitda unavailable"
        ratios.append(_ratio_item("ev_to_ebitda", ev_to_ebitda, "info", note=note))
    else:
        ratios.append(_ratio_item("ev_to_ebitda", None, "info"))

    return {"ratios": ratios, "missing_inputs": missing_inputs}


_ESTIMATE_REVISION_WINDOW_DAYS = 30


def estimate_consensus_payload(consensus):
    if consensus is None:
        return {"status": "insufficient_data"}
    avg = consensus.get("avg")
    low = consensus.get("low")
    high = consensus.get("high")
    if avg is None or low is None or high is None:
        return {"status": "insufficient_data"}
    midpoint = (low + high) / 2
    if avg > midpoint:
        skew = "positive"
    elif avg < midpoint:
        skew = "negative"
    else:
        skew = "neutral"
    return {
        "status": "ok",
        "fiscal_year_end": consensus.get("fiscal_year_end"),
        "analyst_count": consensus.get("analyst_count"),
        "avg": avg,
        "low": low,
        "high": high,
        "midpoint": midpoint,
        "skew": skew,
    }


def _snapshot_avg(snapshot):
    if isinstance(snapshot, dict):
        return snapshot.get("avg")
    return dict(snapshot).get("avg")


def _snapshot_captured_at(snapshot):
    if isinstance(snapshot, dict):
        return snapshot.get("captured_at")
    return dict(snapshot).get("captured_at")


def estimate_revision_trend(snapshots, now):
    window_start = now - timedelta(days=_ESTIMATE_REVISION_WINDOW_DAYS)
    recent = [
        snapshot for snapshot in snapshots
        if datetime.fromisoformat(_snapshot_captured_at(snapshot)).replace(tzinfo=UTC) >= window_start
    ]
    recent.sort(key=lambda snapshot: _snapshot_captured_at(snapshot))
    n = len(recent)
    if n < 2:
        return {"status": "accumulating", "sample_snapshots": n}
    increases = 0
    decreases = 0
    for i in range(1, n):
        previous = _snapshot_avg(recent[i - 1])
        current = _snapshot_avg(recent[i])
        if current is None or previous is None:
            continue
        if current > previous:
            increases += 1
        elif current < previous:
            decreases += 1
    if increases > 0 and decreases == 0:
        direction = "up"
    elif decreases > 0 and increases == 0:
        direction = "down"
    elif increases == 0 and decreases == 0:
        direction = "flat"
    else:
        direction = "mixed"
    return {
        "status": "ok",
        "window_days": _ESTIMATE_REVISION_WINDOW_DAYS,
        "sample_snapshots": n,
        "avg_first": _snapshot_avg(recent[0]),
        "avg_latest": _snapshot_avg(recent[-1]),
        "increases": increases,
        "decreases": decreases,
        "direction": direction,
    }
