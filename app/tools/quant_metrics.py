from datetime import UTC, datetime, timedelta
from statistics import mean


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
    dividend_yield = fundamentals.get("dividend_yield") if fundamentals else None
    dividend = {"yield": dividend_yield}
    if dividend_yield is None:
        provider = str((fundamentals or {}).get("provider") or "yahoo").strip().lower()
        dividend["note"] = f"dividend yield not reported by {provider}"
    return {
        "short_percent_of_float": fundamentals.get("short_percent_of_float") if fundamentals else None,
        "days_to_cover": days_to_cover(shares_short, volumes),
        "dividend": dividend,
    }


def _ratio_item(key, value, status, note=None):
    item = {"key": key, "value": value, "status": status}
    if note is not None:
        item["note"] = note
    return item


def _ttm_value(facts, key):
    node = facts.get(key) or {}
    quarterly = node.get("quarterly") or []
    if len(quarterly) >= 4:
        return sum(entry["val"] for entry in quarterly[:4])
    annual = node.get("annual") or []
    if annual:
        return annual[0]["val"]
    return None


def _latest_instant(facts, key):
    node = facts.get(key) or {}
    instants = node.get("instant") or []
    if instants:
        return instants[0]["val"]
    return None


def backward_ratios_payload(fundamentals, statement_facts=None):
    ratios = []
    missing_inputs = []
    if fundamentals is None:
        fundamentals = {}
    facts = statement_facts or {}
    ebit_ttm = _ttm_value(facts, "ebit")
    interest_ttm = _ttm_value(facts, "interest_expense")
    assets_current = _latest_instant(facts, "assets_current")
    liabilities_current = _latest_instant(facts, "liabilities_current")
    assets_total = _latest_instant(facts, "assets")

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

    if ebit_ttm is None or interest_ttm is None:
        ratios.append(_ratio_item("interest_coverage", None, "info"))
        missing_inputs.append("interest_coverage")
    elif interest_ttm == 0:
        ratios.append(
            _ratio_item("interest_coverage", None, "info", note="no interest expense reported in ttm")
        )
    else:
        ratios.append(
            _ratio_item(
                "interest_coverage",
                ebit_ttm / interest_ttm,
                "info",
                note="operating income / interest expense, ttm, sec companyfacts",
            )
        )

    if assets_current is None or liabilities_current is None or not assets_total:
        ratios.append(_ratio_item("working_capital_to_total_assets", None, "info"))
        missing_inputs.append("working_capital_to_total_assets")
    else:
        ratios.append(
            _ratio_item(
                "working_capital_to_total_assets",
                (assets_current - liabilities_current) / assets_total,
                "info",
                note="(current assets - current liabilities) / total assets, sec companyfacts",
            )
        )

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

    if enterprise_value is None or ebit_ttm is None:
        ratios.append(_ratio_item("ev_to_ebit", None, "info"))
        missing_inputs.append("ev_to_ebit")
    elif ebit_ttm <= 0:
        ratios.append(
            _ratio_item("ev_to_ebit", None, "info", note="ebit is zero or negative; ev/ebit unavailable")
        )
    else:
        ratios.append(
            _ratio_item(
                "ev_to_ebit",
                enterprise_value / ebit_ttm,
                "info",
                note="ev from yahoo; ebit ttm from sec companyfacts",
            )
        )

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


_RATING_DISTRIBUTION_KEYS = ("strong_buy", "buy", "hold", "sell", "strong_sell")


def analyst_ratings_payload(snapshot, current_price):
    if snapshot is None:
        return {"status": "insufficient_data"}
    distribution = {key: snapshot.get(key) for key in _RATING_DISTRIBUTION_KEYS}
    if any(not isinstance(value, (int, float)) for value in distribution.values()):
        return {"status": "insufficient_data"}
    buy_total = distribution["strong_buy"] + distribution["buy"]
    sell_total = distribution["sell"] + distribution["strong_sell"]
    upgrade_room = "none" if distribution["hold"] + sell_total == 0 else "available"
    downgrade_room = "none" if buy_total + distribution["hold"] == 0 else "available"
    price_vs_target = None
    target_avg = snapshot.get("pt_avg")
    if current_price is not None and target_avg and current_price > 0:
        price_vs_target = {
            "price": current_price,
            "target_avg": target_avg,
            "upside_pct": (target_avg - current_price) / current_price * 100,
            "price_above_target": current_price > target_avg,
        }
    monthly_trend = [
        {
            "date": entry.get("date"),
            "buy_total": (entry.get("strong_buy") or 0) + (entry.get("buy") or 0),
            "hold": entry.get("hold"),
            "sell_total": (entry.get("sell") or 0) + (entry.get("strong_sell") or 0),
            "total": entry.get("total"),
            "consensus": entry.get("consensus"),
        }
        for entry in snapshot.get("monthly_history") or []
        if isinstance(entry, dict) and entry.get("date")
    ]
    return {
        "status": "ok",
        "consensus": snapshot.get("consensus"),
        "analyst_count": snapshot.get("analyst_count"),
        "distribution": distribution,
        "buy_total": buy_total,
        "sell_total": sell_total,
        "upgrade_room": upgrade_room,
        "downgrade_room": downgrade_room,
        "price_target": {
            "avg": snapshot.get("pt_avg"),
            "median": snapshot.get("pt_median"),
            "low": snapshot.get("pt_low"),
            "high": snapshot.get("pt_high"),
            "count": snapshot.get("pt_count"),
        },
        "price_vs_target": price_vs_target,
        "monthly_trend": monthly_trend,
    }
