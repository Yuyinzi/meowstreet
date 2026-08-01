from datetime import datetime, timezone
from pathlib import Path

from app.http_client import HttpClient

from . import chrome_cdp


ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_PROFILE = ROOT / "data" / "private" / "investing_chrome_profile"
_DEFAULT_CDP_PORT = 9222
_DEFAULT_CDP_ENDPOINT = f"http://127.0.0.1:{_DEFAULT_CDP_PORT}"
_DEFAULT_INITIAL_URL = "https://www.investing.com/commodities/copper-historical-data"

_YEAR_RANGES = [
    (f"{y}-01-01", f"{min(y + 4, 2099)}-12-31") for y in range(1900, 2100, 5)
]


def _reauth(message):
    return {"status": "session_reauth_required", "message": message}


def _build_api_url(market, start_date, end_date):
    instrument_id = market.get("instrument_id")
    return (
        f"https://api.investing.com/api/financialdata/historical/{instrument_id}"
        f"?start-date={start_date}"
        f"&end-date={end_date}"
        f"&time-frame=Daily"
        f"&add-missing-rows=false"
    )


def _js_fetch_expr(api_url):
    return f"""
(async () => {{
    const response = await fetch("{api_url}", {{
        method: "GET",
        credentials: "include",
        headers: {{
            "accept": "application/json, text/plain, */*",
            "domain-id": "www"
        }}
    }});
    const text = await response.text();
    return {{
        status: response.status,
        contentType: response.headers.get("content-type"),
        body: text
    }};
}})()
"""


def _parse_fetch_result(result, api_url, retrieved_at):
    if not isinstance(result, dict):
        return _reauth(
            f"Investing API {api_url} returned unexpected response type; "
            "session may require re-verification"
        )
    status = result.get("status")
    body = result.get("body", "")
    content_type = result.get("contentType", "")
    if status != 200:
        return _reauth(
            f"Investing API {api_url} returned HTTP {status}; "
            "session may require re-verification"
        )
    if "json" not in content_type.lower():
        return _reauth(
            f"Investing API {api_url} returned {content_type} instead of JSON; "
            "session may require re-verification"
        )
    import json as json_mod

    try:
        payload = json_mod.loads(body)
    except Exception:
        return _reauth(
            f"Investing API {api_url} returned invalid JSON body; "
            "session may require re-verification"
        )
    return {"status": "ok", "payload": payload}


def _fetch_single_range(cdp, market, start_date, end_date, retrieved_at):
    api_url = _build_api_url(market, start_date, end_date)
    expr = _js_fetch_expr(api_url)
    try:
        result = cdp.evaluate(expr)
    except ValueError as exc:
        return _reauth(f"JavaScript fetch for {api_url} failed: {exc}")
    parsed = _parse_fetch_result(result, api_url, retrieved_at)
    if parsed.get("status") != "ok":
        return parsed
    data = parsed["payload"].get("data", [])
    if not data:
        return {"status": "no_data_range", "range": f"{start_date} to {end_date}"}
    return {"status": "ok", "payload": parsed["payload"]}


def _find_chrome():
    import shutil

    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome",
        "google-chrome-stable",
        "google-chrome-beta",
    ]
    for path in candidates:
        if Path(path).exists() or shutil.which(path):
            return path
    raise ValueError(
        "Chrome not found; install Google Chrome or set PATH to its executable"
    )


def _validate_cdp_port(cdp_port):
    try:
        port = int(cdp_port)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid cdp port: {cdp_port}") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"invalid cdp port: {cdp_port}")
    return port


def start_investing_chrome(
    profile_dir=None,
    cdp_port=_DEFAULT_CDP_PORT,
    headless=False,
    initial_url=_DEFAULT_INITIAL_URL,
):
    import subprocess

    cdp_port = _validate_cdp_port(cdp_port)
    chrome = _find_chrome()
    profile = Path(profile_dir or _DEFAULT_PROFILE)
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        chrome,
        f"--remote-debugging-port={cdp_port}",
        f"--remote-allow-origins=http://127.0.0.1:{cdp_port}",
        f"--user-data-dir={profile}",
    ]
    if headless:
        command.append("--headless=new")
    command.append(initial_url)
    proc = subprocess.Popen(
        command,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Chrome at: {chrome}")
    print(f"Profile: {profile}")
    print(f"CDP endpoint: http://127.0.0.1:{cdp_port}")
    if not headless:
        print(
            "Complete any Investing.com verification in the Chrome window, "
            "then run the import command with the same --cdp-endpoint."
        )
    return proc


def fetch_investing_history(
    market,
    start_date=None,
    end_date=None,
    cdp_endpoint=_DEFAULT_CDP_ENDPOINT,
    http_client=None,
    cdp_factory=chrome_cdp.ChromeCDP,
):
    retrieved_at = datetime.now(timezone.utc).isoformat()
    client = http_client or HttpClient()
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
    try:
        cdp = cdp_factory(target["webSocketDebuggerUrl"])
    except Exception as exc:
        return _reauth(
            f"WebSocket connection to the existing Investing.com page failed: {exc}; "
            "restart the dedicated Chrome with scripts/start_investing_chrome.py "
            "and leave the verified page open"
        )
    try:
        requested_start = start_date or "1900-01-01"
        requested_end = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_data = []
        for seg_start, seg_end in _YEAR_RANGES:
            seg_start = max(seg_start, requested_start)
            seg_end = min(seg_end, requested_end)
            if seg_start >= seg_end:
                continue
            result = _fetch_single_range(cdp, market, seg_start, seg_end, retrieved_at)
            if result.get("status") == "session_reauth_required":
                return result
            if result.get("status") == "no_data_range":
                continue
            if result.get("status") == "ok":
                all_data.extend(result["payload"].get("data", []))
        if not all_data:
            return _reauth(
                f"Investing API returned no data for {market.get('price_page_url')} "
                f"({requested_start} to {requested_end}); "
                "session may require re-verification"
            )
        seen = set()
        deduped = []
        for row in all_data:
            date_key = row.get("rowDate", "")
            if date_key and date_key not in seen:
                seen.add(date_key)
                deduped.append(row)
        return {
            "status": "ok",
            "payload": {"data": deduped},
            "retrieved_at": retrieved_at,
        }
    finally:
        cdp.close()
