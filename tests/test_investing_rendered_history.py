import httpx

from app.data_sources.tracked_commodities import MARKET_SERIES
from app.data_sources.investing_rendered_history import (
    _rendered_history_rows_expr,
    fetch_rendered_investing_history,
)


IRON_ORE_URL = (
    "https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data"
)
IRON_ORE_TITLE = "Iron ore fines 62% Fe CFR Futures Historical Prices - Investing.com"
LME_COPPER_URL = (
    "https://www.investing.com/commodities/copper-historical-data?cid=959211"
)
COPPER_TITLE = "Copper Futures Historical Prices - Investing.com"


def market(**overrides):
    m = {
        "price_page_url": IRON_ORE_URL,
        "display_name": "Iron Ore 62% CFR China",
        "instrument": "Iron Ore 62% Fe CFR China index",
    }
    m.update(overrides)
    return m


def cdp_targets_client(targets=None):
    if targets is None:
        targets = [
            {
                "type": "page",
                "url": IRON_ORE_URL,
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
    def __init__(self, url, rows, title=IRON_ORE_TITLE):
        self.commands = []
        self.closed = False
        self._rows = rows
        self._title = title
        self._href = None

    def command(self, method, params=None):
        self.commands.append(method)
        if method == "Page.navigate":
            self._href = params["url"]
        return {}

    def evaluate(self, expression):
        if "location.href" in expression:
            return self._href
        if "document.title" in expression:
            return self._title
        return self._rows

    def close(self):
        self.closed = True


def fake_page_cdp(rows):
    def factory(url):
        return _FakePageCDP(url, rows)

    return factory


class _TransitionPageCDP:
    def __init__(self, old_url, old_rows, new_url, new_rows, title=IRON_ORE_TITLE):
        self.commands = []
        self.closed = False
        self._old_url = old_url
        self._old_rows = old_rows
        self._new_url = new_url
        self._new_rows = new_rows
        self._title = title
        self._committed = False

    def command(self, method, params=None):
        self.commands.append(method)
        return {}

    def evaluate(self, expression):
        if "location.href" in expression:
            href = self._new_url if self._committed else self._old_url
            self._committed = True
            return href
        if "document.title" in expression:
            return self._title
        return self._new_rows if self._committed else self._old_rows

    def close(self):
        self.closed = True


class _WrongTitlePageCDP:
    def __init__(self, url, rows, title):
        self.commands = []
        self.closed = False
        self._href = url
        self._rows = rows
        self._title = title

    def command(self, method, params=None):
        self.commands.append(method)
        return {}

    def evaluate(self, expression):
        if "location.href" in expression:
            return self._href
        if "document.title" in expression:
            return self._title
        return self._rows

    def close(self):
        self.closed = True


class _ProgressivelyRenderingPageCDP(_FakePageCDP):
    def __init__(self, url, rows):
        super().__init__(url, rows)
        self._rendered = False

    def evaluate(self, expression):
        if "location.href" in expression:
            return self._href
        if "document.title" in expression:
            return self._title
        if not self._rendered:
            self._rendered = True
            return [["Jul 31, 2026", ""], ["Jul 30, 2026", "98.25"]]
        return self._rows


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
        timeout_seconds=0,
    )
    assert result["status"] == "render_failed"
    assert "historical data table" in result["message"]


def test_fetch_rendered_history_navigates_to_price_page_url():
    page = _FakePageCDP(
        "ws://127.0.0.1:9222/devtools/page/1", [["Jul 31, 2026", "98.00"]]
    )
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
    )
    assert page.commands == ["Page.navigate"]
    assert page.closed
    assert result["status"] == "ok"


def test_fetch_rendered_history_returns_reauth_when_no_investing_page():
    client = cdp_targets_client(targets=[])
    result = fetch_rendered_investing_history(
        market(), http_client=client, cdp_factory=fake_page_cdp([])
    )
    assert result["status"] == "session_reauth_required"
    assert "No Investing.com page found" in result["message"]


def test_fetch_rendered_history_waits_for_navigation_before_reading_table():
    page = _TransitionPageCDP(
        old_url="https://www.investing.com/commodities/copper-historical-data",
        old_rows=[["Jul 30, 2026", "4.50"]],
        new_url=IRON_ORE_URL,
        new_rows=[["Jul 31, 2026", "98.00"], ["Jul 30, 2026", "98.25"]],
    )
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
    )
    assert result["status"] == "ok"
    assert result["payload"]["data"] == [
        {"rowDate": "Jul 31, 2026", "last_close": "98.00"},
        {"rowDate": "Jul 30, 2026", "last_close": "98.25"},
    ]


def test_fetch_rendered_history_rejects_stale_page_before_navigation_commits():
    page = _TransitionPageCDP(
        old_url="https://www.investing.com/commodities/copper-historical-data",
        old_rows=[["Jul 30, 2026", "4.50"]],
        new_url=IRON_ORE_URL,
        new_rows=[["Jul 31, 2026", "98.00"]],
    )
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
        timeout_seconds=0,
    )
    assert result["status"] == "render_failed"


def test_fetch_rendered_history_rejects_wrong_market_title():
    page = _WrongTitlePageCDP(
        IRON_ORE_URL,
        [["Jul 31, 2026", "98.00"]],
        "Copper Futures Historical Prices - Investing.com",
    )
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
        timeout_seconds=0,
    )
    assert result["status"] == "render_failed"
    assert "market title" in result["message"]


def test_fetch_rendered_history_accepts_lme_copper_generic_page_title():
    lme_market = MARKET_SERIES["copper_lme"]
    page = _FakePageCDP(
        "ws://127.0.0.1:9222/devtools/page/1",
        [["Jul 31, 2026", "13,803.00"]],
        title=COPPER_TITLE,
    )

    result = fetch_rendered_investing_history(
        lme_market,
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
        timeout_seconds=0,
    )

    assert result["status"] == "ok"
    assert result["payload"]["data"] == [
        {"rowDate": "Jul 31, 2026", "last_close": "13,803.00"}
    ]


def test_fetch_rendered_history_waits_for_fully_populated_rows():
    page = _ProgressivelyRenderingPageCDP(
        "ws://127.0.0.1:9222/devtools/page/1",
        [["Jul 31, 2026", "98.00"], ["Jul 30, 2026", "98.25"]],
    )
    result = fetch_rendered_investing_history(
        market(),
        http_client=cdp_targets_client(),
        cdp_factory=lambda url: page,
    )
    assert result["status"] == "ok"
    assert result["payload"]["data"] == [
        {"rowDate": "Jul 31, 2026", "last_close": "98.00"},
        {"rowDate": "Jul 30, 2026", "last_close": "98.25"},
    ]


def test_rendered_rows_expression_requires_date_and_price_headers():
    expression = _rendered_history_rows_expr()

    assert "Date" in expression
    assert "Price" in expression
    assert "tbody" in expression
