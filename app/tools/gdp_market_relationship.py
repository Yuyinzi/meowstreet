from collections import defaultdict

QUAD_LABELS = {
    "0,0": "both down",
    "1,1": "both up",
    "0,1": "index down / GDP up",
    "1,0": "index up / GDP down",
}


def _round_pct(value):
    return round(value, 2)


def _same_direction(quad_case):
    return quad_case in {"0,0", "1,1"}


def _latest_primary_lag_row(lag_rows, primary_lag_months):
    primary_rows = [r for r in lag_rows if r["lag_months"] == primary_lag_months]
    if not primary_rows:
        return None
    return sorted(primary_rows, key=lambda r: r["date"])[-1]


def _latest_quad_row(quad_rows):
    if not quad_rows:
        return None
    return sorted(quad_rows, key=lambda r: r["date"])[-1]


def _distribution(quad_rows):
    if not quad_rows:
        return []
    counts = defaultdict(int)
    for row in quad_rows:
        counts[row["quad_case"]] += 1
    total = len(quad_rows)
    return [
        {
            "case": quad_case,
            "label": QUAD_LABELS.get(quad_case, quad_case),
            "count": count,
            "value": _round_pct(count / total * 100),
        }
        for quad_case, count in sorted(counts.items())
    ]


def _same_direction_pct(quad_rows):
    if not quad_rows:
        return None
    cases = [r["quad_case"] for r in quad_rows if r.get("quad_case")]
    if not cases:
        return None
    same = sum(1 for c in cases if _same_direction(c))
    return _round_pct(same / len(cases) * 100)


def _relationship_signal_usability(
    relationship, latest_primary_lag, same_direction_pct
):
    if relationship.get("region") == "China":
        return "Do not rely on GDP alone"
    if latest_primary_lag is None or same_direction_pct is None:
        return None
    corr = latest_primary_lag.get("rolling_correlation")
    if corr is None:
        return None
    if corr >= 0.4 and same_direction_pct >= 60:
        return "GDP relationship usable"
    if corr >= 0.25 and same_direction_pct >= 55:
        return "GDP relationship usable with caution"
    return "GDP relationship weak"


def _macro_relationship_confidence(relationship, corr, same_direction_pct):
    if relationship.get("region") == "China":
        return "low"
    if corr is None or same_direction_pct is None:
        return "low"
    if corr >= 0.4 and same_direction_pct >= 60:
        return "high"
    if corr >= 0.25 and same_direction_pct >= 55:
        return "medium"
    return "low"


def _correlation_series(lag_rows, primary_lag_months):
    return [
        {"date": r["date"], "value": r["rolling_correlation"]}
        for r in lag_rows
        if r["lag_months"] == primary_lag_months
    ]


def _yoy_series(lag_rows, primary_lag_months):
    primary_rows = [r for r in lag_rows if r["lag_months"] == primary_lag_months]
    by_year = defaultdict(lambda: {"index": None, "gdp": None})
    for r in primary_rows:
        year = int(r["date"][:4])
        by_year[year]["index"] = r["index_yoy"]
        by_year[year]["gdp"] = r["gdp_yoy"]
    return sorted(
        [
            {
                "label": year,
                "index": round(values["index"] * 100, 2)
                if values["index"] is not None
                else None,
                "gdp": round(values["gdp"] * 100, 2)
                if values["gdp"] is not None
                else None,
            }
            for year, values in by_year.items()
        ],
        key=lambda item: item["label"],
    )


def _build_card(relationship, lag_rows, quad_rows):
    primary_lag = relationship["primary_lag_months"]
    latest_lag = _latest_primary_lag_row(lag_rows, primary_lag)
    latest_quad = _latest_quad_row(quad_rows)
    same_dir_pct = _same_direction_pct(quad_rows)
    corr = latest_lag.get("rolling_correlation") if latest_lag else None
    signal = _relationship_signal_usability(relationship, latest_lag, same_dir_pct)
    confidence = _macro_relationship_confidence(relationship, corr, same_dir_pct)

    card = {
        "relationship_id": relationship["relationship_id"],
        "title": relationship.get("title"),
        "region": relationship.get("region"),
        "economy": relationship.get("economy"),
        "index_name": relationship.get("index_name"),
        "primary_lag_months": primary_lag,
        "correlation_window_years": relationship.get("correlation_window_years"),
        "latest": {
            "primary_lag_months": primary_lag,
            "rolling_index_gdp_correlation": corr,
            "quadnomial_current_case": latest_quad["quad_case"]
            if latest_quad
            else None,
            "index_yoy": latest_lag.get("index_yoy") if latest_lag else None,
            "gdp_yoy": latest_lag.get("gdp_yoy") if latest_lag else None,
        },
        "same_direction_pct": same_dir_pct,
        "opposite_direction_pct": _round_pct(100 - same_dir_pct)
        if same_dir_pct is not None
        else None,
        "relationship_signal_usability": signal,
        "portfolio_bias_status": "Portfolio bias requires GDP forecast",
        "macro_relationship_confidence": confidence,
    }
    return card


def build_overview_payload(relationships, load_lag_rows, load_quad_rows):
    cards = []
    for rel in relationships:
        rid = rel["relationship_id"]
        lag = load_lag_rows(rid)
        quad = load_quad_rows(rid)
        cards.append(_build_card(rel, lag, quad))
    return {"relationships": cards}


def build_detail_payload(relationship, lag_rows, quad_rows):
    primary_lag = relationship["primary_lag_months"]
    primary_lag_rows = [r for r in lag_rows if r["lag_months"] == primary_lag]

    lag_correlations = [
        {
            "date": r["date"],
            "lag_months": r["lag_months"],
            "rolling_correlation": r["rolling_correlation"],
            "method_primary": r["lag_months"] == primary_lag,
        }
        for r in lag_rows
    ]

    lag_series = [
        {
            "date": r["date"],
            "lag_months": r["lag_months"],
            "rolling_correlation": r["rolling_correlation"],
        }
        for r in lag_rows
    ]

    return {
        "relationship_id": relationship["relationship_id"],
        "title": relationship.get("title"),
        "region": relationship.get("region"),
        "economy": relationship.get("economy"),
        "index_name": relationship.get("index_name"),
        "primary_lag_months": primary_lag,
        "correlation_window_years": relationship.get("correlation_window_years"),
        "lag_correlations": lag_correlations,
        "lag_series": lag_series,
        "correlation_series": _correlation_series(lag_rows, primary_lag),
        "yoy_series": _yoy_series(lag_rows, primary_lag),
        "quadnomial_distribution": _distribution(quad_rows),
    }
