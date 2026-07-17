import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import growth_cycle
from app.tools.ism_industry_analysis import (
    build_ism_industry_analysis,
    _report_has_sufficient_coverage,
    _group_coverage_by_key,
)


CORE_LABELS = ["strong", "improving", "mixed", "weakening", "weak", "unavailable"]


def _is_adjacent_month(a, b):
    a_dt = datetime.strptime(a, "%Y-%m-%d")
    b_dt = datetime.strptime(b, "%Y-%m-%d")
    return (b_dt.year * 12 + b_dt.month) - (a_dt.year * 12 + a_dt.month) == 1


def evaluate(db_path, since=None):
    con = growth_cycle.connect(db_path)
    try:
        reports = growth_cycle.load_all_ism_report_snapshots(con)

        months = []
        for report in reports:
            if since and report["report_month"] < since:
                continue

            report_id = report["report_id"]
            signals = growth_cycle.load_ism_report_industry_signals(con, report_id)
            coverage = growth_cycle.load_ism_report_industry_signal_coverage(
                con, report_id
            )
            if not signals:
                continue
            if not coverage:
                continue

            coverage_dict = _group_coverage_by_key(coverage)
            if not _report_has_sufficient_coverage(coverage_dict):
                continue

            at_a_glance = growth_cycle.load_ism_at_a_glance_rows(con, report_id)
            comments = growth_cycle.load_ism_report_comments(con, report_id)

            analysis = build_ism_industry_analysis(
                report, signals, coverage, at_a_glance, comments
            )
            months.append(
                {
                    "report_month": report["report_month"],
                    "report_id": report_id,
                    "industries": analysis.get("industries", []),
                }
            )

        total_months = len(months)
        total_industries = sum(len(m["industries"]) for m in months)

        if total_months < 3:
            print(
                f"Insufficient history: only {total_months} eligible month(s) found "
                f"(need at least 3)"
            )
            return

        distribution = {label: 0 for label in CORE_LABELS}
        total_coverage_pct = 0.0
        for month in months:
            for ind in month["industries"]:
                label = ind.get("score_label", "unavailable")
                distribution[label] = distribution.get(label, 0) + 1
                total_coverage_pct += ind.get("score_coverage", 0) or 0

        avg_coverage = (
            total_coverage_pct / total_industries if total_industries > 0 else 0
        )

        persistence_count = 0
        persistence_total = 0
        for i in range(1, len(months)):
            if not _is_adjacent_month(
                months[i - 1]["report_month"], months[i]["report_month"]
            ):
                continue
            prev = {ind["industry"]: ind for ind in months[i - 1]["industries"]}
            curr = {ind["industry"]: ind for ind in months[i]["industries"]}
            for industry, curr_ind in curr.items():
                if industry in prev:
                    persistence_total += 1
                    if curr_ind.get("score_label") == prev[industry].get("score_label"):
                        persistence_count += 1

        persistence_pct = (
            (persistence_count / persistence_total * 100)
            if persistence_total > 0
            else 0
        )

        print(f"Eligible months: {total_months}")
        print(f"Total industries scored: {total_industries}")
        print(f"Average score coverage: {avg_coverage:.1f}%")
        print(f"Score distribution: {distribution}")
        print(
            f"Month-to-month label persistence: "
            f"{persistence_count}/{persistence_total} ({persistence_pct:.1f}%)"
        )
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate ISM industry signal scores across historical reports"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the Growth Cycle database (default: configured path)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only evaluate reports on or after this month (e.g. 2021-01-01)",
    )
    args = parser.parse_args()

    db_path = args.db_path or str(growth_cycle.DEFAULT_DB_PATH)
    evaluate(db_path, since=args.since)


if __name__ == "__main__":
    main()
