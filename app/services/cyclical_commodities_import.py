from pathlib import Path

from app.data_sources import cftc_cot
from app.data_sources import usd
from app.data_sources.fred import FredClient as _FredClient
from app.db import macro_indicators
from app.services import cot_historical_extremes_catalog as allowlist_service


def _parse_cot_zip(zip_path, year, code_registry=None):
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
    rows = cftc_cot.parse_disaggregated_futures_only(
        text, source_url, "", code_registry=code_registry
    )
    for r in rows:
        r["position_category"] = "managed_money"
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


def import_cached_official_commodities(con, cache_dir, years):
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


def _validate_cot_rows_against_allowlist(rows, active_entries):
    persisted = []
    for row in rows:
        entry = active_entries.get(row["commodity_id"])
        if entry is None:
            continue
        if row.get("cftc_contract_market_code") != entry["contract_code"]:
            raise ValueError(
                f"commodities cot {row['commodity_id']} contract market code "
                f"does not match the allowlist"
            )
        persisted.append(row)
    return persisted


def replace_cot_history(con, cache_dir, years, allowlist_path=None):
    cache_dir = Path(cache_dir)
    allowlist = allowlist_service.load_cot_historical_extreme_allowlist(
        allowlist_path or allowlist_service.DEFAULT_ALLOWLIST_PATH
    )
    active_entries = allowlist_service.active_allowlist_entries(allowlist)
    code_registry = {
        entry["contract_code"]: entry["commodity_id"]
        for entry in active_entries.values()
    }
    rows = []
    for year in years:
        zip_path = cache_dir / f"cftc-disaggregated-futures-only-{year}.zip"
        if not zip_path.exists():
            raise ValueError(f"missing cached cftc archive for {year}")
        rows.extend(_parse_cot_zip(zip_path, year, code_registry=code_registry))
    validated = _validate_cot_rows_against_allowlist(rows, active_entries)
    scope = sorted(active_entries)
    count = macro_indicators.replace_cot_history(con, validated, scope)
    ranges = {}
    for row in validated:
        entry = ranges.setdefault(
            row["commodity_id"],
            {"count": 0, "start": row["report_date"], "end": row["report_date"]},
        )
        entry["count"] += 1
        entry["start"] = min(entry["start"], row["report_date"])
        entry["end"] = max(entry["end"], row["report_date"])
    registry_commodities = set(cftc_cot.COT_COMMODITY_REGISTRY.values())
    inactive = sorted(registry_commodities - set(active_entries))
    return {
        "cot_observations": count,
        "usd_observations": 0,
        "ranges": {
            commodity_id: {
                "count": details["count"],
                "start": details["start"],
                "end": details["end"],
            }
            for commodity_id, details in sorted(ranges.items())
        },
        "inactive_commodities": inactive,
    }


def refresh_official_commodities(con, cache_dir, years, fred_client_factory=None):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetch_cot_zips(cache_dir, years)
    _fetch_fred_csvs(cache_dir, fred_client_factory)
    return import_cached_official_commodities(con, cache_dir, years)


def fetch_cot_archives(cache_dir, years):
    fetch_cot_zips(cache_dir, years)
    return [Path(cache_dir) / f"cftc-disaggregated-futures-only-{year}.zip" for year in years]


def fetch_usd_and_inflation_csvs(cache_dir, fred_client_factory=None):
    return _fetch_fred_csvs(cache_dir, fred_client_factory)
