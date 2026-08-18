from datetime import date
from pathlib import Path

from app.data_sources import nfib_sbet
from app.db import macro_indicators


DEFAULT_NFIB_SOURCE_URL = (
    "https://www.nfib.com/wp-content/uploads/2026/07/NFIB-June-2026-SBET-Report.pdf"
)
DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "local_system" / "nfib_cache"
)


def _latest_pdf_path(cache_dir):
    cache = Path(cache_dir)
    if not cache.exists():
        return None
    pdfs = sorted(cache.glob("nfib-sbet-*.pdf"))
    return pdfs[-1] if pdfs else None


def import_cached_official_sbet(con, cache_path, source_url, release_date=None):
    path = Path(cache_path)
    if not path.exists():
        raise ValueError(f"cache path does not exist: {cache_path}")
    payload = nfib_sbet.parse_sbet_report(str(path), source_url, release_date)
    result = macro_indicators.merge_macro_indicator_observations_batch(
        con, payload["observations"]
    )
    return result["observations"]


def refresh_official_sbet_history(con, cache_path, source_url, release_date=None):
    cache = Path(cache_path)
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / "nfib-sbet-current.pdf"
    nfib_sbet.fetch_sbet_report(str(dest), source_url)
    return import_cached_official_sbet(con, str(dest), source_url, release_date)


def _shift_month(year, month, delta):
    total = int(year) * 12 + int(month) - 1 + delta
    return total // 12, total % 12 + 1


def _guard_against_stale_report(observations, reference_date):
    today = reference_date or date.today()
    threshold = _shift_month(today.year, today.month, -2)
    latest = max(observation["date"] for observation in observations)
    latest_month = (int(latest[:4]), int(latest[5:7]))
    if latest_month < threshold:
        raise ValueError(
            f"nfib sbet: latest report is stale: max observation date {latest} "
            f"is before {threshold[0]:04d}-{threshold[1]:02d} month end"
        )


def import_latest_official_sbet(
    con, cache_dir, release_date=None, reference_date=None, http_client=None
):
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    source_url = nfib_sbet.discover_latest_sbet_url(
        reference_date=reference_date, http_client=http_client
    )
    report_year, report_month = nfib_sbet.report_month_from_url(source_url)
    dest = cache / f"nfib-sbet-{report_year:04d}-{report_month:02d}.pdf"
    nfib_sbet.fetch_sbet_report(str(dest), source_url, http_client=http_client)
    payload = nfib_sbet.parse_sbet_report(str(dest), source_url, release_date)
    _guard_against_stale_report(payload["observations"], reference_date)
    result = macro_indicators.merge_macro_indicator_observations_batch(
        con, payload["observations"]
    )
    return result["observations"]
