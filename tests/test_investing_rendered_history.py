import httpx

from app.data_sources.investing_rendered_history import (
    _rendered_history_rows_expr,
    fetch_rendered_investing_history,
)


def market(**overrides):
    m = {
        "price_page_url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures",
        "display_name": "Iron Ore 62% CFR China",
    }
    m.update(overrides)
    return m


def cdp_targets_client(targets=None):
    if targets is None:
        targets = [
            {
                "type": "page",
                "url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
            }
        ]

    def handler(request):
        if request.url.path == "/json/version":
            return httpx.Response(
                200,
                json={"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"},
            )
        if request.url.path == "/json":
            return httpx.Response(200, json=targets)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


class _FakePageCDP:
    def __init__(self, url, rows):
        self.commands = []
        self.closed = False
        self._rows = rows

    def command(self, method, params=None):
        self.commands.append(method)
        return {}

    def evaluate(self, expression):
        if "document.readyState" in expression:
            return "complete"
        return self._rows

    def close(self):
        self.closed = True


def fake_page_cdp(rows):
    def factory(url):
        return _FakePageCDP(url, rows)

    return factory


def test_fetch_rendered_history_returns_default_table_rows():
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=fake_page_cdp(
            [["Jul 31, 2026", "98.00"], ["Jul 30, 2026", "98.25"]]
        ),
    )
    assert result["status"] == "ok"
    assert result["payload"]["data"] == [
        {"rowDate": "Jul 31, 2026", "last_close": "98.00"},
        {"rowDate": "Jul 30, 2026", "last_close": "98.25"},
    ]
    assert result["source_url"] == market()["price_page_url"]
    assert result["retrieved_at"]


def test_fetch_rendered_history_rejects_missing_history_table():
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=fake_page_cdp(None),
    )
    assert result["status"] == "render_failed"
    assert "historical data table" in result["message"]


def test_fetch_rendered_history_navigates_to_price_page_url():
    page = _FakePageCDP("ws://127.0.0.1:9222/devtools/page/1", [])
    fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
    )
    assert page.commands == ["Page.navigate"]
    assert page.closed


def test_fetch_rendered_history_returns_reauth_when_no_investing_page():
    client = cdp_targets_client(targets=[])
    result = fetch_rendered_investing_history(
        market(), http_client=client, cdp_factory=fake_page_cdp([])
    )
    assert result["status"] == "session_reauth_required"
    assert "No Investing.com page found" in result["message"]


def test_rendered_rows_expression_requires_date_and_price_headers():
    expression = _rendered_history_rows_expr()

    assert "Date" in expression
    assert "Price" in expression
    assert "tbody" in expression
