import math

WEEKS_PER_YEAR = 52
TRADING_DAYS_PER_YEAR = 252
MONTHLY_DAILY_RETURNS = 21
QUARTERLY_DAILY_RETURNS = 63
MIN_SAMPLE = 2
MIN_POSITION_COUNT = 8
MAX_POSITION_COUNT = 12
SHARPE_SCENARIOS = (0.5, 1.0, 1.5, 2.0)


def simple_returns(closes):
    if len(closes) < MIN_SAMPLE:
        raise ValueError(f"simple returns require at least {MIN_SAMPLE} closes, got {len(closes)}")
    returns = []
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        if previous == 0:
            raise ValueError(f"close at index {index - 1} is zero")
        returns.append(closes[index] / previous - 1)
    return returns


def sample_covariance(a, b):
    if len(a) != len(b):
        raise ValueError(f"series lengths differ: {len(a)} vs {len(b)}")
    if len(a) < MIN_SAMPLE:
        raise ValueError(f"sample covariance requires at least {MIN_SAMPLE} observations, got {len(a)}")
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    return sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(len(a))) / (len(a) - 1)


def covariance_matrix(returns_by_symbol, symbols):
    if not symbols:
        raise ValueError("symbols are required")
    for symbol in symbols:
        if symbol not in returns_by_symbol:
            raise ValueError(f"missing return series for {symbol}")
    return [
        [sample_covariance(returns_by_symbol[row], returns_by_symbol[col]) for col in symbols]
        for row in symbols
    ]


def signed_weights(allocations):
    gross = sum(abs(allocation) for allocation in allocations)
    if gross == 0:
        raise ValueError("gross exposure is zero")
    return [allocation / gross for allocation in allocations]


def portfolio_variance(weights, cov_matrix):
    count = len(weights)
    if count == 0:
        raise ValueError("weights are required")
    if len(cov_matrix) != count or any(len(row) != count for row in cov_matrix):
        raise ValueError("covariance matrix dimensions do not match weights")
    return sum(
        weights[row] * weights[col] * cov_matrix[row][col]
        for row in range(count)
        for col in range(count)
    )


def weekly_and_annualized_volatility(variance):
    if variance < 0:
        raise ValueError(f"variance {variance} is negative")
    weekly_stdev = math.sqrt(variance)
    return {
        "weekly_stdev": weekly_stdev,
        "annualized_stdev": weekly_stdev * math.sqrt(WEEKS_PER_YEAR),
    }


def average_asset_volatility(variances):
    if not variances:
        raise ValueError("variances are required")
    if any(variance < 0 for variance in variances):
        raise ValueError("asset variances must be non-negative")
    weekly_stdev = math.sqrt(sum(variances) / len(variances))
    return {
        "weekly_stdev": weekly_stdev,
        "annualized_stdev": weekly_stdev * math.sqrt(WEEKS_PER_YEAR),
    }


def portfolio_volatility_report(positions, returns_by_symbol):
    if not positions:
        raise ValueError("positions are required")
    symbols = [position["symbol"] for position in positions]
    allocations = [position["allocation"] for position in positions]
    gross_exposure = sum(abs(allocation) for allocation in allocations)
    weights = signed_weights(allocations)
    cov_matrix = covariance_matrix(returns_by_symbol, symbols)
    variance = portfolio_variance(weights, cov_matrix)
    volatility = weekly_and_annualized_volatility(variance)
    average_asset = average_asset_volatility([cov_matrix[index][index] for index in range(len(symbols))])
    return {
        "gross_exposure": gross_exposure,
        "positions": [
            {"symbol": symbol, "allocation": allocation, "signed_weight": weight}
            for symbol, allocation, weight in zip(symbols, allocations, weights)
        ],
        "variance": variance,
        "weekly_stdev": volatility["weekly_stdev"],
        "annualized_stdev": volatility["annualized_stdev"],
        "average_asset_weekly_stdev": average_asset["weekly_stdev"],
        "average_asset_annualized_stdev": average_asset["annualized_stdev"],
        "sharpe_scenarios": [
            {"sharpe": sharpe, "expected_annual_return": sharpe * volatility["annualized_stdev"]}
            for sharpe in SHARPE_SCENARIOS
        ],
    }


def realized_volatility(returns, periods_per_year):
    if len(returns) < MIN_SAMPLE:
        raise ValueError(f"realized volatility requires at least {MIN_SAMPLE} returns, got {len(returns)}")
    if periods_per_year <= 0:
        raise ValueError(f"periods per year {periods_per_year} must be positive")
    stdev = math.sqrt(_sample_variance(returns))
    return {
        "stdev": stdev,
        "annualized": stdev * math.sqrt(periods_per_year),
        "sample_size": len(returns),
    }


def realized_volatility_report(daily_closes, weekly_closes):
    daily_returns = simple_returns(daily_closes)
    weekly_returns = simple_returns(weekly_closes)
    return {
        "daily": realized_volatility(daily_returns, TRADING_DAYS_PER_YEAR),
        "weekly": realized_volatility(weekly_returns, WEEKS_PER_YEAR),
        "monthly_21d": _horizon_entry(daily_returns, MONTHLY_DAILY_RETURNS, TRADING_DAYS_PER_YEAR),
        "quarterly_63d": _horizon_entry(daily_returns, QUARTERLY_DAILY_RETURNS, TRADING_DAYS_PER_YEAR),
    }


def position_count_check(count):
    if count < 0:
        raise ValueError(f"position count {count} is negative")
    if count > MAX_POSITION_COUNT:
        warning = "over_diversified"
    elif count < MIN_POSITION_COUNT:
        warning = "under_diversified"
    else:
        warning = None
    return {
        "count": count,
        "within_range": MIN_POSITION_COUNT <= count <= MAX_POSITION_COUNT,
        "warning": warning,
    }


def _horizon_entry(returns, count, periods_per_year):
    if len(returns) < count:
        return {
            "status": "insufficient_data",
            "sample_size": len(returns),
            "required": count,
        }
    return realized_volatility(returns[-count:], periods_per_year)


def _sample_variance(values):
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)
