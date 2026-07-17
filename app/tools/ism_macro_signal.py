ISM_MACRO_SIGNAL_VERSION = "ism_macro_signal_v1"

_REQUIRED_METRICS = ["pmi", "new_orders"]
_OPTIONAL_METRICS = ["production", "inventories", "prices", "supplier_deliveries"]
_ALL_METRICS = _REQUIRED_METRICS + _OPTIONAL_METRICS

_SERIES_IDS = {
    "pmi": "ism_manufacturing_pmi",
    "new_orders": "ism_manufacturing_new_orders",
    "production": "ism_manufacturing_production",
    "inventories": "ism_manufacturing_inventories",
    "prices": "ism_manufacturing_prices",
    "supplier_deliveries": "ism_manufacturing_supplier_deliveries",
}


def _phase(pmi):
    if pmi is None:
        return "unavailable"
    if pmi >= 60:
        return "late_expansion"
    if pmi > 50:
        return "expansion"
    if pmi >= 45:
        return "slowdown"
    return "contraction"


def _momentum(point_change):
    if point_change is None:
        return "unavailable"
    if point_change > 0:
        return "rising"
    if point_change < 0:
        return "falling"
    return "flat"


def _level_state(value):
    if value is None:
        return "unavailable"
    if value > 50:
        return "expanding"
    if value < 50:
        return "contracting"
    return "neutral"


def _metric_confirmation(current, previous):
    if current is None or previous is None:
        return "unavailable"
    pc = current - previous
    momentum = "rising" if pc > 0 else ("falling" if pc < 0 else "flat")
    if current > 50 and momentum != "falling":
        return "positive"
    if current < 50 and momentum != "rising":
        return "negative"
    return "mixed"


def _industry_breadth_status(growth_count, contraction_count):
    if growth_count is None or contraction_count is None:
        return "unavailable"
    if growth_count > contraction_count:
        return "positive"
    if contraction_count > growth_count:
        return "negative"
    return "mixed"


def _cycle_state(pmi_value, pmi_momentum, new_orders_momentum):
    if pmi_value is None or pmi_momentum in (None, "unavailable"):
        return "unavailable"
    if pmi_value >= 60 and pmi_momentum == "falling":
        return "peaking"
    if (
        40 <= pmi_value <= 45
        and pmi_momentum != "falling"
        and new_orders_momentum == "rising"
    ):
        return "troughing"
    if pmi_value > 50 and pmi_momentum == "rising":
        return "expansion_rising"
    if pmi_value > 50 and pmi_momentum == "falling":
        return "expansion_slowing"
    if pmi_value <= 50 and pmi_momentum == "rising":
        return "contraction_improving"
    if pmi_value < 50 and pmi_momentum == "falling":
        return "contraction_deepening"
    if pmi_momentum == "flat":
        return "stable"
    return "unavailable"


def _growth_impulse(
    cycle_state, pmi_value, pmi_momentum, new_orders_value, new_orders_momentum
):
    if cycle_state == "troughing":
        return "turning_supportive"
    required = (pmi_value, pmi_momentum, new_orders_value, new_orders_momentum)
    if any(v is None for v in required):
        return "unavailable"
    if (
        pmi_value > 50
        and pmi_momentum == "rising"
        and new_orders_value > 50
        and new_orders_momentum != "falling"
    ):
        return "supports_growth"
    if (pmi_value >= 60 and pmi_momentum == "falling") or (
        pmi_value > 50 and new_orders_value < 50
    ):
        return "growth_caution"
    if pmi_value < 50 and pmi_momentum == "falling" and new_orders_value < 50:
        return "supports_contraction"
    if pmi_value < 50 and pmi_momentum == "rising":
        return "contraction_easing"
    return "mixed"


def _confidence_signal(status, production_conf, inventories_conf, breadth_conf):
    if status == "unavailable":
        return "unavailable"
    optional_available = sum(
        1
        for c in (production_conf, inventories_conf, breadth_conf)
        if c != "unavailable"
    )
    if status == "available" and optional_available >= 3:
        return "high"
    if status == "available" and optional_available >= 1:
        return "medium"
    return "low"


def _growth_pressure(growth_impulse):
    return {
        "supports_growth": "less_easing_pressure",
        "supports_contraction": "more_easing_pressure",
        "turning_supportive": "early_recovery",
        "contraction_easing": "early_recovery",
    }.get(growth_impulse, "mixed")


def _inflation_pressure(prices_current, prices_previous):
    if prices_current is None or prices_previous is None:
        return "unavailable"
    if prices_current >= 60:
        return "elevated"
    if prices_current < 50:
        return "disinflationary"
    return "moderate"


def _supply_pressure(supplier_deliveries_current, supplier_deliveries_previous):
    if supplier_deliveries_current is None or supplier_deliveries_previous is None:
        return "unavailable"
    if supplier_deliveries_current >= 55:
        return "elevated"
    return "normal"


def _combined_pressure(growth_impulse, inflation_pressure, supply_pressure):
    if growth_impulse in ("unavailable", None):
        return "unavailable"
    elevated = inflation_pressure == "elevated" or supply_pressure == "elevated"
    disinflation = inflation_pressure == "disinflationary"
    normal_supply = supply_pressure == "normal"
    if growth_impulse == "supports_contraction" and elevated:
        return "stagflationary_tension"
    if growth_impulse == "supports_growth" and elevated:
        return "inflation_caution"
    if growth_impulse == "supports_contraction" and disinflation and normal_supply:
        return "more_easing_pressure"
    if (
        growth_impulse == "supports_growth"
        and inflation_pressure in ("moderate", "disinflationary")
        and normal_supply
    ):
        return "less_easing_pressure"
    return "mixed_pressure"


def _make_evidence(
    pmi_value, pmi_momentum, new_orders_value, new_orders_momentum, growth_impulse
):
    evidence = []
    if pmi_value is not None and pmi_momentum not in (None, "unavailable"):
        if pmi_value > 50 and pmi_momentum == "rising":
            evidence.append("PMI is above 50 and rising month over month")
        elif pmi_value > 50 and pmi_momentum == "falling":
            evidence.append("PMI is above 50 but falling month over month")
        elif pmi_value > 50 and pmi_momentum == "flat":
            evidence.append("PMI is above 50 and unchanged month over month")
        elif pmi_value <= 50 and pmi_momentum == "rising":
            evidence.append("PMI is at or below 50 but rising month over month")
        elif pmi_value <= 50 and pmi_momentum == "falling":
            evidence.append("PMI is below 50 and falling month over month")
        elif pmi_value <= 50 and pmi_momentum == "flat":
            evidence.append("PMI is at or below 50 and unchanged month over month")
    else:
        evidence.append("PMI is missing or unavailable")
    if new_orders_value is not None and new_orders_momentum not in (
        None,
        "unavailable",
    ):
        if new_orders_value > 50 and new_orders_momentum == "rising":
            evidence.append("New Orders are above 50 and rising month over month")
        elif new_orders_value > 50 and new_orders_momentum == "falling":
            evidence.append("New Orders are above 50 but falling month over month")
        elif new_orders_value > 50 and new_orders_momentum == "flat":
            evidence.append("New Orders are above 50 and unchanged month over month")
        elif new_orders_value <= 50 and new_orders_momentum == "rising":
            evidence.append("New Orders are at or below 50 but rising month over month")
        elif new_orders_value <= 50 and new_orders_momentum == "falling":
            evidence.append("New Orders are below 50 and falling month over month")
        elif new_orders_value <= 50 and new_orders_momentum == "flat":
            evidence.append(
                "New Orders are at or below 50 and unchanged month over month"
            )
    else:
        evidence.append("New Orders are missing or unavailable")
    if growth_impulse == "supports_growth":
        evidence.append("Growth impulse supports continued expansion")
    elif growth_impulse == "growth_caution":
        evidence.append("Growth impulse signals caution in expansion")
    elif growth_impulse == "supports_contraction":
        evidence.append("Growth impulse supports continued contraction")
    elif growth_impulse == "contraction_easing":
        evidence.append("Growth impulse suggests contraction is easing")
    elif growth_impulse == "turning_supportive":
        evidence.append("Growth impulse is turning supportive")
    elif growth_impulse == "mixed":
        evidence.append("Growth impulse is mixed or conflicting")
    return evidence


def _months_apart(m1, m2):
    if m1 > m2:
        m1, m2 = m2, m1
    total_months_1 = m1.year * 12 + m1.month
    total_months_2 = m2.year * 12 + m2.month
    return total_months_2 - total_months_1


def _validate_and_group(reports, at_a_glance_rows):
    if not reports:
        raise ValueError("at least one report snapshot is required")
    reports_sorted = sorted(reports, key=lambda r: r["report_month"])
    report_by_id = {r["report_id"]: r for r in reports_sorted}
    seen = set()
    for row in at_a_glance_rows:
        key = (row["report_id"], row["series_id"])
        if key in seen:
            raise ValueError(
                f"duplicate at-a-glance row for {row['report_id']} {row['series_id']}"
            )
        seen.add(key)
        if row["report_id"] not in report_by_id:
            raise ValueError(
                f"at-a-glance row references unknown report_id {row['report_id']}"
            )
        snap = report_by_id[row["report_id"]]
        if row["report_month"] != snap["report_month"]:
            raise ValueError(
                f"report_month mismatch for {row['report_id']}: "
                f"row has {row['report_month']}, snapshot has {snap['report_month']}"
            )
    rows_by_report = {}
    for row in at_a_glance_rows:
        rows_by_report.setdefault(row["report_id"], []).append(row)
    return reports_sorted, report_by_id, rows_by_report


def _parse_date(date_val):
    from datetime import date, datetime

    if isinstance(date_val, date):
        return date_val
    return datetime.strptime(date_val, "%Y-%m-%d").date()


def build_ism_macro_signal(reports, at_a_glance_rows, industry_breadth=None):
    reports_sorted, report_by_id, rows_by_report = _validate_and_group(
        reports, at_a_glance_rows
    )
    latest_report = reports_sorted[-1]
    latest_id = latest_report["report_id"]
    latest_rows = rows_by_report.get(latest_id, [])

    def _get_series_row(rows, series_id):
        for row in rows:
            if row["series_id"] == series_id:
                return row
        return None

    def _get_value(rows, series_id, field):
        row = _get_series_row(rows, series_id)
        if row is None:
            return None
        return row.get(field)

    def _extract_metric(series_id):
        current = _get_value(latest_rows, series_id, "current_value")
        previous = _get_value(latest_rows, series_id, "previous_value")
        stored_pc = _get_value(latest_rows, series_id, "point_change")
        if stored_pc is not None and current is not None and previous is not None:
            expected = round(current - previous, 1)
            if abs(stored_pc - expected) > 0.001:
                raise ValueError(
                    f"point_change mismatch for {series_id}: "
                    f"stored {stored_pc}, expected {expected}"
                )
        point_change = stored_pc
        if point_change is None and current is not None and previous is not None:
            point_change = round(current - previous, 1)
        return {"current": current, "previous": previous, "point_change": point_change}

    for metric_name in _REQUIRED_METRICS:
        series_id = _SERIES_IDS[metric_name]
        current = _get_value(latest_rows, series_id, "current_value")
        previous = _get_value(latest_rows, series_id, "previous_value")
        for name, val in [("current_value", current), ("previous_value", previous)]:
            if val is not None and not isinstance(val, (int, float)):
                raise ValueError(f"non-numeric {name} for {series_id}")

    pmi_data = _extract_metric(_SERIES_IDS["pmi"])
    new_orders_data = _extract_metric(_SERIES_IDS["new_orders"])
    production_data = _extract_metric(_SERIES_IDS["production"])
    inventories_data = _extract_metric(_SERIES_IDS["inventories"])
    prices_data = _extract_metric(_SERIES_IDS["prices"])
    supplier_deliveries_data = _extract_metric(_SERIES_IDS["supplier_deliveries"])

    pmi_available = pmi_data["current"] is not None and pmi_data["previous"] is not None
    new_orders_available = (
        new_orders_data["current"] is not None
        and new_orders_data["previous"] is not None
    )
    if not pmi_available:
        status = "unavailable"
    elif not new_orders_available:
        status = "partial"
    else:
        status = "available"

    pmi_phase = _phase(pmi_data["current"])
    pmi_momentum = _momentum(pmi_data["point_change"])
    new_orders_momentum = _momentum(new_orders_data["point_change"])
    cycle_state = _cycle_state(pmi_data["current"], pmi_momentum, new_orders_momentum)
    growth_impulse = _growth_impulse(
        cycle_state,
        pmi_data["current"],
        pmi_momentum,
        new_orders_data["current"],
        new_orders_momentum,
    )

    no_conf = _metric_confirmation(
        new_orders_data["current"], new_orders_data["previous"]
    )
    prod_conf = _metric_confirmation(
        production_data["current"], production_data["previous"]
    )
    inv_conf = _metric_confirmation(
        inventories_data["current"], inventories_data["previous"]
    )

    bc = industry_breadth or {}
    breadth_conf = _industry_breadth_status(
        bc.get("growth_count"), bc.get("contraction_count")
    )

    confirmation_positive_count = sum(
        1 for c in (no_conf, prod_conf, inv_conf, breadth_conf) if c == "positive"
    )
    confirmation_available_count = sum(
        1 for c in (no_conf, prod_conf, inv_conf, breadth_conf) if c != "unavailable"
    )

    confidence = _confidence_signal(status, prod_conf, inv_conf, breadth_conf)
    growth_pressure = _growth_pressure(growth_impulse)
    inflation_pressure = _inflation_pressure(
        prices_data["current"], prices_data["previous"]
    )
    supply_pressure = _supply_pressure(
        supplier_deliveries_data["current"], supplier_deliveries_data["previous"]
    )
    combined_pressure = _combined_pressure(
        growth_impulse, inflation_pressure, supply_pressure
    )

    evidence = _make_evidence(
        pmi_data["current"],
        pmi_momentum,
        new_orders_data["current"],
        new_orders_momentum,
        growth_impulse,
    )

    trend = []
    for report in reports_sorted:
        rid = report["report_id"]
        period = report["report_month"]
        report_rows = rows_by_report.get(rid, [])
        pmi_val = _get_value(report_rows, _SERIES_IDS["pmi"], "current_value")
        no_val = _get_value(report_rows, _SERIES_IDS["new_orders"], "current_value")
        point = {"period": period}
        if pmi_val is not None:
            point["pmi"] = pmi_val
        if no_val is not None:
            point["new_orders"] = no_val
        trend.append(point)

    months_loaded = len(reports_sorted)
    has_gap = False
    adjacent_months = 0
    for i in range(1, len(reports_sorted)):
        prev_date = _parse_date(reports_sorted[i - 1]["report_month"])
        curr_date = _parse_date(reports_sorted[i]["report_month"])
        diff = _months_apart(prev_date, curr_date)
        if diff == 1:
            adjacent_months += 1
        else:
            has_gap = True

    latest_momentum_streak = 0
    if pmi_data["point_change"] is not None:
        latest_momentum_streak = 1
        for i in range(len(reports_sorted) - 2, -1, -1):
            curr_date = _parse_date(reports_sorted[i + 1]["report_month"])
            prev_date = _parse_date(reports_sorted[i]["report_month"])
            if _months_apart(prev_date, curr_date) != 1:
                break
            prev_report_rows = rows_by_report.get(reports_sorted[i]["report_id"], [])
            prev_pc = _get_value(prev_report_rows, _SERIES_IDS["pmi"], "point_change")
            if prev_pc is None:
                prev_current = _get_value(
                    prev_report_rows, _SERIES_IDS["pmi"], "current_value"
                )
                prev_previous = _get_value(
                    prev_report_rows, _SERIES_IDS["pmi"], "previous_value"
                )
                if prev_current is not None and prev_previous is not None:
                    prev_pc = round(prev_current - prev_previous, 1)
            if prev_pc is None:
                break
            prev_momentum = _momentum(prev_pc)
            if prev_momentum == pmi_momentum:
                latest_momentum_streak += 1
            else:
                break

    available_required_names = []
    for m in _REQUIRED_METRICS:
        sid = _SERIES_IDS[m]
        if any(row["series_id"] == sid for row in latest_rows):
            available_required_names.append(m)

    available_optional = []
    missing_metrics = []
    for m in _OPTIONAL_METRICS:
        sid = _SERIES_IDS[m]
        if any(row["series_id"] == sid for row in latest_rows):
            available_optional.append(m)
        else:
            missing_metrics.append(m)

    metric_details = {}
    for metric_name, series_id in _SERIES_IDS.items():
        has_row = any(row["series_id"] == series_id for row in latest_rows)
        if not has_row:
            metric_details[metric_name] = {}
            continue
        data = _extract_metric(series_id)
        detail = {}
        if data["current"] is not None:
            detail["current"] = data["current"]
        if data["previous"] is not None:
            detail["previous"] = data["previous"]
        if data["point_change"] is not None:
            detail["point_change"] = data["point_change"]
        if metric_name in ("pmi", "new_orders"):
            detail["level_state"] = _level_state(data["current"])
            detail["momentum"] = _momentum(data["point_change"])
        metric_details[metric_name] = detail

    return {
        "version": ISM_MACRO_SIGNAL_VERSION,
        "status": status,
        "report_id": latest_id,
        "period": latest_report["report_month"],
        "source_url": latest_report.get("source_url", ""),
        "source_hash": latest_report.get("source_hash", ""),
        "phase": pmi_phase,
        "momentum": pmi_momentum,
        "cycle_state": cycle_state,
        "growth_impulse": growth_impulse,
        "confidence": confidence,
        "continuity": {
            "months_loaded": months_loaded,
            "adjacent_months": adjacent_months,
            "has_gap": has_gap,
            "latest_momentum_streak": latest_momentum_streak,
        },
        "trend": trend,
        "metrics": metric_details,
        "confirmations": {
            "new_orders": no_conf,
            "production": prod_conf,
            "inventories": inv_conf,
            "industry_breadth": breadth_conf,
            "positive_count": confirmation_positive_count,
            "available_count": confirmation_available_count,
        },
        "policy_context": {
            "growth_pressure": growth_pressure,
            "inflation_pressure": inflation_pressure,
            "supply_pressure": supply_pressure,
            "combined_pressure": combined_pressure,
        },
        "coverage": {
            "required_metrics": list(_REQUIRED_METRICS),
            "available_required_metrics": available_required_names,
            "optional_metrics": list(_OPTIONAL_METRICS),
            "available_optional_metrics": available_optional,
            "missing_metrics": missing_metrics,
        },
        "evidence": evidence,
    }
