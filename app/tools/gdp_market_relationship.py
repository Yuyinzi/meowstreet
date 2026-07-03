from collections import defaultdict

QUAD_LABELS = {
    "0,0": "A (INDEX DOWN / GDP DOWN)",
    "1,1": "B (INDEX UP / GDP UP)",
    "0,1": "C (INDEX DOWN / GDP UP)",
    "1,0": "D (INDEX UP / GDP DOWN)",
}

QUAD_PLAIN_LABELS = {
    "0,0": "INDEX DOWN / GDP DOWN",
    "1,1": "INDEX UP / GDP UP",
    "0,1": "INDEX DOWN / GDP UP",
    "1,0": "INDEX UP / GDP DOWN",
}

QUAD_INTERPRETATIONS = {
    "0,0": "Same direction; bearish macro confirmation",
    "1,1": "Same direction; bullish macro confirmation",
    "0,1": "Opposite direction; possible profit-taking/correction",
    "1,0": "Opposite direction; lower-confidence/unpredictable case",
}


def _round_pct(value):
    return round(value, 2)


def _same_direction(quad_case):
    return quad_case in {"0,0", "1,1"}


def _method_explainable(quad_case):
    return quad_case in {"0,0", "1,1", "0,1"}


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
            "interpretation": QUAD_INTERPRETATIONS.get(quad_case),
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


def _method_explainable_pct(quad_rows):
    if not quad_rows:
        return None
    cases = [r["quad_case"] for r in quad_rows if r.get("quad_case")]
    if not cases:
        return None
    explainable = sum(1 for c in cases if _method_explainable(c))
    return _round_pct(explainable / len(cases) * 100)


def _average_correlation(rows):
    values = [
        row["rolling_correlation"]
        for row in rows
        if row.get("rolling_correlation") is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _average_primary_lag_correlation(lag_rows, primary_lag_months):
    return _average_correlation(
        [row for row in lag_rows if row["lag_months"] == primary_lag_months]
    )


def _average_lag_correlations(lag_rows, primary_lag_months):
    rows_by_lag = defaultdict(list)
    for row in lag_rows:
        rows_by_lag[row["lag_months"]].append(row)
    return [
        {
            "lag_months": lag,
            "label": _lag_label(lag),
            "value": _average_correlation(rows),
            "method_primary": lag == primary_lag_months,
        }
        for lag, rows in sorted(rows_by_lag.items())
    ]


def _relationship_signal_usability(
    relationship, average_primary_lag_correlation, same_direction_pct
):
    if str(relationship.get("region", "")).lower() == "china":
        return "Do not rely on GDP alone"
    if average_primary_lag_correlation is None or same_direction_pct is None:
        return None
    corr = average_primary_lag_correlation
    if corr >= 0.4 and same_direction_pct >= 60:
        return "GDP relationship usable"
    if corr >= 0.25 and same_direction_pct >= 55:
        return "GDP relationship usable with caution"
    return "GDP relationship weak"


def _macro_relationship_confidence(relationship, corr, same_direction_pct):
    if str(relationship.get("region", "")).lower() == "china":
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
        and r.get("rolling_correlation") is not None
    ]


def _lag_label(lag_months):
    return "No lag" if lag_months == 0 else f"{lag_months}M lag"


def _latest_lag_rows_by_lag(lag_rows):
    latest_by_lag = {}
    for row in sorted(lag_rows, key=lambda item: item["date"]):
        latest_by_lag[row["lag_months"]] = row
    return [latest_by_lag[lag] for lag in sorted(latest_by_lag)]


def _yoy_series(lag_rows):
    no_lag_rows = [r for r in lag_rows if r["lag_months"] == 0]
    return sorted(
        [
            {
                "date": row["date"],
                "index": round(row["index_yoy"] * 100, 2)
                if row["index_yoy"] is not None
                else None,
                "gdp": round(row["gdp_yoy"] * 100, 2)
                if row["gdp_yoy"] is not None
                else None,
            }
            for row in no_lag_rows
        ],
        key=lambda item: item["date"],
    )


def _lag_correlation_series(lag_rows):
    by_date = defaultdict(dict)
    for row in lag_rows:
        value = row.get("rolling_correlation")
        if value is None:
            continue
        by_date[row["date"]][f"lag_{row['lag_months']}"] = value
    return [
        {"date": date, **values}
        for date, values in sorted(by_date.items())
    ]


def _lag_correlation_labels(lag_rows):
    lags = sorted({row["lag_months"] for row in lag_rows})
    return {f"lag_{lag}": _lag_label(lag) for lag in lags}


def _build_card(relationship, lag_rows, quad_rows):
    primary_lag = relationship["primary_lag_months"]
    latest_lag = _latest_primary_lag_row(lag_rows, primary_lag)
    latest_quad = _latest_quad_row(quad_rows)
    same_dir_pct = _same_direction_pct(quad_rows)
    explainable_pct = _method_explainable_pct(quad_rows)
    corr = latest_lag.get("rolling_correlation") if latest_lag else None
    avg_corr = _average_primary_lag_correlation(lag_rows, primary_lag)
    signal = _relationship_signal_usability(relationship, avg_corr, same_dir_pct)
    confidence = _macro_relationship_confidence(relationship, avg_corr, same_dir_pct)

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
            "average_10y_correlation": avg_corr,
            "quadnomial_current_case": latest_quad["quad_case"]
            if latest_quad
            else None,
            "quadnomial_current_label": QUAD_LABELS.get(latest_quad["quad_case"])
            if latest_quad
            else None,
            "quadnomial_current_plain_label": QUAD_PLAIN_LABELS.get(
                latest_quad["quad_case"]
            )
            if latest_quad
            else None,
            "index_yoy": latest_lag.get("index_yoy") if latest_lag else None,
            "gdp_yoy": latest_lag.get("gdp_yoy") if latest_lag else None,
            "primary_lag_date": latest_lag.get("date") if latest_lag else None,
            "quadnomial_date": latest_quad.get("date") if latest_quad else None,
            "quadnomial_period_label": latest_quad.get("period_label")
            if latest_quad
            else None,
        },
        "same_direction_pct": same_dir_pct,
        "method_explainable_pct": explainable_pct,
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
    payload = _build_card(relationship, lag_rows, quad_rows)

    lag_correlations = [
        {
            "date": r["date"],
            "lag_months": r["lag_months"],
            "rolling_correlation": r["rolling_correlation"],
            "label": _lag_label(r["lag_months"]),
            "value": r["rolling_correlation"],
            "method_primary": r["lag_months"] == primary_lag,
        }
        for r in _latest_lag_rows_by_lag(lag_rows)
    ]

    lag_series = [
        {
            "date": r["date"],
            "lag_months": r["lag_months"],
            "rolling_correlation": r["rolling_correlation"],
        }
        for r in lag_rows
    ]

    payload.update(
        {
            "lag_correlations": lag_correlations,
            "lag_series": lag_series,
            "correlation_series": _correlation_series(lag_rows, primary_lag),
            "yoy_series": _yoy_series(lag_rows),
            "lag_correlation_series": _lag_correlation_series(lag_rows),
            "lag_correlation_labels": _lag_correlation_labels(lag_rows),
            "average_lag_correlations": _average_lag_correlations(
                lag_rows, primary_lag
            ),
            "quadnomial_distribution": _distribution(quad_rows),
        }
    )
    return payload
