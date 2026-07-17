import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import growth_cycle
from app.tools.ism_macro_signal import ISM_MACRO_SIGNAL_VERSION, build_ism_macro_signal


_ALLOWED_TRANSITIONS = {
    "expansion_rising": {"expansion_slowing", "peaking", "stable", "unavailable"},
    "expansion_slowing": {
        "expansion_rising",
        "slowdown",
        "contraction_deepening",
        "stable",
        "unavailable",
    },
    "peaking": {"expansion_slowing", "stable", "unavailable"},
    "slowdown": {
        "expansion_rising",
        "expansion_slowing",
        "contraction_deepening",
        "contraction_improving",
        "stable",
        "unavailable",
    },
    "contraction_deepening": {
        "contraction_improving",
        "slowdown",
        "stable",
        "unavailable",
    },
    "contraction_improving": {
        "expansion_rising",
        "slowdown",
        "troughing",
        "stable",
        "unavailable",
    },
    "troughing": {"expansion_rising", "stable", "unavailable"},
    "stable": {
        "expansion_rising",
        "expansion_slowing",
        "slowdown",
        "contraction_deepening",
        "contraction_improving",
        "peaking",
        "troughing",
        "unavailable",
    },
    "unavailable": {
        "expansion_rising",
        "expansion_slowing",
        "slowdown",
        "contraction_deepening",
        "contraction_improving",
        "peaking",
        "troughing",
        "stable",
    },
}


def _is_adjacent_month(a, b):
    a_dt = datetime.strptime(a, "%Y-%m-%d")
    b_dt = datetime.strptime(b, "%Y-%m-%d")
    return (b_dt.year * 12 + b_dt.month) - (a_dt.year * 12 + a_dt.month) == 1


def _is_impossible(from_state, to_state):
    if (
        from_state in _ALLOWED_TRANSITIONS
        and to_state in _ALLOWED_TRANSITIONS[from_state]
    ):
        return False
    return True


def evaluate(db_path, since=None):
    con = growth_cycle.connect(db_path)
    try:
        reports = growth_cycle.load_all_ism_report_snapshots(con)

        if since:
            since_start = since + "-01" if len(since) == 7 else since
            reports = [r for r in reports if r["report_month"] >= since_start]

        if len(reports) < 3:
            print(
                f"Insufficient history: only {len(reports)} report month(s) found "
                f"(need at least 3)"
            )
            return

        all_aag_rows = growth_cycle.load_ism_at_a_glance_rows_for_reports(
            con, [r["report_id"] for r in reports]
        )
        aag_by_report = {}
        for row in all_aag_rows:
            aag_by_report.setdefault(row["report_id"], []).append(row)

        results = []
        for i in range(1, len(reports)):
            window_start = max(0, i - 5)
            window_reports = reports[window_start : i + 1]
            window_rows = []
            for r in window_reports:
                window_rows.extend(aag_by_report.get(r["report_id"], []))
            try:
                results.append(build_ism_macro_signal(window_reports, window_rows))
            except ValueError:
                continue

        if len(results) < 3:
            print(
                f"Insufficient history: only {len(results)} usable signal(s) found "
                f"(need at least 3)"
            )
            return

        status_counts = Counter(r["status"] for r in results)
        cycle_state_counts = Counter(r["cycle_state"] for r in results)
        growth_impulse_counts = Counter(r["growth_impulse"] for r in results)

        transitions = Counter()
        impossible_transitions = Counter()
        for i in range(1, len(results)):
            prev_month = results[i - 1]["period"]
            curr_month = results[i]["period"]
            if _is_adjacent_month(prev_month, curr_month):
                prev_state = results[i - 1]["cycle_state"]
                curr_state = results[i]["cycle_state"]
                transitions[(prev_state, curr_state)] += 1
                if _is_impossible(prev_state, curr_state):
                    impossible_transitions[(prev_state, curr_state)] += 1

        all_missing = Counter()
        for r in results:
            for m in r.get("coverage", {}).get("missing_metrics", []):
                all_missing[m] += 1

        first_month = results[0]["period"]
        last_month = results[-1]["period"]

        print(f"ISM Macro Signal Evaluation")
        print(f"===========================")
        print(f"Version: {ISM_MACRO_SIGNAL_VERSION}")
        print(f"Period: {first_month} to {last_month} ({len(results)} eligible months)")
        print()
        print("Signal Availability:")
        for status in ["available", "partial", "unavailable"]:
            print(f"  {status}: {status_counts.get(status, 0)}")
        print()
        print("Cycle State Distribution:")
        for state, count in sorted(cycle_state_counts.items(), key=lambda x: -x[1]):
            print(f"  {state}: {count}")
        print()
        print("Growth Impulse Distribution:")
        for impulse, count in sorted(
            growth_impulse_counts.items(), key=lambda x: -x[1]
        ):
            print(f"  {impulse}: {count}")
        print()
        print("Month-to-Month Transitions (adjacent calendar months only):")
        for (from_state, to_state), count in sorted(
            transitions.items(), key=lambda x: -x[1]
        ):
            print(f"  {from_state} -> {to_state}: {count}")
        print()
        print("Impossible transitions:")
        if impossible_transitions:
            for (from_state, to_state), count in sorted(
                impossible_transitions.items(), key=lambda x: -x[1]
            ):
                print(f"  {from_state} -> {to_state}: {count} (flagged)")
        else:
            print("  (none)")
        print()
        print("Missing required metrics:")
        for m, count in sorted(all_missing.items(), key=lambda x: -x[1]):
            print(f"  {m}: {count} months")
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate ISM macro signals across historical reports"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the Growth Cycle database (default: configured path)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only evaluate reports on or after this month (e.g. 2025-01, YYYY-MM format)",
    )
    args = parser.parse_args()

    db_path = args.db_path or str(growth_cycle.DEFAULT_DB_PATH)
    evaluate(db_path, since=args.since)


if __name__ == "__main__":
    main()
