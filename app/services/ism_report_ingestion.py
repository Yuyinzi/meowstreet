"""Shared ISM report ingestion service.

Provides survey-aware target selection, archive discovery, pagination,
month normalization, target ordering, and source snapshot lifecycle
for both Manufacturing and Services.
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256

from app.tools import ism_report_archive
from app.tools import ism_report_config


MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


def latest_released_report_month(today=None):
    """Return the latest released report month as ``YYYY-MM-01``.

    Assumes the report for *today*'s month is released next month, so
    the latest available report is the previous calendar month.
    """
    if today is None:
        today = datetime.now()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}-{month:02d}-01"


def month_name(report_month):
    """Return the lowercase English month name for a ``YYYY-MM-01`` string."""
    index = int(report_month[5:7]) - 1
    return MONTHS[index]


def normalize_report_month(value):
    """Normalize ``YYYY-MM`` or ``YYYY-MM-01`` to ``YYYY-MM-01``."""
    import re

    if re.fullmatch(r"20\d{2}-\d{2}", value):
        return f"{value}-01"
    if re.fullmatch(r"20\d{2}-\d{2}-01", value):
        return value
    raise ValueError(f"ism report month must be YYYY-MM: {value}")


def _fetch_or_raise(fetch, url):
    if fetch is None:
        from scripts.fetch_ism_official_reports import fetch_text

        return fetch_text(url)
    return fetch(url)


def _page_has_release_links(html):
    links = ism_report_archive.extract_all_links(html)
    return any("/news-releases/" in link.get("url", "") for link in links)


def discover_prnewswire_reports(
    since_year, survey_type, fetch=None, pagesize=25, max_pages=100
):
    """Discover survey-matching PR Newswire reports from *since_year* onward."""
    reports = []
    seen = set()
    seen_page_content = set()
    since_month = f"{since_year}-01-01"
    reached_before_since = False
    cfg = ism_report_config.load_survey_config(survey_type)

    for page in range(1, max_pages + 1):
        listing_url = ism_report_archive.archive_listing_url(page, pagesize)
        html = _fetch_or_raise(fetch, listing_url)
        content_hash = sha256(html.encode("utf-8")).hexdigest()
        if content_hash in seen_page_content:
            break
        seen_page_content.add(content_hash)
        if not _page_has_release_links(html):
            break
        page_reports = ism_report_archive.parse_archive_listing(html, survey_type)
        for report in page_reports:
            if report["url"] in seen:
                continue
            seen.add(report["url"])
            if report["report_month"] < since_month:
                reached_before_since = True
                continue
            reports.append(report)
        if reached_before_since:
            break
    return sorted(reports, key=lambda item: item["report_month"])


def build_targets(
    survey_type,
    *,
    latest_only=False,
    report_month=None,
    current_year=None,
    backfill_since=None,
    missing_only=False,
    existing_months=frozenset(),
    force_latest=True,
    fetch=None,
    pagesize=25,
    max_pages=100,
    repair_urls=None,
):
    """Build a sorted list of ingestion targets for *survey_type*.

    Each target is a dict with:
        survey_type, report_month, report_id, source_name, url

    When *backfill_since* is set, historical months are discovered from
    PR Newswire and combined with the latest ISM World report.
    """
    cfg = ism_report_config.load_survey_config(survey_type)
    latest_month = latest_released_report_month()
    targets = []
    seen_months = set()

    # Add explicit repair URLs (resolve source from URL)
    for url in repair_urls or []:
        if "prnewswire.com" in url:
            source_name = "prnewswire"
        elif "ismworld.org" in url:
            source_name = "ismworld"
        else:
            source_name = "direct_url"
        targets.append(
            {
                "survey_type": survey_type,
                "report_month": None,
                "report_id": None,
                "source_name": source_name,
                "url": url,
            }
        )
        seen_months.add(None)

    # Add a specific report month
    if report_month:
        normal_month = normalize_report_month(report_month)
        if normal_month >= latest_month:
            if not missing_only or normal_month not in existing_months:
                if (survey_type, normal_month) not in seen_months:
                    url = cfg["ismworld_monthly_url"](month_name(normal_month))
                    rid = ism_report_archive.report_id(normal_month, survey_type)
                    targets.append(
                        {
                            "survey_type": survey_type,
                            "report_month": normal_month,
                            "report_id": rid,
                            "source_name": "ismworld",
                            "url": url,
                        }
                    )
                    seen_months.add((survey_type, normal_month))
        else:
            archive_reports = discover_prnewswire_reports(
                int(normal_month[:4]),
                survey_type,
                fetch=fetch,
                pagesize=pagesize,
                max_pages=max_pages,
            )
            matching = [r for r in archive_reports if r["report_month"] == normal_month]
            if matching:
                item = matching[0]
                if not missing_only or normal_month not in existing_months:
                    if (survey_type, normal_month) not in seen_months:
                        targets.append(
                            {
                                "survey_type": survey_type,
                                "report_month": normal_month,
                                "report_id": item["report_id"],
                                "source_name": "prnewswire",
                                "url": item["url"],
                            }
                        )
                        seen_months.add((survey_type, normal_month))

    # Backfill from PR Newswire
    if backfill_since:
        archive_reports = discover_prnewswire_reports(
            backfill_since,
            survey_type,
            fetch=fetch,
            pagesize=pagesize,
            max_pages=max_pages,
        )
        since_month = f"{backfill_since}-01-01"
        for item in archive_reports:
            if since_month <= item["report_month"] < latest_month:
                if missing_only and item["report_month"] in existing_months:
                    continue
                key = (survey_type, item["report_month"])
                if key not in seen_months:
                    targets.append(
                        {
                            "survey_type": survey_type,
                            "report_month": item["report_month"],
                            "report_id": item["report_id"],
                            "source_name": "prnewswire",
                            "url": item["url"],
                        }
                    )
                    seen_months.add(key)

    # Current year — discover PR Newswire for months before latest
    if current_year:
        archive_reports = discover_prnewswire_reports(
            current_year,
            survey_type,
            fetch=fetch,
            pagesize=pagesize,
            max_pages=max_pages,
        )
        archive_by_month = {r["report_month"]: r for r in archive_reports}
        for m in range(1, 13):
            ym = f"{current_year}-{m:02d}-01"
            if ym > latest_month:
                break
            key = (survey_type, ym)
            if key in seen_months:
                continue
            if missing_only and ym in existing_months:
                continue
            if ym == latest_month:
                url = cfg["ismworld_monthly_url"](month_name(ym))
                rid = ism_report_archive.report_id(ym, survey_type)
                target_source = "ismworld"
            elif ym in archive_by_month:
                item = archive_by_month[ym]
                url = item["url"]
                rid = item["report_id"]
                target_source = "prnewswire"
            else:
                continue
            targets.append(
                {
                    "survey_type": survey_type,
                    "report_month": ym,
                    "report_id": rid,
                    "source_name": target_source,
                    "url": url,
                }
            )
            seen_months.add(key)

    # Latest released report unless suppressed
    if (
        not latest_only
        and not report_month
        and not backfill_since
        and not current_year
        and not repair_urls
    ):
        # Default behavior: fetch latest only
        pass

    if force_latest and (survey_type, latest_month) not in seen_months:
        if not missing_only or latest_month not in existing_months:
            url = cfg["ismworld_monthly_url"](month_name(latest_month))
            rid = ism_report_archive.report_id(latest_month, survey_type)
            targets.append(
                {
                    "survey_type": survey_type,
                    "report_month": latest_month,
                    "report_id": rid,
                    "source_name": "ismworld",
                    "url": url,
                }
            )
            seen_months.add((survey_type, latest_month))

    return targets


def normalize_parsed(parsed, survey_type):
    """Validate and normalize a parser result for *survey_type*.

    Returns the validated dict with ``survey_type`` set and
    ``at_a_glance_rows`` defaulting to an empty list.

    Raises ``ValueError`` on survey type mismatch, unexpected metric
    series, missing report month, or report ID prefix mismatch.
    """
    cfg = ism_report_config.load_survey_config(survey_type)

    if parsed.get("survey_type") != survey_type:
        raise ValueError(
            f"ism report survey mismatch: expected {survey_type}, "
            f"got {parsed.get('survey_type')}"
        )

    report = parsed.get("report", {})
    report_id = report.get("report_id", "")
    prefix = cfg["report_id_prefix"]
    if not report_id.startswith(prefix):
        raise ValueError(
            f"ism report id prefix mismatch: expected {prefix}, got {report_id}"
        )

    if not report.get("report_month"):
        raise ValueError(f"ism report month is missing for {survey_type}")

    allowed = cfg["allowed_metric_series"]
    metrics = parsed.get("metrics", {})
    unexpected = set(metrics) - allowed
    if unexpected:
        raise ValueError(
            f"ism report unexpected metric series: {', '.join(sorted(unexpected))}"
        )

    result = dict(parsed)
    result.setdefault("at_a_glance_rows", [])
    return result


def save_source_snapshot(con, target, html, fetched_at):
    """Persist raw source HTML with *survey_type* before parsing.

    *target* is an ingestion target dict (from ``build_targets``).
    Returns the saved snapshot dict.
    """
    from app.db import growth_cycle

    snapshot = {
        "source_url": target["url"],
        "source_name": target["source_name"],
        "survey_type": target["survey_type"],
        "source_hash": sha256(html.encode("utf-8")).hexdigest(),
        "fetched_at": fetched_at,
        "raw_html": html,
        "parse_status": "fetched",
        "parse_error": None,
        "report_id": None,
        "report_month": None,
    }
    growth_cycle.replace_ism_report_source_snapshot(con, snapshot, commit=True)
    return snapshot


def mark_source_snapshot_success(con, source_url, parsed):
    """Update an existing source snapshot after successful parse.

    Sets ``parse_status = "ok"`` and stores the parsed report identity.
    """
    from app.db import growth_cycle

    report = parsed.get("report", {})
    existing = growth_cycle.load_ism_report_source_snapshot(con, source_url)
    if existing is None:
        raise ValueError(f"ism source snapshot not found: {source_url}")
    existing["parse_status"] = "ok"
    existing["parse_error"] = None
    existing["report_id"] = report.get("report_id")
    existing["report_month"] = report.get("report_month")
    growth_cycle.replace_ism_report_source_snapshot(con, existing, commit=True)
    return existing


def mark_source_snapshot_failed(con, source_url, parse_error):
    """Update an existing source snapshot after parse failure.

    Sets ``parse_status = "failed"`` and preserves the error text.
    """
    from app.db import growth_cycle

    existing = growth_cycle.load_ism_report_source_snapshot(con, source_url)
    if existing is None:
        raise ValueError(f"ism source snapshot not found: {source_url}")
    existing["parse_status"] = "failed"
    existing["parse_error"] = parse_error
    growth_cycle.replace_ism_report_source_snapshot(con, existing, commit=True)
    return existing


def _metric_points(parsed):
    """Convert parsed metrics dict to macro_indicator_points format."""
    return {
        series_id: [
            {
                "date": parsed["report"]["report_month"],
                "value": value,
                "source": "ISM official report",
            }
        ]
        for series_id, value in parsed["metrics"].items()
    }


def persist_parsed_report(con, survey_type, parsed):
    """Atomically persist a validated parsed payload for *survey_type*.

    Writes report, metrics, rankings, comments, and (Manufacturing only)
    At-a-Glance rows in a single transaction. Rolls back on any failure.

    Returns a dict with:
        report_id, survey_type, source, reports, metrics, rankings, comments
    """
    from app.db import growth_cycle
    from app.db import ism_surveys
    from app.db import us_rates_liquidity as usrl
    from app.tools import ism_report_config

    cfg = ism_report_config.load_survey_config(survey_type)
    report = parsed["report"]
    report_month = report["report_month"]

    con.execute("begin")
    try:
        # Delete old metric points for this survey's series + month
        series_ids = sorted(cfg["allowed_metric_series"])
        placeholders = ",".join("?" for _ in series_ids)
        con.execute(
            f"delete from macro_indicator_points where series_id in ({placeholders}) and date = ?",
            (*series_ids, report_month),
        )

        # Insert new metric points
        metrics_count = 0
        for series_id, points in _metric_points(parsed).items():
            series = {
                "series_id": series_id,
                "title": series_id.replace("_", " ").title(),
                "units": "index",
                "source": "ISM official report",
            }
            saved = usrl.merge_macro_indicator_points(con, series, points, commit=False)
            metrics_count += saved["points"]

        # Upsert report snapshot with report-level comments
        saved_report = ism_surveys.replace_report_snapshot(
            con, survey_type, report, parsed.get("comments", []), commit=False
        )

        # Replace industry rankings
        con.execute(
            "delete from ism_industry_rankings where survey_type = ? and date = ?",
            (survey_type, report_month),
        )
        rankings_count = ism_surveys.merge_industry_rankings(
            con, survey_type, parsed.get("rankings", []), commit=False
        )

        # Replace industry comments
        con.execute(
            "delete from ism_industry_comments where survey_type = ? and report_month = ?",
            (survey_type, report_month),
        )
        comments_count = ism_surveys.merge_industry_comments(
            con, survey_type, parsed.get("comments", []), commit=False
        )

        # At-a-Glance rows (Manufacturing only)
        at_a_glance_rows = parsed.get("at_a_glance_rows", [])
        if at_a_glance_rows:
            growth_cycle.replace_ism_at_a_glance_rows(
                con, at_a_glance_rows, commit=False
            )

        con.commit()
    except BaseException:
        con.rollback()
        raise

    return {
        "report_id": report["report_id"],
        "survey_type": survey_type,
        "source": report.get("source_name", "ismworld"),
        "reports": saved_report.get("reports", 1),
        "metrics": metrics_count,
        "rankings": rankings_count,
        "comments": comments_count,
    }


def log_progress(message):
    """Print a progress message to stderr (flushed for real-time output)."""
    print(message, file=sys.stderr, flush=True)


from subprocess import CalledProcessError, TimeoutExpired

_IMPORT_ERRORS = (ValueError, RuntimeError, CalledProcessError, TimeoutExpired)


def positive_int(value):
    """Argparse type validating positive integers for report concurrency."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("report concurrency must be at least 1")
    return parsed


def import_single_target(con, survey_type, target, fetch=None):
    """Fetch, parse, validate, snapshot, and persist one ingestion target.

    Opens no connections — caller owns *con* lifecycle.
    On parse failure the source snapshot is marked 'failed' and the
    original exception propagates.

    Returns the result dict from persist_parsed_report.
    """
    import traceback

    cfg = ism_report_config.load_survey_config(survey_type)
    url = target["url"]
    source_name = target.get("source_name", "ismworld")
    fetched_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    html = _fetch_or_raise(fetch, url)
    save_source_snapshot(con, target, html, fetched_at)

    try:
        parsed = cfg["parse_report"](html, url, fetched_at, source_name)
        validated = normalize_parsed(parsed, survey_type)
    except BaseException:
        mark_source_snapshot_failed(con, url, traceback.format_exc())
        raise

    mark_source_snapshot_success(con, url, validated)

    target_month = target.get("report_month")
    if target_month and validated["report"]["report_month"] != target_month:
        err_msg = (
            f"ism report month mismatch: requested {target_month}, "
            f"got {validated['report']['report_month']}"
        )
        mark_source_snapshot_failed(con, url, err_msg)
        raise ValueError(err_msg)

    try:
        return persist_parsed_report(con, survey_type, validated)
    except BaseException:
        mark_source_snapshot_failed(con, url, traceback.format_exc())
        raise


def import_target_from_db_path(db_path, survey_type, target, index, total, fetch=None):
    """Open a dedicated DB connection and import one target.

    Returns the result dict from import_single_target.
    Closes the connection before returning.
    """
    from app.db import growth_cycle as _gc
    from app.db import us_rates_liquidity as _usrl

    con = _usrl.connect(db_path)
    _gc.init_db(con)
    try:
        report_month = target.get("report_month", "unknown")
        started = time.perf_counter()
        log_progress(
            f"[{index}/{total}] {survey_type} {report_month} fetching {target['url']}"
        )
        result = import_single_target(con, survey_type, target, fetch=fetch)
        elapsed = time.perf_counter() - started
        log_progress(
            f"[{index}/{total}] {report_month} ok "
            f"report_id={result['report_id']} metrics={result['metrics']} "
            f"rankings={result['rankings']} comments={result['comments']} "
            f"{elapsed:.1f}s"
        )
        return result
    finally:
        con.close()


async def _import_targets_async(
    db_path, survey_type, targets, fetch, report_concurrency
):
    """Import targets concurrently, one DB connection per worker."""
    semaphore = asyncio.Semaphore(report_concurrency)
    results_by_index = {}
    failed = 0

    async def run_one(index, target):
        nonlocal failed
        async with semaphore:
            try:
                result = await asyncio.to_thread(
                    import_target_from_db_path,
                    db_path,
                    survey_type,
                    target,
                    index,
                    len(targets),
                    fetch,
                )
                results_by_index[index] = result
            except _IMPORT_ERRORS as exc:
                log_progress(
                    f"[{index}/{len(targets)}] {target['url']}: failed - {exc}"
                )
                results_by_index[index] = None
                failed += 1

    await asyncio.gather(
        *[run_one(index, target) for index, target in enumerate(targets, start=1)]
    )
    return [results_by_index.get(index) for index in sorted(results_by_index)], failed


def import_targets(db_path, survey_type, targets, fetch=None, report_concurrency=1):
    """Import multiple targets concurrently, one connection per worker.

    Returns ``(results, failed_count)`` where *results* is in input
    order and each entry is either a success dict (from
    ``persist_parsed_report``) or ``None`` when the target failed.
    """
    if not targets:
        return [], 0
    log_progress(f"report concurrency={report_concurrency} targets={len(targets)}")
    return asyncio.run(
        _import_targets_async(db_path, survey_type, targets, fetch, report_concurrency)
    )
