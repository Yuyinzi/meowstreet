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
