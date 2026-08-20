from datetime import date, timedelta

import pytest

from app.services import portfolio_analysis as service


RETURN_PATTERN = (0.01, -0.004, 0.006, -0.002, 0.008, -0.006, 0.003)
WEEKLY_COUNT = 130
DAILY_COUNT = 70


def weekly_dates(count, start=date(2020, 1, 6)):
    return [(start + timedelta(weeks=index)).isoformat() for index in range(count)]


def daily_dates(count, start=date(2026, 1, 1)):
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def sample_returns(count, multiplier=1.0):
    return [
        multiplier * RETURN_PATTERN[index % len(RETURN_PATTERN)]
        for index in range(count)
    ]


def closes_from_returns(start, returns):
    closes = [start]
    for value in returns:
        closes.append(closes[-1] * (1 + value))
    return closes


def market_payload(symbol, dates, closes):
    return {
        "symbol": symbol,
        "metrics": {"price": closes[-1]},
        "prices": {"dates": dates, "adjusted_close": closes},
    }


def weekly_series(multiplier=1.0, count=WEEKLY_COUNT, start_price=100.0):
    return closes_from_returns(start_price, sample_returns(count - 1, multiplier))


def series_map(symbols, multipliers, weekly_count=WEEKLY_COUNT):
    dates = weekly_dates(weekly_count)
    result = {("^GSPC", "1wk"): (dates, weekly_series(1.0, weekly_count))}
    for symbol, multiplier in zip(symbols, multipliers):
        result[(symbol, "1wk")] = (dates, weekly_series(multiplier, weekly_count, 50.0))
        result[(symbol, "1d")] = (
            daily_dates(DAILY_COUNT),
            closes_from_returns(50.0, sample_returns(DAILY_COUNT - 1, multiplier)),
        )
    return result


def stub_market_data(monkeypatch, series, fail_symbols=()):
    def fake_fetch(symbol, **kwargs):
        if symbol in fail_symbols:
            raise ValueError(
                f"market data fetch failed for {symbol}: HTTP 404 Not Found"
            )
        interval = kwargs.get("interval", "1d")
        key = (symbol, interval)
        if key not in series:
            raise ValueError(f"market data is missing for {symbol}")
        dates, closes = series[key]
        return market_payload(symbol, dates, closes)

    monkeypatch.setattr(service.market_data, "fetch_market_data", fake_fetch)


def portfolio_payload():
    return {
        "positions": [
            {"symbol": "AAA", "side": "long", "allocation": 100},
            {"symbol": "BBB", "side": "short", "allocation": 100},
            {"symbol": "CCC", "side": "long", "allocation": 50},
            {"symbol": "DDD", "side": "short", "allocation": 50},
        ],
        "margin_capital": 50_000,
        "declared_bias": "long",
        "instrument": "us_stock",
    }


def test_ticker_risk_profile_known_beta(monkeypatch):
    stub_market_data(monkeypatch, series_map(["AAA"], [2.0]))

    profile = service.get_ticker_risk_profile("aaa")

    assert profile["symbol"] == "AAA"
    assert profile["benchmark"] == "^GSPC"
    window_entries = {
        entry["window"]: entry for entry in profile["beta"]["windows"]
    }
    assert window_entries[105]["status"] == "ok"
    assert window_entries[105]["beta"] == pytest.approx(2.0)
    assert window_entries[157]["status"] == "insufficient_data"
    assert window_entries[261]["status"] == "insufficient_data"
    rolling = profile["beta"]["rolling_beta"]
    assert len(rolling) == WEEKLY_COUNT - 1 - 105 + 1
    assert all(entry["beta"] == pytest.approx(2.0) for entry in rolling)
    volatility = profile["realized_volatility"]
    assert volatility["daily"]["annualized"] > 0
    assert volatility["weekly"]["annualized"] > 0
    assert volatility["monthly_21d"]["annualized"] > 0
    assert profile["data"] == {
        "weekly_start": weekly_dates(WEEKLY_COUNT)[0],
        "weekly_end": weekly_dates(WEEKLY_COUNT)[-1],
        "weekly_count": WEEKLY_COUNT,
    }


def test_ticker_risk_profile_beta_uses_most_recent_window(monkeypatch):
    dates = weekly_dates(WEEKLY_COUNT)
    market_returns = sample_returns(WEEKLY_COUNT - 1)
    stock_returns = [
        (2.0 if index >= WEEKLY_COUNT - 1 - 105 else 0.5) * value
        for index, value in enumerate(market_returns)
    ]
    stub_market_data(
        monkeypatch,
        {
            ("^GSPC", "1wk"): (dates, closes_from_returns(100.0, market_returns)),
            ("AAA", "1wk"): (dates, closes_from_returns(50.0, stock_returns)),
            ("AAA", "1d"): (
                daily_dates(DAILY_COUNT),
                closes_from_returns(50.0, sample_returns(DAILY_COUNT - 1, 2.0)),
            ),
        },
    )

    profile = service.get_ticker_risk_profile("AAA")

    assert profile["beta"]["windows"][0]["beta"] == pytest.approx(2.0)


def test_ticker_risk_profile_aligns_to_common_dates(monkeypatch):
    series = series_map(["AAA"], [2.0])
    dates, closes = series[("AAA", "1wk")]
    series[("AAA", "1wk")] = (["2019-12-30"] + dates, [49.0] + closes)
    stub_market_data(monkeypatch, series)

    profile = service.get_ticker_risk_profile("AAA")

    assert profile["data"]["weekly_start"] == dates[0]
    assert profile["data"]["weekly_count"] == WEEKLY_COUNT
    window_105 = profile["beta"]["windows"][0]
    assert window_105["beta"] == pytest.approx(2.0)


def test_ticker_risk_profile_requires_two_common_points(monkeypatch):
    stub_market_data(
        monkeypatch,
        {("^GSPC", "1wk"): (["2026-01-05"], [100.0]), ("AAA", "1wk"): (["2026-02-02"], [50.0]), ("AAA", "1d"): (["2026-01-01", "2026-01-02"], [50.0, 50.5])},
    )

    with pytest.raises(ValueError, match="fewer than 2 common"):
        service.get_ticker_risk_profile("AAA")


def test_portfolio_analysis_happy_path(monkeypatch):
    stub_market_data(
        monkeypatch, series_map(["AAA", "BBB", "CCC", "DDD"], [2.0, 0.5, 1.5, 1.0])
    )

    result = service.get_portfolio_analysis(portfolio_payload())

    assert result["missing_inputs"] == []
    assert result["positions"] == [
        {"symbol": "AAA", "side": 1, "allocation": 100.0},
        {"symbol": "BBB", "side": -1, "allocation": 100.0},
        {"symbol": "CCC", "side": 1, "allocation": 50.0},
        {"symbol": "DDD", "side": -1, "allocation": 50.0},
    ]
    assert result["window"] == {
        "start_date": weekly_dates(WEEKLY_COUNT)[0],
        "end_date": weekly_dates(WEEKLY_COUNT)[-1],
        "weekly_count": WEEKLY_COUNT,
    }
    volatility = result["volatility"]
    assert volatility["status"] == "ok"
    assert volatility["gross_exposure"] == pytest.approx(300.0)
    assert volatility["annualized_stdev"] > 0
    assert volatility["position_count_check"]["count"] == 4
    assert volatility["position_count_check"]["warning"] == "under_diversified"
    correlation = result["correlation"]
    assert correlation["status"] == "ok"
    assert correlation["symbols"] == ["AAA", "BBB", "CCC", "DDD"]
    assert correlation["overall_average"] == pytest.approx(-1 / 3)
    beta = result["beta"]
    assert beta["status"] == "ok"
    assert beta["excluded_from_portfolio"] == []
    betas = {entry["symbol"]: entry["beta"] for entry in beta["per_position"]}
    assert betas == pytest.approx({"AAA": 2.0, "BBB": 0.5, "CCC": 1.5, "DDD": 1.0})
    portfolio = beta["portfolio"]
    assert portfolio["gross_exposure"] == pytest.approx(300.0)
    assert portfolio["net_exposure"] == pytest.approx(0.0)
    assert portfolio["portfolio_beta"] == pytest.approx(175 / 300)
    assert set(beta["sizing"]) == {"equal_weight", "risk_parity", "beta_parity"}
    gates = result["gates"]
    assert gates["position_count"]["status"] == "below"
    assert gates["position_count"]["tier"]["min_positions"] == 8
    assert gates["volatility"]["status"] in ("below", "within", "above")
    assert gates["correlation"]["status"] == "outside"
    assert gates["net_beta"]["status"] == "outside"
    assert gates["return_targets"]["min_sharpe"] == 2.0
    assert gates["beta_macro_alignment"]["status"] == "aligned"
    inference = result["outperformance_inference"]
    assert inference["status"] == "valid"
    assert inference["gross_long"] == pytest.approx(150.0)
    assert inference["gross_short"] == pytest.approx(150.0)


def test_portfolio_analysis_omits_optional_gates(monkeypatch):
    stub_market_data(
        monkeypatch, series_map(["AAA", "BBB", "CCC", "DDD"], [2.0, 0.5, 1.5, 1.0])
    )
    payload = {"positions": portfolio_payload()["positions"]}

    result = service.get_portfolio_analysis(payload)

    gates = result["gates"]
    assert gates["position_count"] == {
        "status": "unknown",
        "reason": "margin_capital not provided",
    }
    assert "return_targets" not in gates
    assert "beta_macro_alignment" not in gates
    assert gates["volatility"]["status"] in ("below", "within", "above")


def test_portfolio_analysis_missing_symbol_degrades(monkeypatch):
    stub_market_data(
        monkeypatch,
        series_map(["AAA", "BBB", "CCC"], [2.0, 0.5, 1.5]),
        fail_symbols=("DDD",),
    )

    result = service.get_portfolio_analysis(portfolio_payload())

    assert [item["symbol"] for item in result["missing_inputs"]] == ["DDD"]
    assert "HTTP 404" in result["missing_inputs"][0]["reason"]
    assert result["volatility"]["status"] == "ok"
    assert result["correlation"]["status"] == "ok"
    assert result["correlation"]["symbols"] == ["AAA", "BBB", "CCC"]
    assert result["beta"]["status"] == "ok"
    assert result["beta"]["portfolio"]["gross_exposure"] == pytest.approx(250.0)
    inference = result["outperformance_inference"]
    assert inference["gross_long"] == pytest.approx(150.0)
    assert inference["gross_short"] == pytest.approx(150.0)
    assert inference["status"] == "valid"


def test_portfolio_analysis_fewer_than_two_usable_positions(monkeypatch):
    stub_market_data(
        monkeypatch,
        series_map(["AAA"], [2.0]),
        fail_symbols=("BBB",),
    )
    payload = {
        "positions": [
            {"symbol": "AAA", "side": "long", "allocation": 100},
            {"symbol": "BBB", "side": "short", "allocation": 100},
        ],
        "margin_capital": 50_000,
        "declared_bias": "neutral",
        "instrument": "cfd",
    }

    result = service.get_portfolio_analysis(payload)

    assert result["volatility"] == {
        "status": "insufficient_data",
        "reason": "fewer than 2 usable positions",
    }
    assert result["correlation"]["status"] == "insufficient_data"
    assert result["beta"]["status"] == "insufficient_data"
    gates = result["gates"]
    assert gates["volatility"]["status"] == "unknown"
    assert gates["correlation"]["status"] == "unknown"
    assert gates["net_beta"]["status"] == "unknown"
    assert gates["return_targets"]["status"] == "unknown"
    assert gates["beta_macro_alignment"]["status"] == "unknown"
    assert gates["position_count"]["status"] == "below"
    assert result["outperformance_inference"]["status"] == "valid"


def test_portfolio_analysis_single_side_outperformance_insufficient(monkeypatch):
    stub_market_data(monkeypatch, series_map(["AAA", "CCC"], [2.0, 1.5]))
    payload = {
        "positions": [
            {"symbol": "AAA", "side": "long", "allocation": 100},
            {"symbol": "CCC", "side": "long", "allocation": 50},
        ]
    }

    result = service.get_portfolio_analysis(payload)

    inference = result["outperformance_inference"]
    assert inference["status"] == "insufficient_data"
    assert inference["gross_long"] == pytest.approx(150.0)
    assert inference["gross_short"] == 0


def test_portfolio_analysis_position_beta_uses_most_recent_window(monkeypatch):
    dates = weekly_dates(WEEKLY_COUNT)
    market_returns = sample_returns(WEEKLY_COUNT - 1)
    stock_returns = [
        (2.0 if index >= WEEKLY_COUNT - 1 - 105 else 0.5) * value
        for index, value in enumerate(market_returns)
    ]
    stub_market_data(
        monkeypatch,
        {
            ("^GSPC", "1wk"): (dates, closes_from_returns(100.0, market_returns)),
            ("AAA", "1wk"): (dates, closes_from_returns(50.0, stock_returns)),
            ("BBB", "1wk"): (dates, weekly_series(1.0, WEEKLY_COUNT, 50.0)),
        },
    )
    payload = {
        "positions": [
            {"symbol": "AAA", "side": "long", "allocation": 100},
            {"symbol": "BBB", "side": "short", "allocation": 100},
        ]
    }

    result = service.get_portfolio_analysis(payload)

    betas = {
        entry["symbol"]: entry["beta"] for entry in result["beta"]["per_position"]
    }
    assert betas["AAA"] == pytest.approx(2.0)
    assert betas["BBB"] == pytest.approx(1.0)


def test_portfolio_analysis_beta_uses_each_position_own_history(monkeypatch):
    dates = weekly_dates(WEEKLY_COUNT)
    short_dates = weekly_dates(81)
    stub_market_data(
        monkeypatch,
        {
            ("^GSPC", "1wk"): (dates, weekly_series(1.0, WEEKLY_COUNT)),
            ("AAA", "1wk"): (dates, weekly_series(2.0, WEEKLY_COUNT, 50.0)),
            ("BBB", "1wk"): (short_dates, weekly_series(0.5, 81, 50.0)),
        },
    )
    payload = {
        "positions": [
            {"symbol": "AAA", "side": "long", "allocation": 100},
            {"symbol": "BBB", "side": "short", "allocation": 100},
        ]
    }

    result = service.get_portfolio_analysis(payload)

    assert result["window"]["weekly_count"] == 81
    beta = result["beta"]
    assert beta["status"] == "ok"
    entries = {entry["symbol"]: entry for entry in beta["per_position"]}
    assert entries["AAA"]["status"] == "ok"
    assert entries["AAA"]["beta"] == pytest.approx(2.0)
    assert entries["BBB"]["status"] == "insufficient_data"
    assert entries["BBB"]["sample_size"] == 80
    assert beta["excluded_from_portfolio"] == ["BBB"]
    assert beta["portfolio"]["portfolio_beta"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda payload: payload.update({"positions": []}), "non-empty list"),
        (lambda payload: payload.update({"positions": "AAA"}), "non-empty list"),
        (
            lambda payload: payload["positions"][0].update({"side": "flat"}),
            "side must be long or short, got flat",
        ),
        (
            lambda payload: payload["positions"][0].update({"allocation": 0}),
            "allocation must be positive, got 0",
        ),
        (
            lambda payload: payload["positions"][0].update({"allocation": -5}),
            "allocation must be positive, got -5",
        ),
        (
            lambda payload: payload["positions"][0].update({"allocation": "100"}),
            "allocation must be positive",
        ),
        (
            lambda payload: payload["positions"][0].update({"symbol": " "}),
            "position symbol is required",
        ),
        (
            lambda payload: payload["positions"][1].update({"symbol": "aaa"}),
            "position symbol AAA is duplicated",
        ),
        (
            lambda payload: payload.update({"margin_capital": -1}),
            "margin_capital must be positive, got -1",
        ),
        (
            lambda payload: payload.update({"declared_bias": "bullish"}),
            "unknown declared bias bullish",
        ),
        (
            lambda payload: payload.update({"instrument": "futures"}),
            "unknown instrument futures",
        ),
    ],
)
def test_portfolio_analysis_validation_errors(mutate, match):
    payload = portfolio_payload()
    mutate(payload)

    with pytest.raises(ValueError, match=match):
        service.get_portfolio_analysis(payload)
