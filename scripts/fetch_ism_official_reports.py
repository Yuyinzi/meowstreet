import argparse
import hashlib
import subprocess
import sys
from subprocess import CalledProcessError, TimeoutExpired
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from app.tools import ism_ai_extraction, ism_official_report, ism_prnewswire_archive


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


def fetch_text(url):
    result = subprocess.run(
        ["curl", "-sS", url],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    text = result.stdout
    if _is_sso_page(text):
        raise ValueError("ism official report requires ISM membership login")
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


def merge_metrics(con, parsed):
    count = 0
    for series_id, points in metric_points(parsed).items():
        series = {
            "series_id": series_id,
            "title": series_id.replace("_", " ").title(),
            "units": "index",
            "source": "ISM official report",
        }
        saved = us_rates_liquidity.merge_macro_indicator_points(con, series, points)
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


def merge_ai_metrics(con, payload):
    count = 0
    for row in payload["at_a_glance_rows"]:
        series = {
            "series_id": row["series_id"],
            "title": row["label"],
            "units": "index",
            "source": "ISM AI extraction",
        }
        saved = us_rates_liquidity.merge_macro_indicator_points(
            con,
            series,
            ai_metric_points(payload)[row["series_id"]],
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
    prepared = ism_official_report.prepare_report_for_ai(
        html,
        url,
        fetched_at,
        source_name=source_name,
    )
    us_rates_liquidity.replace_ism_report_source_snapshot(
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
    payload = ism_ai_extraction.extract_with_client(
        prepared["report_text"],
        ai_client,
    )
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
    us_rates_liquidity.replace_ism_at_a_glance_rows(
        con, ai_at_a_glance_rows(payload, url, source_hash)
    )
    us_rates_liquidity.replace_ism_report_snapshot(
        con,
        ai_report_snapshot(payload, url, source_hash, fetched_at),
        ai_comments(payload, url, source_hash),
    )
    saved = us_rates_liquidity.replace_ism_ai_report_outputs(
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
        "rankings": 0,
        "comments": len(payload["respondent_comments"]),
        "at_a_glance_rows": len(payload["at_a_glance_rows"]),
        "source_name": source_name,
        **saved,
    }


def import_report(con, month, fetch=None, now=None):
    return import_report_url(
        con,
        report_url(month),
        source_name="ismworld",
        fetch=fetch,
        now=now,
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


def month_name_from_report_month(report_month):
    month_index = int(report_month[5:7]) - 1
    return MONTHS[month_index]


def latest_released_report_month(today=None):
    if today is None:
        today = datetime.now()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}-{month:02d}-01"


def backfill_targets(
    archive_reports,
    since_year,
    latest_report_month,
    existing_months,
    missing_only,
):
    since_month = f"{since_year}-01-01"
    archive_by_month = {
        item["report_month"]: item
        for item in archive_reports
        if since_month <= item["report_month"] < latest_report_month
    }
    targets = []
    for report_month in sorted(archive_by_month):
        if missing_only and report_month in existing_months:
            continue
        item = archive_by_month[report_month]
        targets.append(
            {
                "source_name": "prnewswire",
                "url": item["url"],
                "report_month": item["report_month"],
                "report_id": item["report_id"],
            }
        )
    if not missing_only or latest_report_month not in existing_months:
        targets.append(
            {
                "source_name": "ismworld",
                "url": report_url(month_name_from_report_month(latest_report_month)),
                "report_month": latest_report_month,
                "report_id": ism_prnewswire_archive.report_id(latest_report_month),
            }
        )
    return targets


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--month", action="append", choices=MONTHS)
    parser.add_argument("--current-year", action="store_true")
    parser.add_argument("--url", action="append")
    parser.add_argument("--prnewswire-pages", type=int, default=0)
    parser.add_argument("--prnewswire-pagesize", type=int, default=25)
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    results = []
    failed = 0
    for url in requested_urls(args):
        try:
            result = import_report_url(con, url)
            results.append(result)
        except (ValueError, CalledProcessError, TimeoutExpired) as exc:
            print(f"ism_official_report/{url}: failed - {exc}", file=sys.stderr)
            failed += 1
    months = (
        []
        if (args.url or args.prnewswire_pages)
        and not args.month
        and not args.current_year
        else requested_months(args)
    )
    for month in months:
        try:
            result = import_report(con, month)
            results.append(result)
        except ism_official_report.IsmReportUnavailable as exc:
            if args.current_year:
                print(
                    f"ism_official_report/{month}: skipped - {exc}",
                    file=sys.stderr,
                )
                continue
            print(f"ism_official_report/{month}: failed - {exc}", file=sys.stderr)
            failed += 1
        except (ValueError, CalledProcessError, TimeoutExpired) as exc:
            print(f"ism_official_report/{month}: failed - {exc}", file=sys.stderr)
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
