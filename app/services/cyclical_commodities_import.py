from pathlib import Path

from app.data_sources import cftc_cot
from app.data_sources import usd
from app.data_sources.fred import FredClient as _FredClient
from app.db import macro_indicators


def _parse_cot_zip(zip_path, year):
    import hashlib
    import io
    import zipfile
    from datetime import datetime, timedelta

    data = Path(zip_path).read_bytes()
    source_url = cftc_cot.historical_report_url(year)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        txt_name = None
        for name in zf.namelist():
            if name.endswith(".txt"):
                txt_name = name
                break
        if txt_name is None:
            raise ValueError(f"no txt file in cftc zip for {year}")
        text = zf.read(txt_name).decode("utf-8", errors="replace")
    rows = cftc_cot.parse_disaggregated_futures_only(text, source_url, "")
    for r in rows:
        try:
            report_dt = datetime.strptime(r["report_date"], "%Y-%m-%d")
            r["publication_date"] = (report_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            r["publication_date_basis"] = "estimated: report_date_plus_3_calendar_days"
        except (ValueError, TypeError):
            r["publication_date"] = ""
            r["publication_date_basis"] = "unavailable"
    return rows


def _import_cot_years(con, cache_dir, years):
    cache_dir = Path(cache_dir)
    total = 0
    for year in years:
        zip_path = cache_dir / f"cftc-disaggregated-futures-only-{year}.zip"
        if not zip_path.exists():
            continue
        rows = _parse_cot_zip(zip_path, year)
        macro_indicators.merge_cot_observations(con, rows)
        total += len(rows)
    return total


def _import_usd_observations(con, cache_dir):
    parsed = usd.parse_usd_csvs(cache_dir)
    total = 0
    for series_id in list(usd.USD_SERIES.values()) + list(
        usd.INFLATION_SERIES.values()
    ):
        id, title = series_id
        payload = parsed.get(id)
        if payload is None or not payload.get("observations"):
            continue
        series = {
            "series_id": id,
            "title": title,
            "units": payload.get("units", "index"),
            "source": "fred",
        }
        macro_indicators.merge_macro_indicator_observations(
            con, series, payload["observations"]
        )
        total += len(payload["observations"])
    return total


def _fred_cache_dir(cache_dir):
    return Path(cache_dir)


def _fetch_fred_csvs(cache_dir, fred_client_factory=None):
    fred = (fred_client_factory or _FredClient)(_fred_cache_dir(cache_dir))
    series_ids = list(usd.USD_SERIES) + list(usd.INFLATION_SERIES)
    fred.fetch_csvs(series_ids)
    return series_ids


def fetch_cot_zips(cache_dir, years):
    cache_dir = Path(cache_dir)
    for year in years:
        cftc_cot.fetch_historical_report(year, cache_dir)


def import_cached_official_(con, cache_dir, years):
    cot_count = _import_cot_years(con, cache_dir, years)
    usd_count = _import_usd_observations(con, cache_dir)
    return {
        "cot_observations": cot_count,
        "usd_observations": usd_count,
    }


def import_cached_official_cot_only(con, cache_dir, years):
    cot_count = _import_cot_years(con, cache_dir, years)
    return {"cot_observations": cot_count, "usd_observations": 0}


def import_cached_official_usd_only(con, cache_dir):
    usd_count = _import_usd_observations(con, cache_dir)
    return {"cot_observations": 0, "usd_observations": usd_count}


def refresh_official_(con, cache_dir, years, fred_client_factory=None):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetch_cot_zips(cache_dir, years)
    _fetch_fred_csvs(cache_dir, fred_client_factory)
    return import_cached_official_(con, cache_dir, years)
