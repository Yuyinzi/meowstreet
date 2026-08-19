import pytest

from app.services import pair_analysis as service


def industry_context(symbol, sector):
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Inc",
        "status": "resolved",
        "sector": sector,
        "industry": "Some Industry",
        "cycle_tag": "cyclical",
    }


def market_payload(dates, closes):
    return {
        "symbol": "X",
        "metrics": {"price": closes[-1]},
        "prices": {"dates": dates, "adjusted_close": closes},
    }


LONG_DATES = ["2024-01-0%s" % day for day in range(1, 8)]
LONG_CLOSES = [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0]
SHORT_CLOSES = [20.0, 20.2, 20.1, 20.4, 20.3, 20.6, 20.5]


def stub_dependencies(monkeypatch):
    def fake_context(symbol, db_path=None, http_client=None):
        sector = "Information Technology" if symbol == "AAA" else "Consumer Staples"
        return industry_context(symbol, sector)

    def fake_market_data(symbol, **kwargs):
        closes = LONG_CLOSES if symbol == "AAA" else SHORT_CLOSES
        return market_payload(LONG_DATES, closes)

    monkeypatch.setattr(
        service.ticker_context_service, "get_ticker_industry_context", fake_context
    )
    monkeypatch.setattr(service.market_data, "fetch_market_data", fake_market_data)


def test_pair_analysis_assembles_full_payload(monkeypatch):
    stub_dependencies(monkeypatch)

    payload = service.get_pair_analysis("AAA", "BBB", sessions=5)

    assert payload["long"]["symbol"] == "AAA"
    assert payload["short"]["symbol"] == "BBB"
    assert payload["pair"]["pair_type"] == "cross_sector_constituent"
    assert payload["pair"]["retained_risks"] == ["sector", "stock"]
    assert payload["window"] == {
        "sessions": 5,
        "start_date": "2024-01-03",
        "end_date": "2024-01-07",
    }
    assert payload["outperformance"]["long_return"] == pytest.approx(13.0 / 11.0 - 1)
    assert payload["outperformance"]["short_return"] == pytest.approx(20.5 / 20.1 - 1)
    assert payload["outperformance"]["outperformance"] == pytest.approx(
        payload["outperformance"]["long_return"]
        - payload["outperformance"]["short_return"]
    )
    series = payload["series"]
    assert series["dates"] == LONG_DATES[-5:]
    assert len(series["ratio"]) == 5
    assert len(series["spread"]) == 5
    assert len(series["cew_index"]) == 5
    assert series["ratio"][0] == pytest.approx(11.0 / 20.1)
    assert series["cew_index"][0] == pytest.approx(series["ratio"][0])


def test_pair_analysis_same_sector_pair_is_intra_sector(monkeypatch):
    stub_dependencies(monkeypatch)

    payload = service.get_pair_analysis("AAA", "AAA", sessions=3)

    assert payload["pair"]["pair_type"] == "intra_sector_constituent"


def test_pair_analysis_caps_sessions_window(monkeypatch):
    stub_dependencies(monkeypatch)

    payload = service.get_pair_analysis("AAA", "BBB", sessions=999)

    assert payload["window"]["sessions"] == 7


def test_pair_analysis_rejects_invalid_sessions(monkeypatch):
    stub_dependencies(monkeypatch)

    with pytest.raises(ValueError, match="sessions abc is not a number"):
        service.get_pair_analysis("AAA", "BBB", sessions="abc")


def test_pair_analysis_propagates_market_data_errors(monkeypatch):
    def fake_context(symbol, db_path=None, http_client=None):
        return industry_context(symbol, "Information Technology")

    def fake_market_data(symbol, **kwargs):
        raise ValueError(f"market data fetch failed for {symbol}: HTTP 429 Too Many Requests")

    monkeypatch.setattr(
        service.ticker_context_service, "get_ticker_industry_context", fake_context
    )
    monkeypatch.setattr(service.market_data, "fetch_market_data", fake_market_data)

    with pytest.raises(ValueError, match="market data fetch failed for AAA"):
        service.get_pair_analysis("AAA", "BBB")
