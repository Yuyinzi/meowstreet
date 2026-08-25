import argparse
import asyncio
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import IntegrityError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.http_client import HttpClient

from app.db import growth_cycle
from app.db import ism_surveys
from app.db import macro_indicators
from app.db import us_rates_liquidity
from app.tools import ism_ai_extraction, ism_official_report, ism_prnewswire_archive
from app.services import ism_report_ingestion as ingestion


BASE_URL = (
    "https://www.ismworld.org/supply-management-news-and-reports/reports/"
    "ism-pmi-reports/pmi/{month}/"
)

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

_IMPORT_ERRORS = (ValueError, IntegrityError)
_FETCH_ATTEMPTS = 4


def extract_prepared_report_payload(con, prepared, source, ai_client):
    from app.db import growth_cycle as _growth_cycle
    from scripts.extract_ism_report_ai import extract_or_load_factual_sections_async

    _growth_cycle.init_db(con)

    log_progress(
        f"section extraction concurrency=3 sections={len(ism_ai_extraction.FACTUAL_SECTION_NAMES)}"
    )
    factual_payload = asyncio.run(
        extract_or_load_factual_sections_async(
            con,
            prepared["report_text"],
            source,
            ai_client,
            progress=log_progress,
        )
    )
    return ism_ai_extraction.validate_factual_extraction(factual_payload)


def import_target(con, target, index, total, fetch, ai_client, model):
    report_month = target.get("report_month", "unknown")
    source_name = target["source_name"]
    url = target["url"]
    started = time.perf_counter()
    log_progress(f"[{index}/{total}] {report_month} {source_name} fetching {url}")
    result = import_report_url(
        con,
        url,
        source_name=source_name,
        fetch=fetch,
        ai_client=ai_client,
        model=model,
    )
    elapsed = time.perf_counter() - started
    log_progress(
        f"[{index}/{total}] {report_month} ok report_id={result['report_id']} "
        f"metrics={result['metrics']} comments={result['comments']} "
        f"at_a_glance_rows={result['at_a_glance_rows']} {elapsed:.1f}s"
    )
    return result


def import_target_from_db_path(db_path, target, index, total, fetch, ai_client, model):
    con = growth_cycle.connect(db_path)
    try:
        return import_target(con, target, index, total, fetch, ai_client, model)
    finally:
        con.close()


def log_progress(message):
    print(message, file=sys.stderr, flush=True)


async def import_targets_async(
    db_path, targets, fetch, ai_client, model, report_concurrency
):
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
                    target,
                    index,
                    len(targets),
                    fetch,
                    ai_client,
                    model,
                )
                results_by_index[index] = result
            except _IMPORT_ERRORS as exc:
                print(
                    f"ism_official_report/{target['url']}: failed - {exc}",
                    file=sys.stderr,
                )
                failed += 1

    await asyncio.gather(
        *[run_one(index, target) for index, target in enumerate(targets, start=1)]
    )
    return [results_by_index[index] for index in sorted(results_by_index)], failed


def import_targets(db_path, targets, fetch, ai_client, model, report_concurrency):
    if not targets:
        return [], 0
    log_progress(f"report concurrency={report_concurrency} targets={len(targets)}")
    return asyncio.run(
        import_targets_async(
            db_path,
            targets,
            fetch,
            ai_client,
            model,
            report_concurrency,
        )
    )


def build_ai_client(config):
    from app import llm
    from scripts.extract_ism_report_ai import OpenAIJsonClient, llm_timeout

    def client_factory():
        return llm.build_async_client(
            config,
            max_retries=0,
            timeout=llm_timeout(),
            error_context="ISM report extraction",
        )

    return OpenAIJsonClient(
        client_factory(),
        config["model"],
        client_factory=client_factory,
        progress=log_progress,
    )


def fetched_at_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def report_url(month):
    normalized = month.strip().lower()
    if normalized not in MONTHS:
        raise ValueError(f"ism report month is unknown: {month}")
    return BASE_URL.format(month=normalized)


def _is_sso_page(html):
    return "Object moved" in html and "ecommerce.ismworld.org" in html


def _is_captcha_page(html):
    markers = [
        "captcha_form",
        "grecaptcha.execute",
        "google.com/recaptcha",
        "rtoken",
    ]
    lowered = html.lower()
    return sum(marker.lower() in lowered for marker in markers) >= 2


def fetch_text(url, http_client=None):
    client = http_client or HttpClient(max_attempts=_FETCH_ATTEMPTS)
    response = client.request("GET", url, timeout=30, browser=True)
    text = response.content.decode("utf-8", errors="replace")
    if _is_sso_page(text):
        raise ValueError("ism official report requires ISM membership login")
    if _is_captcha_page(text):
        raise ValueError("ism official report blocked by captcha")
    return text


def metric_points(parsed):
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


def merge_metrics(con, parsed, commit=True):
    count = 0
    for series_id, points in metric_points(parsed).items():
        series = {
            "series_id": series_id,
            "title": series_id.replace("_", " ").title(),
            "units": "index",
            "source": "ISM official report",
        }
        saved = macro_indicators.merge_macro_indicator_points(
            con, series, points, commit=commit
        )
        count += saved["points"]
    return count


def ai_metric_points(payload):
    report_month = payload["report"]["report_month"]
    return {
        row["series_id"]: [
            {
                "date": report_month,
                "value": row["current_value"],
                "source": "ISM AI extraction",
            }
        ]
        for row in payload["at_a_glance_rows"]
    }


def merge_ai_metrics(con, payload, commit=True):
    count = 0
    for row in payload["at_a_glance_rows"]:
        series = {
            "series_id": row["series_id"],
            "title": row["label"],
            "units": "index",
            "source": "ISM AI extraction",
        }
        saved = macro_indicators.merge_macro_indicator_points(
            con,
            series,
            ai_metric_points(payload)[row["series_id"]],
            commit=commit,
        )
        count += saved["points"]
    return count


def ai_report_snapshot(payload, source_url, source_hash, fetched_at):
    report = payload["report"]
    return {
        "report_id": report["report_id"],
        "report_month": report["report_month"],
        "title": report["title"],
        "source_url": source_url,
        "source_hash": source_hash,
        "fetched_at": fetched_at,
        "parse_status": "ok",
        "next_report_period": None,
        "next_release_at": None,
        "next_release_label": "",
    }


def ai_comments(payload, source_url, source_hash):
    report = payload["report"]
    return [
        {
            "report_id": report["report_id"],
            "report_month": report["report_month"],
            "comment_index": index,
            "industry": comment["industry"],
            "comment_text": comment["comment_text"],
            "source_url": source_url,
            "source_hash": source_hash,
        }
        for index, comment in enumerate(payload["respondent_comments"], start=1)
    ]


def ai_at_a_glance_rows(payload, source_url, source_hash):
    report = payload["report"]
    return [
        {
            "report_id": report["report_id"],
            "report_month": report["report_month"],
            "series_id": row["series_id"],
            "label": row["label"],
            "current_value": row["current_value"],
            "previous_value": row["previous_value"],
            "point_change": row["point_change"],
            "direction": row["direction"],
            "rate_of_change": row["rate_of_change"],
            "trend_months": row["trend_months"],
            "source_url": source_url,
            "source_hash": source_hash,
        }
        for row in payload["at_a_glance_rows"]
    ]


def source_name_for_url(url):
    if "prnewswire.com" in url:
        return "prnewswire"
    if "ismworld.org" in url:
        return "ismworld"
    raise ValueError(f"ism report source is unsupported: {url}")


def source_snapshot(
    url, source_name, html, fetched_at, parse_status, parse_error=None, parsed=None
):
    report = parsed["report"] if parsed else {}
    return {
        "source_url": url,
        "source_name": source_name,
        "source_hash": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "fetched_at": fetched_at,
        "raw_html": html,
        "parse_status": parse_status,
        "parse_error": parse_error,
        "report_id": report.get("report_id"),
        "report_month": report.get("report_month"),
    }


def import_report_url(
    con,
    url,
    source_name=None,
    fetch=None,
    now=None,
    ai_client=None,
    model=None,
):
    if fetch is None:
        fetch = fetch_text
    if now is None:
        now = fetched_at_now
    if source_name is None:
        source_name = source_name_for_url(url)
    fetched_at = now()
    html = fetch(url)
    source_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": url,
            "source_name": source_name,
            "source_hash": source_hash,
            "fetched_at": fetched_at,
            "raw_html": html,
            "parse_status": "fetched",
            "parse_error": None,
            "report_id": None,
            "report_month": None,
        },
    )
    log_progress(f"raw snapshot saved source={source_name} url={url}")
    prepared = ism_official_report.prepare_report_for_ai(
        html,
        url,
        fetched_at,
        source_name=source_name,
    )
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": url,
            "source_name": source_name,
            "source_hash": source_hash,
            "fetched_at": fetched_at,
            "raw_html": html,
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": prepared["report_id"],
            "report_month": prepared["report_month"],
        },
    )
    log_progress(
        f"prepared report_id={prepared['report_id']} report_month={prepared['report_month']}"
    )
    source = {
        "report_id": prepared["report_id"],
        "report_month": prepared["report_month"],
        "source_url": url,
        "source_hash": source_hash,
        "model": model,
        "updated_at": fetched_at,
    }
    payload = extract_prepared_report_payload(con, prepared, source, ai_client)
    if payload["report"]["report_id"] != prepared["report_id"]:
        raise ValueError(
            f"llm report_id mismatch for {url}: expected {prepared['report_id']}, "
            f"llm returned {payload['report']['report_id']}"
        )
    if payload["report"]["report_month"] != prepared["report_month"]:
        raise ValueError(
            f"llm report_month mismatch for {url}: expected {prepared['report_month']}, "
            f"llm returned {payload['report']['report_month']}"
        )
    metric_count = merge_ai_metrics(con, payload)
    ranking_rows = ism_official_report.parse_rankings(
        ism_official_report.normalize_text(prepared["report_text"]),
        prepared["report_month"],
    )
    con.execute(
        "delete from ism_industry_rankings where survey_type = 'manufacturing' and date = ?",
        (prepared["report_month"],),
    )
    ism_surveys.merge_industry_rankings(con, "manufacturing", ranking_rows)
    growth_cycle.replace_ism_at_a_glance_rows(
        con, ai_at_a_glance_rows(payload, url, source_hash)
    )
    growth_cycle.replace_ism_report_snapshot(
        con,
        ai_report_snapshot(payload, url, source_hash, fetched_at),
        ai_comments(payload, url, source_hash),
    )
    saved = growth_cycle.replace_ism_ai_report_outputs(
        con,
        payload,
        {
            "source_url": url,
            "source_hash": source_hash,
            "model": model,
            "prompt_version": ism_ai_extraction.PROMPT_VERSION,
        },
    )
    return {
        "report_id": payload["report"]["report_id"],
        "metrics": metric_count,
        "rankings": len(ranking_rows),
        "comments": len(payload["respondent_comments"]),
        "at_a_glance_rows": len(payload["at_a_glance_rows"]),
        "source_name": source_name,
        **saved,
    }


def import_report(con, month, fetch=None, now=None, ai_client=None, model=None):
    return import_report_url(
        con,
        report_url(month),
        source_name="ismworld",
        fetch=fetch,
        now=now,
        ai_client=ai_client,
        model=model,
    )


def requested_months(args):
    if args.current_year:
        return MONTHS[: datetime.now().month - 1]
    if args.month:
        return args.month
    return [MONTHS[datetime.now().month - 2]]


def requested_urls(args, fetch=None):
    if fetch is None:
        fetch = fetch_text
    urls = list(args.url or [])
    for page in range(1, args.prnewswire_pages + 1):
        listing_url = ism_prnewswire_archive.archive_listing_url(
            page,
            args.prnewswire_pagesize,
        )
        html = fetch(listing_url)
        urls.extend(
            item["url"] for item in ism_prnewswire_archive.parse_archive_listing(html)
        )
    seen = set()
    result = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def main(argv=None, fetch=None, ai_client_factory=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--month", action="append", choices=MONTHS)
    parser.add_argument("--current-year", action="store_true")
    parser.add_argument("--url", action="append")
    parser.add_argument("--prnewswire-pages", type=int, default=0)
    parser.add_argument("--prnewswire-pagesize", type=int, default=25)
    parser.add_argument("--backfill-since", type=int)
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--latest-only", action="store_true")
    parser.add_argument("--report-concurrency", type=ingestion.positive_int, default=1)
    parser.add_argument("--report-month")
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    growth_cycle.init_db(con)
    if ai_client_factory is None:
        from app import llm

        config = llm.load_openai_config(args, root=ROOT)
        ai_client = build_ai_client(config)
        model = config["model"]
    else:
        config = {"model": "test-model"}
        ai_client = ai_client_factory(config)
        model = config["model"]
    results = []
    failed = 0
    if args.latest_only:
        targets = ingestion.build_targets(
            "manufacturing",
            force_latest=True,
            fetch=fetch,
        )
        for target in targets:
            try:
                result = import_report_url(
                    con,
                    target["url"],
                    source_name=target["source_name"],
                    fetch=fetch,
                    ai_client=ai_client,
                    model=model,
                )
                results.append(result)
            except _IMPORT_ERRORS as exc:
                print(
                    f"ism_official_report/{target['url']}: failed - {exc}",
                    file=sys.stderr,
                )
                failed += 1
    elif args.report_month:
        normalized = ingestion.normalize_report_month(args.report_month)
        latest = ingestion.latest_released_report_month()
        if normalized == latest:
            targets = [
                {
                    "source_name": "ismworld",
                    "url": report_url(ingestion.month_name(normalized)),
                }
            ]
        else:
            archive_reports = ingestion.discover_prnewswire_reports(
                since_year=int(normalized[:4]),
                survey_type="manufacturing",
                fetch=fetch,
            )
            targets = [
                {"source_name": "prnewswire", "url": item["url"]}
                for item in archive_reports
                if item["report_month"] == normalized
            ]
            if not targets:
                print(
                    f"ism_official_report/{args.report_month}: no archive entry found",
                    file=sys.stderr,
                )
                failed += 1
        for target in targets:
            try:
                result = import_report_url(
                    con,
                    target["url"],
                    source_name=target["source_name"],
                    fetch=fetch,
                    ai_client=ai_client,
                    model=model,
                )
                results.append(result)
            except _IMPORT_ERRORS as exc:
                print(
                    f"ism_official_report/{target['url']}: failed - {exc}",
                    file=sys.stderr,
                )
                failed += 1
    elif args.backfill_since:
        existing_months = growth_cycle.load_existing_ism_report_months(con)
        targets = ingestion.build_targets(
            "manufacturing",
            backfill_since=args.backfill_since,
            missing_only=args.missing_only,
            existing_months=existing_months,
            force_latest=True,
            fetch=fetch,
        )
        target_results, target_failed = import_targets(
            args.db_path,
            targets,
            fetch,
            ai_client,
            model,
            args.report_concurrency,
        )
        results.extend(target_results)
        failed += target_failed
    else:
        for url in requested_urls(args, fetch=fetch):
            try:
                result = import_report_url(
                    con, url, fetch=fetch, ai_client=ai_client, model=model
                )
                results.append(result)
            except _IMPORT_ERRORS as exc:
                print(f"ism_official_report/{url}: failed - {exc}", file=sys.stderr)
                failed += 1
        if args.current_year:
            existing_months = growth_cycle.load_existing_ism_report_months(con)
            targets = ingestion.build_targets(
                "manufacturing",
                current_year=datetime.now().year,
                missing_only=not args.force,
                existing_months=existing_months,
                force_latest=True,
                fetch=fetch,
            )
            target_results, target_failed = import_targets(
                args.db_path,
                targets,
                fetch,
                ai_client,
                model,
                args.report_concurrency,
            )
            results.extend(target_results)
            failed += target_failed
        else:
            months = (
                []
                if (args.url or args.prnewswire_pages) and not args.month
                else requested_months(args)
            )
            for month in months:
                try:
                    result = import_report(
                        con, month, fetch=fetch, ai_client=ai_client, model=model
                    )
                    results.append(result)
                except ism_official_report.IsmReportUnavailable as exc:
                    print(
                        f"ism_official_report/{month}: failed - {exc}",
                        file=sys.stderr,
                    )
                    failed += 1
                except _IMPORT_ERRORS as exc:
                    print(
                        f"ism_official_report/{month}: failed - {exc}",
                        file=sys.stderr,
                    )
                    failed += 1
    con.close()
    for result in results:
        print(
            f"{result['report_id']}: source={result.get('source_name', 'ismworld')} "
            f"metrics={result['metrics']} rankings={result['rankings']} "
            f"comments={result['comments']} at_a_glance_rows={result['at_a_glance_rows']}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
