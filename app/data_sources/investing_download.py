import time
from datetime import datetime, timezone
from pathlib import Path

from app.http_client import HttpClient

from . import chrome_cdp


ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = ROOT / "data" / "private" / "investing_downloads"
_CDP_ENDPOINT = "http://127.0.0.1:9222"
_POLL_INTERVAL = 0.5


def _reauth(message):
    return {"status": "session_reauth_required", "message": message}


def _download_failed(message):
    return {"status": "download_failed", "message": message}


def _click_download_expr():
    return """
(() => {
    const candidates = document.querySelectorAll('a, button, span, div');
    for (const el of candidates) {
        const text = (el.textContent || '').trim().toLowerCase();
        if (text.includes('download data')) {
            el.click();
            return {clicked: true, tag: el.tagName, text: el.textContent.trim().slice(0, 60)};
        }
    }
    return {clicked: false};
})()
"""


def _page_ready_expr():
    return "document.readyState"


def wait_for_completed_csv(download_dir, before_names, timeout_seconds=60):
    deadline = time.time() + timeout_seconds
    while True:
        current_names = {p.name for p in download_dir.iterdir()}
        new_names = current_names - before_names
        csv_names = {n for n in new_names if n.lower().endswith(".csv")}
        crdownload_names = {
            n for n in current_names if n.lower().endswith(".crdownload")
        }
        if csv_names and not crdownload_names:
            candidate = download_dir / list(csv_names)[0]
            size1 = candidate.stat().st_size
            time.sleep(_POLL_INTERVAL)
            if candidate.exists():
                size2 = candidate.stat().st_size
                if size2 == size1 and size2 > 0:
                    return candidate
        if time.time() >= deadline:
            break
        time.sleep(_POLL_INTERVAL)
    return None


def download_commodity_csv(
    market,
    cdp_endpoint=None,
    http_client=None,
    browser_cdp_factory=chrome_cdp.ChromeCDP,
    page_cdp_factory=chrome_cdp.ChromeCDP,
    download_dir=None,
    timeout_seconds=60,
):
    endpoint = cdp_endpoint or _CDP_ENDPOINT
    dl_dir = Path(download_dir or DOWNLOAD_DIR)
    dl_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    client = http_client or HttpClient()

    page_cdp = None
    browser_cdp = None
    try:
        version_payload, error = chrome_cdp.load_chrome_version(client, endpoint)
        if error:
            return _reauth(error)
        browser_ws = chrome_cdp.find_browser_target(version_payload)
        if not browser_ws:
            return _reauth(
                f"Chrome CDP endpoint at {endpoint} did not return a browser websocket URL; "
                "restart Chrome with --remote-debugging-port"
            )

        targets, error = chrome_cdp.load_chrome_targets(client, endpoint)
        if error:
            return _reauth(error)
        target = chrome_cdp.find_page_target(targets, "www.investing.com")
        if target is None:
            return _reauth(
                f"No Investing.com page found in the Chrome session at {endpoint}. "
                "Start the dedicated Chrome with scripts/start_investing_chrome.py, "
                "open and verify an Investing.com method page, and leave it open."
            )

        browser_cdp = browser_cdp_factory(browser_ws)
        browser_cdp.command(
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(dl_dir.resolve())},
        )

        page_cdp = page_cdp_factory(target["webSocketDebuggerUrl"])
        page_cdp.command("Page.navigate", {"url": market["price_page_url"]})

        ready = page_cdp.evaluate(_page_ready_expr())
        if ready != "complete":
            for _ in range(20):
                time.sleep(0.5)
                ready = page_cdp.evaluate(_page_ready_expr())
                if ready == "complete":
                    break

        before_names = {p.name for p in dl_dir.iterdir()}

        click_result = page_cdp.evaluate(_click_download_expr())
        if not isinstance(click_result, dict) or not click_result.get("clicked"):
            return _download_failed(
                f"Could not find Download Data control on {market['price_page_url']}"
            )

        csv_path = wait_for_completed_csv(dl_dir, before_names, timeout_seconds)
        if csv_path is None:
            return _download_failed(
                f"Download timed out after {timeout_seconds}s for {market['price_page_url']}; "
                "no new CSV appeared in the download directory"
            )

        return {
            "status": "ok",
            "csv_path": csv_path,
            "source_url": market["price_page_url"],
            "retrieved_at": retrieved_at,
        }
    finally:
        if page_cdp:
            page_cdp.close()
        if browser_cdp:
            browser_cdp.close()
