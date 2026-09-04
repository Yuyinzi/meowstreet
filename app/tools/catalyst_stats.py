from datetime import date, timedelta
from statistics import mean, stdev

from app.tools.portfolio_volatility import simple_returns


MIN_RETURN_SAMPLES = 30
_MONTHS_PER_QUARTER = 3
_MONTHS_PER_YEAR = 12


def filing_frequency(filings, today):
    dated = []
    for filing in filings:
        try:
            filing_date = date.fromisoformat(str(filing.get("filing_date")))
        except (ValueError, TypeError):
            continue
        dated.append((filing_date, filing))
    if isinstance(today, str):
        today = date.fromisoformat(today)
    if not dated:
        return {"status": "insufficient_data"}
    dated.sort(key=lambda entry: entry[0])
    first_date = dated[0][0]
    window_days = (today - first_date).days
    if window_days <= 0:
        return {"status": "insufficient_data"}
    window_months = window_days / 30.4375
    total = len(dated)
    classified = [entry for entry in dated if entry[1].get("is_earnings") is not None]
    earnings = sum(1 for entry in classified if entry[1]["is_earnings"])
    non_earnings = len(classified) - earnings
    unclassified = total - len(classified)
    return {
        "status": "ok",
        "window_months": round(window_months, 1),
        "total": total,
        "earnings": earnings,
        "non_earnings": non_earnings,
        "unclassified": unclassified,
        "per_year": round(total / window_months * _MONTHS_PER_YEAR, 2),
        "per_quarter": round(total / window_months * _MONTHS_PER_QUARTER, 2),
        "per_month": round(total / window_months, 2),
        "non_earnings_per_month": round(non_earnings / window_months, 2) if len(classified) == total else None,
    }


def large_move_days(closes, dates):
    if len(closes) != len(dates):
        raise ValueError(f"closes and dates length differ: {len(closes)} vs {len(dates)}")
    returns = simple_returns(closes)
    move_dates = list(dates[1:])
    n = len(returns)
    if n < MIN_RETURN_SAMPLES:
        return {"status": "insufficient_data", "sample_days": n}
    center = mean(returns)
    sigma = stdev(returns)
    if sigma == 0:
        return {"status": "insufficient_data", "sample_days": n}
    moves = []
    for value, move_date in zip(returns, move_dates):
        abs_sigma = abs(value - center) / sigma
        if abs_sigma > 1.0:
            moves.append({
                "date": str(move_date),
                "return": value,
                "abs_sigma": round(abs_sigma, 2),
                "beyond_2sigma": abs_sigma > 2.0,
            })
    moves.sort(key=lambda move: move["abs_sigma"], reverse=True)
    return {
        "status": "ok",
        "sample_days": n,
        "mean_return": center,
        "stdev": sigma,
        "moves": moves,
    }


def daily_return_calendar(closes, dates):
    if len(closes) != len(dates):
        raise ValueError(f"closes and dates length differ: {len(closes)} vs {len(dates)}")
    returns = simple_returns(closes)
    return [{"date": str(day), "return": round(value, 6)} for day, value in zip(dates[1:], returns)]


def align_moves_with_filings(moves, filing_dates, tolerance_days=1):
    parsed_dates = set()
    for value in filing_dates:
        try:
            parsed_dates.add(date.fromisoformat(str(value)))
        except (ValueError, TypeError):
            continue
    aligned = []
    for move in moves:
        try:
            move_date = date.fromisoformat(str(move.get("date")))
        except (ValueError, TypeError):
            aligned.append({**move, "filing_within_window": None})
            continue
        matched = any(
            (move_date - timedelta(days=tolerance_days)) <= filing <= (move_date + timedelta(days=tolerance_days))
            for filing in parsed_dates
        )
        aligned.append({**move, "filing_within_window": matched})
    return aligned
