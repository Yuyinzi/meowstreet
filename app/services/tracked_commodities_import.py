from datetime import timedelta, date as date_type
from pathlib import Path

from app.data_sources import investing_chrome
from app.data_sources.investing_download import download_commodity_csv
from app.data_sources.investing_rendered_history import (
    fetch_rendered_investing_history,
)
from app.data_sources.tracked_commodities import (
    ACTIVE_MARKET_SERIES,
    MARKET_SERIES,
    build_commodity_series_payload,
    free_web_series,
    parse_commodity_csv,
    parse_investing_history_payload,
    validate_free_web_markets,
)
from app.db import macro_indicators


def _require_active_market(series_id):
    if series_id not in ACTIVE_MARKET_SERIES:
        raise ValueError(f"unknown or archived method commodity market: {series_id}")
    return series_id


def _active_series_ids(markets):
    if markets is None:
        return list(free_web_series())
    series_ids = [_require_active_market(sid) for sid in markets]
    validate_free_web_markets(series_ids)
    return series_ids


def _browser_fetcher(start_date=None, end_date=None, markets=None, cdp_endpoint=None):
    endpoint = cdp_endpoint or "http://127.0.0.1:9222"
    series_ids = _active_series_ids(markets)
    results = {}
    for sid in series_ids:
        meta = ACTIVE_MARKET_SERIES[sid]
        kwargs = {
            "market": meta,
            "cdp_endpoint": endpoint,
        }
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        browser_result = investing_chrome.fetch_investing_history(**kwargs)
        if browser_result["status"] != "ok":
            raise ValueError(browser_result["message"])
        observations = parse_investing_history_payload(
            browser_result["payload"],
            sid,
            retrieved_at=browser_result["retrieved_at"],
        )
        results[sid] = build_commodity_series_payload(sid, observations)
    return results


def refresh_tracked_commodities(
    con,
    fetcher=_browser_fetcher,
    start_date=None,
    end_date=None,
    markets=None,
    cdp_endpoint=None,
):
    series_ids = _active_series_ids(markets)
    if start_date is None and end_date is None:
        latest_dates = []
        for sid in series_ids:
            points = macro_indicators.load_macro_indicator_points(con, sid)
            if points:
                latest_dates.append(max(p["date"] for p in points))
        if latest_dates:
            start_date = (
                date_type.fromisoformat(min(latest_dates)) - timedelta(days=14)
            ).isoformat()
    kwargs = {"start_date": start_date, "end_date": end_date, "markets": series_ids}
    if cdp_endpoint:
        kwargs["cdp_endpoint"] = cdp_endpoint
    payload = fetcher(**kwargs)
    try:
        result = {"series": 0, "observations": 0}
        for sid, item in payload.items():
            _require_active_market(sid)
            macro_indicators.merge_macro_indicator_observations(
                con, item["series"], item["observations"], commit=False
            )
            result["series"] += 1
            result["observations"] += len(item["observations"])
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise


def import_commodity_browser_downloads(
    con,
    markets=None,
    downloader=download_commodity_csv,
    cdp_endpoint=None,
    dry_run=False,
):
    series_ids = _active_series_ids(markets)
    all_payloads = []
    ranges = {}
    for sid in series_ids:
        meta = ACTIVE_MARKET_SERIES[sid]
        result = downloader(meta, cdp_endpoint=cdp_endpoint)
        if result["status"] != "ok":
            raise ValueError(
                f"{sid}: browser download failed — {result.get('message', result['status'])}"
            )
        csv_text = Path(result["csv_path"]).read_text(encoding="utf-8")
        observations = parse_commodity_csv(
            csv_text,
            sid,
            source_url=result["source_url"],
            retrieved_at=result["retrieved_at"],
        )
        if not observations:
            raise ValueError(f"{sid}: parsed 0 valid observations from downloaded CSV")
        ranges[sid] = {
            "start_date": result.get("start_date"),
            "end_date": result.get("end_date"),
        }
        all_payloads.append(
            (sid, build_commodity_series_payload(sid, observations))
        )
    if dry_run:
        return {
            "series": len(all_payloads),
            "observations": sum(
                len(payload["observations"]) for _, payload in all_payloads
            ),
            "ranges": ranges,
        }
    try:
        result = {"series": 0, "observations": 0}
        for sid, payload in all_payloads:
            macro_indicators.merge_macro_indicator_observations(
                con, payload["series"], payload["observations"], commit=False
            )
            result["series"] += 1
            result["observations"] += len(payload["observations"])
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise


def _newer_observations(con, series_id, observations):
    points = macro_indicators.load_macro_indicator_points(con, series_id)
    if not points:
        raise ValueError(
            f"{series_id}: rendered history refresh requires an existing baseline"
        )
    latest_date = max(point["date"] for point in points)
    newer = [row for row in observations if row["date"] > latest_date]
    if not newer:
        raise ValueError(
            f"{series_id}: rendered history has no dates newer than {latest_date}"
        )
    return newer


def import_commodity_browser_rows(
    con,
    markets=None,
    fetcher=fetch_rendered_investing_history,
    cdp_endpoint=None,
    dry_run=False,
):
    series_ids = _active_series_ids(markets)
    all_payloads = []
    ranges = {}
    for sid in series_ids:
        meta = ACTIVE_MARKET_SERIES[sid]
        result = fetcher(meta, cdp_endpoint=cdp_endpoint)
        if result["status"] != "ok":
            raise ValueError(
                f"{sid}: rendered history fetch failed — {result.get('message', result['status'])}"
            )
        observations = parse_investing_history_payload(
            result["payload"],
            sid,
            retrieved_at=result["retrieved_at"],
        )
        newer = _newer_observations(con, sid, observations)
        ranges[sid] = {
            "start_date": newer[0]["date"],
            "end_date": newer[-1]["date"],
        }
        all_payloads.append((sid, build_commodity_series_payload(sid, newer)))
    if dry_run:
        return {
            "series": len(all_payloads),
            "observations": sum(
                len(payload["observations"]) for _, payload in all_payloads
            ),
            "ranges": ranges,
        }
    try:
        result = {"series": 0, "observations": 0}
        for sid, payload in all_payloads:
            macro_indicators.merge_macro_indicator_observations(
                con, payload["series"], payload["observations"], commit=False
            )
            result["series"] += 1
            result["observations"] += len(payload["observations"])
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise


def import_commodity_csv_files(con, csv_paths_by_market):
    try:
        result = {"series": 0, "observations": 0}
        for series_id, csv_path in csv_paths_by_market.items():
            _require_active_market(series_id)
            text = Path(csv_path).read_text(encoding="utf-8")
            observations = parse_commodity_csv(text, series_id)
            payload = build_commodity_series_payload(series_id, observations)
            macro_indicators.merge_macro_indicator_observations(
                con, payload["series"], payload["observations"], commit=False
            )
            result["series"] += 1
            result["observations"] += len(observations)
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
