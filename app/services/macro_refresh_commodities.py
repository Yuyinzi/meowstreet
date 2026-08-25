from datetime import date
from datetime import timedelta
from pathlib import Path
import tempfile

from app.data_sources import cftc_cot
from app.data_sources import oil
from app.data_sources import usd
from app.data_sources.fred import FredClient
from app.db import macro_indicators
from app.services import cyclical_commodities_import
from app.services import dce_iron_ore_sina_import
from app.services import shfe_copper_import
from app.services import tracked_commodities_import


TRACKED_ARTIFACT = "commodities.tracked"
CFTC_ARTIFACT = "commodities.cftc"
CYCLICAL_FRED_ARTIFACT = "commodities.cyclical_fred"
OIL_ARTIFACT = "commodities.oil"
SHFE_ARTIFACT = "commodities.shfe"
DCE_ARTIFACT = "commodities.dce_sina"


def _put(artifacts, key, value):
    if hasattr(artifacts, "put"):
        artifacts.put(key, value)
    else:
        artifacts[key] = value


def _get(artifacts, key):
    if hasattr(artifacts, "get"):
        return artifacts.get(key)
    if key not in artifacts:
        raise ValueError(f"macro refresh artifact is missing: {key}")
    return artifacts[key]


def _bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, Path):
        return value.read_bytes()
    if isinstance(value, str):
        path = Path(value)
        if path.exists():
            return path.read_bytes()
        return value.encode("utf-8")
    raise ValueError(f"macro refresh artifact has unsupported value: {type(value).__name__}")


def fetch_tracked_commodities(
    artifacts,
    *,
    fetcher=None,
    start_date=None,
    end_date=None,
    markets=None,
    cdp_endpoint=None,
):
    fetch = fetcher or tracked_commodities_import._browser_fetcher
    payload = fetch(
        start_date=start_date,
        end_date=end_date,
        markets=markets,
        cdp_endpoint=cdp_endpoint,
    )
    _put(artifacts, TRACKED_ARTIFACT, payload)
    return {"artifact_key": TRACKED_ARTIFACT, "series": len(payload), "payload": payload}


def persist_tracked_commodities(db_path, artifacts):
    payload = _get(artifacts, TRACKED_ARTIFACT)
    con = macro_indicators.connect(db_path)
    try:
        series_count = 0
        observation_count = 0
        for series_id, item in payload.items():
            macro_indicators.merge_macro_indicator_observations(
                con, item["series"], item["observations"], commit=False
            )
            series_count += 1
            observation_count += len(item["observations"])
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "status": "ok",
        "artifact_key": TRACKED_ARTIFACT,
        "series": series_count,
        "observations": observation_count,
    }


def fetch_cyclical_cot(artifacts, years, *, fetcher=None, http_client=None):
    archives = {}
    with tempfile.TemporaryDirectory() as directory:
        cache_dir = Path(directory)
        for year in years:
            if fetcher is None:
                path = cftc_cot.fetch_historical_report(
                    year, cache_dir, http_client=http_client
                )
                archives[year] = path.read_bytes()
            else:
                archives[year] = _bytes(fetcher(year))
    result = {"artifact_key": CFTC_ARTIFACT, "years": list(years), "archives": archives}
    _put(artifacts, CFTC_ARTIFACT, result)
    return result


def persist_cyclical_cot(db_path, artifacts, *, allowlist_path=None):
    staged = _get(artifacts, CFTC_ARTIFACT)
    with tempfile.TemporaryDirectory() as directory:
        cache_dir = Path(directory)
        for year, value in staged["archives"].items():
            (cache_dir / f"cftc-disaggregated-futures-only-{year}.zip").write_bytes(
                _bytes(value)
            )
        con = macro_indicators.connect(db_path)
        try:
            result = cyclical_commodities_import.import_cached_official_cot_only(
                con, cache_dir, staged["years"]
            )
        finally:
            con.close()
    return {"status": "ok", "artifact_key": CFTC_ARTIFACT, **result}


def fetch_cyclical_fred(artifacts, *, fetcher=None, http_client=None):
    series_ids = list(usd.USD_SERIES) + list(usd.INFLATION_SERIES)
    values = {}
    if fetcher is None:
        with tempfile.TemporaryDirectory() as directory:
            paths = FredClient(directory, http_client=http_client).fetch_csvs(series_ids)
            values = {series_id: path.read_bytes() for series_id, path in paths.items()}
    else:
        values = {series_id: _bytes(fetcher(series_id)) for series_id in series_ids}
    result = {"artifact_key": CYCLICAL_FRED_ARTIFACT, "series": values}
    _put(artifacts, CYCLICAL_FRED_ARTIFACT, values)
    return result


def persist_cyclical_fred(db_path, artifacts):
    values = _get(artifacts, CYCLICAL_FRED_ARTIFACT)
    with tempfile.TemporaryDirectory() as directory:
        cache_dir = Path(directory)
        for series_id, value in values.items():
            (cache_dir / f"{series_id}.csv").write_bytes(_bytes(value))
        con = macro_indicators.connect(db_path)
        try:
            result = cyclical_commodities_import.import_cached_official_usd_only(
                con, cache_dir
            )
        finally:
            con.close()
    return {"status": "ok", "artifact_key": CYCLICAL_FRED_ARTIFACT, **result}


def fetch_oil(
    artifacts,
    api_key,
    *,
    fetcher=None,
    price_start_date=None,
    full_price_history=False,
):
    if not str(api_key or "").strip():
        raise ValueError("EIA_KEY is not set")
    fetch = fetcher or oil.fetch_oil_observations
    if full_price_history:
        payload = fetch(api_key, full_price_history=True)
    else:
        payload = fetch(api_key, price_start_date=price_start_date)
    result = {"artifact_key": OIL_ARTIFACT, "payload": payload}
    _put(artifacts, OIL_ARTIFACT, payload)
    return result


def persist_oil(db_path, artifacts, *, fetcher=None):
    payload = _get(artifacts, OIL_ARTIFACT)
    if fetcher is not None:
        raise ValueError("oil persistence does not accept a fetcher")
    con = macro_indicators.connect(db_path)
    try:
        series_count = 0
        observation_count = 0
        for item in payload.values():
            macro_indicators.merge_macro_indicator_observations(
                con, item["series"], item["observations"], commit=False
            )
            series_count += 1
            observation_count += len(item["observations"])
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return {"status": "ok", "artifact_key": OIL_ARTIFACT, "series": series_count, "observations": observation_count}


def fetch_shfe_copper(
    artifacts,
    trade_dates,
    *,
    fetcher=None,
    progress_callback=None,
):
    requested = sorted(set(trade_dates))
    if not requested:
        raise ValueError("shfe cu trade dates are required")
    fetch = fetcher or shfe_copper_import._default_fetcher(progress_callback)
    rows = []
    for month_start, month_end in shfe_copper_import._calendar_months(
        requested[0], requested[-1]
    ):
        rows.extend(fetch(month_start, month_end))
    result = {"artifact_key": SHFE_ARTIFACT, "trade_dates": requested, "rows": rows}
    _put(artifacts, SHFE_ARTIFACT, result)
    return result


def persist_shfe_copper(db_path, artifacts, *, progress_callback=None):
    staged = _get(artifacts, SHFE_ARTIFACT)
    rows = staged["rows"]
    rows_by_date = {}
    for row in rows:
        rows_by_date.setdefault(row["trade_date"], []).append(row)

    con = macro_indicators.connect(db_path)
    try:
        result = {
            "raw_dates_requested": len(staged["trade_dates"]),
            "raw_dates_published": 0,
            "raw_observations": 0,
            "derived_observations": 0,
            "rebuild_start_date": staged["trade_dates"][0],
            "rebuild_end_date": staged["trade_dates"][-1],
        }
        for trade_date in staged["trade_dates"]:
            date_rows = rows_by_date.get(trade_date)
            if not date_rows:
                continue

            def staged_fetcher(start_date, end_date, date_rows=date_rows):
                return date_rows

            date_result = shfe_copper_import.import_shfe_cu_dates(
                con,
                [trade_date],
                fetcher=staged_fetcher,
                progress_callback=progress_callback,
            )
            result["raw_dates_published"] += date_result["raw_dates_published"]
            result["raw_observations"] += date_result["raw_observations"]
        final_main_rows = macro_indicators.load_shfe_cu_main_observations(con)
        requested_dates = set(staged["trade_dates"])
        result["derived_observations"] = len(
            {row["date"] for row in final_main_rows if row["date"] in requested_dates}
        )
    finally:
        con.close()
    return {"status": "ok", "artifact_key": SHFE_ARTIFACT, **result}


def fetch_dce_iron_ore_sina(
    artifacts,
    *,
    db_path=None,
    con=None,
    today_date=None,
    initial=False,
    fetcher=None,
):
    effective_today = today_date or date.today().isoformat()
    stored_rows = []
    if not initial and (db_path is not None or con is not None):
        owns_connection = con is None
        read_con = con or macro_indicators.connect(db_path)
        try:
            stored_rows = macro_indicators.load_macro_indicator_observations(
                read_con, dce_iron_ore_sina_import.DCE_IRON_ORE_SINA_SERIES_ID
            )
        finally:
            if owns_connection:
                read_con.close()
    if initial or not stored_rows:
        start_date = dce_iron_ore_sina_import.DCE_IRON_ORE_SINA_START_DATE
    else:
        start_date = dce_iron_ore_sina_import._overlap_start(stored_rows)
    end_date = (date.fromisoformat(effective_today) + timedelta(days=1)).isoformat()
    fetch = fetcher or dce_iron_ore_sina_import._default_fetcher
    payload = fetch(start_date, end_date)
    if not payload["observations"]:
        raise ValueError("sina I0 returned no valid observations")
    result = {
        "artifact_key": DCE_ARTIFACT,
        "payload": payload,
        "initial": initial,
        "start_date": start_date,
        "end_date": end_date,
    }
    _put(artifacts, DCE_ARTIFACT, result)
    return result


def persist_dce_iron_ore_sina(db_path, artifacts):
    staged = _get(artifacts, DCE_ARTIFACT)
    payload = staged["payload"]
    con = macro_indicators.connect(db_path)
    try:
        macro_indicators.merge_macro_indicator_observations(
            con, payload["series"], payload["observations"], commit=False
        )
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "status": "ok",
        "artifact_key": DCE_ARTIFACT,
        "series": payload["series"]["series_id"],
        "observations": len(payload["observations"]),
        "start_date": staged["start_date"],
        "end_date": staged["end_date"],
    }


fetch_tracked = fetch_tracked_commodities
persist_tracked = persist_tracked_commodities
fetch_cftc = fetch_cyclical_cot
persist_cftc = persist_cyclical_cot
fetch_dce = fetch_dce_iron_ore_sina
persist_dce = persist_dce_iron_ore_sina
