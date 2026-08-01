import time
from datetime import datetime, timezone

from app.http_client import HttpClient

from . import chrome_cdp


_CDP_ENDPOINT = "http://127.0.0.1:9222"
_POLL_INTERVAL = 0.5
_PAGE_READY_TIMEOUT_SECONDS = 30


def _reauth(message):
    return {"status": "session_reauth_required", "message": message}


def _render_failed(message):
    return {"status": "render_failed", "message": message}


def _rendered_history_rows_expr():
    return """
(() => {
    const headers = (table) => [...table.querySelectorAll('th')]
        .map((th) => (th.textContent || '').trim());
    const matches = [...document.querySelectorAll('table')]
        .filter((table) => headers(table).includes('Date') && headers(table).includes('Price'));
    const table = matches.at(-1);
    if (!table) {
        return null;
    }
    const rows = [...table.querySelectorAll('tbody tr')].map((tr) => {
        const cells = [...tr.querySelectorAll('td')].map((td) => (td.textContent || '').trim());
        return [cells[0] || null, cells[1] || null];
    });
    if (rows.length === 0) {
        return null;
    }
    return rows;
})()
"""


def _wait_for_rendered_rows(cdp, timeout_seconds=_PAGE_READY_TIMEOUT_SECONDS):
    deadline = time.time() + timeout_seconds
    while True:
        rows = cdp.evaluate(_rendered_history_rows_expr())
        if rows:
            return rows
        if time.time() >= deadline:
            return None
        time.sleep(_POLL_INTERVAL)


def _load_investing_target(client, cdp_endpoint):
    targets, error = chrome_cdp.load_chrome_targets(client, cdp_endpoint)
    if error:
        return _reauth(error)
    target = chrome_cdp.find_page_target(targets, "www.investing.com")
    if target is None:
        return _reauth(
            f"No Investing.com page found in the Chrome session at {cdp_endpoint}. "
            "Start the dedicated Chrome with scripts/start_investing_chrome.py, "
            "open and verify an Investing.com method page, and leave it open."
        )
    return target


def _normalize_rendered_row(row):
    if isinstance(row, dict):
        return row.get("rowDate"), row.get("last_close")
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return row[0], row[1]
    return None, None


def _rendered_rows_payload(result, source_url):
    if not isinstance(result, list):
        return _render_failed(
            "could not find the Investing historical data table with Date and "
            f"Price columns on {source_url}"
        )
    if not result:
        return _render_failed(
            f"the Investing historical data table on {source_url} contained no rows"
        )
    rows = []
    for raw_row in result:
        row_date, last_close = _normalize_rendered_row(raw_row)
        if not row_date or not last_close:
            return _render_failed(
                f"the Investing historical data table on {source_url} "
                "contained a row with a blank date or price"
            )
        rows.append({"rowDate": row_date, "last_close": last_close})
    return {
        "status": "ok",
        "payload": {"data": rows},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_url": source_url,
    }


def fetch_rendered_investing_history(
    market,
    cdp_endpoint=_CDP_ENDPOINT,
    http_client=None,
    cdp_factory=chrome_cdp.ChromeCDP,
    timeout_seconds=_PAGE_READY_TIMEOUT_SECONDS,
):
    target = _load_investing_target(http_client or HttpClient(), cdp_endpoint)
    if target.get("status"):
        return target
    try:
        cdp = cdp_factory(target["webSocketDebuggerUrl"])
    except Exception as exc:
        return _reauth(
            f"WebSocket connection to the existing Investing.com page failed: {exc}; "
            "restart the dedicated Chrome with scripts/start_investing_chrome.py "
            "and leave the verified page open"
        )
    try:
        cdp.command("Page.navigate", {"url": market["price_page_url"]})
        result = _wait_for_rendered_rows(cdp, timeout_seconds)
    except ValueError as exc:
        return _render_failed(f"browser evaluation failed: {exc}")
    finally:
        cdp.close()
    return _rendered_rows_payload(result, market["price_page_url"])
