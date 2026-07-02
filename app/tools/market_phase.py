from app.db.benchmark_market_data import BENCHMARKS, BENCHMARKS_BY_ID


def compute_market_phase_series(rows):
    rolling_high = None
    series = []
    for row in rows:
        close = float(row["close"])
        high = float(row["high"] if row.get("high") is not None else close)
        rolling_high = high if rolling_high is None else max(rolling_high, high)
        bear_market_level = rolling_high * 0.8
        status = "bear_market" if close <= bear_market_level else "bull_market"
        drawdown_pct = round((close / rolling_high - 1) * 100, 2)
        series.append(
            {
                "date": row["date"],
                "close": close,
                "rolling_high": round(rolling_high, 4),
                "bear_market_level": round(bear_market_level, 4),
                "drawdown_pct": drawdown_pct,
                "market_phase_status": status,
                "bull_market_index": close if status == "bull_market" else None,
                "bear_market_index": close if status == "bear_market" else None,
            }
        )
    return series


def build_market_phase_payload(benchmark_id, rows):
    benchmark = BENCHMARKS_BY_ID.get(benchmark_id)
    if not benchmark:
        raise ValueError(f"benchmark is unknown: {benchmark_id}")
    if not rows:
        raise ValueError(f"benchmark has no price rows: {benchmark_id}")
    series = compute_market_phase_series(rows)
    latest = series[-1]
    return {
        "benchmark_id": benchmark_id,
        "title": benchmark["title"],
        "region": benchmark["region"],
        "data_through": latest["date"],
        "latest": latest,
        "series": series,
    }


def build_dashboard_payload(load_rows):
    markets = []
    for benchmark in BENCHMARKS:
        rows = load_rows(benchmark["id"])
        if rows:
            markets.append(build_market_phase_payload(benchmark["id"], rows))
    return {"markets": markets}
