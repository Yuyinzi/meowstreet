BENCHMARKS = [
    {"id": "us_sp500", "title": "S&P 500", "region": "US"},
    {"id": "us_nasdaq_100", "title": "Nasdaq 100", "region": "US"},
    {"id": "us_nasdaq_composite", "title": "Nasdaq Composite", "region": "US"},
    {"id": "us_djia", "title": "Dow Jones Industrial Average", "region": "US"},
    {"id": "europe_stoxx_50", "title": "Eurostoxx 50", "region": "Europe"},
    {"id": "europe_stoxx_600", "title": "Eurostoxx 600", "region": "Europe"},
    {"id": "uk_ftse_100", "title": "FTSE 100", "region": "UK"},
    {"id": "uk_ftse_250", "title": "FTSE 250", "region": "UK"},
    {"id": "uk_ftse_350", "title": "FTSE 350", "region": "UK"},
    {"id": "germany_dax_40", "title": "DAX 40", "region": "Germany"},
    {"id": "hong_kong_hsi", "title": "Hang Seng Index", "region": "Hong Kong"},
    {
        "id": "hong_kong_hscei",
        "title": "Hang Seng China Enterprises",
        "region": "Hong Kong",
    },
    {"id": "japan_nikkei_225", "title": "Nikkei 225", "region": "Japan"},
    {"id": "australia_asx_200", "title": "ASX 200", "region": "Australia"},
]

BENCHMARKS_BY_ID = {benchmark["id"]: benchmark for benchmark in BENCHMARKS}


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


def build_market_phase_summary_payload(benchmark_id, rows):
    payload = build_market_phase_payload(benchmark_id, rows)
    return {
        "benchmark_id": payload["benchmark_id"],
        "title": payload["title"],
        "region": payload["region"],
        "data_through": payload["data_through"],
        "latest": payload["latest"],
    }


def build_dashboard_payload(load_rows, benchmark_ids=None):
    benchmarks = [
        b for b in BENCHMARKS if benchmark_ids is None or b["id"] in benchmark_ids
    ]
    markets = []
    for benchmark in benchmarks:
        rows = load_rows(benchmark["id"])
        if rows:
            markets.append(build_market_phase_summary_payload(benchmark["id"], rows))
    return {"markets": markets}
