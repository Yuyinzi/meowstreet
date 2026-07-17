import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import growth_cycle
from app.tools.ism_ai_extraction import declared_industry_count


CORE_SIGNAL_TYPES = [
    "overall_growth",
    "overall_contraction",
    "new_orders",
    "production",
    "backlog",
]

CORE_DIRECTIONS = {
    "overall_growth": "growth",
    "overall_contraction": "contraction",
    "new_orders": "growth",
    "production": "growth",
    "backlog": "higher",
}


def backfill_single_report(con, report_id, verbose=False):
    signals = growth_cycle.load_ism_report_industry_signals(con, report_id)
    if not signals:
        return {
            "report_id": report_id,
            "complete": 0,
            "partial": 0,
            "status": "no_signals",
        }

    report_month = signals[0]["report_month"]
    source_url = signals[0]["source_url"]
    source_hash = signals[0]["source_hash"]

    groups = {}
    for signal in signals:
        key = (signal["signal_type"], signal["direction"])
        groups.setdefault(key, []).append(signal)

    coverage_rows = []
    for (signal_type, direction), group in groups.items():
        extracted_count = len(group)
        list_present = extracted_count > 0
        declared = declared_industry_count(group[0]["evidence_text"])
        if declared is not None and extracted_count == declared:
            validation_status = "complete"
        else:
            validation_status = "partial"
        coverage_rows.append(
            {
                "signal_type": signal_type,
                "direction": direction,
                "list_present": list_present,
                "declared_count": declared,
                "extracted_count": extracted_count,
                "validation_status": validation_status,
                "evidence_text": group[0]["evidence_text"],
            }
        )

    complete_count = sum(
        1 for r in coverage_rows if r["validation_status"] == "complete"
    )
    partial_count = sum(1 for r in coverage_rows if r["validation_status"] == "partial")

    growth_cycle.replace_ism_report_industry_signal_coverage(
        con, report_id, report_month, coverage_rows, source_url, source_hash
    )

    if verbose:
        for row in coverage_rows:
            core = "core" if row["signal_type"] in CORE_SIGNAL_TYPES else "secondary"
            print(
                f"  {row['signal_type']}/{row['direction']}: "
                f"{row['validation_status']} "
                f"({row['extracted_count']}/{row['declared_count'] or '?'}) "
                f"[{core}]"
            )

    return {
        "report_id": report_id,
        "complete": complete_count,
        "partial": partial_count,
        "status": "ok",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Backfill ISM industry signal coverage from stored signal rows"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="path to market_data.sqlite (default: configured path)",
    )
    parser.add_argument(
        "--report-id",
        default=None,
        help="target a specific report (e.g. ism_manufacturing_2026_06)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print per-list coverage details"
    )
    args = parser.parse_args()

    con = growth_cycle.connect(args.db_path) if args.db_path else growth_cycle.connect()

    if args.report_id:
        report_ids = [args.report_id]
    else:
        rows = con.execute(
            "select distinct report_id from ism_report_industry_signals order by report_id"
        ).fetchall()
        report_ids = [row["report_id"] for row in rows]

    if not report_ids:
        print("no industry signal rows found in the database")
        return

    total_complete = 0
    total_partial = 0
    total_no_signals = 0
    core_complete = 0
    core_partial = 0
    core_unavailable = 0

    core_direction_pairs = [
        ("overall_growth", "growth"),
        ("overall_contraction", "contraction"),
        ("new_orders", "growth"),
        ("new_orders", "decrease"),
        ("production", "growth"),
        ("production", "decrease"),
        ("backlog", "higher"),
        ("backlog", "lower"),
    ]

    for report_id in report_ids:
        result = backfill_single_report(con, report_id, verbose=args.verbose)
        if result["status"] == "ok":
            total_complete += result["complete"]
            total_partial += result["partial"]
        elif result["status"] == "no_signals":
            total_no_signals += 1

        signals = growth_cycle.load_ism_report_industry_signals(con, report_id)
        groups = {}
        for signal in signals:
            key = (signal["signal_type"], signal["direction"])
            groups.setdefault(key, []).append(signal)
        seen_core_pairs = set()
        for (signal_type, direction), group in groups.items():
            if signal_type in CORE_SIGNAL_TYPES:
                seen_core_pairs.add((signal_type, direction))
                declared = declared_industry_count(group[0]["evidence_text"])
                if declared is not None and len(group) == declared:
                    core_complete += 1
                else:
                    core_partial += 1
        for pair in core_direction_pairs:
            if pair not in seen_core_pairs:
                core_unavailable += 1

    con.close()

    print(f"\nprocessed {len(report_ids)} report(s)")
    print(f"total complete lists: {total_complete}")
    print(f"total partial lists: {total_partial}")
    print(f"core complete lists: {core_complete}")
    print(f"core partial lists: {core_partial}")
    print(f"core unavailable lists: {core_unavailable}")
    if total_no_signals:
        print(f"reports with no signals: {total_no_signals}")


if __name__ == "__main__":
    main()
