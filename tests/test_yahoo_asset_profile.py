import httpx
import pytest

from app.data_sources import yahoo_asset_profile
from app.http_client import HttpClient


def quote_page_html():
    return (
        "<html><body>"
        '<h1 class="heading yf-ndxd9a">NVIDIA Corporation (NVDA)</h1>'
        '<p title="Technology" class="yf-oynzgn"><a href="/sectors/technology/">Technology</a></p>'
        " <h3>Sector</h3>"
        '<p title="Semiconductors" class="yf-oynzgn"><a href="/sectors/technology/semiconductors/">Semiconductors</a></p>'
        " <h3>Industry</h3>"
        "</body></html>"
    )


def etf_page_html():
    return (
        "<html><body>"
        '<h1 class="heading yf-ndxd9a">State Street SPDR S&amp;P 500 ETF Trust (SPY)</h1>'
        "</body></html>"
    )


def mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_fetch_asset_profile_requests_quote_page_with_browser_headers():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(200, text=quote_page_html())

    profile = yahoo_asset_profile.fetch_asset_profile(
        " nvda ", http_client=mock_client(handler)
    )

    assert seen["url"] == "https://finance.yahoo.com/quote/NVDA/"
    assert "Mozilla" in seen["user_agent"]
    assert profile == {
        "symbol": "NVDA",
        "company_name": "NVIDIA Corporation",
        "provider": "yahoo",
        "provider_sector": "Technology",
        "provider_industry": "Semiconductors",
    }


def test_fetch_asset_profile_unescapes_html_entities():
    def handler(request):
        return httpx.Response(200, text=etf_page_html())

    profile = yahoo_asset_profile.fetch_asset_profile(
        "SPY", http_client=mock_client(handler)
    )

    assert profile["company_name"] == "State Street SPDR S&P 500 ETF Trust"
    assert profile["provider_sector"] is None
    assert profile["provider_industry"] is None


def test_fetch_asset_profile_raises_on_404():
    def handler(request):
        return httpx.Response(404, text="Not Found")

    with pytest.raises(ValueError, match="asset profile fetch failed for NOPE: HTTP 404"):
        yahoo_asset_profile.fetch_asset_profile("NOPE", http_client=mock_client(handler))


def test_fetch_asset_profile_raises_when_heading_missing():
    def handler(request):
        return httpx.Response(200, text="<html><body>unexpected</body></html>")

    with pytest.raises(ValueError, match="asset profile unavailable for NVDA"):
        yahoo_asset_profile.fetch_asset_profile("NVDA", http_client=mock_client(handler))


def test_fetch_asset_profile_requires_symbol():
    with pytest.raises(ValueError, match="symbol is required"):
        yahoo_asset_profile.fetch_asset_profile("   ")


def fundamentals_page_html():
    return (
        '<html><body>"'
        '"forwardPE":{"raw":16.336937,"fmt":"16.34"},'
        '"forwardEps":{"raw":13.041,"fmt":"13.04"},'
        '"trailingEps":{"raw":6.67,"fmt":"6.67"},'
        '"marketCap":{"raw":5.16e12,"fmt":"5.16T"},'
        '"sharesShort":{"raw":292667375,"fmt":"292.67M"},'
        '"shortRatio":{"raw":2.23,"fmt":"2.23"},'
        '"shortPercentOfFloat":{"raw":0.0126,"fmt":"1.26%"},'
        '"dividendYield":{"raw":0.0048,"fmt":"0.48%"},'
        '"debtToEquity":{"raw":6.555,"fmt":"6.55%"},'
        '"currentRatio":{"raw":3.441,"fmt":"3.44"},'
        '"quickRatio":{"raw":2.139,"fmt":"2.14"},'
        '"returnOnEquity":{"raw":1.14288,"fmt":"114.29%"},'
        '"returnOnAssets":{"raw":0.52727,"fmt":"52.73%"},'
        '"bookValue":{"raw":8.07,"fmt":"8.07"},'
        '"totalDebt":{"raw":12.814e9,"fmt":"12.81B"},'
        '"totalCash":{"raw":53.17e9,"fmt":"53.17B"},'
        '"freeCashflow":{"raw":46.34e9,"fmt":"46.34B"},'
        '"enterpriseValue":{"raw":5.116e12,"fmt":"5.12T"},'
        '"ebitda":{"raw":165.5e9,"fmt":"165.5B"}'
        "</body></html>"
    )


def fundamentals_partial_html():
    return (
        '<html><body>"'
        '"forwardPE":{"raw":16.336937,"fmt":"16.34"},'
        '"marketCap":{"raw":5.16e12,"fmt":"5.16T"}'
        "</body></html>"
    )


def test_parse_quote_fundamentals_extracts_all_fields():
    result = yahoo_asset_profile.parse_quote_fundamentals(fundamentals_page_html())

    assert result["provider"] == "yahoo"
    assert result["forward_pe"] == pytest.approx(16.336937)
    assert result["forward_eps"] == pytest.approx(13.041)
    assert result["trailing_eps"] == pytest.approx(6.67)
    assert result["market_cap"] == pytest.approx(5.16e12)
    assert result["shares_short"] == pytest.approx(292667375)
    assert result["short_ratio"] == pytest.approx(2.23)
    assert result["short_percent_of_float"] == pytest.approx(0.0126)
    assert result["dividend_yield"] == pytest.approx(0.0048)
    assert result["debt_to_equity"] == pytest.approx(6.555)
    assert result["current_ratio"] == pytest.approx(3.441)
    assert result["quick_ratio"] == pytest.approx(2.139)
    assert result["return_on_equity"] == pytest.approx(1.14288)
    assert result["return_on_assets"] == pytest.approx(0.52727)
    assert result["book_value"] == pytest.approx(8.07)
    assert result["total_debt"] == pytest.approx(12.814e9)
    assert result["total_cash"] == pytest.approx(53.17e9)
    assert result["free_cashflow"] == pytest.approx(46.34e9)
    assert result["enterprise_value"] == pytest.approx(5.116e12)
    assert result["ebitda"] == pytest.approx(165.5e9)


def test_parse_quote_fundamentals_tolerates_missing_fields():
    result = yahoo_asset_profile.parse_quote_fundamentals(fundamentals_partial_html())

    assert result["forward_pe"] == pytest.approx(16.336937)
    assert result["market_cap"] == pytest.approx(5.16e12)
    assert result["forward_eps"] is None
    assert result["shares_short"] is None
    assert result["provider"] == "yahoo"


def test_parse_quote_fundamentals_tolerates_escaped_json():
    html = (
        '<html><body>\\"forwardPE\\":{\\"raw\\":20.5,\\"fmt\\":\\"20.5\\"}'
        "</body></html>"
    )
    result = yahoo_asset_profile.parse_quote_fundamentals(html)
    assert result["forward_pe"] == pytest.approx(20.5)


def test_fetch_quote_fundamentals_requests_quote_page():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, text=fundamentals_partial_html())

    result = yahoo_asset_profile.fetch_quote_fundamentals(
        " nvda ", http_client=mock_client(handler)
    )

    assert seen["url"] == "https://finance.yahoo.com/quote/NVDA/"
    assert result["forward_pe"] == pytest.approx(16.336937)


def test_fetch_quote_fundamentals_raises_on_http_error():
    def handler(request):
        return httpx.Response(500, text="Internal Server Error")

    with pytest.raises(ValueError, match="asset profile fetch failed for NVDA: HTTP 500"):
        yahoo_asset_profile.fetch_quote_fundamentals("NVDA", http_client=mock_client(handler))


def test_fetch_quote_fundamentals_requires_symbol():
    with pytest.raises(ValueError, match="symbol is required"):
        yahoo_asset_profile.fetch_quote_fundamentals("   ")


def test_fetch_quote_fundamentals_raises_when_no_fields_parse():
    def handler(request):
        return httpx.Response(200, text="<html><body>consent wall</body></html>")

    with pytest.raises(ValueError, match="quote fundamentals unavailable for NVDA"):
        yahoo_asset_profile.fetch_quote_fundamentals("NVDA", http_client=mock_client(handler))
