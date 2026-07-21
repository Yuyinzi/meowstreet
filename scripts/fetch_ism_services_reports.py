import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import growth_cycle
from app.db import ism_surveys
from app.db import us_rates_liquidity
from app.tools import ism_services_report
from scripts import fetch_ism_official_reports
from scripts.fetch_ism_official_reports import fetched_at_now


BASE_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/{month}/"

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

_SURVEY_TYPE = "services"


def report_url(month):
    normalized = month.strip().lower()
    if normalized not in MONTHS:
        raise ValueError(f"ism services report month is unknown: {month}")
    return BASE_URL.format(month=normalized)


def requested_months(count=1, today=None):
    if today is None:
        today = datetime.now()
    months = []
    for i in range(count):
        raw_month = today.month - 1 - i
        y = today.year
        m = raw_month
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}-01")
    return sorted(months)


def month_name(report_month):
    index = int(report_month[5:7]) - 1
    return MONTHS[index]


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
        saved = us_rates_liquidity.merge_macro_indicator_points(
            con, series, points, commit=commit
        )
        count += saved["points"]
    return count


def main(argv=None, fetch=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--months", type=int, default=1)
    args = parser.parse_args(argv)

    if fetch is None:
        fetch = fetch_ism_official_reports.fetch_text

    con = us_rates_liquidity.connect(args.db_path)
    growth_cycle.init_db(con)

    report_months = requested_months(args.months)
    results = []
    failed = 0

    for report_month in report_months:
        month = month_name(report_month)
        url = report_url(month)
        html = None
        source_hash = None
        fetched_at = None
        try:
            fetched_at = fetched_at_now()
            html = fetch(url)
            source_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

            parsed = ism_services_report.parse_report(html, url, fetched_at, "ismworld")

            if parsed["report"]["report_month"] != report_month:
                raise ValueError(
                    f"ism services report month mismatch: requested {report_month}, got {parsed['report']['report_month']}"
                )

            con.execute("begin")
            try:
                growth_cycle.replace_ism_report_source_snapshot(
                    con,
                    {
                        "source_url": url,
                        "source_name": "ismworld",
                        "source_hash": source_hash,
                        "fetched_at": fetched_at,
                        "raw_html": html,
                        "parse_status": "parsed",
                        "parse_error": None,
                        "report_id": parsed["report"]["report_id"],
                        "report_month": parsed["report"]["report_month"],
                    },
                    commit=False,
                )
                con.execute(
                    "delete from macro_indicator_points where series_id in (?, ?, ?, ?) and date = ?",
                    (
                        "ism_services_pmi",
                        "ism_services_business_activity",
                        "ism_services_new_orders",
                        "ism_services_order_backlog",
                        parsed["report"]["report_month"],
                    ),
                )
                metric_count = merge_metrics(con, parsed, commit=False)
                ism_surveys.replace_report_snapshot(
                    con,
                    _SURVEY_TYPE,
                    parsed["report"],
                    parsed["comments"],
                    commit=False,
                )
                con.execute(
                    "delete from ism_industry_rankings where survey_type = ? and date = ?",
                    (_SURVEY_TYPE, parsed["report"]["report_month"]),
                )
                ism_surveys.merge_industry_rankings(
                    con, _SURVEY_TYPE, parsed["rankings"], commit=False
                )
                con.execute(
                    "delete from ism_industry_comments where survey_type = ? and report_month = ?",
                    (_SURVEY_TYPE, parsed["report"]["report_month"]),
                )
                ism_surveys.merge_industry_comments(
                    con, _SURVEY_TYPE, parsed["comments"], commit=False
                )
                con.commit()
            except BaseException:
                con.rollback()
                raise

            result = {
                "report_id": parsed["report"]["report_id"],
                "metrics": metric_count,
                "rankings": len(parsed["rankings"]),
                "comments": len(parsed["comments"]),
            }
            results.append(result)
            print(
                f"{result['report_id']}: source=ismworld metrics={result['metrics']} "
                f"rankings={result['rankings']} comments={result['comments']}"
            )
        except Exception as exc:
            if html is not None:
                existing = con.execute(
                    "select parse_status from ism_report_source_snapshots where source_url = ?",
                    (url,),
                ).fetchone()
                if existing is None or existing["parse_status"] != "parsed":
                    growth_cycle.replace_ism_report_source_snapshot(
                        con,
                        {
                            "source_url": url,
                            "source_name": "ismworld",
                            "source_hash": source_hash,
                            "fetched_at": fetched_at,
                            "raw_html": html,
                            "parse_status": "failed",
                            "parse_error": str(exc),
                            "report_id": None,
                            "report_month": None,
                        },
                    )
            print(
                f"ism_services_report/{url}: failed - {exc}",
                file=sys.stderr,
            )
            failed += 1

    con.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
