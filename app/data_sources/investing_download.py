import time
from datetime import datetime, timezone
from pathlib import Path

from app.http_client import HttpClient

from . import chrome_cdp


ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = ROOT / "data" / "private" / "investing_downloads"
_CDP_ENDPOINT = "http://127.0.0.1:9222"
_POLL_INTERVAL = 0.5
method_HISTORY_START_DATE = "2016-01-01"
_RANGE_REFRESH_TIMEOUT_SECONDS = 30


def _reauth(message):
    return {"status": "session_reauth_required", "message": message}


def _download_failed(message):
    return {"status": "download_failed", "message": message}


def _click_download_expr():
    return """
(() => {
    const anchor = [...document.querySelectorAll('a[download]')].find((el) =>
        /historical data\\.csv$/i.test(el.getAttribute('download') || '')
    );
    const trigger = anchor ? anchor.previousElementSibling : null;
    if (!trigger) {
        return {clicked: false};
    }
    trigger.click();
    return {
        clicked: true,
        tag: trigger.tagName,
        text: (trigger.textContent || '').trim().slice(0, 60),
    };
})()
"""


def _page_ready_expr():
    return "document.readyState"


def _download_anchor_href_expr():
    return """
(() => {
    const anchor = [...document.querySelectorAll('a[download]')].find((element) =>
        /historical data\\.csv$/i.test(element.getAttribute('download') || '')
    );
    return anchor?.href || null;
})()
"""


def _download_href_expr():
    return """
(() => {
    const anchor = [...document.querySelectorAll('a[download]')].find((element) =>
        /historical data\\.csv$/i.test(element.getAttribute('download') || '')
    );
    const href = anchor?.href || null;
    return href && href.startsWith('blob:') ? href : null;
})()
"""


def _set_method_history_range_expr(start_date):
    return f"""
(() => {{
    const controls = [...document.querySelectorAll('input[type=date]')];
    if (controls.length !== 2) {{
        return {{applied: false, reason: 'historical date controls unavailable'}};
    }}
    const [start, end] = controls;
    const endDate = end.max;
    if (!/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(endDate) || endDate < '{start_date}') {{
        return {{applied: false, reason: 'page did not expose a valid latest available date'}};
    }}
    const setValue = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype, 'value'
    ).set;
    for (const [control, value] of [[start, '{start_date}'], [end, endDate]]) {{
        setValue.call(control, value);
        control.dispatchEvent(new Event('input', {{bubbles: true}}));
        control.dispatchEvent(new Event('change', {{bubbles: true}}));
    }}
    const panel = start.closest('div.absolute');
    const apply = panel
        ? [...panel.querySelectorAll('div')].find(
            (element) => (element.textContent || '').trim() === 'Apply'
        )
        : null;
    if (!apply) {{
        return {{applied: false, reason: 'historical date range apply control unavailable'}};
    }}
    apply.click();
    return {{
        applied: true,
        start_date: start.value,
        end_date: end.value,
        range_text: (start.parentElement?.parentElement?.innerText || '').trim(),
    }};
}})()
"""


def _open_method_history_range_expr():
    return """
(() => {
    const pattern = /^\\d{2}\\/\\d{2}\\/\\d{4} - \\d{2}\\/\\d{2}\\/\\d{4}$/;
    const candidates = [...document.querySelectorAll('div')].filter((element) =>
        pattern.test((element.textContent || '').trim())
    );
    const trigger = candidates.at(-1);
    if (!trigger) {
        return {opened: false, reason: 'historical date range control unavailable'};
    }
    trigger.click();
    return {opened: true};
})()
"""


def _method_history_range_state_expr():
    return """
(() => {
    const controls = [...document.querySelectorAll('input[type=date]')];
    const rangeTexts = [...document.querySelectorAll('div')]
        .map((element) => (element.textContent || '').trim())
        .filter((text) => /^\\d{2}\\/\\d{2}\\/\\d{4} - \\d{2}\\/\\d{2}\\/\\d{4}$/.test(text));
    return {
        start_date: controls[0]?.value || null,
        end_date: controls[1]?.value || null,
        range_text: rangeTexts.at(-1) || null,
    };
})()
"""


def set_method_history_range(
    page_cdp,
    start_date=method_HISTORY_START_DATE,
    timeout_seconds=_RANGE_REFRESH_TIMEOUT_SECONDS,
):
    opened = page_cdp.evaluate(_open_method_history_range_expr())
    if not isinstance(opened, dict) or not opened.get("opened"):
        reason = opened.get("reason") if isinstance(opened, dict) else None
        return _download_failed(reason or "could not open historical date range")

    deadline = time.time() + timeout_seconds
    end_date = None
    expected_range_text = None
    while True:
        result = page_cdp.evaluate(_set_method_history_range_expr(start_date))
        if isinstance(result, dict) and result.get("applied"):
            end_date = result.get("end_date")
            if result.get("start_date") != start_date or not end_date:
                return _download_failed(
                    "page did not apply the requested historical date range"
                )
            expected_range_text = "{} - {}".format(
                datetime.strptime(start_date, "%Y-%m-%d").strftime("%m/%d/%Y"),
                datetime.strptime(end_date, "%Y-%m-%d").strftime("%m/%d/%Y"),
            )
        state = page_cdp.evaluate(_method_history_range_state_expr())
        if (
            isinstance(state, dict)
            and end_date is not None
            and state.get("range_text") == expected_range_text
        ):
            return {
                "status": "ok",
                "start_date": start_date,
                "end_date": end_date,
            }
        if time.time() >= deadline:
            break
        time.sleep(_POLL_INTERVAL)
    return _download_failed(
        f"page did not apply historical date range {start_date} to {end_date}"
    )


def wait_for_download_href(page_cdp, previous_href=None, timeout_seconds=60):
    deadline = time.time() + timeout_seconds
    while True:
        href = page_cdp.evaluate(_download_href_expr())
        if href and href != previous_href:
            return href
        if time.time() >= deadline:
            return None
        time.sleep(_POLL_INTERVAL)


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

        previous_download_href = page_cdp.evaluate(_download_anchor_href_expr())
        if previous_download_href is None:
            return _download_failed(
                f"Download Data control was not ready for {market['price_page_url']}"
            )

        range_result = set_method_history_range(page_cdp)
        if range_result["status"] != "ok":
            return range_result

        refreshed_download_href = wait_for_download_href(
            page_cdp,
            previous_href=previous_download_href,
            timeout_seconds=timeout_seconds,
        )
        if refreshed_download_href is None:
            return _download_failed(
                f"Download Data CSV did not refresh for {market['price_page_url']}"
            )

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
            "start_date": range_result["start_date"],
            "end_date": range_result["end_date"],
        }
    finally:
        if page_cdp:
            page_cdp.close()
        if browser_cdp:
            browser_cdp.close()
