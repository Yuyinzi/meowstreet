HEADLINE_CONFIG = [
    ("treasury_10y", "10-Year Treasury"),
    ("treasury_2y", "2-Year Treasury"),
    ("tens_twos_spread", "10Y - 2Y Spread"),
    ("tips_10y", "10Y Real Rate"),
    ("cpi_based_real_rate", "CPI Real Rate"),
    ("fed_funds", "Fed Funds"),
]

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


def build_dashboard_payload(series_rows, latest_points, latest_macro_points=None):
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
                "sp500_pe": None,
                "curve_status": curve_status,
                "method_interpretation": _method_interpretation(curve_status),
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
    sp500_pe = _value(macro_points, "sp500_pe")
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
        "sp500_pe": sp500_pe,
        "curve_status": curve_status,
        "method_interpretation": _method_interpretation(curve_status),
    }
    return {
        "as_of": _as_of(latest_points),
        "source": _source(latest_points),
        "headline": _headline_payload(points, derived),
        "curve": _curve_payload(series, points),
        "real_rates": _real_rate_payload(series, points),
        "derived": derived,
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
        "series_ids": ["treasury_10y", "cpi_yoy", "vix", "sp500_pe"],
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
    pe = _time_series(_series_points(points_by_id, "sp500_pe"))
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
        {
            "kind": "multi_series",
            "title": "CPI Real Rate vs S&P 500 PE",
            "series": [{**point, "real_rate": point["value"]} for point in real_rate],
            "secondary_series": pe,
            "keys": ["real_rate", "sp500_pe"],
            "labels": {"real_rate": "CPI Real Rate", "sp500_pe": "S&P 500 PE"},
        },
    ]
