SERIES_TO_KEY = {
    "ism_services_pmi": "pmi",
    "ism_services_business_activity": "business_activity",
    "ism_services_new_orders": "new_orders",
    "ism_services_order_backlog": "order_backlog",
}

REQUIRED_LABELS = {
    "pmi": "Services PMI",
    "business_activity": "Business Activity",
    "new_orders": "New Orders",
}


def _metric(rows):
    clean = [row for row in rows if row.get("value") is not None]
    if not clean:
        return None
    latest = clean[-1]
    previous = clean[-2] if len(clean) > 1 else None
    change = latest["value"] - previous["value"] if previous else None
    return {
        "period": latest["date"],
        "value": float(latest["value"]),
        "previous_value": float(previous["value"]) if previous else None,
        "point_change": change,
        "level": "expanding"
        if latest["value"] > 50
        else "contracting"
        if latest["value"] < 50
        else "neutral",
        "momentum": "rising"
        if change is not None and change > 0
        else "falling"
        if change is not None and change < 0
        else "flat"
        if change == 0
        else "unavailable",
    }


def build_signal(points_by_series_id):
    metrics = {
        key: _metric(points_by_series_id.get(series_id, []))
        for series_id, key in SERIES_TO_KEY.items()
    }
    missing = sorted(
        label for key, label in REQUIRED_LABELS.items() if metrics[key] is None
    )
    if missing:
        return {
            "version": "ism_services_signal_v1",
            "state": "pending_inputs",
            "metrics": metrics,
            "missing_inputs": missing,
        }
    pmi = metrics["pmi"]
    activity = metrics["business_activity"]
    orders = metrics["new_orders"]
    periods = {pmi["period"], activity["period"], orders["period"]}
    if len(periods) > 1:
        return {
            "version": "ism_services_signal_v1",
            "state": "stale_periods",
            "period": max(periods),
            "metrics": metrics,
            "backlog_confirmation": "unavailable",
            "missing_inputs": [],
            "note": f"required metrics span multiple periods: {', '.join(sorted(periods))}",
        }
    if all(metric["value"] > 50 for metric in (pmi, activity, orders)):
        state = "supports_growth"
    elif pmi["value"] > 50 and (activity["value"] <= 50 or orders["value"] <= 50):
        state = "growth_caution"
    elif (
        pmi["value"] < 50
        and pmi["momentum"] == "rising"
        and "rising" in (activity["momentum"], orders["momentum"])
    ):
        state = "contraction_easing"
    elif all(metric["value"] < 50 for metric in (pmi, activity, orders)):
        state = "supports_contraction"
    else:
        state = "mixed"
    backlog = metrics["order_backlog"]
    backlog_state = "unavailable"
    if backlog and backlog["period"] == pmi["period"]:
        backlog_state = (
            backlog["level"]
            .replace("expanding", "supports_growth")
            .replace("contracting", "supports_contraction")
        )
    return {
        "version": "ism_services_signal_v1",
        "state": state,
        "period": pmi["period"],
        "metrics": metrics,
        "backlog_confirmation": backlog_state,
        "missing_inputs": [],
    }


def build_latest_payload(points_by_series_id):
    period = None
    payload = {}
    for series_id, key in SERIES_TO_KEY.items():
        points = points_by_series_id.get(series_id, [])
        if not points:
            payload[key] = None
            continue
        latest = points[-1]
        payload[key] = latest["value"]
        if period is None or latest["date"] > period:
            period = latest["date"]
    return {"period": period, **payload}


def build_card(signal, breadth):
    metrics = signal.get("metrics", {})
    pmi = metrics.get("pmi") or {}
    activity = metrics.get("business_activity") or {}
    orders = metrics.get("new_orders") or {}
    return {
        "id": "ism_services",
        "segments": {
            "services_cycle": {
                "value": pmi.get("value"),
                "label": pmi.get("level"),
                "state": signal.get("state"),
                "pmi": pmi.get("value"),
                "level": pmi.get("level"),
                "momentum": pmi.get("momentum"),
                "backlog_confirmation": signal.get("backlog_confirmation"),
            },
            "business_activity": {
                "value": activity.get("value"),
                "trend": activity.get("momentum"),
                "level": activity.get("level"),
                "momentum": activity.get("momentum"),
            },
            "new_orders": {
                "value": orders.get("value"),
                "trend": orders.get("momentum"),
                "level": orders.get("level"),
                "momentum": orders.get("momentum"),
            },
            "industry_breadth": breadth,
        },
    }


def build_detail(points_by_series_id, signal, industry_payload):
    all_keys = list(SERIES_TO_KEY.values())
    labels = {
        "pmi": "PMI",
        "business_activity": "Business Activity",
        "new_orders": "New Orders",
        "order_backlog": "Order Backlog",
    }
    rows_by_date = {}
    for series_id, key in SERIES_TO_KEY.items():
        for point in points_by_series_id.get(series_id, []):
            if point.get("value") is None:
                continue
            row = rows_by_date.setdefault(point["date"], {"date": point["date"]})
            row[key] = float(point["value"])
    all_rows = [rows_by_date[date_key] for date_key in sorted(rows_by_date)]
    latest = dict(all_rows[-1]) if all_rows else None
    if latest:
        latest.pop("date", None)
    return {
        "detail_id": "ism_services",
        "title": "ISM Services",
        "charts": [
            {
                "id": "ism_services_heat_map",
                "kind": "heat_map",
                "title": "ISM Services Heat Map",
                "keys": all_keys,
                "labels": labels,
                "series": all_rows,
            },
        ],
        "latest": latest,
        "signal": signal,
        "industries": industry_payload,
    }
