import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from app.tools import ism_official_report


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


def import_report(con, month, fetch=None, now=None):
    if fetch is None:
        fetch = fetch_text
    if now is None:
        now = fetched_at_now
    url = report_url(month)
    html = fetch(url)
    parsed = ism_official_report.parse_report(html, url, now())
    metric_count = merge_metrics(con, parsed)
    us_rates_liquidity.merge_ism_industry_rankings(con, parsed["rankings"])
    saved = us_rates_liquidity.replace_ism_report_snapshot(
        con,
        parsed["report"],
        parsed["comments"],
    )
    at_a_glance_saved = us_rates_liquidity.replace_ism_at_a_glance_rows(
        con,
        parsed["at_a_glance_rows"],
    )
    return {
        "report_id": parsed["report"]["report_id"],
        "metrics": metric_count,
        "rankings": len(parsed["rankings"]),
        "comments": saved["comments"],
        "at_a_glance_rows": at_a_glance_saved["at_a_glance_rows"],
    }


def requested_months(args):
    if args.current_year:
        return MONTHS[: datetime.now().month - 1]
    if args.month:
        return args.month
    return [MONTHS[datetime.now().month - 2]]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--month", action="append", choices=MONTHS)
    parser.add_argument("--current-year", action="store_true")
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    results = []
    failed = 0
    for month in requested_months(args):
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
        except ValueError as exc:
            print(f"ism_official_report/{month}: failed - {exc}", file=sys.stderr)
            failed += 1
    con.close()
    for result in results:
        print(
            f"{result['report_id']}: metrics={result['metrics']} "
            f"rankings={result['rankings']} comments={result['comments']} "
            f"at_a_glance_rows={result['at_a_glance_rows']}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
