import math
from datetime import date

MIN_SAMPLE = 2
MIN_WINDOW = 2
ONE_YEAR_DAYS = 365
TWO_YEAR_DAYS = 730
ONE_YEAR_MIN_SAMPLE = 52
TWO_YEAR_MIN_SAMPLE = 104
SIGNED_MATRIX_DISCLAIMER = "indicative only, does not account for weightings"


def pearson(x, y):
    if len(x) != len(y):
        raise ValueError(f"series lengths differ: {len(x)} vs {len(y)}")
    if len(x) < MIN_SAMPLE:
        raise ValueError(f"pearson correlation requires at least {MIN_SAMPLE} observations, got {len(x)}")
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    dev_x = [value - mean_x for value in x]
    dev_y = [value - mean_y for value in y]
    var_x = sum(value * value for value in dev_x)
    var_y = sum(value * value for value in dev_y)
    if var_x == 0 or var_y == 0:
        raise ValueError("pearson correlation is undefined for a zero variance series")
    cov = sum(dev_x[i] * dev_y[i] for i in range(len(x)))
    return cov / math.sqrt(var_x * var_y)


def rolling_correlation(dates, returns_a, returns_b, window):
    _require_aligned(dates, returns_a, returns_b)
    if window < MIN_WINDOW:
        raise ValueError(f"correlation window {window} is too small")
    if len(dates) < window:
        return []
    return [
        {
            "end_date": max(dates[start : start + window]),
            "correlation": pearson(
                returns_a[start : start + window],
                returns_b[start : start + window],
            ),
        }
        for start in range(len(dates) - window + 1)
    ]


def correlation_windows(dates, returns_a, returns_b):
    _require_aligned(dates, returns_a, returns_b)
    return {
        "overall": _overall_entry(returns_a, returns_b),
        "one_year": _dated_window_entry(dates, returns_a, returns_b, ONE_YEAR_DAYS, ONE_YEAR_MIN_SAMPLE),
        "two_year": _dated_window_entry(dates, returns_a, returns_b, TWO_YEAR_DAYS, TWO_YEAR_MIN_SAMPLE),
    }


def signed_correlation_matrix(positions, returns_by_symbol):
    if len(positions) < 2:
        raise ValueError(f"signed correlation matrix requires at least 2 positions, got {len(positions)}")
    symbols = [position["symbol"] for position in positions]
    sides = [_require_side(position) for position in positions]
    for symbol in symbols:
        if symbol not in returns_by_symbol:
            raise ValueError(f"missing return series for {symbol}")
    lengths = {len(returns_by_symbol[symbol]) for symbol in symbols}
    if len(lengths) != 1:
        raise ValueError("return series must all have equal length")
    count = len(symbols)
    matrix = [
        [
            None
            if row == col
            else pearson(returns_by_symbol[symbols[row]], returns_by_symbol[symbols[col]])
            * sides[row]
            * sides[col]
            for col in range(count)
        ]
        for row in range(count)
    ]
    per_position_average = [
        sum(matrix[row][col] for col in range(count) if col != row) / (count - 1)
        for row in range(count)
    ]
    upper_triangle = [matrix[row][col] for row in range(count) for col in range(row + 1, count)]
    return {
        "symbols": symbols,
        "sides": sides,
        "matrix": matrix,
        "per_position_average": per_position_average,
        "overall_average": sum(upper_triangle) / len(upper_triangle),
        "disclaimer": SIGNED_MATRIX_DISCLAIMER,
    }


def _require_aligned(dates, returns_a, returns_b):
    if len(returns_a) != len(returns_b):
        raise ValueError(f"series lengths differ: {len(returns_a)} vs {len(returns_b)}")
    if len(dates) != len(returns_a):
        raise ValueError(f"dates length {len(dates)} does not match series length {len(returns_a)}")


def _require_side(position):
    side = position["side"]
    if side not in (1, -1):
        raise ValueError(f"position {position['symbol']} side must be 1 or -1, got {side}")
    return side


def _overall_entry(returns_a, returns_b):
    if len(returns_a) < MIN_SAMPLE:
        return {"status": "insufficient_data", "sample_size": len(returns_a)}
    return {
        "status": "ok",
        "correlation": pearson(returns_a, returns_b),
        "sample_size": len(returns_a),
    }


def _dated_window_entry(dates, returns_a, returns_b, days, min_sample):
    parsed = [date.fromisoformat(value) for value in dates]
    newest = max(parsed)
    indices = [index for index, value in enumerate(parsed) if (newest - value).days <= days]
    if len(indices) < min_sample:
        return {
            "status": "insufficient_data",
            "sample_size": len(indices),
            "min_sample": min_sample,
        }
    window_a = [returns_a[index] for index in indices]
    window_b = [returns_b[index] for index in indices]
    return {
        "status": "ok",
        "correlation": pearson(window_a, window_b),
        "sample_size": len(indices),
    }
