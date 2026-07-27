from pathlib import Path

from app.data_sources import nfib_sbet
from app.db import macro_indicators


DEFAULT_NFIB_SOURCE_URL = "https://www.nfib.com/sbet/june-2026"
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
