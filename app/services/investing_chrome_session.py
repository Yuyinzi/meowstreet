from time import monotonic, sleep
from urllib.parse import urlparse

from app.data_sources import chrome_cdp, investing_chrome
from app.http_client import HttpClient


DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_READY_TIMEOUT_SECONDS = 60
_POLL_INTERVAL = 0.5


def ensure_investing_chrome(
    client=None,
    cdp_endpoint=DEFAULT_CDP_ENDPOINT,
    timeout_seconds=DEFAULT_READY_TIMEOUT_SECONDS,
):
    if timeout_seconds <= 0:
        raise ValueError("chrome readiness timeout must be positive")
    client = client or HttpClient(max_attempts=1)
    deadline = monotonic() + timeout_seconds
    targets, error = chrome_cdp.load_chrome_targets(
        client, cdp_endpoint, timeout=min(10, timeout_seconds)
    )
    if not error:
        return targets
    endpoint = urlparse(cdp_endpoint)
    if endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(f"remote chrome endpoint unavailable: {error}")
    try:
        investing_chrome.start_investing_chrome(
            cdp_port=endpoint.port or 9222, headless=False
        )
    except OSError as exc:
        raise ValueError(f"investing chrome startup failed: {exc}") from exc
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ValueError(
                f"Chrome CDP endpoint at {cdp_endpoint} did not become ready: {error}"
            )
        targets, error = chrome_cdp.load_chrome_targets(
            client, cdp_endpoint, timeout=min(10, remaining)
        )
        if not error:
            return targets
        sleep(min(_POLL_INTERVAL, max(0, deadline - monotonic())))
