import fcntl
import time
from pathlib import Path

from app.data_sources import chrome_cdp, investing_chrome
from app.data_sources.tracked_commodities import ACTIVE_MARKET_SERIES
from app.http_client import HttpClient
from app.services import tracked_commodities_import


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_PROFILE_DIR = ROOT / "data" / "private" / "investing_chrome_profile"
DEFAULT_CDP_PORT = 9223
DEFAULT_LOCK_PATH = (
    ROOT / "data" / "local_system" / "investing_rendered_refresh.lock"
)
DEFAULT_READY_TIMEOUT_SECONDS = 60

_POLL_INTERVAL = 0.5
_REFRESH_MARKET = "iron_ore_62_cfr_china"


def _acquire_lock(lock_path):
    lock_path = Path(lock_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(lock_path, "w")
    except OSError as exc:
        raise ValueError(
            f" investing rendered refresh cannot create lock file {lock_path}: {exc}"
        ) from exc
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        raise ValueError(" investing rendered refresh already running (lock held)")
    return lock_file


def _release_lock(lock_file):
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
    finally:
        lock_file.close()


def _wait_for_cdp(client, cdp_endpoint, timeout_seconds):
    deadline = time.time() + timeout_seconds
    last_error = None
    while True:
        targets, error = chrome_cdp.load_chrome_targets(client, cdp_endpoint)
        if not error:
            return targets
        last_error = error
        if time.time() >= deadline:
            raise ValueError(
                f"Chrome CDP endpoint at {cdp_endpoint} did not become ready: {last_error}"
            )
        time.sleep(_POLL_INTERVAL)


def refresh_investing_rendered(
    con,
    profile_dir=None,
    cdp_port=DEFAULT_CDP_PORT,
    lock_path=DEFAULT_LOCK_PATH,
    readiness_timeout=DEFAULT_READY_TIMEOUT_SECONDS,
    http_client=None,
    start_chrome=investing_chrome.start_investing_chrome,
    wait_for_cdp=_wait_for_cdp,
    importer=tracked_commodities_import.import_commodity_browser_rows,
):
    lock_file = _acquire_lock(lock_path)
    proc = None
    effective_profile = profile_dir or DEFAULT_PROFILE_DIR
    endpoint = f"http://127.0.0.1:{cdp_port}"
    try:
        try:
            proc = start_chrome(
                profile_dir=effective_profile,
                cdp_port=cdp_port,
                headless=True,
                initial_url=ACTIVE_MARKET_SERIES[_REFRESH_MARKET]["price_page_url"],
            )
        except OSError as exc:
            raise ValueError(
                f"failed to start headless Chrome with profile {effective_profile}: {exc}"
            ) from exc
        client = http_client or HttpClient()
        wait_for_cdp(client, endpoint, readiness_timeout)
        importer_result = importer(
            con,
            markets=[_REFRESH_MARKET],
            cdp_endpoint=endpoint,
        )
        return {
            **importer_result,
            "status": "ok",
            "cdp_endpoint": endpoint,
            "profile_dir": str(effective_profile),
        }
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait()
        _release_lock(lock_file)
