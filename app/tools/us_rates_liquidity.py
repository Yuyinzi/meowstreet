import hashlib
import json
from calendar import monthrange
from datetime import date, timedelta

HEADLINE_CONFIG = [
    ("treasury_10y", "10-Year Treasury"),
    ("treasury_2y", "2-Year Treasury"),
    ("tens_twos_spread", "10Y - 2Y Spread"),
    ("tips_10y", "10Y Real Rate"),
    ("cpi_based_real_rate", "CPI Real Rate"),
    ("fed_funds", "Fed Funds"),
]

CREDIT_HEADLINE_CONFIG = [
    ("bbb_credit_spread", "BBB Credit Spread"),
    ("ccc_credit_spread", "CCC Credit Spread"),
    ("ccc_bbb_quality_spread", "CCC vs BBB Quality Spread"),
    ("credit_conditions", "Credit Conditions"),
]

BBB_CREDIT_ZONES = [
    (1.5, "very_low"),
    (2.5, "normal"),
    (4.0, "tightening"),
    (6.0, "stressed"),
]

CCC_BBB_QUALITY_ZONES = [
    (3.0, "low_dispersion"),
    (5.0, "normal"),
    (8.0, "weak_credit_pressure"),
    (12.0, "serious_deterioration"),
]

CCC_CREDIT_ZONES = [
    (5.0, "calm"),
    (8.0, "elevated"),
    (12.0, "stressed"),
]

PERCENTILE_LABELS = [
    (25, "low"),
    (75, "normal"),
    (90, "elevated"),
]

CREDIT_RISK_THRESHOLD = 2.0
CREDIT_DISPERSION_THRESHOLD = 4.0

CREDIT_SERIES_IDS = [
    "aaa_corporate_yield",
    "bbb_corporate_yield",
    "ccc_corporate_yield",
]

CREDIT_GAP_THRESHOLD_DAYS = 14
CREDIT_INTERPRETATION_SCOPE = "us_credit_conditions"
CREDIT_INTERPRETATION_PROMPT_VERSION = "credit-cat-v1"
CREDIT_SOURCE_NOTE = (
    "P05 workbook history is merged with latest FRED ICE/BofA observations. "
    "Missing dates are shown as a data gap and are not interpolated."
)

CURVE_SERIES_IDS = [
    "treasury_1m",
    "treasury_3m",
    "treasury_6m",
    "treasury_1y",
    "treasury_2y",
    "treasury_3y",
    "treasury_5y",
    "treasury_7y",
    "treasury_10y",
    "treasury_20y",
    "treasury_30y",
]

WORKBOOK_NOMINAL_CURVE_SERIES_IDS = [
    "treasury_1m",
    "treasury_3m",
    "treasury_6m",
    "treasury_1y",
    "treasury_2y",
    "treasury_3y",
    "treasury_5y",
    "treasury_7y",
    "treasury_10y",
    "treasury_20y",
]

REAL_RATE_SERIES_IDS = [
    "tips_5y",
    "tips_7y",
    "tips_10y",
    "tips_20y",
    "tips_30y",
]

SHORT_LABELS = {
    "treasury_1m": "1M",
    "treasury_3m": "3M",
    "treasury_6m": "6M",
    "treasury_1y": "1Y",
    "treasury_2y": "2Y",
    "treasury_3y": "3Y",
    "treasury_5y": "5Y",
    "treasury_7y": "7Y",
    "treasury_10y": "10Y",
    "treasury_20y": "20Y",
    "treasury_30y": "30Y",
    "tips_5y": "5Y TIPS",
    "tips_7y": "7Y TIPS",
    "tips_10y": "10Y TIPS",
    "tips_20y": "20Y TIPS",
    "tips_30y": "30Y TIPS",
}


def _round(value):
    if value is None:
        return None
    return round(value, 2)


def _classify_zone(value, zones):
    if value is None:
        return "missing"
    for threshold, label in zones:
        if value < threshold:
            return label
    return "crisis"


def _bbb_credit_zone(value):
    return _classify_zone(value, BBB_CREDIT_ZONES)


def _ccc_bbb_quality_zone(value):
    return _classify_zone(value, CCC_BBB_QUALITY_ZONES)


def _ccc_credit_zone(value):
    return _classify_zone(value, CCC_CREDIT_ZONES)


def _percentile_rank(values, value):
    clean_values = sorted(v for v in values if v is not None)
    if value is None or not clean_values:
        return None
    count = len([v for v in clean_values if v <= value])
    return round((count / len(clean_values)) * 100)


def _percentile_label(percentile):
    if percentile is None:
        return "missing"
    for threshold, label in PERCENTILE_LABELS:
        if percentile < threshold:
            return label
    return "extreme"


def _trend_label(change, threshold):
    if change is None:
        return "missing"
    if change >= threshold:
        return "rising"
    if change <= -threshold:
        return "falling"
    return "stable"


def _parse_series_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _subtract_months(value, months):
    month_index = value.year * 12 + value.month - 1 - months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _lookback_value(series, latest_date, months):
    target_date = _subtract_months(latest_date, months)
    dated_values = [
        (_parse_series_date(row.get("date")), row["value"])
        for row in series
        if row.get("value") is not None
    ]
    dated_values = [
        (row_date, value)
        for row_date, value in dated_values
        if row_date is not None and row_date < latest_date
    ]
    if not dated_values:
        return None
    previous_values = [
        (row_date, value) for row_date, value in dated_values if row_date <= target_date
    ]
    if previous_values:
        return previous_values[-1][1]
    next_values = [
        (row_date, value) for row_date, value in dated_values if row_date > target_date
    ]
    if next_values and next_values[0][0] <= target_date + timedelta(days=7):
        return next_values[0][1]
    return None


def _trend_summary(series):
    dated_series = [
        {
            "date": _parse_series_date(row.get("date")),
            "value": row["value"],
        }
        for row in series
        if row.get("value") is not None
    ]
    dated_series = [row for row in dated_series if row["date"] is not None]
    dated_series.sort(key=lambda row: row["date"])
    if not dated_series:
        return {
            "change_1m": None,
            "change_3m": None,
            "trend_1m": "missing",
            "trend_3m": "missing",
            "acceleration": "none",
        }
    latest = dated_series[-1]["value"]
    latest_date = dated_series[-1]["date"]
    one_month_value = _lookback_value(dated_series, latest_date, 1)
    three_month_value = _lookback_value(dated_series, latest_date, 3)
    change_1m = (
        _round(latest - one_month_value) if one_month_value is not None else None
    )
    change_3m = (
        _round(latest - three_month_value) if three_month_value is not None else None
    )
    trend_1m = _trend_label(change_1m, 0.25)
    trend_3m = _trend_label(change_3m, 0.50)
    acceleration = "none"
    if change_1m is not None and change_3m is not None:
        monthly_three_month_rate = abs(change_3m / 3)
        if change_1m >= 0.50 and change_1m > monthly_three_month_rate:
            acceleration = "accelerating_up"
        elif change_1m <= -0.50 and abs(change_1m) > monthly_three_month_rate:
            acceleration = "accelerating_down"
    return {
        "change_1m": change_1m,
        "change_3m": change_3m,
        "trend_1m": trend_1m,
        "trend_3m": trend_3m,
        "acceleration": acceleration,
    }


def _series_values_for_key(series, key):
    return [
        {"date": row["date"], "value": row[key]}
        for row in series
        if row.get(key) is not None
    ]


def _credit_metric_diagnostic(series, key, zone_func):
    value_series = _series_values_for_key(series, key)
    values = [row["value"] for row in value_series]
    latest = values[-1] if values else None
    percentile = _percentile_rank(values, latest)
    return {
        "value": latest,
        "zone": zone_func(latest),
        "percentile": percentile,
        "percentile_label": _percentile_label(percentile),
        **_trend_summary(value_series),
    }


def _credit_diagnostics_from_series(points_by_id):
    bbb_series = _bbb_credit_spread_series(points_by_id)
    ccc_series = _ccc_credit_spread_series(points_by_id)
    ccc_bbb_series = _ccc_bbb_quality_spread_series(points_by_id)
    return {
        "bbb_credit_spread": _credit_metric_diagnostic(
            bbb_series, "bbb_credit_spread", _bbb_credit_zone
        ),
        "ccc_credit_spread": _credit_metric_diagnostic(
            ccc_series, "ccc_credit_spread", _ccc_credit_zone
        ),
        "ccc_bbb_quality_spread": _credit_metric_diagnostic(
            ccc_bbb_series, "ccc_bbb_quality_spread", _ccc_bbb_quality_zone
        ),
    }


def _credit_conditions_status_from_diagnostics(diagnostics):
    bbb = diagnostics.get("bbb_credit_spread", {})
    quality = diagnostics.get("ccc_bbb_quality_spread", {})
    if bbb.get("zone") in (None, "missing") or quality.get("zone") in (None, "missing"):
        return "missing"
    if (
        bbb.get("zone") == "crisis"
        or quality.get("zone") == "crisis"
        or (
            bbb.get("acceleration") == "accelerating_up"
            and quality.get("acceleration") == "accelerating_up"
            and bbb.get("trend_3m") == "rising"
            and quality.get("trend_3m") == "rising"
        )
    ):
        return "crisis_stress"
    if (
        (bbb.get("trend_1m") == "rising" and quality.get("trend_1m") == "rising")
        or bbb.get("zone") == "stressed"
        or quality.get("zone") == "serious_deterioration"
    ):
        return "risk_rising"
    if (
        bbb.get("trend_1m") in ("stable", "falling")
        and quality.get("trend_1m") == "rising"
    ) or (
        bbb.get("zone") in ("very_low", "normal")
        and quality.get("zone") == "weak_credit_pressure"
    ):
        return "weak_credit_warning"
    if (
        bbb.get("trend_1m") in ("stable", "falling")
        and quality.get("trend_1m") in ("stable", "falling")
        and bbb.get("zone") in ("very_low", "normal")
        and quality.get("zone") in ("low_dispersion", "normal")
    ):
        return "healthy"
    return "mixed"


def _credit_conditions_diagnostics_series(points_by_id):
    bbb_by_date = {
        row["date"]: row["bbb_credit_spread"]
        for row in _bbb_credit_spread_series(points_by_id)
    }
    ccc_by_date = {
        row["date"]: row["ccc_credit_spread"]
        for row in _ccc_credit_spread_series(points_by_id)
    }
    quality_by_date = {
        row["date"]: row["ccc_bbb_quality_spread"]
        for row in _ccc_bbb_quality_spread_series(points_by_id)
    }
    rows = []
    for date in sorted(set(bbb_by_date) & set(ccc_by_date) & set(quality_by_date)):
        rows.append(
            {
                "date": date,
                "bbb_credit_spread": bbb_by_date[date],
                "ccc_credit_spread": ccc_by_date[date],
                "ccc_bbb_quality_spread": quality_by_date[date],
            }
        )
    return rows


def _credit_conditions_diagnostics_detail(points_by_id):
    series = _credit_conditions_diagnostics_series(points_by_id)
    diagnostics = _credit_diagnostics_from_series(points_by_id)
    return [
        {
            "kind": "credit_diagnostics",
            "title": "Credit Conditions",
            "status": _credit_conditions_status_from_diagnostics(diagnostics),
            "metrics": {
                "bbb_credit_spread": {
                    "label": "BBB - 10Y",
                    **diagnostics["bbb_credit_spread"],
                },
                "ccc_credit_spread": {
                    "label": "CCC - 10Y",
                    **diagnostics["ccc_credit_spread"],
                },
                "ccc_bbb_quality_spread": {
                    "label": "CCC - BBB",
                    **diagnostics["ccc_bbb_quality_spread"],
                },
            },
            "series": series,
        }
    ]


def _series_by_id(series_rows):
    return {row["series_id"]: row for row in series_rows}


def _points_by_id(latest_points):
    return {row["series_id"]: row for row in latest_points}


def _macro_points_by_id(latest_macro_points):
    return {row["series_id"]: row for row in latest_macro_points or []}


def _value(points, series_id):
    point = points.get(series_id)
    if point is None:
        return None
    return point["value"]


def _source(points):
    if not points:
        return None
    return sorted(points, key=lambda row: row["date"])[-1].get("source_workbook")


def _as_of(points):
    dates = [row["date"] for row in points]
    return max(dates) if dates else None


def _curve_status(tens_twos_spread):
    if tens_twos_spread is None:
        return "missing"
    if tens_twos_spread < 0:
        return "inverted"
    if tens_twos_spread < 0.5:
        return "flat"
    return "steep"


def _method_interpretation(curve_status):
    messages = {
        "steep": "Steep positive curve: growth expectations are not yet recessionary; confirm with credit spreads, VIX, GDP, and PMI before using as risk-on evidence.",
        "flat": "Flat curve: policy-sensitive yields are close to long yields; treat as late-cycle caution and confirm with growth and credit indicators.",
        "inverted": "Inverted curve: recession risk signal is active; do not treat equity strength alone as sufficient macro confirmation.",
        "missing": "No US rates data found. Run scripts/import_us_rates_liquidity.py.",
    }
    return messages[curve_status]


def _point_payload(series, point):
    return {
        "series_id": series["series_id"],
        "label": SHORT_LABELS.get(series["series_id"], series["title"]),
        "maturity_months": series.get("maturity_months"),
        "value": point["value"],
    }


def _curve_payload(series, points):
    return [
        _point_payload(series[series_id], points[series_id])
        for series_id in CURVE_SERIES_IDS
        if series_id in series and series_id in points
    ]


def _real_rate_payload(series, points):
    return [
        _point_payload(series[series_id], points[series_id])
        for series_id in REAL_RATE_SERIES_IDS
        if series_id in series and series_id in points
    ]


def _headline_payload(points, derived):
    values = {
        "treasury_10y": _value(points, "treasury_10y"),
        "treasury_2y": _value(points, "treasury_2y"),
        "tens_twos_spread": derived["tens_twos_spread"],
        "tips_10y": _value(points, "tips_10y"),
        "cpi_based_real_rate": derived["cpi_based_real_rate"],
        "fed_funds": _value(points, "fed_funds"),
    }
    return [
        {
            "id": item_id,
            "label": label,
            "value": values[item_id],
            "unit": "%",
        }
        for item_id, label in HEADLINE_CONFIG
        if values[item_id] is not None
    ]


def _corporate_credit_values(points, macro_points):
    ten_year_data = points.get("treasury_10y", [])
    aaa_data = macro_points.get("aaa_corporate_yield", [])
    bbb_data = macro_points.get("bbb_corporate_yield", [])
    ccc_data = macro_points.get("ccc_corporate_yield", [])
    if not ten_year_data or not aaa_data:
        return {}
    if isinstance(ten_year_data, dict):
        ten_year = ten_year_data.get("value")
        aaa = aaa_data.get("value") if isinstance(aaa_data, dict) else None
        bbb = bbb_data.get("value") if isinstance(bbb_data, dict) else None
        ccc = ccc_data.get("value") if isinstance(ccc_data, dict) else None
        result = {}
        if aaa is not None and ten_year is not None:
            result["aaa_credit_spread"] = _round(aaa - ten_year)
        if bbb is not None and ten_year is not None:
            result["bbb_credit_spread"] = _round(bbb - ten_year)
        if ccc is not None and ten_year is not None:
            result["ccc_credit_spread"] = _round(ccc - ten_year)
        if bbb is not None and aaa is not None:
            result["bbb_aaa_quality_spread"] = _round(bbb - aaa)
        if ccc is not None and bbb is not None:
            result["ccc_bbb_quality_spread"] = _round(ccc - bbb)
        if ccc is not None and aaa is not None:
            result["ccc_aaa_quality_spread"] = _round(ccc - aaa)
        return result
    ten_year_by_date = {p["date"]: p["value"] for p in ten_year_data}
    ten_year_dates = sorted(ten_year_by_date.keys())
    aaa_by_date = {p["date"]: p["value"] for p in aaa_data}
    bbb_by_date = {p["date"]: p["value"] for p in bbb_data}
    ccc_by_date = {p["date"]: p["value"] for p in ccc_data}
    latest_common = None
    for date in sorted(aaa_by_date.keys(), reverse=True):
        closest = None
        for td in reversed(ten_year_dates):
            if td <= date:
                closest = td
                break
        if closest is not None:
            latest_common = (date, closest)
            break
    if latest_common is None:
        return {}
    corp_date, ten_date = latest_common
    ten_year = ten_year_by_date[ten_date]
    aaa = aaa_by_date.get(corp_date)
    bbb = bbb_by_date.get(corp_date)
    ccc = ccc_by_date.get(corp_date)
    result = {"credit_as_of": corp_date}
    if aaa is not None:
        result["aaa_credit_spread"] = _round(aaa - ten_year)
    if bbb is not None:
        result["bbb_credit_spread"] = _round(bbb - ten_year)
    if ccc is not None:
        result["ccc_credit_spread"] = _round(ccc - ten_year)
    if bbb is not None and aaa is not None:
        result["bbb_aaa_quality_spread"] = _round(bbb - aaa)
    if ccc is not None and bbb is not None:
        result["ccc_bbb_quality_spread"] = _round(ccc - bbb)
    if ccc is not None and aaa is not None:
        result["ccc_aaa_quality_spread"] = _round(ccc - aaa)
    return result


def _credit_regime(derived):
    bbb_spread = derived.get("bbb_credit_spread")
    ccc_bbb_spread = derived.get("ccc_bbb_quality_spread")
    if bbb_spread is None or ccc_bbb_spread is None:
        return "missing"
    high_risk = bbb_spread >= CREDIT_RISK_THRESHOLD
    high_dispersion = ccc_bbb_spread >= CREDIT_DISPERSION_THRESHOLD
    if high_risk and high_dispersion:
        return "high_risk_high_dispersion"
    if high_risk:
        return "high_risk_low_dispersion"
    if high_dispersion:
        return "low_risk_high_dispersion"
    return "low_risk_low_dispersion"


def _credit_conditions_status(derived):
    regime = _credit_regime(derived)
    return {
        "low_risk_low_dispersion": "supportive",
        "low_risk_high_dispersion": "selective",
        "high_risk_high_dispersion": "risk_off",
        "high_risk_low_dispersion": "stress",
        "missing": "missing",
    }[regime]


def _credit_headline_payload(derived):
    values = {
        "bbb_credit_spread": derived.get("bbb_credit_spread"),
        "ccc_credit_spread": derived.get("ccc_credit_spread"),
        "ccc_bbb_quality_spread": derived.get("ccc_bbb_quality_spread"),
        "credit_conditions": derived.get("credit_conditions_status"),
    }
    return [
        {
            "id": item_id,
            "label": label,
            "value": values[item_id],
            "unit": "%" if item_id != "credit_conditions" else "",
        }
        for item_id, label in CREDIT_HEADLINE_CONFIG
        if values[item_id] is not None
    ]


def _credit_coverage(points_by_id):
    common_dates = None
    for series_id in CREDIT_SERIES_IDS:
        dates = {
            row["date"]
            for row in _series_points(points_by_id, series_id)
            if row.get("value") is not None
        }
        common_dates = dates if common_dates is None else common_dates & dates
    if not common_dates:
        return {
            "series_ids": CREDIT_SERIES_IDS,
            "start_date": None,
            "latest_date": None,
            "gap_start": None,
            "gap_end": None,
            "has_gap": False,
            "source_note": CREDIT_SOURCE_NOTE,
        }
    sorted_dates = sorted(common_dates)
    gap_start = None
    gap_end = None
    for previous, current in zip(sorted_dates, sorted_dates[1:]):
        previous_date = _parse_series_date(previous)
        current_date = _parse_series_date(current)
        if previous_date is None or current_date is None:
            continue
        if (current_date - previous_date).days > CREDIT_GAP_THRESHOLD_DAYS:
            gap_start = (previous_date + timedelta(days=1)).isoformat()
            gap_end = (current_date - timedelta(days=1)).isoformat()
    return {
        "series_ids": CREDIT_SERIES_IDS,
        "start_date": sorted_dates[0],
        "latest_date": sorted_dates[-1],
        "gap_start": gap_start,
        "gap_end": gap_end,
        "has_gap": gap_start is not None,
        "source_note": CREDIT_SOURCE_NOTE,
    }


def credit_interpretation_snapshot(derived, coverage):
    metrics = {
        "bbb_credit_spread": derived.get("credit_diagnostics", {}).get(
            "bbb_credit_spread"
        ),
        "ccc_credit_spread": derived.get("credit_diagnostics", {}).get(
            "ccc_credit_spread"
        ),
        "ccc_bbb_quality_spread": derived.get("credit_diagnostics", {}).get(
            "ccc_bbb_quality_spread"
        ),
    }
    payload = {
        "scope": CREDIT_INTERPRETATION_SCOPE,
        "prompt_version": CREDIT_INTERPRETATION_PROMPT_VERSION,
        "as_of": derived.get("credit_as_of"),
        "status": derived.get("credit_conditions_status", "missing"),
        "metrics": metrics,
        "coverage": coverage or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {**payload, "hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def build_dashboard_payload(
    series_rows,
    latest_points,
    latest_macro_points=None,
    credit_rate_points=None,
    credit_macro_points=None,
    credit_macro_series_points=None,
):
    if not series_rows or not latest_points:
        curve_status = "missing"
        return {
            "as_of": None,
            "source": None,
            "headline": [],
            "curve": [],
            "real_rates": [],
            "derived": {
                "tens_twos_spread": None,
                "ten_year_real_rate": None,
                "ten_year_breakeven_inflation": None,
                "cpi_based_real_rate": None,
                "vix": None,
                "curve_status": curve_status,
                "method_interpretation": _method_interpretation(curve_status),
                "aaa_credit_spread": None,
                "bbb_credit_spread": None,
                "ccc_credit_spread": None,
                "bbb_aaa_quality_spread": None,
                "ccc_bbb_quality_spread": None,
                "ccc_aaa_quality_spread": None,
                "credit_conditions_status": "missing",
            },
        }
    series = _series_by_id(series_rows)
    points = _points_by_id(latest_points)
    macro_points = _macro_points_by_id(latest_macro_points)
    ten_year = _value(points, "treasury_10y")
    two_year = _value(points, "treasury_2y")
    ten_year_real = _value(points, "tips_10y")
    cpi_yoy = _value(macro_points, "cpi_yoy")
    vix = _value(macro_points, "vix")
    cpi_based_real_rate = (
        _round(ten_year - cpi_yoy)
        if ten_year is not None and cpi_yoy is not None
        else None
    )
    tens_twos_spread = (
        _round(ten_year - two_year)
        if ten_year is not None and two_year is not None
        else None
    )
    breakeven = (
        _round(ten_year - ten_year_real)
        if ten_year is not None and ten_year_real is not None
        else None
    )
    curve_status = _curve_status(tens_twos_spread)
    derived = {
        "tens_twos_spread": tens_twos_spread,
        "ten_year_real_rate": ten_year_real,
        "ten_year_breakeven_inflation": breakeven,
        "cpi_based_real_rate": cpi_based_real_rate,
        "vix": vix,
        "curve_status": curve_status,
        "method_interpretation": _method_interpretation(curve_status),
    }
    credit_pts = credit_rate_points if credit_rate_points is not None else points
    credit_macro = (
        credit_macro_points if credit_macro_points is not None else macro_points
    )
    derived.update(_corporate_credit_values(credit_pts, credit_macro))
    if credit_rate_points is not None and credit_macro_points is not None:
        credit_points_by_id = {}
        credit_points_by_id.update(credit_rate_points)
        credit_points_by_id.update(credit_macro_points)
        credit_diagnostics = _credit_diagnostics_from_series(credit_points_by_id)
        derived["credit_diagnostics"] = credit_diagnostics
        derived["credit_conditions_status"] = (
            _credit_conditions_status_from_diagnostics(credit_diagnostics)
        )
    else:
        derived["credit_conditions_status"] = _credit_conditions_status(derived)
    credit_coverage = _credit_coverage(credit_macro_series_points or {})
    credit_snapshot = credit_interpretation_snapshot(derived, credit_coverage)
    return {
        "as_of": _as_of(latest_points),
        "credit_as_of": derived.get("credit_as_of"),
        "source": _source(latest_points),
        "headline": _headline_payload(points, derived)
        + _credit_headline_payload(derived),
        "curve": _curve_payload(series, points),
        "real_rates": _real_rate_payload(series, points),
        "derived": derived,
        "credit_coverage": credit_coverage,
        "credit_interpretation_snapshot": credit_snapshot,
    }


RECENT_WINDOW_POINTS = 1048

DETAIL_CONFIG = {
    "treasury_10y": {
        "title": "10-Year Treasury",
        "series_ids": ["treasury_10y"],
        "chart_titles": [
            "10 Year Treasury Yield (Historical)",
            "10 Year Treasury Yield (Last 20 Years)",
        ],
        "labels": {"value": "10-Year Treasury"},
    },
    "treasury_2y": {
        "title": "2-Year Treasury",
        "series_ids": ["treasury_2y"],
        "chart_titles": [
            "2 Year Treasury Yield (Historical)",
            "2 Year Treasury Yield (Last 20 Years)",
        ],
        "labels": {"value": "2-Year Treasury"},
    },
    "fed_funds": {
        "title": "Fed Funds",
        "series_ids": ["fed_funds"],
        "chart_titles": [
            "Fed Funds Effective Rate (Historical)",
            "Fed Funds Effective Rate (Last 20 Years)",
        ],
        "labels": {"value": "Fed Funds"},
    },
    "tips_10y": {
        "title": "10Y Real Rate",
        "series_ids": ["tips_10y"],
        "chart_titles": [
            "10yr Treasury Inflation-Protected Security Yield (Historical)",
            "10yr Treasury Inflation-Protected Security Yield (Last 10 Years)",
        ],
        "labels": {"value": "10-Year TIPS"},
    },
    "tens_twos_spread": {
        "title": "10Y - 2Y Spread",
        "series_ids": ["treasury_10y", "treasury_2y"],
        "chart_titles": [
            "10Y - 2Y Treasury Spread (Historical)",
            "10Y - 2Y Treasury Spread (Last 20 Years)",
        ],
        "labels": {"value": "10Y - 2Y Spread"},
    },
    "yield_curve_shape": {
        "title": "Yield Curve Shape",
        "series_ids": WORKBOOK_NOMINAL_CURVE_SERIES_IDS + REAL_RATE_SERIES_IDS,
    },
    "cpi_based_real_rate": {
        "title": "CPI Real Rate",
        "series_ids": ["treasury_10y", "cpi_yoy", "vix"],
    },
    "corporate_yields": {
        "title": "Corporate Yields",
        "series_ids": [
            "aaa_corporate_yield",
            "bbb_corporate_yield",
            "ccc_corporate_yield",
        ],
    },
    "treasury_credit_spreads": {
        "title": "Treasury Credit Spreads",
        "series_ids": [
            "treasury_10y",
            "aaa_corporate_yield",
            "bbb_corporate_yield",
            "ccc_corporate_yield",
        ],
    },
    "quality_spreads": {
        "title": "Quality Spreads",
        "series_ids": [
            "aaa_corporate_yield",
            "bbb_corporate_yield",
            "ccc_corporate_yield",
        ],
    },
    "bbb_credit_spread": {
        "title": "BBB Credit Spread",
        "series_ids": ["treasury_10y", "bbb_corporate_yield"],
    },
    "ccc_credit_spread": {
        "title": "CCC Credit Spread",
        "series_ids": ["treasury_10y", "ccc_corporate_yield"],
    },
    "ccc_bbb_quality_spread": {
        "title": "CCC vs BBB Quality Spread",
        "series_ids": ["bbb_corporate_yield", "ccc_corporate_yield"],
    },
    "credit_risk_regime": {
        "title": "Credit Risk Regime",
        "series_ids": ["treasury_10y", "bbb_corporate_yield", "ccc_corporate_yield"],
    },
    "credit_conditions_diagnostics": {
        "title": "Credit Conditions",
        "series_ids": ["treasury_10y", "bbb_corporate_yield", "ccc_corporate_yield"],
    },
}


def detail_series_ids(detail_id):
    config = DETAIL_CONFIG.get(detail_id)
    if config is None:
        raise ValueError(f"us rates detail is unknown: {detail_id}")
    return config["series_ids"]


def _series_points(points_by_id, series_id):
    return points_by_id.get(series_id, [])


def _time_series_points(points):
    return [
        {"date": row["date"], "value": row["value"]}
        for row in points
        if row.get("value") is not None
    ]


def _spread_series(points_by_id):
    ten_year = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "treasury_10y")
    }
    two_year = {
        row["date"]: row["value"] for row in _series_points(points_by_id, "treasury_2y")
    }
    return [
        {"date": date, "value": _round(ten_year[date] - two_year[date])}
        for date in sorted(set(ten_year) & set(two_year))
    ]


def _recent(series):
    return series[-RECENT_WINDOW_POINTS:]


def _time_series_detail(detail_id, points_by_id):
    config = DETAIL_CONFIG[detail_id]
    if detail_id == "tens_twos_spread":
        series = _spread_series(points_by_id)
    else:
        series = _time_series_points(
            _series_points(points_by_id, config["series_ids"][0])
        )
    return [
        {
            "kind": "time_series",
            "title": config["chart_titles"][0],
            "keys": ["value"],
            "labels": config["labels"],
            "series": series,
        },
        {
            "kind": "time_series",
            "title": config["chart_titles"][1],
            "keys": ["value"],
            "labels": config["labels"],
            "series": _recent(series),
        },
    ]


def _corporate_yields_series(points_by_id):
    aaa = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "aaa_corporate_yield")
    }
    bbb = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "bbb_corporate_yield")
    }
    ccc = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "ccc_corporate_yield")
    }
    dates = sorted(set(aaa) & set(bbb) & set(ccc))
    return [
        {"date": date, "aaa": aaa[date], "bbb": bbb[date], "ccc": ccc[date]}
        for date in dates
    ]


def _credit_spread_series(points_by_id):
    ten_year_points = _series_points(points_by_id, "treasury_10y")
    ten_year_by_date = {row["date"]: row["value"] for row in ten_year_points}
    ten_year_dates = sorted(ten_year_by_date.keys())
    aaa = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "aaa_corporate_yield")
    }
    bbb = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "bbb_corporate_yield")
    }
    ccc = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "ccc_corporate_yield")
    }
    common_dates = sorted(set(aaa) & set(bbb) & set(ccc))
    result = []
    for date in common_dates:
        closest = None
        for td in reversed(ten_year_dates):
            if td <= date:
                closest = td
                break
        if closest is None:
            continue
        ten_val = ten_year_by_date[closest]
        result.append(
            {
                "date": date,
                "aaa_spread": _round(aaa[date] - ten_val),
                "bbb_spread": _round(bbb[date] - ten_val),
                "ccc_spread": _round(ccc[date] - ten_val),
            }
        )
    return result


def _quality_spread_series(points_by_id):
    aaa = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "aaa_corporate_yield")
    }
    bbb = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "bbb_corporate_yield")
    }
    ccc = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "ccc_corporate_yield")
    }
    dates = sorted(set(aaa) & set(bbb) & set(ccc))
    return [
        {
            "date": date,
            "bbb_aaa": _round(bbb[date] - aaa[date]),
            "ccc_bbb": _round(ccc[date] - bbb[date]),
            "ccc_aaa": _round(ccc[date] - aaa[date]),
        }
        for date in dates
    ]


def _corporate_yields_detail(points_by_id):
    series = _corporate_yields_series(points_by_id)
    return [
        {
            "kind": "time_series",
            "title": "Corporate Yields (Historical)",
            "keys": ["aaa", "bbb", "ccc"],
            "labels": {"aaa": "AAA", "bbb": "BBB", "ccc": "CCC"},
            "series": series,
        },
    ]


def _treasury_credit_spreads_detail(points_by_id):
    series = _credit_spread_series(points_by_id)
    return [
        {
            "kind": "time_series",
            "title": "Treasury Credit Spreads (Historical)",
            "keys": ["aaa_spread", "bbb_spread", "ccc_spread"],
            "labels": {
                "aaa_spread": "AAA - 10Y",
                "bbb_spread": "BBB - 10Y",
                "ccc_spread": "CCC - 10Y",
            },
            "series": series,
        },
    ]


def _quality_spreads_detail(points_by_id):
    series = _quality_spread_series(points_by_id)
    return [
        {
            "kind": "time_series",
            "title": "Quality Spreads (Historical)",
            "keys": ["bbb_aaa", "ccc_bbb", "ccc_aaa"],
            "labels": {
                "bbb_aaa": "BBB - AAA",
                "ccc_bbb": "CCC - BBB",
                "ccc_aaa": "CCC - AAA",
            },
            "series": series,
        },
    ]


def _single_credit_spread_series(points_by_id, corporate_series_id):
    ten_year_points = _series_points(points_by_id, "treasury_10y")
    ten_year_by_date = {row["date"]: row["value"] for row in ten_year_points}
    ten_year_dates = sorted(ten_year_by_date.keys())
    corporate = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, corporate_series_id)
    }
    result = []
    for date in sorted(corporate.keys()):
        closest = None
        for td in reversed(ten_year_dates):
            if td <= date:
                closest = td
                break
        if closest is None:
            continue
        result.append(
            {
                "date": date,
                "yield": corporate[date],
                "spread": _round(corporate[date] - ten_year_by_date[closest]),
            }
        )
    return result


def _single_credit_spread_detail(detail_id, points_by_id):
    config = DETAIL_CONFIG[detail_id]
    rating = detail_id.replace("_credit_spread", "").upper()
    corporate_series_id = f"{rating.lower()}_corporate_yield"
    series = _single_credit_spread_series(points_by_id, corporate_series_id)
    return [
        {
            "kind": "time_series",
            "title": f"{rating} Yield & Credit Spread",
            "keys": ["yield", "spread"],
            "labels": {
                "yield": f"{rating} Yield",
                "spread": f"{rating} - 10Y Credit Spread",
            },
            "series": series,
        },
    ]


def _date_value_map(points):
    return {row["date"]: row["value"] for row in points}


def _latest_on_or_before(sorted_dates, target):
    result = None
    for d in sorted_dates:
        if d <= target:
            result = d
        else:
            break
    return result


def _bbb_credit_spread_series(points_by_id):
    treasury = _date_value_map(_series_points(points_by_id, "treasury_10y"))
    bbb = _date_value_map(_series_points(points_by_id, "bbb_corporate_yield"))
    treasury_dates = sorted(treasury.keys())
    rows = []
    for date in sorted(bbb):
        closest = _latest_on_or_before(treasury_dates, date)
        if closest is not None:
            rows.append(
                {
                    "date": date,
                    "bbb_credit_spread": _round(bbb[date] - treasury[closest]),
                }
            )
    return rows


def _ccc_bbb_quality_spread_series(points_by_id):
    bbb = _date_value_map(_series_points(points_by_id, "bbb_corporate_yield"))
    ccc = _date_value_map(_series_points(points_by_id, "ccc_corporate_yield"))
    rows = []
    for date in sorted(set(bbb) & set(ccc)):
        rows.append(
            {
                "date": date,
                "ccc_bbb_quality_spread": _round(ccc[date] - bbb[date]),
            }
        )
    return rows


def _bbb_credit_spread_detail(points_by_id):
    return [
        {
            "kind": "time_series",
            "title": "BBB Credit Spread",
            "keys": ["bbb_credit_spread"],
            "labels": {"bbb_credit_spread": "BBB - 10Y"},
            "series": _bbb_credit_spread_series(points_by_id),
        }
    ]


def _ccc_bbb_quality_spread_detail(points_by_id):
    return [
        {
            "kind": "time_series",
            "title": "CCC vs BBB Quality Spread",
            "keys": ["ccc_bbb_quality_spread"],
            "labels": {"ccc_bbb_quality_spread": "CCC - BBB"},
            "series": _ccc_bbb_quality_spread_series(points_by_id),
        }
    ]


def _ccc_credit_spread_series(points_by_id):
    treasury = _date_value_map(_series_points(points_by_id, "treasury_10y"))
    ccc = _date_value_map(_series_points(points_by_id, "ccc_corporate_yield"))
    treasury_dates = sorted(treasury.keys())
    rows = []
    for date in sorted(ccc):
        closest = _latest_on_or_before(treasury_dates, date)
        if closest is not None:
            rows.append(
                {
                    "date": date,
                    "ccc_credit_spread": _round(ccc[date] - treasury[closest]),
                }
            )
    return rows


def _ccc_credit_spread_detail(points_by_id):
    return [
        {
            "kind": "time_series",
            "title": "CCC Credit Spread",
            "keys": ["ccc_credit_spread"],
            "labels": {"ccc_credit_spread": "CCC - 10Y"},
            "series": _ccc_credit_spread_series(points_by_id),
        }
    ]


def _credit_risk_regime_series(points_by_id):
    bbb_series = _bbb_credit_spread_series(points_by_id)
    ccc_bbb_series = _ccc_bbb_quality_spread_series(points_by_id)
    bbb_by_date = {row["date"]: row["bbb_credit_spread"] for row in bbb_series}
    ccc_bbb_by_date = {
        row["date"]: row["ccc_bbb_quality_spread"] for row in ccc_bbb_series
    }
    rows = []
    for date in sorted(set(bbb_by_date) & set(ccc_bbb_by_date)):
        derived = {
            "bbb_credit_spread": bbb_by_date[date],
            "ccc_bbb_quality_spread": ccc_bbb_by_date[date],
        }
        rows.append(
            {
                "date": date,
                **derived,
                "regime": _credit_regime(derived),
            }
        )
    return rows


def _credit_risk_regime_detail(points_by_id):
    series = _credit_risk_regime_series(points_by_id)
    return [
        {
            "kind": "credit_regime",
            "title": "Credit Risk Regime",
            "x_key": "bbb_credit_spread",
            "y_key": "ccc_bbb_quality_spread",
            "x_label": "BBB - 10Y",
            "y_label": "CCC - BBB",
            "thresholds": {
                "bbb_credit_spread": CREDIT_RISK_THRESHOLD,
                "ccc_bbb_quality_spread": CREDIT_DISPERSION_THRESHOLD,
            },
            "current": series[-1] if series else None,
            "series": series,
        }
    ]


def _point_for_date(points, date):
    for point in points:
        if point["date"] == date:
            return point
    return None


def _available_dates(points_by_id, series_ids):
    date_sets = [
        {point["date"] for point in _series_points(points_by_id, series_id)}
        for series_id in series_ids
        if _series_points(points_by_id, series_id)
    ]
    if not date_sets:
        return []
    return sorted(set.intersection(*date_sets))


def _workbook_like_comparison_date(points_by_id, primary_series_id, row_index):
    points = _series_points(points_by_id, primary_series_id)
    if len(points) < row_index:
        return points[0]["date"] if points else None
    return points[-row_index]["date"]


def _selected_comparison_date(
    points_by_id,
    series_ids,
    requested_date,
    default_primary_series_id,
    default_row_index,
):
    dates = _available_dates(points_by_id, series_ids)
    if not dates:
        return None
    if requested_date in dates:
        return requested_date
    default_date = _workbook_like_comparison_date(
        points_by_id,
        default_primary_series_id,
        default_row_index,
    )
    return default_date if default_date in dates else dates[0]


def _curve_comparison_series(points_by_id, series_ids, current_date, comparison_date):
    series = []
    for series_id in series_ids:
        points = _series_points(points_by_id, series_id)
        current = _point_for_date(points, current_date) if current_date else None
        comparison = (
            _point_for_date(points, comparison_date) if comparison_date else None
        )
        series.append(
            {
                "label": SHORT_LABELS.get(series_id, series_id),
                "current": current["value"] if current else None,
                "comparison": comparison["value"] if comparison else None,
            }
        )
    return series


def _curve_y_domain(points_by_id, series_ids):
    values = [
        point["value"]
        for series_id in series_ids
        for point in _series_points(points_by_id, series_id)
        if point.get("value") is not None
    ]
    if not values:
        return {"min": None, "max": None}
    return {"min": min(values), "max": max(values)}


def _selected_curve_dates(
    points_by_id, options, series_ids, default_comparison_series, default_comparison_row
):
    dates = _available_dates(points_by_id, series_ids)
    if not dates:
        return None, None, []
    requested_current = options.get("current_date")
    requested_comparison = options.get("comparison_date")
    current_date = requested_current if requested_current in dates else dates[-1]
    default_comparison = _workbook_like_comparison_date(
        points_by_id,
        default_comparison_series,
        default_comparison_row,
    )
    if default_comparison not in dates:
        default_comparison = dates[0]
    comparison_date = (
        requested_comparison if requested_comparison in dates else default_comparison
    )
    return current_date, comparison_date, dates


def _curve_detail(points_by_id, options):
    nominal_current, nominal_comparison, nominal_dates = _selected_curve_dates(
        points_by_id,
        {
            "current_date": options.get("nominal_current_date"),
            "comparison_date": options.get("nominal_comparison_date"),
        },
        WORKBOOK_NOMINAL_CURVE_SERIES_IDS,
        "treasury_10y",
        270,
    )
    real_current, real_comparison, real_dates = _selected_curve_dates(
        points_by_id,
        {
            "current_date": options.get("real_current_date"),
            "comparison_date": options.get("real_comparison_date"),
        },
        REAL_RATE_SERIES_IDS,
        "tips_10y",
        21,
    )
    nominal_series = _curve_comparison_series(
        points_by_id,
        WORKBOOK_NOMINAL_CURVE_SERIES_IDS,
        nominal_current,
        nominal_comparison,
    )
    real_series = _curve_comparison_series(
        points_by_id, REAL_RATE_SERIES_IDS, real_current, real_comparison
    )
    return [
        {
            "kind": "curve_comparison",
            "title": "US Yield Curve - Comparative Analysis",
            "keys": ["current", "comparison"],
            "labels": {
                "current": nominal_current or "Curve date 1",
                "comparison": nominal_comparison or "Curve date 2",
            },
            "date_options": nominal_dates,
            "selected_current_date": nominal_current,
            "selected_comparison_date": nominal_comparison,
            "y_domain": _curve_y_domain(
                points_by_id,
                WORKBOOK_NOMINAL_CURVE_SERIES_IDS,
            ),
            "series": nominal_series,
        },
        {
            "kind": "curve_comparison",
            "title": "US Real Yield Curve (TIPS) - Comparative Analysis",
            "keys": ["current", "comparison"],
            "labels": {
                "current": real_current or "Curve date 1",
                "comparison": real_comparison or "Curve date 2",
            },
            "date_options": real_dates,
            "selected_current_date": real_current,
            "selected_comparison_date": real_comparison,
            "y_domain": _curve_y_domain(points_by_id, REAL_RATE_SERIES_IDS),
            "series": real_series,
        },
    ]


def build_detail_payload(detail_id, series_rows, points_by_id, options=None):
    if options is None:
        options = {}
    config = DETAIL_CONFIG.get(detail_id)
    if config is None:
        raise ValueError(f"us rates detail is unknown: {detail_id}")
    if detail_id == "cpi_based_real_rate":
        charts = _cpi_real_rate_detail_payload(points_by_id)
    elif detail_id == "yield_curve_shape":
        charts = _curve_detail(points_by_id, options)
    elif detail_id == "corporate_yields":
        charts = _corporate_yields_detail(points_by_id)
    elif detail_id == "treasury_credit_spreads":
        charts = _treasury_credit_spreads_detail(points_by_id)
    elif detail_id == "quality_spreads":
        charts = _quality_spreads_detail(points_by_id)
    elif detail_id == "bbb_credit_spread":
        charts = _bbb_credit_spread_detail(points_by_id)
    elif detail_id == "ccc_credit_spread":
        charts = _ccc_credit_spread_detail(points_by_id)
    elif detail_id == "ccc_bbb_quality_spread":
        charts = _ccc_bbb_quality_spread_detail(points_by_id)
    elif detail_id in ("credit_conditions_diagnostics", "credit_risk_regime"):
        charts = _credit_conditions_diagnostics_detail(points_by_id)
    else:
        charts = _time_series_detail(detail_id, points_by_id)
    return {
        "detail_id": detail_id,
        "title": config["title"],
        "source": _source(
            [point for points in points_by_id.values() for point in points]
        ),
        "charts": charts,
    }


def _time_series(points):
    return [
        {"date": row["date"], "value": row["value"]}
        for row in points
        if row.get("value") is not None
    ]


def _computed_cpi_real_rate_series(points_by_id):
    treasury = {
        row["date"]: row["value"]
        for row in _series_points(points_by_id, "treasury_10y")
    }
    cpi = {row["date"]: row["value"] for row in _series_points(points_by_id, "cpi_yoy")}
    return [
        {"date": date, "value": _round(treasury[date] - cpi[date])}
        for date in sorted(set(treasury) & set(cpi))
    ]


def _cpi_real_rate_detail_payload(points_by_id):
    real_rate = _computed_cpi_real_rate_series(points_by_id)
    vix = _time_series(_series_points(points_by_id, "vix"))
    return [
        {
            "kind": "time_series",
            "title": "10Y Treasury Minus CPI YoY",
            "keys": ["value"],
            "series": real_rate,
            "labels": {"value": "CPI Real Rate"},
            "value_unit": "%",
        },
        {
            "kind": "multi_series",
            "title": "CPI Real Rate vs VIX",
            "series": [{**point, "real_rate": point["value"]} for point in real_rate],
            "secondary_series": vix,
            "keys": ["real_rate", "vix"],
            "labels": {"real_rate": "CPI Real Rate", "vix": "VIX"},
        },
    ]
